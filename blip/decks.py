"""Deck loading + validation.

A deck file is:
    {"name": "Week 2", "language": "zh-CN", "words": [ {...}, ... ]}

Word fields:
    term     the thing being learned          (currently stored as "hanzi")
    reading  romanization / pronunciation     (currently stored as "pinyin")
    tones    optional, Chinese-only           drives tone colors + the read-out
    cat      hsk|slang|swear|gaming|idiom|common
    meaning  English gloss
    note     usage/nuance note
    alt      optional alternate form
    say      optional TTS override (when `term` has latin/digits, e.g. 666)

ALL deck I/O goes through here. The generic-language rename (hanzi->term,
pinyin->reading; ROADMAP Phase 2) is a change to _normalize() and nothing else —
the rest of the app already reads via word_term()/word_reading().
"""
import json
import os
import re
from pathlib import Path

from . import paths
from .logging_setup import get

log = get("decks")

CATEGORIES = ("hsk", "slang", "swear", "gaming", "idiom", "common")
DEFAULT_LANGUAGE = "zh-CN"


# --- field accessors: the whole app reads words through these -----------------
def word_term(w):
    return w.get("term") or w.get("hanzi", "")


def word_reading(w):
    return w.get("reading") or w.get("pinyin", "")


def word_tones(w):
    return w.get("tones", "")


def word_say(w):
    """Text handed to the TTS engine."""
    return w.get("say") or word_term(w)


def _normalize(deck_id, data, source):
    if isinstance(data, list):                 # tolerate a bare word list
        data = {"name": deck_id, "words": data}
    # Keep every key the file carried (forward-compat: a companion app — Blipfeed
    # — or a future version may add fields we don't manage; they must survive a
    # round-trip). Then normalize the ones we own on top.
    deck = {k: v for k, v in data.items() if k not in ("id", "source")}
    deck.update({
        "id": deck_id,
        "name": data.get("name", deck_id),
        "language": data.get("language", DEFAULT_LANGUAGE),
        "voice": data.get("voice"),            # optional per-deck voice override
        # `archived` (the Blipfeed⇄Blip seam): retired from review, still listed.
        # Absent means active — readers must treat missing as False.
        "archived": bool(data.get("archived", False)),
        "words": data.get("words", []),
        "source": source,
    })
    return deck


def validate(deck):
    """Return a list of human-readable problems. Empty == fine.

    Third-party decks *will* be malformed; fail loudly and specifically rather
    than crashing later inside the renderer.
    """
    problems = []
    seen_ids, seen_terms = set(), set()
    for i, w in enumerate(deck.get("words", [])):
        where = f"{deck['id']}[{i}]"
        term = word_term(w)
        if not term:
            problems.append(f"{where}: missing term/hanzi")
        if not w.get("id"):
            problems.append(f"{where} ({term}): missing id")
        elif w["id"] in seen_ids:
            problems.append(f"{where} ({term}): duplicate id {w['id']}")
        else:
            seen_ids.add(w["id"])
        if term in seen_terms:
            problems.append(f"{where}: duplicate term {term}")
        else:
            seen_terms.add(term)
        if not w.get("meaning"):
            problems.append(f"{where} ({term}): missing meaning")
        cat = w.get("cat")
        if cat and cat not in CATEGORIES:
            problems.append(f"{where} ({term}): unknown cat {cat!r}")
        # tones are optional, but if present should line up with the reading
        tones, reading = word_tones(w), word_reading(w)
        if tones and reading and tones not in ("—", ""):
            n_syl = len(reading.split())
            n_tone = len(str(tones).replace(" ", "").split("-"))
            if n_syl != n_tone:
                problems.append(
                    f"{where} ({term}): {n_syl} syllables but {n_tone} tones "
                    f"({reading!r} vs {tones!r}) — tone colors will fall back")
    return problems


def load_all(strict=False):
    """Every deck, bundled + user, ordered by filename.

    A user deck with the same id as a bundled one **replaces** it. That's what
    makes editing a shipped deck work once installed: the bundled copy is
    read-only, so `save()` writes to the user dir, and this is where that copy
    takes over. Without it you'd see the deck twice.
    """
    by_id = {}
    for d in paths.decks_dirs():             # bundled first, user last (wins)
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                log.exception("skipping unreadable deck: %s", f)
                continue
            deck = _normalize(f.stem, data, f)
            problems = validate(deck)
            if problems:
                for p in problems[:10]:
                    log.warning("deck problem: %s", p)
                if strict:
                    raise ValueError(f"{f.name}: {problems[0]}")
            if deck["id"] in by_id:
                log.info("user deck %s overrides the bundled one", deck["id"])
            by_id[deck["id"]] = deck
    return sorted(by_id.values(), key=lambda d: d["id"])


def all_words(decks=None):
    """Every word across every deck (audio is keyed per word)."""
    decks = decks if decks is not None else load_all()
    return [w for d in decks for w in d["words"]]


