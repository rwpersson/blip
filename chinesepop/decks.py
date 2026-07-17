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
    return {
        "id": deck_id,
        "name": data.get("name", deck_id),
        "language": data.get("language", DEFAULT_LANGUAGE),
        "voice": data.get("voice"),            # optional per-deck voice override
        "words": data.get("words", []),
        "source": source,
    }


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
    """Every deck, bundled + user, ordered by filename."""
    decks = []
    for d in paths.decks_dirs():
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
            decks.append(deck)
    return decks


def all_words(decks=None):
    """Every word across every deck (audio is keyed per word)."""
    decks = decks if decks is not None else load_all()
    return [w for d in decks for w in d["words"]]


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
    """Existing file if we loaded it from one, else a new file in the user dir."""
    return deck.get("source") or (user_decks_dir() / f"{deck['id']}.json")


def to_json(deck):
    """Serialize, dropping our in-memory bookkeeping and empty fields."""
    return {
        "schema": SCHEMA,
        "name": deck.get("name", deck["id"]),
        "language": deck.get("language", DEFAULT_LANGUAGE),
        "voice": deck.get("voice"),
        "words": [{k: w[k] for k in _WORD_FIELDS if w.get(k)}
                  for w in deck.get("words", [])],
    }


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
            "voice": voice, "words": [], "source": None}


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
