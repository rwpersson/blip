"""Shared import plumbing: the result shape, field guessing, and row->word.

Import is deliberately two-phase — parse, then map — because no source has a fixed
schema. An Anki note's fields are whatever its notetype declares ("Simplified",
"Front", "Expression"…), and a CSV's columns are whatever someone typed. Guessing
is a convenience; the user always confirms.
"""
import re
from dataclasses import dataclass, field

from ..logging_setup import get

log = get("importers")

# Our fields, and the source names we'll guess them from (lowercased substrings).
OUR_FIELDS = ("term", "reading", "meaning", "note", "tones", "cat", "alt", "say")

_GUESSES = {
    "term": ("term", "word", "simplified", "hanzi", "chinese", "expression",
             "front", "characters", "vocab", "traditional"),
    "reading": ("reading", "pinyin", "pronunciation", "romaji", "kana", "romanization"),
    "meaning": ("meaning", "definition", "english", "translation", "back",
                "gloss", "sense"),
    "note": ("note", "notes", "usage", "example", "comment", "extra", "mnemonic"),
    "tones": ("tone", "tones"),
    "cat": ("cat", "category", "tag", "tags", "type", "pos"),
}

_TAG_RE = re.compile(r"<[^>]+>")
_SOUND_RE = re.compile(r"\[sound:[^\]]*\]", re.I)
_IMG_RE = re.compile(r"<img[^>]*>", re.I)
_NBSP = "\xa0"


@dataclass
class ImportResult:
    """What a source gave us, before any mapping."""
    fields: list                       # the source's own field/column names
    rows: list                         # list of {source_field: value}
    source: str = ""                   # file name, for messages
    notes: list = field(default_factory=list)   # warnings worth showing the user

    def sample(self, n=5):
        return self.rows[:n]


def clean(value):
    """Strip the junk that rides along in exported fields.

    Anki fields are HTML: they carry tags, `[sound:x.mp3]` refs, images and
    &nbsp;. A CSV from a spreadsheet carries stray whitespace. Cards should hold
    text, not markup.
    """
    if value is None:
        return ""
    s = str(value)
    s = _SOUND_RE.sub(" ", s)
    s = _IMG_RE.sub(" ", s)
    s = re.sub(r"<br\s*/?>|</div>|</p>", " ", s, flags=re.I)
    s = _TAG_RE.sub("", s)
    s = (s.replace("&nbsp;", " ").replace(_NBSP, " ")
          .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", s).strip()


def guess_mapping(fields):
    """Best-guess {our field: their field}. The user confirms/overrides."""
    mapping = {}
    used = set()
    for ours, hints in _GUESSES.items():
        for f in fields:
            if f in used:
                continue
            low = str(f).lower()
            if any(h in low for h in hints):
                mapping[ours] = f
                used.add(f)
                break
    # Fall back to position: first unused column is the term, next the meaning.
    spare = [f for f in fields if f not in used]
    if "term" not in mapping and spare:
        mapping["term"] = spare.pop(0)
    if "meaning" not in mapping and spare:
        mapping["meaning"] = spare.pop(0)
    return mapping


def _normalize_cat(value):
    """Map a source's category/tag onto one of ours, or drop it.

    Imported tags are freeform ("hsk1", "HSK Level 1", "verb"), and a foreign
    value here produces a deck that fails validation and renders with the wrong
    pill. Anything we don't recognise is dropped — the card then just falls back
    to `common`, which is honest.
    """
    from .. import decks as decks_mod

    if not value:
        return None
    v = str(value).strip().lower()
    if v in decks_mod.CATEGORIES:
        return v
    for known in decks_mod.CATEGORIES:          # "hsk1", "HSK Level 1" -> hsk
        if v.startswith(known):
            return known
    return None


def build_words(result, mapping, language="zh-CN", autofill=True, cat=None):
    """Turn mapped rows into our word dicts.

    Rows without a term are dropped (they're usually blank lines or media-only
    notes); duplicates within the import are collapsed; unrecognised categories
    are dropped rather than poisoning the deck. Returns (words, report).
    """
    from .. import lang

    words, seen = [], set()
    skipped_no_term = dupes = dropped_cats = 0
    for row in result.rows:
        w = {}
        for ours, theirs in mapping.items():
            if not theirs:
                continue
            val = clean(row.get(theirs, ""))
            if val:
                w[ours] = val
        term = w.get("term")
        if not term:
            skipped_no_term += 1
            continue
        if term in seen:
            dupes += 1
            continue
        seen.add(term)

        if "cat" in w:
            normalized = _normalize_cat(w["cat"])
            if normalized:
                w["cat"] = normalized
            else:
                del w["cat"]
                dropped_cats += 1
        if cat and not w.get("cat"):
            w["cat"] = _normalize_cat(cat) or None
            if not w["cat"]:
                del w["cat"]
        if autofill:
            lang.autofill(w, language)
        words.append(w)

    report = {"imported": len(words), "skipped_no_term": skipped_no_term,
              "duplicates_in_file": dupes, "unrecognised_categories": dropped_cats,
              "source": result.source}
    return words, report
