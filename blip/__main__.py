"""Entry point:  python -m blip"""
import sys
import threading

from . import decks as decks_mod
from . import firstrun
from . import paths, settings as settings_mod, win32
from .app import App
from .audio import cues, tts
from .logging_setup import get, setup


def _console(msg, newline=False):
    """Best-effort console write. Under pythonw / a frozen build there's no real
    stdout, so this must never raise."""
    try:
        sys.stdout.write(msg + ("\n" if newline else ""))
        sys.stdout.flush()
    except Exception:
        pass


def _generate_audio_in_background(decks, settings, app, log):
    """Fill in missing audio AFTER the overlay is up, on a daemon thread.

    A big first launch has hundreds of clips to synthesize over the network; doing
    it before the window appeared made the app look hung for minutes (and if you
    closed it mid-way, nothing was cached, so the next launch started over). Now
    the overlay is usable immediately and cards whose clips aren't ready yet just
    play silently until they are. Progress shows in the console, the log, and the
    panel's status line."""
    def on_progress(done, total, _word):
        if done == 1:
            log.info("Generating %s audio clip(s) in the background…", total)
            app.root.after(0, app.panel.set_generating, True)
        _console(f"\rGenerating audio… {done}/{total}   ")
        if done == total or done % 25 == 0:
            log.info("audio %s/%s", done, total)

    def run():
        try:
            ok, total = tts.generate(decks, settings, progress=on_progress)
        except Exception:
            log.exception("background audio generation crashed")
            return
        if total:
            _console(f"\rGenerating audio… {ok}/{total}  done.", newline=True)
            log.info("Audio generation done: %s/%s.", ok, total)
        app.root.after(0, app.panel.set_generating, False)

    threading.Thread(target=run, daemon=True, name="audio-gen").start()


def main(argv=None):
    setup()
    log = get("main")
    paths.ensure_dirs()

    first = firstrun.is_first_run()
    s = settings_mod.load()
    # Must happen before any window exists, or Windows renders us at 96 DPI and
    # bitmap-stretches the result (blurry text on any scaled display).
    if s.dpi_aware and not win32.set_dpi_aware():
        log.info("could not enable DPI awareness — the overlay may look soft")
    cues.ensure()

    all_decks = decks_mod.load_all()
    if not all_decks:
        log.error("No decks found in %s — nothing to run.",
                  ", ".join(str(d) for d in paths.decks_dirs()))
        return 1

    # Only synthesize what we'll actually study — no point generating swear audio
    # for someone who turned swears off.
    decks = decks_mod.apply_filters(all_decks, s)
    if not decks:
        log.error("Every deck is filtered out (check hide_swears / enabled_decks).")
        return 1
    if len(decks) != len(all_decks) or any(
            len(d["words"]) != len(o["words"])
            for d, o in zip(decks, all_decks) if d["id"] == o["id"]):
        log.info("Filters active: studying %s of %s deck(s), %s of %s word(s)",
                 len(decks), len(all_decks),
                 sum(len(d["words"]) for d in decks),
                 sum(len(d["words"]) for d in all_decks))

    if first:
        # Show the welcome BEFORE synthesizing: the first run has ~900 clips to
        # make, and a stranger staring at a silent screen deserves to know why.
        # It can also change hide_swears, which decides what we synthesize at all.
        log.info("First run — showing the welcome window")
        s = firstrun.show(deck_count=len(decks),
                          word_count=sum(len(d["words"]) for d in decks),
                          clips_needed=len(tts.missing_clips(decks, s)))
        decks = decks_mod.apply_filters(all_decks, s)
        if not decks:
            log.error("Every deck is filtered out.")
            return 1

    words = sum(len(d["words"]) for d in decks)
    log.info("Blip %s — %s deck(s), %s words, every %ss.",
             __import__("blip").__version__, len(decks), words,
             s.interval_seconds)
    hk = s.hotkeys
    log.info("%s show/hide panel · %s silent%s",
             hk["panel"], hk["mute"],
             f" · {hk['got']}/{hk['miss']} knew it/didn't" if s.recall_hotkeys else "")

    # Build the overlay first, THEN synthesize missing audio in the background —
    # so the app is on screen and usable at once instead of blocking for minutes.
    app = App(decks, s)
    _generate_audio_in_background(decks, s, app, log)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
