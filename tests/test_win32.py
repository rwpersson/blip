"""The invariants that make this app usable while gaming.

These are NOT unit tests of pure logic — they drive real windows and assert on
real Win32 state, because that's the only thing that actually proves:

  * a pop never steals focus from the game
  * the cursor always passes through the card to the game

If these break, the app is unusable in its one intended context. See CLAUDE.md.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

import pytest

from chinesepop import decks as decks_mod
from chinesepop import win32
from chinesepop.app import App

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

HERE = Path(__file__).resolve().parent
u = win32._user32
u.IsWindowVisible.restype = wintypes.BOOL
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.WindowFromPoint.restype = wintypes.HWND
u.WindowFromPoint.argtypes = [wintypes.POINT]
u.GetForegroundWindow.restype = wintypes.HWND
u.SetForegroundWindow.argtypes = [wintypes.HWND]


WORDS = [
    {"id": "01", "hanzi": "牛逼", "pinyin": "niú bī", "tones": "2-1",
     "cat": "slang", "meaning": "awesome", "note": "n"},
    {"id": "02", "hanzi": "加油", "pinyin": "jiā yóu", "tones": "1-2",
     "cat": "common", "meaning": "go for it", "note": "n"},
    {"id": "03", "hanzi": "躺平", "pinyin": "tǎng píng", "tones": "3-2",
     "cat": "slang", "meaning": "lie flat", "note": "n"},
]


@pytest.fixture(scope="module")
def _app(tmp_path_factory):
    """ONE App for the whole module.

    Tk does not survive repeated Tk() create/destroy cycles in a single process
    ("invalid command name tcl_findLibrary"), so a per-test App makes the suite
    flaky. The real app only ever builds one root, so a shared one is also the
    honest thing to test.
    """
    from chinesepop import scheduler as sched_mod
    from chinesepop import settings as settings_mod

    tmp = tmp_path_factory.mktemp("state")
    orig = sched_mod.paths.state_file
    sched_mod.paths.state_file = lambda: tmp / "state.json"   # never the real one

    s = settings_mod.Settings()
    s.set("play_audio", False)
    s.set("autostart", False)
    s.set("panel_hint_seconds", 0)
    deck = {"id": "t", "name": "T", "language": "zh-CN", "voice": None,
            "words": WORDS, "source": None}
    a = App([deck], s)
    try:
        yield a
    finally:
        try:
            a.quit()
        except Exception:
            pass
        sched_mod.paths.state_file = orig


@pytest.fixture
def app(_app):
    """Per-test reset of the shared App's mutable state."""
    _app.annoying = True
    _app.current = None
    _app.hide_card()
    _app.root.update()
    return _app


@pytest.fixture
def words():
    return WORDS


def pump(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.02)


def test_windows_are_no_activate(app):
    for win in (app.root, app.card.back, app.card.text, app.flash.win):
        assert win32.ex_style(win) & win32.WS_EX_NOACTIVATE, f"{win} can take focus"


def test_dpi_scale_is_sane(app):
    """Asserted here because this module owns the process's only Tk root."""
    scale = win32.scale_for_window(app.root)
    assert 0.5 <= scale <= 4.0
    assert win32.dpi_for_window(app.root) >= 96


def test_card_panel_is_rounded_but_text_layer_is_not(app, words):
    """Rounded corners come from a window REGION (DWM rounding doesn't apply to
    layered override-redirect windows). Only the panel needs clipping — the text
    layer's background is colour-keyed away, so it has no corners to show."""
    u.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN]
    probe = win32._gdi32.CreateRectRgn(0, 0, 1, 1)
    app.annoying = False
    app._show(words[0])
    pump(app, 0.3)
    assert u.GetWindowRgn(win32.hwnd_of(app.card.back), probe) != 0
    assert u.GetWindowRgn(win32.hwnd_of(app.card.text), probe) == 0


def test_rounding_survives_a_resize(app, words):
    """The region is in pixels, so it must be re-applied every place() — the card
    resizes with its content."""
    u.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN]
    probe = win32._gdi32.CreateRectRgn(0, 0, 1, 1)
    app.annoying = False
    for w in words[:2]:
        app._show(w)
        pump(app, 0.3)
        assert u.GetWindowRgn(win32.hwnd_of(app.card.back), probe) != 0


def test_zero_radius_means_square(app):
    win32.unround_window(app.card.back)
    u.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN]
    probe = win32._gdi32.CreateRectRgn(0, 0, 1, 1)
    assert u.GetWindowRgn(win32.hwnd_of(app.card.back), probe) == 0


