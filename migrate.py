"""
One-shot migrations for the Phase-2 data-model change.

    python migrate.py --dry-run      # show what would happen (do this first)
    python migrate.py                # do it

Two things move:

1. **Audio -> content-addressed names.** Clips used to be `<word id>.mp3`; they're
   now `hash(text+voice+rate).mp3` so authored/imported decks can't collide. Files
   are RENAMED in place, so nothing has to be re-synthesized. Identical clips that
   collapse to one name (the same word in two decks) are de-duplicated.

2. **Decks -> generic fields.** `hanzi`->`term`, `pinyin`->`reading`, plus explicit
   `schema` and `language`, so a deck can describe any language rather than being
   implicitly Chinese.

Safe to re-run: it only touches what still looks un-migrated.
"""
import json
import sys

from chinesepop import decks as decks_mod
from chinesepop import paths, settings as settings_mod
from chinesepop.audio import clips
from chinesepop.logging_setup import get, setup

log = get("migrate")

DECK_SCHEMA = 1


def migrate_audio(decks, s, dry_run):
    """Rename id-named clips to their content-addressed names."""
    audio = paths.audio_dir()
    if not audio.exists():
        log.info("audio: no audio dir, nothing to migrate")
        return
    renamed = deduped = missing = 0
    # On a dry run nothing actually moves, so track the names we *would* create —
    # otherwise every duplicate looks like a fresh rename and the preview lies.
    created = set()

    def exists(p):
        return p.exists() or p.name in created

    for deck in decks:
        for w in deck["words"]:
            for kind, _text, new_path, _v, _r in clips.specs_for(w, s, deck):
                suffix = "" if kind == clips.WORD else f"_{kind}"
                old_path = audio / f"{w['id']}{suffix}.mp3"
                if not old_path.exists() or old_path == new_path:
                    if not exists(new_path):
                        missing += 1
                    continue
                if exists(new_path):
                    # another card already produced this exact clip (e.g. two
                    # words with the same tone pattern share one tones clip)
                    deduped += 1
                    if not dry_run:
                        old_path.unlink()
                else:
                    renamed += 1
                    created.add(new_path.name)
                    if not dry_run:
                        old_path.rename(new_path)
    log.info("audio: %s renamed, %s de-duplicated, %s not on disk yet%s",
             renamed, deduped, missing, "  [dry run]" if dry_run else "")


def migrate_deck_file(path, dry_run):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"name": path.stem, "words": data}
    if data.get("schema") == DECK_SCHEMA and not any(
            "hanzi" in w or "pinyin" in w for w in data.get("words", [])):
        return False                       # already migrated

    out = {
        "schema": DECK_SCHEMA,
        "name": data.get("name", path.stem),
        "language": data.get("language", "zh-CN"),
        "voice": data.get("voice"),
        "words": [],
    }
    for w in data.get("words", []):
        new = {"id": w["id"]}
        if "hanzi" in w or "term" in w:
            new["term"] = w.get("term") or w.get("hanzi")
        if w.get("pinyin") or w.get("reading"):
            new["reading"] = w.get("reading") or w.get("pinyin")
        for k in ("tones", "cat", "meaning", "note", "alt", "say"):
            if w.get(k):
                new[k] = w[k]
        out["words"].append(new)

    if not dry_run:
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return True


def migrate_decks(dry_run):
    changed = 0
    for d in paths.decks_dirs():
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            if migrate_deck_file(f, dry_run):
                changed += 1
                log.info("decks: migrated %s%s", f.name,
                         "  [dry run]" if dry_run else "")
    if not changed:
        log.info("decks: already up to date")


def main():
    setup()
    dry_run = "--dry-run" in sys.argv
    paths.ensure_dirs()
    s = settings_mod.load()

    # audio first: it needs the OLD ids, which the deck migration preserves anyway,
    # but the spec text must match what was originally spoken.
    decks = decks_mod.load_all()
    if not decks:
        log.error("no decks found")
        return 1
    migrate_audio(decks, s, dry_run)
    migrate_decks(dry_run)
    if dry_run:
        log.info("dry run — nothing was changed. Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
