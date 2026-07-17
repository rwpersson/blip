import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chinesepop import settings as settings_mod  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    """Default settings, never touching the user's real files."""
    s = settings_mod.Settings()
    s.set("play_audio", False)
    s.set("autostart", False)
    s.set("panel_hint_seconds", 0)
    return s


@pytest.fixture
def state_path(tmp_path):
    """A throwaway state file — the real state.json holds actual progress."""
    return tmp_path / "state.json"


@pytest.fixture
def words():
    return [
        {"id": "01", "hanzi": "牛逼", "pinyin": "niú bī", "tones": "2-1",
         "cat": "slang", "meaning": "awesome", "note": "n"},
        {"id": "02", "hanzi": "加油", "pinyin": "jiā yóu", "tones": "1-2",
         "cat": "common", "meaning": "go for it", "note": "n"},
        {"id": "03", "hanzi": "躺平", "pinyin": "tǎng píng", "tones": "3-2",
         "cat": "slang", "meaning": "lie flat", "note": "n"},
    ]
