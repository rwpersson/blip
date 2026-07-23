"""Deck loading + validation. Third-party decks WILL be malformed."""
import json

from blip import decks as d


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


# --- deck-archive contract (Blipfeed <-> Blip seam) --------------------------
def test_archived_flag_defaults_to_false_when_absent():
    """Readers must treat a missing `archived` key as active."""
    deck = d._normalize("x", {"name": "X", "words": []}, None)
    assert deck["archived"] is False


def test_archived_true_round_trips_and_omits_when_false(tmp_path):
    deck = d._normalize("imm", {"name": "Imm", "archived": True,
                                "words": [{"id": "1", "term": "你好",
                                           "meaning": "hi"}]}, None)
    assert deck["archived"] is True
    p = d.save(deck, tmp_path / "imm.json")
    assert json.loads(p.read_text(encoding="utf-8"))["archived"] is True

    # un-archiving omits the key entirely (writers keep active decks clean)
    d.set_archived(deck, False)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "archived" not in raw
    # ...and it reloads as active
    assert d._normalize("imm", raw, None)["archived"] is False


def test_rewrite_preserves_unknown_keys_and_words(tmp_path):
    """The rewrite rule: a routine save must carry through fields we don't manage
    (forward-compat) and never touch the words, or Blip could silently drop data
    a companion app wrote."""
    src = {"schema": 1, "name": "Imm", "language": "zh-CN", "voice": None,
           "archived": True, "blipfeed_meta": {"graduated": "2026-07-21"},
           "words": [{"id": "1", "term": "你好", "reading": "nǐ hǎo",
                      "tones": "3-3", "cat": "common", "meaning": "hi",
                      "note": "greeting", "alt": "您好"}]}
    deck = d._normalize("imm", src, None)
    raw = d.to_json(deck)
    assert raw["blipfeed_meta"] == {"graduated": "2026-07-21"}   # unknown key kept
    assert raw["archived"] is True
    w = raw["words"][0]
    assert (w["note"], w["alt"], w["tones"]) == ("greeting", "您好", "3-3")
