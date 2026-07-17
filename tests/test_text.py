"""Tone read-out + the profanity filter (pure functions, no Tk)."""
import pytest

from chinesepop.text import censor_display, censor_speech, tones_to_text


@pytest.mark.parametrize("tones,expected", [
    ("2-1", "second tone, first tone"),
    ("4", "fourth tone"),
    ("3-3-·-2", "third tone, third tone, neutral tone, second tone"),
    ("4-·", "fourth tone, neutral tone"),
    ("—", ""),          # loanwords have no tones -> no clip at all
    ("", ""),
])
def test_tones_to_text(tones, expected):
    assert tones_to_text(tones) == expected


@pytest.mark.parametrize("raw,display,spoken", [
    ("bastard; son of a bitch", "b*****d; son of a b***h", "scoundrel; scoundrel"),
    ("utter bullshit", "utter bull****", "utter nonsense"),
    ("get lost!; piss off!", "get lost!; p**s off!", "get lost!; get lost!"),
    ("f***! (strong)", "f***! (strong)", "eff! (strong)"),
    ("damn it", "d**n it", "darn it"),
])
def test_censor(raw, display, spoken):
    assert censor_display(raw) == display
    assert censor_speech(raw) == spoken


def test_censor_leaves_clean_text_alone():
    clean = "to ponder; mull over"
    assert censor_display(clean) == clean
    assert censor_speech(clean) == clean


def test_spoken_never_contains_the_swear():
    """The whole point: TTS must not voice profanity."""
    for raw in ["bastard", "son of a bitch", "bullshit", "piss off", "damn"]:
        spoken = censor_speech(raw).lower()
        assert not any(bad in spoken for bad in
                       ("bastard", "bitch", "bullshit", "piss", "damn"))
