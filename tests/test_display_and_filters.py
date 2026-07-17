"""DPI, monitors, content filters, hotkey validation — the Phase 4 engine bits."""
import sys

import pytest

from chinesepop import decks as d
from chinesepop import hotkeys as hk
from chinesepop import settings as settings_mod
from chinesepop import win32

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


# ------------------------------ monitors ------------------------------------
def test_monitors_are_enumerated():
    mons = win32.monitors()
    assert mons, "there is always at least one screen"
    for m in mons:
        assert m["width"] > 0 and m["height"] > 0
    assert sum(1 for m in mons if m["primary"]) >= 1
    assert mons[0]["primary"], "the primary monitor sorts first"


def test_monitor_rect_falls_back_when_index_is_gone():
    """A monitor can be unplugged between runs — don't strand the overlay."""
    assert win32.monitor_rect(99) == win32.monitor_rect(0)
    assert win32.monitor_rect(-5) == win32.monitor_rect(0)


def test_monitor_rect_shape():
    x, y, w, h = win32.monitor_rect(0)
    assert w > 0 and h > 0


# NOTE: no Tk in this module. Only ONE Tk root may exist per process — a second
# one after the first is destroyed dies with "invalid command name
# tcl_findLibrary" and takes test_win32 down with it. DPI/scale is asserted there,
# against the shared root.


# ------------------------------ filters -------------------------------------
@pytest.fixture
def decks_fixture():
    return [
        {"id": "a", "name": "A", "language": "zh-CN", "voice": None, "source": None,
         "words": [{"id": "1", "term": "牛逼", "meaning": "m", "cat": "slang"},
                   {"id": "2", "term": "傻逼", "meaning": "m", "cat": "swear"}]},
        {"id": "b", "name": "B", "language": "zh-CN", "voice": None, "source": None,
         "words": [{"id": "1", "term": "加油", "meaning": "m", "cat": "common"}]},
    ]


def test_hide_swears_drops_only_that_category(decks_fixture, settings):
    settings.set("hide_swears", True)
    out = d.apply_filters(decks_fixture, settings)
    terms = [d.word_term(w) for deck in out for w in deck["words"]]
    assert "傻逼" not in terms
    assert "牛逼" in terms and "加油" in terms


def test_filters_never_mutate_the_loaded_decks(decks_fixture, settings):
    """The editor shows the same deck objects — a filter must not delete cards
    from under it."""
    settings.set("hide_swears", True)
    d.apply_filters(decks_fixture, settings)
    assert len(decks_fixture[0]["words"]) == 2


def test_enabled_decks_narrows_rotation(decks_fixture, settings):
    settings.set("enabled_decks", ["b"])
    out = d.apply_filters(decks_fixture, settings)
    assert [x["id"] for x in out] == ["b"]


def test_empty_enabled_means_all(decks_fixture, settings):
    settings.set("enabled_decks", [])
    assert len(d.apply_filters(decks_fixture, settings)) == 2


def test_a_deck_emptied_by_filters_is_dropped(settings):
    """An all-swears deck with swears hidden would otherwise stall the scheduler."""
    decks = [{"id": "s", "name": "S", "language": "zh-CN", "voice": None,
              "source": None,
              "words": [{"id": "1", "term": "傻逼", "meaning": "m", "cat": "swear"}]}]
    settings.set("hide_swears", True)
    assert d.apply_filters(decks, settings) == []


# ------------------------------ hotkeys -------------------------------------
@pytest.mark.parametrize("spec,mods_vk", [
    ("ctrl+alt+c", (hk.MOD_CONTROL | hk.MOD_ALT, ord("C"))),
    ("ctrl+shift+m", (hk.MOD_CONTROL | hk.MOD_SHIFT, ord("M"))),
    ("alt+f4", (hk.MOD_ALT, 0x73)),
])
def test_parse_hotkeys(spec, mods_vk):
    assert hk.parse(spec) == mods_vk


@pytest.mark.parametrize("bad", ["", "ctrl+", "meta+x", "ctrl+alt+notakey"])
def test_parse_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        hk.parse(bad)


def test_is_available_probes_for_real():
    assert hk.is_available("ctrl+alt+shift+f24") in (True, False)   # no crash
    assert hk.is_available("not a hotkey") is False


def test_conflicts_finds_duplicate_bindings():
    s = settings_mod.Settings()
    s.set("hotkeys", {"panel": "ctrl+alt+c", "mute": "ctrl+alt+c",
                      "got": "ctrl+alt+j", "miss": "ctrl+alt+k"})
    dupes = hk.conflicts(s)
    assert "ctrl+alt+c" in dupes
    assert set(dupes["ctrl+alt+c"]) == {"panel", "mute"}


def test_no_conflicts_by_default():
    assert hk.conflicts(settings_mod.Settings()) == {}


def test_build_skips_a_broken_binding():
    s = settings_mod.Settings()
    s.set("hotkeys", {"panel": "ctrl+alt+c", "mute": "gibberish",
                      "got": "ctrl+alt+j", "miss": "ctrl+alt+k"})
    ids = [hid for hid, _m, _v in hk.build(s)]
    assert hk.PANEL in ids and hk.MUTE not in ids     # bad one dropped, rest live