def test_card_is_placed_on_the_target_monitor(app, words):
    """winfo_screenwidth() is the primary screen only; the card must land on the
    monitor the user picked."""
    mx, my, mw, _mh = app.rect
    app.annoying = False
    app._show(words[0])
    pump(app, 0.4)
    app.card.text.update_idletasks()
    x, w = app.card.text.winfo_x(), app.card.text.winfo_reqwidth()
    assert x >= mx and x + w <= mx + mw, "card spilled off the target monitor"
    assert abs(x - (mx + (mw - w) // 2)) <= 1, "card isn't centered on it"


def test_tooltips_do_not_steal_focus(app):
    """Tooltips are new windows that appear over the game — every window this app
    creates has to obey the no-activate rule, not just the obvious three."""
    from chinesepop.ui.panel import _Tooltip
    tip = _Tooltip(app.panel.play_btn, "hello", app.panel.f)
    tip._show()
    pump(app, 0.2)
    try:
        assert tip.tip is not None
        assert win32.ex_style(tip.tip) & win32.WS_EX_NOACTIVATE
    finally:
        tip._hide()
    assert tip.tip is None


def test_every_panel_button_has_a_word(app):
    """A lone glyph can't tell anyone what it does — '📝' meaning 'make your own
    flashcards' was real user feedback."""
    labelled = [b for b in _all_labels(app.root)
                if b.cget("cursor") == "hand2" and b.cget("text")]
    wordy = [b.cget("text") for b in labelled
             if any(ch.isalpha() for ch in b.cget("text"))]
    assert any("card" in t.lower() for t in wordy), "no button mentions cards"
    assert any("setting" in t.lower() for t in wordy)


def _all_labels(widget, out=None):
    out = [] if out is None else out
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            out.append(child)
        _all_labels(child, out)
    return out


def test_card_and_flash_are_click_through_panel_is_not(app):
    for win in (app.card.back, app.card.text, app.flash.win):
        assert win32.ex_style(win) & win32.WS_EX_TRANSPARENT
    # the panel must stay clickable or the buttons do nothing
    assert not (win32.ex_style(app.root) & win32.WS_EX_TRANSPARENT)


def test_click_at_card_center_passes_through(app, words):
    app._show(words[0])
    pump(app, 0.5)
    card_hwnd = win32.hwnd_of(app.card.text)
    back_hwnd = win32.hwnd_of(app.card.back)
    app.card.text.update_idletasks()
    cx = app.card.text.winfo_x() + app.card.text.winfo_width() // 2
    cy = app.card.text.winfo_y() + app.card.text.winfo_height() // 2
    hit = u.WindowFromPoint(wintypes.POINT(cx, cy))
    assert hit not in (card_hwnd, back_hwnd), "the card swallowed a click"


def test_pops_never_steal_focus_from_another_process(app, words, tmp_path):
    """The headline guarantee. A window in another process must keep focus while
    we fire pops at it."""
    # A per-run file: the helper outlives a failed run by up to 25s, and a shared
    # fixed path let one run read the previous run's stale HWND.
    hwnd_file = str(tmp_path / "helper_hwnd.txt")
    helper = subprocess.Popen([sys.executable, str(HERE / "helper_window.py"),
                               hwnd_file])
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            if os.path.exists(hwnd_file) and open(hwnd_file).read().strip():
                break
            time.sleep(0.05)
        game = int(open(hwnd_file).read().strip())
        time.sleep(0.5)

        # Give the helper focus, retrying: a single SetForegroundWindow can lose
        # a race on a busy machine, and a flaky *setup* would mean the real
        # assertion below never runs — which is worse than a failure.
        deadline = time.time() + 5
        while time.time() < deadline and u.GetForegroundWindow() != game:
            u.SetForegroundWindow(game)    # user tabs into their game
            pump(app, 0.25)
        assert u.GetForegroundWindow() == game, "test setup: helper never got focus"

        app.annoying = True
        for _ in range(3):
            app.next_now()
            pump(app, 0.8)

        assert u.GetForegroundWindow() == game, "a pop stole focus from the game!"
    finally:
        helper.terminate()


def test_card_hides_and_shows(app, words):
    # annoying mode off, or a brand-new word always takes the flash path and the
    # card deliberately stays hidden until the English read-out.
    app.annoying = False
    app._show(words[0])
    pump(app, 0.4)
    assert u.IsWindowVisible(win32.hwnd_of(app.card.text))
    app.hide_card()
    pump(app, 0.2)
    assert not u.IsWindowVisible(win32.hwnd_of(app.card.text))
    assert not u.IsWindowVisible(win32.hwnd_of(app.flash.win))


def test_new_word_flashes_and_keeps_card_hidden(app, words):
    """Weak/new words always flash; the card waits for the English read-out."""
    app.annoying = True
    app._show(words[0])
    pump(app, 0.4)
    assert app._flashing
    assert not u.IsWindowVisible(win32.hwnd_of(app.card.text))
