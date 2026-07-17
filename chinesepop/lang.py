"""Language helpers — the only place that knows a language's specifics.

Right now that means Chinese: deriving a reading (pinyin) and tone pattern from
the characters, so authoring a card is "type 你好, get nǐ hǎo + 3-3" instead of
hand-typing diacritics.

Deliberately isolated: decks declare their own `language`, so adding Japanese later
means adding a branch here, not touching the app.

Note on trust: auto-fill is a *suggestion*. pypinyin is very good at polyphones
(银行 yín háng, not xíng) because it uses a phrase dictionary, but it can still
disagree with a careful reading — e.g. it neutralises 电子 to "diàn zi" where the
dictionary says "diàn zǐ". Authors must always be able to override it.
"""
from .logging_setup import get

log = get("lang")

NEUTRAL = "·"


def supports_autofill(language):
    return bool(language) and language.lower().startswith("zh")


def _tone_of(tone3_syllable):
    """'niu2' -> '2';  'de5' -> '·';  'flag' -> None (not a Chinese syllable)."""
    if not tone3_syllable:
        return None
    last = tone3_syllable[-1]
    if last in "1234":
        return last
    if last == "5":
        return NEUTRAL
    return None


def derive_reading(term, language="zh-CN"):
    """(reading, tones) for a term, e.g. ('niú bī', '2-1').

    Returns ('', '') when we can't help (non-Chinese deck, or pypinyin missing).
    Non-Chinese fragments pass through: 立flag -> ('lì flag', '4').
    """
    if not term or not supports_autofill(language):
        return "", ""
    try:
        from pypinyin import Style, pinyin
    except ImportError:
        log.warning("pypinyin not installed — reading auto-fill unavailable")
        return "", ""

    try:
        marked = [s[0] for s in pinyin(term, style=Style.TONE)]
        numbered = [s[0] for s in pinyin(term, style=Style.TONE3,
                                         neutral_tone_with_five=True)]
    except Exception:
        log.exception("pypinyin failed for %r", term)
        return "", ""

    reading = " ".join(marked)
    tones = [t for t in (_tone_of(s) for s in numbered) if t is not None]
    # Only claim a tone pattern when it lines up with the reading, or the card
    # would fail validation and lose its tone colors anyway.
    if len(tones) != len(marked):
        return reading, ""
    return reading, "-".join(tones)


def autofill(word, language="zh-CN", overwrite=False):
    """Fill in a word's missing reading/tones in place. Returns the fields set."""
    from . import decks as decks_mod

    filled = []
    term = decks_mod.word_term(word)
    if not term:
        return filled
    has_reading = bool(decks_mod.word_reading(word))
    has_tones = bool(decks_mod.word_tones(word))
    if has_reading and has_tones and not overwrite:
        return filled

    reading, tones = derive_reading(term, language)
    if reading and (overwrite or not has_reading):
        word["reading"] = reading
        word.pop("pinyin", None)          # don't leave a stale legacy field
        filled.append("reading")
    if tones and (overwrite or not has_tones):
        word["tones"] = tones
        filled.append("tones")
    return filled
