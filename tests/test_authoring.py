"""Authoring: creating decks and cards, and saving them."""
import json

import pytest

from blip import decks as d


@pytest.fixture
def deck():
    return d.create("My Deck", language="zh-CN")


def test_create_slugifies(deck):
    assert deck["id"] == "my-deck"
    assert deck["words"] == [] and deck["language"] == "zh-CN"


def test_add_word_autofills_reading_and_tones(deck):
    pytest.importorskip("pypinyin")
    w = d.add_word(deck, {"term": "牛逼", "meaning": "awesome", "cat": "slang"})
    assert w["reading"] == "niú bī" and w["tones"] == "2-1"
    assert w["id"] == "1"


def test_ids_are_per_deck_not_global(deck):
    """Audio is content-addressed, so ids only have to be unique in their deck —
    two decks both starting at 1 is fine and must not collide."""
    other = d.create("Other")
    a = d.add_word(deck, {"term": "牛逼", "meaning": "m"}, autofill=False)
    b = d.add_word(other, {"term": "加油", "meaning": "m"}, autofill=False)
    assert a["id"] == b["id"] == "1"


def test_add_word_rejects_duplicate_term(deck):
    d.add_word(deck, {"term": "牛逼", "meaning": "m"}, autofill=False)
    with pytest.raises(ValueError, match="already in this deck"):
        d.add_word(deck, {"term": "牛逼", "meaning": "again"}, autofill=False)


def test_add_word_requires_a_term(deck):
    with pytest.raises(ValueError, match="needs a term"):
        d.add_word(deck, {"meaning": "no term"})


def test_add_word_accepts_legacy_field_names(deck):
    w = d.add_word(deck, {"hanzi": "牛逼", "pinyin": "niú bī", "meaning": "m"},
                   autofill=False)
    assert w["term"] == "牛逼" and w["reading"] == "niú bī"
    assert "hanzi" not in w and "pinyin" not in w


def test_update_and_delete(deck):
    w = d.add_word(deck, {"term": "牛逼", "meaning": "m"}, autofill=False)
    d.update_word(deck, w["id"], {"meaning": "awesome"})
    assert deck["words"][0]["meaning"] == "awesome"
    with pytest.raises(KeyError):
        d.update_word(deck, "nope", {"meaning": "x"})
    assert d.delete_word(deck, w["id"]) is True
    assert deck["words"] == []
    assert d.delete_word(deck, w["id"]) is False


def test_find_term_across_decks(deck):
    d.add_word(deck, {"term": "牛逼", "meaning": "m"}, autofill=False)
    found_deck, found = d.find_term([deck], "牛逼")
    assert found_deck is deck and found["term"] == "牛逼"
    assert d.find_term([deck], "nope") == (None, None)


def test_save_roundtrips_and_drops_empty_fields(deck, tmp_path):
    d.add_word(deck, {"term": "牛逼", "meaning": "awesome", "note": ""},
               autofill=False)
    p = d.save(deck, tmp_path / "my-deck.json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["schema"] == d.SCHEMA and raw["language"] == "zh-CN"
    assert raw["words"][0]["term"] == "牛逼"
    assert "note" not in raw["words"][0]      # empty fields aren't persisted
    assert "source" not in raw                # in-memory bookkeeping isn't either


def test_saved_deck_reloads_cleanly(deck, tmp_path, monkeypatch):
    pytest.importorskip("pypinyin")
    d.add_word(deck, {"term": "牛逼", "meaning": "awesome", "cat": "slang"})
    d.save(deck, tmp_path / "my-deck.json")
    monkeypatch.setattr(d.paths, "decks_dirs", lambda: [tmp_path])
    loaded = d.load_all()
    assert len(loaded) == 1
    assert d.validate(loaded[0]) == []        # a deck we wrote must validate
    assert d.word_reading(loaded[0]["words"][0]) == "niú bī"
