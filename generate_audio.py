"""
Pre-generate spoken-audio MP3s for every word in every deck (decks/*.json) using
edge-tts (Microsoft's free neural TTS). Files are cached in ./audio/<id>.mp3,
keyed by the word's globally-unique id.

Run once (needs internet):    python generate_audio.py
Re-generate everything:       python generate_audio.py --force

pop.py also calls ensure_audio() on startup to fill in anything missing, so
adding words to a deck + launching the app is enough.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

# Windows consoles default to cp1252 and crash when printing Chinese; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Clear, standard male Mandarin (news-anchor articulation) — the tones come
# through cleanly. Slowed a bit so each tone is easy to hear.
VOICE = "zh-CN-YunyangNeural"
# Other male options: zh-CN-YunxiNeural (lively), zh-CN-YunjianNeural (energetic),
# zh-CN-YunfengNeural, zh-CN-YunhaoNeural. Female: zh-CN-XiaoxiaoNeural.

RATE = "-15%"   # slower than native so each tone is easy to catch.

# The tone read-out and the meaning are spoken in English (male, to match).
TONES_VOICE = "en-US-GuyNeural"
TONES_RATE = "-5%"
MEANING_VOICE = "en-US-GuyNeural"
MEANING_RATE = "-8%"

ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "audio"
DECKS_DIR = ROOT / "decks"

_ORDINALS = {"1": "first", "2": "second", "3": "third", "4": "fourth"}

# Profanity filter for the ENGLISH meaning. Each row: (regex, display, spoken).
# `display` is what the card shows (asterisked); `spoken` is a clean word so the
# TTS never actually pronounces the swear. Order matters (specific first).
_PROFANITY = [
    (r"son of a bitch", "son of a b***h", "scoundrel"),
    (r"bullshit",       "bull****",       "nonsense"),
    (r"dumbass",        "dumba**",        "dummy"),
    (r"asshole[s]?",    "a**hole",        "jerk"),
    (r"bastard[s]?",    "b*****d",         "scoundrel"),
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
_PROFANITY = [(re.compile(p, re.I), d, s) for p, d, s in _PROFANITY]


def censor_display(text):
    """Meaning as shown on the card — swears asterisked."""
    for rx, disp, _ in _PROFANITY:
        text = rx.sub(disp, text)
    return text


def censor_speech(text):
    """Meaning as SPOKEN — swears replaced with clean words so TTS never says them."""
    for rx, _, spoken in _PROFANITY:
        text = rx.sub(spoken, text)
    return text


def load_words():
    """Every word across every deck (audio is keyed by the global word id)."""
    words = []
    for f in sorted(DECKS_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        words.extend(data.get("words", data if isinstance(data, list) else []))
    return words


def _text_for(word):
    # Use an explicit 'say' field if given (e.g. for entries containing letters
    # or numbers), otherwise speak the characters directly.
    return word.get("say") or word["hanzi"]


def tones_to_text(tones):
    """'3-3-·-2' -> 'third tone, third tone, neutral tone, second tone'.
    Returns '' when there are no real tones to read (e.g. loanwords)."""
    parts, has_tone = [], False
    for tok in str(tones).replace(" ", "").split("-"):
        if tok in _ORDINALS:
            parts.append(f"{_ORDINALS[tok]} tone")
            has_tone = True
        elif tok in ("·", "5"):
            parts.append("neutral tone")
    return ", ".join(parts) if has_tone else ""


def _clips_for(word):
    """Return (text, out_path, voice, rate) for each audio clip of a word:
    the spoken word, the English tone read-out, and the English meaning."""
    clips = [(_text_for(word), AUDIO_DIR / f"{word['id']}.mp3", VOICE, RATE)]
    tones_text = tones_to_text(word.get("tones", ""))
    if tones_text:
        clips.append((tones_text, AUDIO_DIR / f"{word['id']}_tones.mp3",
                      TONES_VOICE, TONES_RATE))
    meaning = censor_speech(str(word.get("meaning", ""))).replace(";", ",").strip()
    if meaning:
        clips.append((meaning, AUDIO_DIR / f"{word['id']}_meaning.mp3",
                      MEANING_VOICE, MEANING_RATE))
    return clips


async def _generate_one(text, out_path, voice, rate):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(str(out_path))


async def _generate_missing_async(words, force=False):
    AUDIO_DIR.mkdir(exist_ok=True)
    todo = []
    for w in words:
        for text, out, voice, rate in _clips_for(w):
            if force or not out.exists() or out.stat().st_size == 0:
                todo.append((w, text, out, voice, rate))

    if not todo:
        return 0, 0

    ok = 0
    for i, (w, text, out, voice, rate) in enumerate(todo, 1):
        try:
            await _generate_one(text, out, voice, rate)
            ok += 1
            print(f"  [{i}/{len(todo)}] {w['hanzi']:<8} -> {out.name}")
        except Exception as e:  # network hiccup, etc. — keep going.
            print(f"  [{i}/{len(todo)}] ! failed {w['hanzi']}: {e}")
    return ok, len(todo)


def ensure_audio(words=None, force=False, quiet=False):
    """Generate any missing audio. Returns (generated_ok, attempted).

    Safe to call at startup: if edge-tts or the network is unavailable it just
    reports the failure and returns, so the app can still run (silently) .
    """
    if words is None:
        words = load_words()
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        if not quiet:
            print("edge-tts not installed; run:  pip install edge-tts")
        return 0, 0
    try:
        return asyncio.run(_generate_missing_async(words, force=force))
    except Exception as e:
        if not quiet:
            print(f"audio generation error: {e}")
        return 0, 0


if __name__ == "__main__":
    force = "--force" in sys.argv
    print(f"Generating audio (voice={VOICE}, rate={RATE}) ...")
    ok, total = ensure_audio(force=force)
    if total == 0:
        print("All audio already present. Nothing to do.")
    else:
        print(f"Done: {ok}/{total} generated. Files in {AUDIO_DIR}")
