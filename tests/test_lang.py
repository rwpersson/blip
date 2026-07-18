"""Reading/tone auto-fill — the thing that makes authoring a card bearable."""
import pytest

from blip import lang

pypinyin = pytest.importorskip("pypinyin")


@pytest.mark.parametrize("term,reading,tones", [
    ("牛逼", "niú bī", "2-1"),
    ("躺平", "tǎng píng", "3-2"),
    ("潜移默化", "qián yí mò huà", "2-2-4-4"),
    ("妈", "mā", "1"),
])
def test_derive_reading(term, reading, tones):
    assert lang.derive_reading(term) == (reading, tones)


def test_neutral_tone_uses_our_marker():
    reading, tones = lang.derive_reading("的")
    assert reading == "de"
    assert tones == lang.NEUTRAL


def test_polyphones_use_context():
    """The whole reason pypinyin beats a naive char->pinyin map (and why we don't
    need g2pw's BERT): 行 and 长 depend on the word."""
    assert lang.derive_reading("银行")[0] == "yín háng"
    assert lang.derive_reading("行走")[0] == "xíng zǒu"
    assert lang.derive_reading("长大")[0] == "zhǎng dà"


def test_mixed_latin_terms_dont_explode():
    """666 / 立flag / emo are real cards in the decks."""
    reading, tones = lang.derive_reading("立flag")
    assert reading == "lì flag"
    # a tone list that doesn't match the syllables would break tone colors, so we
    # decline to guess rather than emit a bad one
    assert tones == ""
    assert lang.derive_reading("emo") == ("emo", "")


def test_non_chinese_language_declines():
    assert lang.derive_reading("neko", "ja-JP") == ("", "")
    assert not lang.supports_autofill("ja-JP")
    assert lang.supports_autofill("zh-CN")


def test_autofill_fills_only_missing_fields():
    w = {"term": "牛逼", "reading": "MY OWN"}
    filled = lang.autofill(w)
    assert w["reading"] == "MY OWN"        # author's value wins
    assert w["tones"] == "2-1"             # missing one gets filled
    assert filled == ["tones"]


def test_autofill_overwrite_replaces():
    w = {"term": "牛逼", "reading": "wrong", "tones": "9-9"}
    lang.autofill(w, overwrite=True)
    assert w["reading"] == "niú bī" and w["tones"] == "2-1"


def test_autofill_drops_legacy_pinyin_field():
    w = {"term": "牛逼", "pinyin": "old"}
    lang.autofill(w, overwrite=True)
    assert "pinyin" not in w and w["reading"] == "niú bī"


def test_autofill_noop_without_term():
    assert lang.autofill({"meaning": "x"}) == []
