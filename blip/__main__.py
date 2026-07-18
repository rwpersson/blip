"""Entry point:  python -m blip"""
import sys

from . import decks as decks_mod
from . import firstrun
from . import paths, settings as settings_mod, win32
from .app import App
from .audio import cues, tts
from .logging_setup import get, setup


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

    ok, total = tts.generate(decks, s)
    if total:
        log.info("Generated %s/%s audio clips.", ok, total)

    words = sum(len(d["words"]) for d in decks)
    log.info("Blip %s — %s deck(s), %s words, every %ss.",
             __import__("blip").__version__, len(decks), words,
             s.interval_seconds)
    hk = s.hotkeys
    log.info("%s show/hide panel · %s silent%s",
             hk["panel"], hk["mute"],
             f" · {hk['got']}/{hk['miss']} knew it/didn't" if s.recall_hotkeys else "")

    App(decks, s).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
