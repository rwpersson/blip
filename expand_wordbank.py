"""
Add words to a deck.

1. Put your entries in the NEW list below.
2. Run:  python expand_wordbank.py --deck <deck-id>
         (deck-id is the decks/<id>.json filename, e.g. week-2)

IDs are assigned automatically and are globally unique (max id across ALL decks
+ 1), so audio never collides. Entries whose `hanzi` already exists in ANY deck
are skipped, so it's safe to re-run. After adding, run generate_audio.py.
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DECKS_DIR = ROOT / "decks"

# Each entry: hanzi, pinyin, tones, cat, meaning, note (+ optional alt / say).
# cat: hsk | idiom | slang | swear | gaming | common
NEW = [
    # {"hanzi": "词", "pinyin": "cí", "tones": "2", "cat": "hsk",
    #  "meaning": "word", "note": "example note"},
]


def _all_words():
    words = []
    for f in sorted(DECKS_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        words.extend(data.get("words", data if isinstance(data, list) else []))
    return words


def _next_id(words):
    nums = [int(w["id"]) for w in words if str(w.get("id", "")).isdigit()]
    return (max(nums) + 1) if nums else 1


def main():
    if "--deck" not in sys.argv:
        ids = [f.stem for f in sorted(DECKS_DIR.glob("*.json"))]
        print("Usage: python expand_wordbank.py --deck <deck-id>")
        print("Available decks:", ", ".join(ids) or "(none — see new_deck.py)")
        return
    deck_id = sys.argv[sys.argv.index("--deck") + 1]
    path = DECKS_DIR / f"{deck_id}.json"
    if not path.exists():
        print(f"No deck '{deck_id}'. Create it first: python new_deck.py")
        return

    deck = json.loads(path.read_text(encoding="utf-8"))
    deck.setdefault("words", [])
    every = _all_words()
    existing = {w["hanzi"] for w in every}
    nid = _next_id(every)
    added = 0
    for w in NEW:
        if w["hanzi"] in existing:
            continue
        entry = {"id": f"{nid:02d}"}
        entry.update(w)
        deck["words"].append(entry)
        existing.add(w["hanzi"])
        nid += 1
        added += 1
    path.write_text(json.dumps(deck, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"Added {added} words to '{deck_id}'. "
          f"Deck now has {len(deck['words'])}. Run generate_audio.py next.")


if __name__ == "__main__":
    main()
