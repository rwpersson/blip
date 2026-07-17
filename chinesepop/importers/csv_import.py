"""CSV / TSV import.

Covers the common "I have a word list" case. Sniffs the delimiter and whether
there's a header row, so a plain two-column file Just Works.
"""
import csv
import io
from pathlib import Path

from ..logging_setup import get
from .common import _GUESSES, ImportResult

log = get("importers.csv")

_HEADER_WORDS = {h for hints in _GUESSES.values() for h in hints}


def _looks_like_header(row):
    """csv.Sniffer's has_header() is unreliable on short files and CJK data — it
    guesses by column type, so 'Hanzi,Pinyin,English' over one data row reads as
    data. If any cell is a field name we recognise, it's a header.
    """
    return any(str(c).strip().lower() in _HEADER_WORDS for c in row)


def _read_text(path):
    """Spreadsheets love to emit UTF-8-BOM or cp1252; try in that order."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse(path, delimiter=None, has_header=None):
    text = _read_text(path)
    if not text.strip():
        return ImportResult([], [], Path(path).name, ["file is empty"])

    sample = text[:4096]
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows_raw = [r for r in reader if any(c.strip() for c in r)]
    if not rows_raw:
        return ImportResult([], [], Path(path).name, ["no rows found"])

    if has_header is None:
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = False
        # ...and trust our own names check over the sniffer, which under-detects.
        has_header = has_header or _looks_like_header(rows_raw[0])

    notes = []
    if has_header:
        fields = [c.strip() or f"column {i+1}"
                  for i, c in enumerate(rows_raw[0])]
        body = rows_raw[1:]
    else:
        width = max(len(r) for r in rows_raw)
        fields = [f"column {i+1}" for i in range(width)]
        body = rows_raw
        notes.append("no header row detected — columns are positional")

    rows = []
    for r in body:
        if len(r) > len(fields):        # ragged row: keep the data, name the extras
            fields += [f"column {i+1}" for i in range(len(fields), len(r))]
        rows.append({f: (r[i] if i < len(r) else "") for i, f in enumerate(fields)})

    notes.append(f"delimiter {delimiter!r}, {len(rows)} row(s)")
    return ImportResult(fields, rows, Path(path).name, notes)
