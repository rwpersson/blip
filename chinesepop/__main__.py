"""Entry point:  python -m chinesepop"""
import sys

from . import decks as decks_mod
from . import paths, settings as settings_mod
from .app import App
from .audio import cues, tts
from .logging_setup import get, setup


def main(argv=None):
    setup()
    log = get("main")
    paths.ensure_dirs()

    s = settings_mod.load()
    cues.ensure()

    decks = decks_mod.load_all()
    if not decks:
        log.error("No decks found in %s — nothing to run.",
                  ", ".join(str(d) for d in paths.decks_dirs()))
        return 1

    ok, total = tts.generate(decks, s)
    if total:
        log.info("Generated %s/%s audio clips.", ok, total)

    words = sum(len(d["words"]) for d in decks)
    log.info("Chinese Pop %s — %s deck(s), %s words, every %ss.",
             __import__("chinesepop").__version__, len(decks), words,
             s.interval_seconds)
    hk = s.hotkeys
    log.info("%s show/hide panel · %s silent%s",
             hk["panel"], hk["mute"],
             f" · {hk['got']}/{hk['miss']} knew it/didn't" if s.recall_hotkeys else "")

    App(decks, s).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
