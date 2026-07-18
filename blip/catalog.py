"""The creator-deck catalog: bundled decks the user opts into.

The app ships two kinds of bundled deck:

  * the **starter** (paths.bundled_decks_dir()) — active out of the box, so a
    fresh install is never empty;
  * the **catalog** (paths.bundled_catalog_dir()) — a library the user browses
    and installs piecemeal. decks.load_all() never touches it; a deck becomes
    active only when install() copies its JSON into user_dir()/decks and
    synthesizes the audio.

Shipping personal study decks baked in, active for everyone, is the opposite of
the "author your own" direction — so the weeks live here, opt-in, and the app
opens on a neutral sampler instead.

Pure logic, no Tk. catalog_ui.py is a thin shell over this; the install step is
safe to call from a worker thread (tts.generate never raises, and a missing clip
just plays silent).
"""
import json
import shutil
from dataclasses import dataclass, field

from . import decks as decks_mod
from . import paths
from .audio import tts
from .logging_setup import get

log = get("catalog")


@dataclass
class Entry:
    """What the browser shows for one catalog deck, without committing to it."""
    id: str
    name: str
    language: str
    word_count: int
    categories: dict            # cat -> count, for the little breakdown
    sample: list                # a few terms, to give the flavor
    installed: bool


def _catalog_files():
    d = paths.bundled_catalog_dir()
    return sorted(d.glob("*.json")) if d.exists() else []


def _load_file(path):
    """A validated deck dict, or None if the file is unusable (logged, not
    raised — one broken catalog file must not sink the whole browser)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("skipping unreadable catalog deck: %s", path)
        return None
    deck = decks_mod._normalize(path.stem, data, path)
    problems = decks_mod.validate(deck)
    if problems:
        for p in problems[:5]:
            log.warning("catalog deck problem: %s", p)
    return deck


def is_installed(deck_id):
    """Whether the user has this catalog deck in their own decks dir."""
    return (decks_mod.user_decks_dir() / f"{deck_id}.json").exists()


def entries():
    """Every catalog deck as a lightweight Entry, ordered by id."""
    out = []
    for f in _catalog_files():
        deck = _load_file(f)
        if deck is None:
            continue
        words = deck["words"]
        cats = {}
        for w in words:
            c = w.get("cat") or "common"
            cats[c] = cats.get(c, 0) + 1
        out.append(Entry(
            id=deck["id"],
            name=deck["name"],
            language=deck["language"],
            word_count=len(words),
            categories=dict(sorted(cats.items(), key=lambda kv: -kv[1])),
            sample=[decks_mod.word_term(w) for w in words[:6]],
            installed=is_installed(deck["id"]),
        ))
    return out


def load(deck_id):
    """The full deck dict for one catalog id, for a detailed preview. Raises
    KeyError if there's no such catalog deck."""
    for f in _catalog_files():
        if f.stem == deck_id:
            deck = _load_file(f)
            if deck is not None:
                return deck
    raise KeyError(f"no catalog deck {deck_id!r}")


def install(deck_id, settings=None, progress=None, generate_audio=True):
    """Copy a catalog deck into the user's decks, then synthesize its audio.

    Returns (deck, ok, attempted): the installed deck, and how many audio clips
    were made of how many needed. Audio is best-effort — offline or engine-down
    just leaves clips missing (silent cards), to be filled on a later launch.
    """
    deck = load(deck_id)                          # raises if unknown
    dest = decks_mod.user_decks_dir()
    dest.mkdir(parents=True, exist_ok=True)
    src = paths.bundled_catalog_dir() / f"{deck_id}.json"
    out = dest / f"{deck_id}.json"
    shutil.copy2(src, out)
    log.info("installed catalog deck %s -> %s", deck_id, out)

    ok = attempted = 0
    if generate_audio and settings is not None:
        ok, attempted = tts.generate([deck], settings, progress=progress)
    return deck, ok, attempted


def install_all(settings=None, progress=None, generate_audio=True):
    """Install every not-yet-installed catalog deck. progress(i, total, word) is
    threaded straight through to the audio generator across all decks."""
    todo = [e for e in entries() if not e.installed]
    installed = []
    total_ok = total_att = 0
    for e in todo:
        deck, ok, att = install(e.id, settings, progress, generate_audio)
        installed.append(deck)
        total_ok += ok
        total_att += att
    return installed, total_ok, total_att


def uninstall(deck_id):
    """Remove an installed catalog deck from the user's decks. Only removes it if
    it's genuinely one of ours — never a deck the user authored themselves.
    Returns True if a file was removed. Audio is left alone (content-addressed
    and possibly shared with other decks; orphan cleanup is a separate concern).
    """
    if deck_id not in {f.stem for f in _catalog_files()}:
        return False
    target = decks_mod.user_decks_dir() / f"{deck_id}.json"
    if target.exists():
        target.unlink()
        log.info("uninstalled catalog deck %s", deck_id)
        return True
    return False
