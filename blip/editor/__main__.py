"""Entry point:  python -m blip.editor"""
import sys

from .. import paths, settings as settings_mod, win32
from ..logging_setup import get, setup
from .window import EditorWindow


def main():
    setup()
    log = get("editor")
    paths.ensure_dirs()
    s = settings_mod.load()
    if s.dpi_aware:
        win32.set_dpi_aware()      # before any window — otherwise blurry text
    log.info("Deck editor — decks in %s",
             ", ".join(str(d) for d in paths.decks_dirs()))
    EditorWindow(s).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
