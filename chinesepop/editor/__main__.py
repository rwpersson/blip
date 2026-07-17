"""Entry point:  python -m chinesepop.editor"""
import sys

from .. import paths, settings as settings_mod
from ..logging_setup import get, setup
from .window import EditorWindow


def main():
    setup()
    log = get("editor")
    paths.ensure_dirs()
    s = settings_mod.load()
    log.info("Deck editor — decks in %s",
             ", ".join(str(d) for d in paths.decks_dirs()))
    EditorWindow(s).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
