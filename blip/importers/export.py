"""Exporting a deck.

Trivial, and that's the point: because audio is content-addressed and synthesized
locally, a deck is just its JSON. There's no media to bundle, so sharing is a
small text file and the recipient's machine makes the audio in their chosen voice.
"""
import csv
import json
from pathlib import Path

from .. import decks as decks_mod

CSV_COLUMNS = ("term", "reading", "tones", "cat", "meaning", "note", "alt", "say")


def to_json_file(deck, path):
    path = Path(path)
    path.write_text(json.dumps(decks_mod.to_json(deck), ensure_ascii=False,
                               indent=2), encoding="utf-8")
    return path


def to_csv_file(deck, path):
    path = Path(path)
    # utf-8-sig so Excel doesn't mangle the characters
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for word in deck["words"]:
            row = {k: word.get(k, "") for k in CSV_COLUMNS}
            row["term"] = decks_mod.word_term(word)
            row["reading"] = decks_mod.word_reading(word)
            w.writerow(row)
    return path
