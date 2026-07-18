"""Import: CSV and Anki.

The Anki tests build a real .apkg (a zip around a real SQLite collection) rather
than mocking, because every hard part of that format — \x1f-packed fields,
notetype-defined names, HTML and [sound:] junk — only shows up in the real thing.
"""
import json
import sqlite3
import zipfile

import pytest

from blip.importers import anki_import, common, csv_import, export


# ------------------------------- CSV ----------------------------------------
def test_csv_with_header(tmp_path):
    p = tmp_path / "words.csv"
    p.write_text("Hanzi,Pinyin,English\n牛逼,niú bī,awesome\n加油,jiā yóu,go\n",
                 encoding="utf-8")
    r = csv_import.parse(p)
    assert r.fields == ["Hanzi", "Pinyin", "English"]
    assert len(r.rows) == 2
    m = common.guess_mapping(r.fields)
    assert m["term"] == "Hanzi" and m["reading"] == "Pinyin" and m["meaning"] == "English"
    words, report = common.build_words(r, m, autofill=False)
    assert report["imported"] == 2
    assert words[0] == {"term": "牛逼", "reading": "niú bī", "meaning": "awesome"}


def test_csv_tab_separated_without_header(tmp_path):
    p = tmp_path / "words.tsv"
    p.write_text("牛逼\tawesome\n加油\tgo\n", encoding="utf-8")
    r = csv_import.parse(p)
    assert len(r.rows) == 2
    m = common.guess_mapping(r.fields)          # positional fallback
    assert m["term"] == "column 1" and m["meaning"] == "column 2"
    words, _ = common.build_words(r, m, autofill=False)
    assert words[0]["term"] == "牛逼" and words[0]["meaning"] == "awesome"


def test_csv_handles_bom_and_blank_lines(tmp_path):
    p = tmp_path / "excel.csv"
    p.write_bytes("﻿Term,Meaning\n牛逼,awesome\n\n,\n".encode("utf-8"))
    r = csv_import.parse(p)
    assert r.fields[0] == "Term"                # BOM stripped, not part of the name
    words, report = common.build_words(r, common.guess_mapping(r.fields),
                                       autofill=False)
    assert report["imported"] == 1


def test_csv_empty_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    r = csv_import.parse(p)
    assert r.rows == [] and "empty" in " ".join(r.notes)


def test_build_words_drops_termless_and_dedupes(tmp_path):
    r = common.ImportResult(["a", "b"], [
        {"a": "牛逼", "b": "awesome"},
        {"a": "", "b": "orphan meaning"},       # no term -> dropped
        {"a": "牛逼", "b": "dupe"},             # same term -> collapsed
    ], "x.csv")
    words, report = common.build_words(r, {"term": "a", "meaning": "b"},
                                       autofill=False)
    assert report == {"imported": 1, "skipped_no_term": 1,
                      "duplicates_in_file": 1, "unrecognised_categories": 0,
                      "source": "x.csv"}
    assert len(words) == 1


def test_imported_categories_are_normalized_or_dropped():
    """An Anki tag like 'hsk1' is not one of our categories. Left alone it makes
    the imported deck fail validation, so it must be normalized or dropped."""
    from blip import decks as d

    r = common.ImportResult(["t", "m", "c"], [
        {"t": "妈妈", "m": "mother", "c": "hsk1"},        # -> hsk
        {"t": "牛逼", "m": "awesome", "c": "SLANG"},       # -> slang
        {"t": "银行", "m": "bank", "c": "noun-phrase"},    # unknown -> dropped
    ], "x")
    words, report = common.build_words(
        r, {"term": "t", "meaning": "m", "cat": "c"}, autofill=False)
    assert words[0]["cat"] == "hsk"
    assert words[1]["cat"] == "slang"
    assert "cat" not in words[2]
    assert report["unrecognised_categories"] == 1

    deck = d.create("Imported")
    for w in words:
        d.add_word(deck, w, autofill=False)
    assert d.validate(deck) == []          # the whole point: it must validate


def test_build_words_autofills(tmp_path):
    pytest.importorskip("pypinyin")
    r = common.ImportResult(["a", "b"], [{"a": "牛逼", "b": "awesome"}], "x.csv")
    words, _ = common.build_words(r, {"term": "a", "meaning": "b"})
    assert words[0]["reading"] == "niú bī" and words[0]["tones"] == "2-1"


# ------------------------------- cleaning -----------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("<div>awesome</div>", "awesome"),
    ("niú bī[sound:rec1234.mp3]", "niú bī"),
    ("cat<br>dog", "cat dog"),
    ('<img src="x.jpg">word', "word"),
    ("a&nbsp;b", "a b"),
    ("&amp;&lt;&gt;", "&<>"),
    ("  lots   of   space ", "lots of space"),
    (None, ""),
])
def test_clean_strips_export_junk(raw, expected):
    """Anki fields are HTML carrying media refs; cards should hold text."""
    assert common.clean(raw) == expected


