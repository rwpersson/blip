"""
Create a new (empty) deck.

    python new_deck.py "Week 3"
    python new_deck.py "HSK 6 Verbs" hsk6-verbs      # optional custom id

Then add words to it with expand_wordbank.py (--deck <id>) and run
generate_audio.py to make the audio.
"""
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DECKS_DIR = ROOT / "decks"


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def main():
    if len(sys.argv) < 2:
        print('Usage: python new_deck.py "Deck Name" [id]')
        return
    name = sys.argv[1]
    deck_id = sys.argv[2] if len(sys.argv) > 2 else slugify(name)
    DECKS_DIR.mkdir(exist_ok=True)
    path = DECKS_DIR / f"{deck_id}.json"
    if path.exists():
        print(f"Deck '{deck_id}' already exists at {path}")
        return
    path.write_text(json.dumps({"name": name, "words": []},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f'Created deck "{name}"  ->  decks/{deck_id}.json')
    print(f"Add words:      python expand_wordbank.py --deck {deck_id}")
    print(f"Then audio:     python generate_audio.py")
    print("Decks are ordered by filename — prefix ids (2-, 3-, …) to order them.")


if __name__ == "__main__":
    main()
