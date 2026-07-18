"""The creator-deck catalog: browse, install, uninstall.

No network here — install()'s audio step is exercised with a stub generator, so
these stay fast and offline. The real tts path is covered elsewhere.
"""
import json

import pytest

from chinesepop import catalog
from chinesepop import decks as decks_mod


def _deck(deck_id, name, words):
    return {"schema": 1, "name": name, "language": "zh-CN", "voice": None,
            "words": words}


def _word(wid, term, cat="common"):
    return {"id": wid, "term": term, "reading": "cè shì", "tones": "4-4",
            "cat": cat, "meaning": "test", "note": ""}


@pytest.fixture
def cat(tmp_path, monkeypatch):
    """A tmp catalog dir + tmp user-decks dir, wired into the module."""
    catalog_dir = tmp_path / "catalog"
    user_decks = tmp_path / "user" / "decks"
    catalog_dir.mkdir(parents=True)
    user_decks.mkdir(parents=True)

    (catalog_dir / "alpha.json").write_text(json.dumps(_deck(
        "alpha", "Alpha", [_word("1", "甲", "hsk"), _word("2", "乙", "slang"),
                           _word("3", "丙", "hsk")])), encoding="utf-8")
    (catalog_dir / "beta.json").write_text(json.dumps(_deck(
        "beta", "Beta", [_word("1", "丁", "swear")])), encoding="utf-8")

    monkeypatch.setattr(catalog.paths, "bundled_catalog_dir", lambda: catalog_dir)
    monkeypatch.setattr(decks_mod, "user_decks_dir", lambda: user_decks)
    return {"catalog": catalog_dir, "user": user_decks}


def test_entries_list_the_catalog_with_metadata(cat):
    es = {e.id: e for e in catalog.entries()}
    assert set(es) == {"alpha", "beta"}
    assert es["alpha"].name == "Alpha"
    assert es["alpha"].word_count == 3
    assert es["alpha"].categories == {"hsk": 2, "slang": 1}   # sorted by count
    assert es["alpha"].sample[:2] == ["甲", "乙"]
    assert es["alpha"].installed is False


def test_install_copies_the_deck_and_flips_installed(cat):
    deck, ok, att = catalog.install("alpha", generate_audio=False)
    assert deck["id"] == "alpha"
    assert (cat["user"] / "alpha.json").exists()
    assert catalog.is_installed("alpha")
    assert {e.id: e.installed for e in catalog.entries()}["alpha"] is True
    assert (ok, att) == (0, 0)                    # audio skipped


def test_install_generates_audio_through_the_provider(cat, monkeypatch):
    """Settings + generate_audio -> the deck is handed to tts.generate with the
    progress callback intact."""
    seen = {}

    def fake_generate(decks, settings, progress=None, **kw):
        seen["decks"] = [d["id"] for d in decks]
        seen["progress"] = progress
        return 7, 9

    monkeypatch.setattr(catalog.tts, "generate", fake_generate)
    cb = lambda *a: None
    deck, ok, att = catalog.install("alpha", settings=object(), progress=cb)
    assert seen["decks"] == ["alpha"]
    assert seen["progress"] is cb
    assert (ok, att) == (7, 9)


def test_install_all_installs_only_the_missing(cat, monkeypatch):
    monkeypatch.setattr(catalog.tts, "generate", lambda *a, **k: (1, 1))
    catalog.install("alpha", settings=object())
    installed, ok, att = catalog.install_all(settings=object())
    assert [d["id"] for d in installed] == ["beta"]   # alpha already there
    assert catalog.is_installed("beta")


def test_load_unknown_deck_raises(cat):
    with pytest.raises(KeyError):
        catalog.load("nope")


def test_uninstall_removes_only_catalog_decks(cat):
    catalog.install("alpha", generate_audio=False)
    assert catalog.uninstall("alpha") is True
    assert not catalog.is_installed("alpha")
    assert catalog.uninstall("alpha") is False        # already gone
    # a deck the user authored (not in the catalog) is never touched
    (cat["user"] / "mine.json").write_text("{}", encoding="utf-8")
    assert catalog.uninstall("mine") is False
    assert (cat["user"] / "mine.json").exists()


def test_a_broken_catalog_file_is_skipped_not_fatal(cat):
    (cat["catalog"] / "broken.json").write_text("{ not json", encoding="utf-8")
    ids = {e.id for e in catalog.entries()}
    assert ids == {"alpha", "beta"}                   # broken one silently dropped