# ------------------------------- Anki ---------------------------------------
def _make_apkg(path, notes, field_names=("Front", "Back"), db_name="collection.anki2"):
    """A minimal but *real* .apkg: zip + sqlite with Anki's schema shape."""
    db = path.parent / "collection.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE col (id integer primary key, models text, decks text)")
    con.execute("CREATE TABLE notes (id integer primary key, mid integer, "
                "flds text, tags text)")
    con.execute("CREATE TABLE cards (id integer primary key, nid integer, "
                "did integer)")
    models = {"1": {"name": "Basic",
                    "flds": [{"name": n} for n in field_names]}}
    decks = {"1": {"name": "Chinese::HSK1"}}
    con.execute("INSERT INTO col VALUES (1, ?, ?)",
                (json.dumps(models), json.dumps(decks)))
    for i, (flds, tags) in enumerate(notes, start=1):
        con.execute("INSERT INTO notes VALUES (?, 1, ?, ?)",
                    (i, anki_import.FIELD_SEP.join(flds), tags))
        con.execute("INSERT INTO cards VALUES (?, ?, 1)", (i, i))
    con.commit()
    con.close()

    apkg = path.parent / "deck.apkg"
    with zipfile.ZipFile(apkg, "w") as z:
        z.write(db, db_name)
        z.writestr("media", "{}")
    return apkg


def test_anki_parse_uses_notetype_field_names(tmp_path):
    apkg = _make_apkg(tmp_path / "x", [(["牛逼", "awesome"], "slang")],
                      field_names=("Simplified", "English"))
    r = anki_import.parse(apkg)
    assert "Simplified" in r.fields and "English" in r.fields
    assert r.rows[0]["Simplified"] == "牛逼"
    assert r.rows[0]["Tags"] == "slang"


def test_anki_end_to_end_import(tmp_path):
    apkg = _make_apkg(tmp_path / "x", [
        (["牛逼", "<div>awesome</div>[sound:a.mp3]"], ""),
        (["加油", "go for it"], "common"),
    ], field_names=("Simplified", "English"))
    r = anki_import.parse(apkg)
    m = common.guess_mapping(r.fields)
    assert m["term"] == "Simplified" and m["meaning"] == "English"
    words, report = common.build_words(r, m, autofill=False)
    assert report["imported"] == 2
    # HTML and the [sound:] ref must not survive into the card
    assert words[0]["meaning"] == "awesome"


def test_anki_unnamed_notetype_falls_back_to_positional(tmp_path):
    """Newer files keep field names in a protobuf blob we can't read; we must
    still import rather than fail."""
    apkg = _make_apkg(tmp_path / "x", [(["牛逼", "awesome", "extra"], "")],
                      field_names=("Front",))          # fewer names than values
    r = anki_import.parse(apkg)
    assert "Field 2" in r.fields and "Field 3" in r.fields
    assert r.rows[0]["Field 2"] == "awesome"


def test_anki_deck_filter_and_listing(tmp_path):
    apkg = _make_apkg(tmp_path / "x", [(["牛逼", "awesome"], "")])
    assert anki_import.list_decks(apkg) == ["Chinese::HSK1"]
    assert len(anki_import.parse(apkg, deck_name="HSK1").rows) == 1
    with pytest.raises(anki_import.AnkiImportError, match="No deck matching"):
        anki_import.parse(apkg, deck_name="Japanese")


def test_anki_rejects_unreadable_file_with_a_clear_message(tmp_path):
    bad = tmp_path / "bad.apkg"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("media", "{}")               # no collection at all
    with pytest.raises(anki_import.AnkiImportError, match="No readable Anki"):
        anki_import.parse(bad)


def test_anki_zstd_collection_reports_actionably(tmp_path, monkeypatch):
    """The newest exports are zstd-compressed. Without the lib we must explain
    what to do, not crash."""
    apkg = _make_apkg(tmp_path / "x", [(["牛逼", "a"], "")],
                      db_name="collection.anki21b")
    monkeypatch.setitem(__import__("sys").modules, "zstandard", None)
    with pytest.raises(anki_import.AnkiImportError) as e:
        anki_import.parse(apkg)
    assert "zstandard" in str(e.value)


# ------------------------------- export -------------------------------------
def test_export_roundtrips_through_csv(tmp_path):
    from blip import decks as d
    deck = d.create("Round Trip")
    d.add_word(deck, {"term": "牛逼", "reading": "niú bī", "tones": "2-1",
                      "meaning": "awesome", "cat": "slang"}, autofill=False)
    csv_path = export.to_csv_file(deck, tmp_path / "out.csv")

    r = csv_import.parse(csv_path)
    words, _ = common.build_words(r, common.guess_mapping(r.fields), autofill=False)
    assert words[0]["term"] == "牛逼"
    assert words[0]["meaning"] == "awesome"


def test_export_json_is_a_loadable_deck(tmp_path, monkeypatch):
    from blip import decks as d
    deck = d.create("Shareable")
    d.add_word(deck, {"term": "牛逼", "meaning": "awesome"}, autofill=False)
    export.to_json_file(deck, tmp_path / "shareable.json")
    monkeypatch.setattr(d.paths, "decks_dirs", lambda: [tmp_path])
    loaded = d.load_all()
    assert loaded[0]["name"] == "Shareable"
    assert d.word_term(loaded[0]["words"][0]) == "牛逼"
