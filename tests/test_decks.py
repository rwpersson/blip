"""Deck loading + validation. Third-party decks WILL be malformed."""
import json

from chinesepop import decks as d


def _deck(words, deck_id="t"):
    return {"id": deck_id, "name": "T", "language": "zh-CN", "voice": None,
            "words": words, "source": None}


def test_field_accessors_support_both_schemas():
    """Phase 2 renames hanzi->term / pinyin->reading; both must read cleanly."""
    old = {"hanzi": "牛逼", "pinyin": "niú bī", "tones": "2-1"}
    new = {"term": "牛逼", "reading": "niú bī", "tones": "2-1"}
    for w in (old, new):
        assert d.word_term(w) == "牛逼"
        assert d.word_reading(w) == "niú bī"
        assert d.word_tones(w) == "2-1"


def test_word_say_prefers_override():
    assert d.word_say({"hanzi": "666", "say": "六六六"}) == "六六六"
    assert d.word_say({"hanzi": "牛逼"}) == "牛逼"


def test_validate_accepts_a_good_deck():
    assert d.validate(_deck([
        {"id": "1", "hanzi": "牛逼", "pinyin": "niú bī", "tones": "2-1",
         "cat": "slang", "meaning": "awesome"}])) == []


def test_validate_catches_bad_data():
    problems = d.validate(_deck([
        {"id": "1", "hanzi": "a", "meaning": "m"},
        {"id": "1", "hanzi": "b", "meaning": "m"},          # duplicate id
        {"id": "2", "hanzi": "a", "meaning": "m"},          # duplicate term
        {"id": "3", "hanzi": "c"},                          # missing meaning
        {"id": "4", "hanzi": "d", "meaning": "m", "cat": "bogus"},
        {"hanzi": "e", "meaning": "m"},                     # missing id
    ]))
    joined = " | ".join(problems)
    assert "duplicate id" in joined
    assert "duplicate term" in joined
    assert "missing meaning" in joined
    assert "unknown cat" in joined
    assert "missing id" in joined


def test_validate_flags_tone_syllable_mismatch():
    problems = d.validate(_deck([
        {"id": "1", "hanzi": "立flag", "pinyin": "lì flag", "tones": "4",
         "meaning": "to jinx"}]))
    assert any("tones" in p for p in problems)


def test_load_all_reads_real_decks(tmp_path, monkeypatch):
    deck = {"name": "Fixture", "language": "ja-JP",
            "words": [{"id": "1", "term": "猫", "reading": "neko",
                       "meaning": "cat", "cat": "common"}]}
    (tmp_path / "fixture.json").write_text(json.dumps(deck), encoding="utf-8")
    monkeypatch.setattr(d.paths, "decks_dirs", lambda: [tmp_path])
    loaded = d.load_all()
    assert len(loaded) == 1
    assert loaded[0]["id"] == "fixture"
    assert loaded[0]["language"] == "ja-JP"      # decks carry their own language
    assert d.word_term(loaded[0]["words"][0]) == "猫"


def test_load_all_skips_unreadable_deck(tmp_path, monkeypatch):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(d.paths, "decks_dirs", lambda: [tmp_path])
    assert d.load_all() == []                    # logged, not crashed
