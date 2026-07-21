"""User settings.

Everything that used to be a module constant in pop.py lives here, backed by a
JSON file in the user data dir. Defaults are the values the app shipped with.

Access as attributes:  settings.interval_seconds
Unknown keys in the file are preserved (forward-compat), missing keys fall back
to DEFAULTS, so an old settings file keeps working after an upgrade.
"""
import json
from copy import deepcopy

from . import paths
from .logging_setup import get

log = get("settings")

SCHEMA = 1

DEFAULTS = {
    "schema": SCHEMA,

    # --- timing ---
    "interval_seconds": 25,       # how often a word pops
    "display_seconds": 22,        # how long the card stays (0 = until next)
    "first_popup_after": 2,
    "autostart": True,            # begin the cycle on launch

    # --- fast mode (⚡): denser pace, quicker pops — toggle it live ---
    "fast_mode": False,           # start in fast mode? (also the live toggle state)
    "fast_interval_seconds": 8,   # pop interval while fast
    "fast_rate": "+40%",          # word spoken at this edge-tts rate while fast
                                  # (tempo change, not pitch — tones stay intact).
                                  # Fast mode speaks only the word: no tones/meaning.

    # --- audio ---
    "play_audio": True,           # start with sound on
    "word_repeats": 3,
    "say_tones": True,            # English tone read-out after the word
    "say_meaning": True,
    "repeat_gap": 0.35,
    "silent_word_secs": 1.2,      # flash beat length when muted

    # --- spaced learning ---
    "active_set_size": 12,        # words in progress at once
    "graduate_at": 9,             # exposures before a word counts as learned
    "schedule_min": [0.25, 1, 3, 7, 15, 30, 60, 180, 720, 1440],

    # --- recall quiz ---
    "reveal_quiz": True,
    "reveal_delay": 3.0,

    # --- anti-habituation ---
    "chime_on": True,
    "chime_every_min": 3,         # random run of cards between chimes
    "chime_every_max": 8,
    "flash_prob": 0.28,           # odds a normal pop flashes fullscreen
    "flash_new_until": 3,         # words this new ALWAYS flash

    # --- annoying mode ---
    "annoying_mode": True,
    "annoy_hanzi_frac": 0.78,
    "annoy_text_alpha": 0.50,

    # --- appearance ---
    "card_width": 360,
    "card_alpha": 0.62,           # panel only; text stays solid
    "card_radius": 12,            # rounded corners (0 = square)
    "margin": 24,
    "hanzi_size": 50,
    "pinyin_size": 17,
    "halo_thickness": 2,
    "font": "Microsoft YaHei UI",

    # --- display ---
    "dpi_aware": True,            # crisp on scaled displays; off = let Windows blur us
    "monitor": 0,                 # which screen the overlay lives on (0 = primary)

    # --- content ---
    "active_deck": "",            # "" = resume last used
    "hide_swears": False,         # skip the swear category entirely
    "enabled_decks": [],          # [] = all; otherwise deck ids to study

    # --- panel / hotkeys ---
    "panel_hint_seconds": 4,
    "panel_max_deck_rows": 8,     # taller deck lists scroll instead of growing
    "quiz_length": 20,            # Test Mode: questions per test (capped at pool)
    "recall_hotkeys": True,
    "hotkeys": {
        "panel": "ctrl+alt+c",
        "mute": "ctrl+alt+m",
        "got": "ctrl+alt+j",
        "miss": "ctrl+alt+k",
        "fast": "ctrl+alt+f",
    },

    # --- tts (Phase 3 swaps the provider) ---
    "tts_provider": "edge",
    "voice": "zh-CN-YunyangNeural",
    "rate": "-15%",
    "tones_voice": "en-US-GuyNeural",
    "tones_rate": "-5%",
    "meaning_voice": "en-US-GuyNeural",
    "meaning_rate": "-8%",
}


class Settings:
    def __init__(self, data=None):
        self._data = deepcopy(DEFAULTS)
        if data:
            self._data.update(data)

    # attribute access: settings.interval_seconds
    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def as_dict(self):
        return deepcopy(self._data)

    def save(self, path=None):
        path = path or paths.settings_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except Exception:
            log.exception("could not save settings to %s", path)


def _migrate(data):
    """Bring an older settings file up to the current schema."""
    v = data.get("schema", 0)
    if v < 1:
        data["schema"] = 1        # first versioned release; nothing to move yet
    # `hotkeys` is a nested dict, so a whole-dict override from an older file
    # silently drops any hotkey added since (e.g. `fast`). Backfill the missing
    # ones from DEFAULTS so a new binding works without editing settings.json.
    hk = data.get("hotkeys")
    if isinstance(hk, dict):
        for name, default in DEFAULTS["hotkeys"].items():
            hk.setdefault(name, default)
    return data


def load(path=None):
    path = path or paths.settings_file()
    data = {}
    if path.exists():
        try:
            data = _migrate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            log.exception("settings file unreadable, using defaults: %s", path)
            data = {}
    return Settings(data)
