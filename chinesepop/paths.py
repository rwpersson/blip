"""Where things live.

Bundled content (decks, code) ships with the app and is read-only. User data
(progress, settings, custom decks, generated audio) must live under %APPDATA% —
once installed under Program Files the install dir is not writable.

During development, running from a source checkout keeps everything in-tree so
you don't have to hunt for files; set CHINESEPOP_PORTABLE=1 to force that.
"""
import os
import sys
from pathlib import Path

APP_NAME = "ChinesePop"

# Root of the source checkout / install.
PKG_DIR = Path(__file__).resolve().parent
APP_DIR = PKG_DIR.parent


def _frozen():
    return getattr(sys, "frozen", False)


def user_dir() -> Path:
    """Per-user writable data dir."""
    if os.environ.get("CHINESEPOP_PORTABLE") == "1" or not _frozen():
        return APP_DIR                      # dev: keep everything in the checkout
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME


def bundled_decks_dir() -> Path:
    return APP_DIR / "decks"


def bundled_catalog_dir() -> Path:
    """Creator decks that ship with the app but are NOT auto-loaded.

    Unlike bundled_decks_dir() (the starter, active out of the box), these are an
    opt-in library: the catalog browser previews them and copies the ones the
    user picks into user_dir()/decks. Shipping the JSON costs ~130 KB; the audio
    is synthesized on install, never shipped.
    """
    return APP_DIR / "catalog"


def decks_dirs() -> list[Path]:
    """Decks that ship with the app, plus any the user added."""
    dirs = [bundled_decks_dir()]
    user_decks = user_dir() / "decks"
    if user_decks != dirs[0] and user_decks.exists():
        dirs.append(user_decks)
    return dirs


def audio_dir() -> Path:
    return user_dir() / "audio"


def sounds_dir() -> Path:
    return user_dir() / "sounds"


def state_file() -> Path:
    return user_dir() / "state.json"


def settings_file() -> Path:
    return user_dir() / "settings.json"


def log_dir() -> Path:
    return user_dir() / "logs"


def ensure_dirs():
    for d in (user_dir(), audio_dir(), sounds_dir(), log_dir()):
        d.mkdir(parents=True, exist_ok=True)
