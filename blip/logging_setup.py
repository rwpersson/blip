"""Logging.

You cannot debug a stranger's crash without this. Everything that used to be a
bare `except: pass` should log at warning/exception level instead, so a user can
send one file when something breaks.

Console output is UTF-8 forced: the Windows console defaults to cp1252 and
*raises* when printing Chinese, which has already silently killed one long
generation run.
"""
import logging
import logging.handlers
import sys

from . import paths

LOG_NAME = "blip"


def _force_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def setup(level=logging.INFO, console=True):
    """Configure the root app logger. Safe to call more than once."""
    _force_utf8_console()
    log = logging.getLogger(LOG_NAME)
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)
    log.propagate = False

    try:
        paths.log_dir().mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            paths.log_dir() / "blip.log", maxBytes=512_000, backupCount=2,
            encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        log.addHandler(fh)
    except Exception:
        pass          # never let logging setup stop the app from starting

    if console:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(ch)
    return log


def get(name=None):
    return logging.getLogger(LOG_NAME if not name else f"{LOG_NAME}.{name}")
