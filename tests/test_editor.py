"""Editor logic — no Tk. Everything here is what the window delegates to."""
import pytest

from blip import decks as d
from blip.editor.controller import EditorController


@pytest.fixture
def ctl(settings, tmp_path, monkeypatch):
    # user decks are written to user_dir()/decks, so that's where we must read from
    monkeypatch.setattr(d.paths, "user_dir", lambda: tmp_path)
    monkeypatch.setattr(d.paths, "decks_dirs", lambda: [tmp_path / "decks"])
    monkeypatch.setattr("blip.audio.clips.paths.audio_dir",
                        lambda: tmp_path / "audio")
    return EditorController(settings)


def test_create_deck_persists_and_rejects_duplicates(ctl, tmp_path):
    deck = ctl.create_deck("Week 9")
    assert (tmp_path / "decks" / "week-9.json").exists()
    assert ctl.deck_by_id("week-9") is deck
    with pytest.raises(ValueError, match="already exists"):
        ctl.create_deck("Week 9")
    with pytest.raises(ValueError, match="needs a name"):
        ctl.create_deck("   ")


def test_validate_card_requires_term_and_meaning(ctl):
    assert "Term is required" in ctl.validate_card({"meaning": "x"})
    assert "Meaning is required" in ctl.validate_card({"term": "x"})
    assert ctl.validate_card({"term": "牛逼", "meaning": "awesome"}) == []


def test_validate_card_warns_on_tone_syllable_mismatch(ctl):
    """Not fatal — you can save it — but it silently kills tone colors, so say so."""
    problems = ctl.validate_card({"term": "牛逼", "meaning": "m",
                                  "reading": "niú bī", "tones": "2"})
    assert any("syllable" in p for p in problems)
    assert not any(p.endswith("required") for p in problems)


def test_save_card_creates_then_updates(ctl):
    deck = ctl.create_deck("Test")
    w = ctl.save_card(deck, {"term": "牛逼", "meaning": "awesome"})
    assert w["id"] == "1"
    ctl.save_card(deck, {"term": "牛逼", "meaning": "badass"}, word_id=w["id"])
    assert len(deck["words"]) == 1
    assert deck["words"][0]["meaning"] == "badass"
    # and it survived to disk
    reloaded = d.load_all()[0]
    assert reloaded["words"][0]["meaning"] == "badass"


def test_save_card_clears_fields_the_user_emptied(ctl):
    """An edit that blanks a field must remove it, not silently keep the old value."""
    deck = ctl.create_deck("Test")
    w = ctl.save_card(deck, {"term": "牛逼", "meaning": "m", "note": "old note"})
    ctl.save_card(deck, {"term": "牛逼", "meaning": "m", "note": ""}, word_id=w["id"])
    assert "note" not in deck["words"][0]


def test_duplicate_of_finds_term_in_another_deck(ctl):
    a = ctl.create_deck("A")
    b = ctl.create_deck("B")
    ctl.save_card(a, {"term": "牛逼", "meaning": "awesome"})
    found, _ = ctl.duplicate_of("牛逼", b)
    assert found is a
    assert ctl.duplicate_of("加油", b) == (None, None)


def test_duplicate_of_ignores_the_card_being_edited(ctl):
    a = ctl.create_deck("A")
    w = ctl.save_card(a, {"term": "牛逼", "meaning": "awesome"})
    # editing that same card must not report itself as a duplicate
    assert ctl.duplicate_of("牛逼", a, exclude_id=w["id"]) == (None, None)


def test_delete_card_persists(ctl):
    deck = ctl.create_deck("Test")
    w = ctl.save_card(deck, {"term": "牛逼", "meaning": "m"})
    assert ctl.delete_card(deck, w["id"]) is True
    assert d.load_all()[0]["words"] == []


def test_delete_deck_removes_the_file(ctl, tmp_path):
    deck = ctl.create_deck("Doomed")
    path = tmp_path / "decks" / "doomed.json"
    assert path.exists()
    ctl.delete_deck(deck)
    assert not path.exists()
    assert ctl.deck_by_id("doomed") is None


def test_autofill_is_a_suggestion(ctl):
    pytest.importorskip("pypinyin")
    assert ctl.autofill("牛逼", "zh-CN") == ("niú bī", "2-1")
    assert ctl.autofill("neko", "ja-JP") == ("", "")


def test_import_words_skips_ones_already_in_the_deck(ctl):
    deck = ctl.create_deck("Target")
    ctl.save_card(deck, {"term": "牛逼", "meaning": "awesome"})
    report, added = ctl.import_words(
        deck,
        [{"term": "牛逼", "meaning": "dupe"}, {"term": "加油", "meaning": "go"}],
        generate_audio=False)
    assert report == {"added": 1, "skipped_existing": 1}
    assert len(deck["words"]) == 2
    assert d.load_all()[0]["words"][1]["term"] == "加油"     # persisted


def test_card_audio_ready_reflects_disk(ctl, tmp_path):
    from blip.audio import clips
    deck = ctl.create_deck("Test")
    w = ctl.save_card(deck, {"term": "牛逼", "meaning": "awesome"})
    assert ctl.card_audio_ready(w, deck) is False
    audio = tmp_path / "audio"
    audio.mkdir(exist_ok=True)
    for _k, _t, p, _v, _r in clips.specs_for(w, ctl.s, deck):
        p.write_bytes(b"x")
    assert ctl.card_audio_ready(w, deck) is True


def test_user_deck_overrides_bundled_one(settings, tmp_path, monkeypatch):
    """Editing a shipped deck after install is copy-on-write: the bundled dir is
    read-only, so the copy lands in the user dir — and must not show up twice."""
    bundled = tmp_path / "bundled"
    user = tmp_path / "user" / "decks"
    bundled.mkdir(parents=True)
    user.mkdir(parents=True)
    (bundled / "week-1.json").write_text(
        '{"schema":1,"name":"Week 1","words":[{"id":"1","term":"旧","meaning":"old"}]}',
        encoding="utf-8")
    (user / "week-1.json").write_text(
        '{"schema":1,"name":"Week 1 (edited)","words":['
        '{"id":"1","term":"新","meaning":"new"}]}', encoding="utf-8")
    monkeypatch.setattr(d.paths, "decks_dirs", lambda: [bundled, user])

    loaded = d.load_all()
    assert len(loaded) == 1                        # not two decks with one id
    assert loaded[0]["name"] == "Week 1 (edited)"  # the user's copy wins
    assert d.word_term(loaded[0]["words"][0]) == "新"
