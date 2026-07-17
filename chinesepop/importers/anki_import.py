"""Anki `.apkg` import.

An .apkg is a ZIP containing a SQLite collection plus media. The awkward parts,
all of which this handles or reports clearly:

* **Which database?** Old exports have `collection.anki2`. Newer ones add
  `collection.anki21`, and the newest write `collection.anki21b`, which is
  **zstd-compressed** — unreadable by sqlite3 directly. We prefer the newest
  readable one and say so plainly if it needs zstd we don't have.
* **No fixed schema.** A note's fields are a single `flds` column with values
  joined by `\x1f`. The *names* live in the notetype JSON — in `col.models`
  (old) or the `notetypes` table (new, where the field names sit in a protobuf
  blob we can't parse, so we fall back to positional names).
* **Fields are HTML** carrying `[sound:…]` refs, `<img>`, `&nbsp;` — stripped by
  `common.clean()`.
* **Media is not imported.** We re-synthesize instead: one consistent voice, no
  redistribution question, and a much smaller footprint. (The clips are
  content-addressed, so an imported word you already have costs nothing.)
"""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from ..logging_setup import get
from .common import ImportResult

log = get("importers.anki")

FIELD_SEP = "\x1f"
_DB_NAMES = ("collection.anki21b", "collection.anki21", "collection.anki2")


class AnkiImportError(Exception):
    """Something we can explain to the user, rather than a stack trace."""


def _extract_db(apkg, workdir):
    """Pull out the newest collection we can actually read."""
    with zipfile.ZipFile(apkg) as z:
        names = set(z.namelist())
        for candidate in _DB_NAMES:
            if candidate not in names:
                continue
            raw = z.read(candidate)
            if candidate.endswith("b"):          # zstd-compressed
                try:
                    import zstandard
                except ImportError:
                    log.info("%s is zstd-compressed and `zstandard` isn't "
                             "installed; trying an older collection", candidate)
                    continue
                raw = zstandard.ZstdDecompressor().stream_reader(raw).read()
            out = Path(workdir) / "collection.sqlite"
            out.write_bytes(raw)
            return out, candidate
    raise AnkiImportError(
        "No readable Anki collection in this file. If it was exported by a very "
        "recent Anki it may be zstd-compressed — `pip install zstandard`, or "
        "re-export with 'Support older Anki versions' ticked.")


def _field_names(con):
    """{notetype id: [field names]} from whichever schema this file uses."""
    names = {}
    # Old schema: the whole notetype config is JSON in col.models
    try:
        row = con.execute("SELECT models FROM col").fetchone()
        if row and row[0]:
            for mid, model in json.loads(row[0]).items():
                names[int(mid)] = [f["name"] for f in model.get("flds", [])]
    except sqlite3.Error:
        pass
    if names:
        return names
    # New schema: field names live in the `fields` table
    try:
        for mid, ord_, name in con.execute(
                "SELECT ntid, ord, name FROM fields ORDER BY ntid, ord"):
            names.setdefault(int(mid), []).append(name)
    except sqlite3.Error:
        pass
    return names


def _deck_names(con):
    try:
        row = con.execute("SELECT decks FROM col").fetchone()
        if row and row[0]:
            return {int(k): v.get("name", "") for k, v in json.loads(row[0]).items()}
    except (sqlite3.Error, json.JSONDecodeError, AttributeError):
        pass
    try:
        return {int(i): n for i, n in con.execute("SELECT id, name FROM decks")}
    except sqlite3.Error:
        return {}


def parse(apkg_path, deck_name=None):
    """Read notes out of an .apkg. Returns an ImportResult whose `fields` are the
    notetype's own field names — the caller maps them."""
    apkg_path = Path(apkg_path)
    notes_out, all_fields, extra = [], [], []

    with tempfile.TemporaryDirectory() as tmp:
        db_path, which = _extract_db(apkg_path, tmp)
        extra.append(f"read {which}")
        con = sqlite3.connect(db_path)
        try:
            field_names = _field_names(con)
            decks = _deck_names(con)

            # Restrict to one Anki deck if asked (notes reach decks via cards)
            note_filter, params = "", []
            if deck_name:
                ids = [i for i, n in decks.items()
                       if n and deck_name.lower() in n.replace("\x1f", "::").lower()]
                if not ids:
                    raise AnkiImportError(
                        f"No deck matching {deck_name!r}. Found: "
                        + ", ".join(sorted(n for n in decks.values() if n)))
                q = ",".join("?" * len(ids))
                note_filter = (f" WHERE n.id IN (SELECT DISTINCT nid FROM cards "
                               f"WHERE did IN ({q}))")
                params = ids

            try:
                rows = con.execute(
                    f"SELECT n.id, n.mid, n.flds, n.tags FROM notes n{note_filter}",
                    params).fetchall()
            except sqlite3.Error as e:
                raise AnkiImportError(f"Couldn't read notes: {e}") from e

            seen_fields = []
            for _nid, mid, flds, tags in rows:
                values = (flds or "").split(FIELD_SEP)
                names = field_names.get(int(mid)) or []
                if len(names) < len(values):     # unnamed/protobuf notetype
                    names = list(names) + [f"Field {i+1}"
                                           for i in range(len(names), len(values))]
                row = {names[i]: v for i, v in enumerate(values)}
                if tags and tags.strip():
                    row["Tags"] = tags.strip()
                for k in row:
                    if k not in seen_fields:
                        seen_fields.append(k)
                notes_out.append(row)
            all_fields = seen_fields
        finally:
            con.close()

    if not notes_out:
        extra.append("no notes found")
    extra.append(f"{len(notes_out)} note(s)")
    extra.append("media is not imported — audio is re-synthesized in your voice")
    return ImportResult(all_fields, notes_out, apkg_path.name, extra)


def list_decks(apkg_path):
    """Deck names inside an .apkg, so the user can pick one."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path, _ = _extract_db(Path(apkg_path), tmp)
        con = sqlite3.connect(db_path)
        try:
            return sorted(n.replace("\x1f", "::")
                          for n in _deck_names(con).values() if n)
        finally:
            con.close()
