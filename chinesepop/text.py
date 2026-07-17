"""Pure text transforms: the tone read-out and the profanity filter.

No I/O, no Tk — easy to unit test.
"""
import re

_ORDINALS = {"1": "first", "2": "second", "3": "third", "4": "fourth"}


def tones_to_text(tones):
    """'3-3-·-2' -> 'third tone, third tone, neutral tone, second tone'.
    Returns '' when there are no real tones to read (loanwords, non-tonal langs)."""
    parts, has_tone = [], False
    for tok in str(tones).replace(" ", "").split("-"):
        if tok in _ORDINALS:
            parts.append(f"{_ORDINALS[tok]} tone")
            has_tone = True
        elif tok in ("·", "5"):
            parts.append("neutral tone")
    return ", ".join(parts) if has_tone else ""


# (regex, display, spoken). `display` asterisks the swear on the card; `spoken`
# swaps in a clean word so the TTS never voices it. Order matters — specific first.
_PROFANITY_RULES = [
    (r"son of a bitch", "son of a b***h", "scoundrel"),
    (r"bullshit",       "bull****",       "nonsense"),
    (r"dumbass",        "dumba**",        "dummy"),
    (r"asshole[s]?",    "a**hole",        "jerk"),
    (r"bastard[s]?",    "b*****d",        "scoundrel"),
    (r"bitch(?:es)?",   "b***h",          "jerk"),
    (r"piss off",       "p**s off",       "get lost"),
    (r"\bpiss\b",       "p**s",           "buzz off"),
    (r"f\*\*\*ing",     "f***ing",        "freaking"),
    (r"f\*\*\* off",    "f*** off",       "get lost"),
    (r"f\*\*\*",        "f***",           "eff"),
    (r"fuck\w*",        "f***",           "eff"),
    (r"sh\*t",          "sh*t",           "crud"),
    (r"\bshit\b",       "s**t",           "crud"),
    (r"\bdamn\b",       "d**n",           "darn"),
    (r"\bass\b",        "a**",            "jerk"),
    (r"\bprick\b",      "p***k",          "jerk"),
    (r"\bdick\b",       "d**k",           "jerk"),
]
_PROFANITY = [(re.compile(p, re.I), d, s) for p, d, s in _PROFANITY_RULES]


def censor_display(text):
    """Meaning as shown on the card — swears asterisked."""
    for rx, disp, _ in _PROFANITY:
        text = rx.sub(disp, text)
    return text


def censor_speech(text):
    """Meaning as SPOKEN — swears replaced so the TTS never says them."""
    for rx, _, spoken in _PROFANITY:
        text = rx.sub(spoken, text)
    return text