def apply_filters(decks, settings):
    """The decks/words actually studied, per the user's settings.

    Shipping decks full of profanity with no way to turn it off is a support
    problem, so `hide_swears` drops that category outright. `enabled_decks`
    narrows which decks are in rotation ([] means all).

    Returns new deck dicts — never mutates the loaded ones, or a filter would
    quietly delete cards from the editor's view too.
    """
    enabled = set(settings.get("enabled_decks") or [])
    hide_swears = settings.get("hide_swears")
    out = []
    for d in decks:
        if d.get("archived"):
            continue                  # archived = listable in the editor, not reviewed
        if enabled and d["id"] not in enabled:
            continue
        words = d["words"]
        if hide_swears:
            words = [w for w in words if w.get("cat") != "swear"]
        if not words:
            continue                  # an empty deck would stall the scheduler
        out.append({**d, "words": words})
    return out


# --------------------------- writing (authoring / import) --------------------
SCHEMA = 1
_WORD_FIELDS = ("id", "term", "reading", "tones", "cat", "meaning", "note",
                "alt", "say")


def slugify(name):
    out = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return out or "deck"


def user_decks_dir():
    """Where decks the user creates or imports go — never the bundled dir, which
    is read-only once installed."""
    d = paths.user_dir() / "decks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_path(deck):
    """Where this deck should be written.

    Its own file if we can write there; otherwise the user dir — editing a
    bundled deck after install is copy-on-write, and load_all() lets the copy win.
    """
    source = deck.get("source")
    if source:
        source = Path(source)
        if os.access(source.parent, os.W_OK):
            return source
        log.info("%s is read-only; saving %s to the user deck dir",
                 source.parent, deck["id"])
    return user_decks_dir() / f"{deck['id']}.json"


# Deck-level keys we serialize ourselves; everything else is carried through
# untouched so a rewrite never drops a field we don't manage (contract rule).
_MANAGED_DECK_KEYS = {"id", "source", "schema", "name", "language", "voice",
                      "archived", "words"}


def to_json(deck):
    """Serialize, dropping our in-memory bookkeeping and empty fields.

    Preserves the archive flag and any unknown deck-level keys — the rewrite rule
    of the deck-archive contract: carry through fields you didn't intend to change,
    so a routine save on our side never silently un-archives or loses data.
    """
    out = {
        "schema": SCHEMA,
        "name": deck.get("name", deck["id"]),
        "language": deck.get("language", DEFAULT_LANGUAGE),
        "voice": deck.get("voice"),
    }
    if deck.get("archived"):
        out["archived"] = True         # omit when active, to keep active decks clean
    for k, v in deck.items():          # forward-compat: unknown deck-level keys
        if k not in _MANAGED_DECK_KEYS:
            out[k] = v
    out["words"] = [{k: w[k] for k in _WORD_FIELDS if w.get(k)}
                    for w in deck.get("words", [])]
    return out


def save(deck, path=None):
    path = Path(path or deck_path(deck))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_json(deck), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    deck["source"] = path
    return path


def create(name, language=DEFAULT_LANGUAGE, deck_id=None, voice=None):
    """A new, empty deck (not yet saved)."""
    return {"id": deck_id or slugify(name), "name": name, "language": language,
            "voice": voice, "archived": False, "words": [], "source": None}


def set_archived(deck, archived):
    """Archive or un-archive a deck — the Blipfeed⇄Blip contract flag.

    Only the flag changes: words, voice, name, schema, ids, audio, and any keys
    we don't manage are all preserved (to_json carries them through). Writes the
    deck and returns its path.
    """
    deck["archived"] = bool(archived)
    return save(deck)


def next_word_id(deck):
    """Ids only need to be unique *within* a deck — audio is content-addressed,
    so an imported deck's ids can't collide with anything."""
    nums = [int(w["id"]) for w in deck["words"] if str(w.get("id", "")).isdigit()]
    return str(max(nums) + 1) if nums else "1"


def find_term(decks, term):
    """(deck, word) for a term anywhere, so the UI can warn about duplicates."""
    for d in decks:
        for w in d["words"]:
            if word_term(w) == term:
                return d, w
    return None, None


def add_word(deck, word, autofill=True):
    """Append a word, assigning an id and filling in reading/tones if we can.
    Returns the stored word. Raises ValueError on a duplicate term."""
    term = word_term(word)
    if not term:
        raise ValueError("a card needs a term")
    if any(word_term(w) == term for w in deck["words"]):
        raise ValueError(f"{term!r} is already in this deck")
    stored = {k: v for k, v in word.items() if k in _WORD_FIELDS and v}
    stored["term"] = term
    stored.pop("hanzi", None)
    if word.get("pinyin") and not stored.get("reading"):
        stored["reading"] = word["pinyin"]
    stored["id"] = word.get("id") or next_word_id(deck)
    if autofill:
        from . import lang
        lang.autofill(stored, deck.get("language", DEFAULT_LANGUAGE))
    deck["words"].append(stored)
    return stored


def update_word(deck, word_id, changes, autofill=False):
    for w in deck["words"]:
        if w["id"] == word_id:
            w.update({k: v for k, v in changes.items() if k in _WORD_FIELDS})
            if autofill:
                from . import lang
                lang.autofill(w, deck.get("language", DEFAULT_LANGUAGE),
                              overwrite=True)
            return w
    raise KeyError(word_id)


def delete_word(deck, word_id):
    before = len(deck["words"])
    deck["words"] = [w for w in deck["words"] if w["id"] != word_id]
    return len(deck["words"]) < before
