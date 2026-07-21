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

from blip import decks as decks_mod
from blip import win32
from blip.app import App

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

HERE = Path(__file__).resolve().parent
u = win32._user32
u.IsWindowVisible.restype = wintypes.BOOL
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.WindowFromPoint.restype = wintypes.HWND
u.WindowFromPoint.argtypes = [wintypes.POINT]
u.GetForegroundWindow.restype = wintypes.HWND
u.SetForegroundWindow.argtypes = [wintypes.HWND]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                       ctypes.POINTER(wintypes.DWORD)]
u.GetWindowThreadProcessId.restype = wintypes.DWORD
u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
u.GetAncestor.restype = wintypes.HWND
_GA_ROOT = 2


def _root_window(hwnd):
    """The top-level window WindowFromPoint's hit belongs to. WindowFromPoint
    returns the innermost child (a Label), so compare roots, not raw handles."""
    return u.GetAncestor(hwnd, _GA_ROOT)


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
    from blip import scheduler as sched_mod
    from blip import settings as settings_mod

    tmp = tmp_path_factory.mktemp("state")
    orig = sched_mod.paths.state_file
    sched_mod.paths.state_file = lambda: tmp / "state.json"   # never the real one

    s = settings_mod.Settings()
    s.set("play_audio", False)
    s.set("autostart", False)
    s.set("panel_hint_seconds", 0)
    # Two decks, not one: the app ships four, and a single-deck panel can't
    # exercise the deck picker at all.
    deck = {"id": "t", "name": "T", "language": "zh-CN", "voice": None,
            "words": WORDS, "source": None}
    deck2 = {"id": "t2", "name": "T Two", "language": "zh-CN", "voice": None,
             "words": WORDS[:2], "source": None}
    a = App([deck, deck2], s)
    try:
        yield a
    finally:
        # Stop the audio but do NOT destroy the root. Another module creates its
        # own Tk() afterwards, and destroy-then-create is exactly the churn that
        # wedges Tcl with 'invalid command name tcl_findLibrary' (CLAUDE.md) —
        # it made the suite error ~50% of runs. Coexisting roots are fine; the
        # process is about to exit and take this one with it.
        try:
            from blip.audio import player
            player.stop()
            a.root.withdraw()
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


def test_overlay_never_calls_deiconify():
    """Gotcha #2: show with ShowWindow(SW_SHOWNOACTIVATE), never deiconify() —
    Tk's own map/unmap can activate the window.

    A *static* check, and deliberately so: mutation testing showed that nothing
    else catches this. Swapping show_no_activate() for deiconify() leaves every
    other test in this file green, because Windows refuses our process the
    foreground while another app owns it — so on a developer's desktop a broken
    overlay can't demonstrate the theft, and the behavioural test below passes
    vacuously. AST, not grep: the word appears in docstrings that explain the rule.

    Only the overlay is covered. Settings/editor/first-run are separate processes
    and are *supposed* to want focus.
    """
    import ast

    pkg = HERE.parent / "blip"
    files = [pkg / "app.py", pkg / "win32.py", *sorted((pkg / "ui").glob("*.py"))]
    offenders = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "deiconify"):
                offenders.append(f"{f.name}:{node.lineno}")
    assert not offenders, (
        f"{offenders} call deiconify(); use win32.show_no_activate() — Tk's map "
        "can activate the window and pull focus off the game")


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


def test_fast_mode_toggle_changes_pace_and_persists(app, monkeypatch):
    """⚡ Fast flips the pop interval and remembers itself, and its clip top-up
    runs off the network."""
    from blip.audio import tts
    from blip.ui import theme

    monkeypatch.setattr(tts, "generate_async", lambda *a, **k: None)   # no network
    monkeypatch.setattr(app.s, "save", lambda *a, **k: None)           # no real file
    prev_fast, prev_set = app.fast, app.s.get("fast_mode")
    try:
        app.fast = False
        assert app._interval_ms() == app.s.interval_seconds * 1000
        app.toggle_fast()
        assert app.fast is True
        assert app._interval_ms() == app.s.fast_interval_seconds * 1000
        assert app.s.get("fast_mode") is True                 # persisted
        assert app.panel.fast_btn.cget("bg") == theme.BTN_PRIMARY  # filled when on
        app.toggle_fast()
        assert app.fast is False
        assert app._interval_ms() == app.s.interval_seconds * 1000
    finally:
        app.fast = prev_fast
        app.s.set("fast_mode", prev_set)
        app.panel.set_fast(prev_fast)


def test_opening_test_mode_pauses_the_overlay(app, monkeypatch):
    """Clicking Test Mode should pause the pops and silence a word being read,
    so the user doesn't have to pause manually first."""
    import blip.quiz_ui as quiz_ui
    from blip.app import PAUSED, RUNNING
    from blip.audio import player

    launched = {}
    monkeypatch.setattr(quiz_ui, "open_quiz",
                        lambda deck_id=None: launched.__setitem__("deck", deck_id))
    prev = app.state
    try:
        app.play()
        pump(app, 0.2)
        assert app.state == RUNNING
        tok = player._play_token
        app.open_quiz()
        pump(app, 0.1)
        assert app.state == PAUSED, "Test Mode didn't pause the overlay"
        assert player._play_token > tok, "in-flight audio wasn't cancelled"
        assert launched.get("deck") is not None, "the quiz launcher wasn't called"
        assert not u.IsWindowVisible(win32.hwnd_of(app.card.text))
    finally:
        app.stop()
        app.state = prev


def test_tooltips_do_not_steal_focus(app):
    """Tooltips are new windows that appear over the game — every window this app
    creates has to obey the no-activate rule, not just the obvious three."""
    from blip.ui.panel import _Tooltip
    tip = _Tooltip(app.panel.play_btn, "hello", app.panel.f)
    tip._show()
    pump(app, 0.2)
    try:
        assert tip.tip is not None
        assert win32.ex_style(tip.tip) & win32.WS_EX_NOACTIVATE
    finally:
        tip._hide()
    assert tip.tip is None


def test_panel_tooltip_renders_above_the_panel(app):
    """The tooltip and the panel are both WS_EX_TOPMOST; showing the tooltip
    doesn't raise it within that band, so it drew *behind* the panel — invisible.
    _show() re-raises it. Prove it actually wins the z-fight over the panel."""
    from blip.ui.panel import _Tooltip
    app.panel.show(app.rect)
    pump(app, 0.2)
    tip = _Tooltip(app.panel.play_btn, "Start / pause the cards", app.panel.f)
    tip._show()
    pump(app, 0.3)
    try:
        tip.tip.update_idletasks()
        # a point at the tooltip's centre, which overlaps the panel body below
        # the (mid-panel) Play button
        tx = tip.tip.winfo_rootx() + tip.tip.winfo_width() // 2
        ty = tip.tip.winfo_rooty() + tip.tip.winfo_height() // 2
        hit = _root_window(u.WindowFromPoint(wintypes.POINT(tx, ty)))
        assert hit != _root_window(win32.hwnd_of(app.root)), \
            "the tooltip is hidden behind the panel"
        assert hit == _root_window(win32.hwnd_of(tip.tip)), \
            "something else is over the tooltip"
    finally:
        tip._hide()
        app.panel.hide()


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


def _visible_deck_rows(panel):
    return [i for i, r in enumerate(panel.deck_rows) if r["row"].winfo_ismapped()]


def test_deck_list_is_collapsed_until_asked_for(app):
    """The panel is summoned for ~2 seconds; the deck list is the only part that
    grows without bound. Collapsed it costs one row."""
    p = app.panel
    p.show(app.rect)
    pump(app, 0.2)
    try:
        assert _visible_deck_rows(p) == [p.deck_index]
        assert p.deck_rows[p.deck_index]["chev"].cget("text").startswith("▾")

        collapsed_h = app.root.winfo_reqheight()
        p._deck_click(p.deck_index)          # collapsed: any click means "open"
        pump(app, 0.2)
        assert _visible_deck_rows(p) == list(range(len(p.deck_rows)))
        assert p.deck_rows[p.deck_index]["chev"].cget("text").startswith("▴")
        assert app.root.winfo_reqheight() > collapsed_h

        p._deck_click(1)                     # expanded: a click is a choice
        pump(app, 0.2)
        assert app.deck_index == 1, "click didn't switch deck"
        assert not p.expanded, "picking a deck should collapse the list"
        assert app.root.winfo_reqheight() == collapsed_h
    finally:
        p.hide()
        app.select_deck(0)


def test_expanded_deck_list_cannot_outgrow_the_screen(app):
    """A 40-deck import must not push the buttons off the bottom. The list is
    capped at panel_max_deck_rows and scrolls past that."""
    p = app.panel
    real_rows, real_counts = p.deck_rows, p._counts
    p.deck_rows = real_rows * 15                  # pretend: 45 decks
    p._counts = real_counts * 15
    try:
        p._set_expanded(True)
        pump(app, 0.2)
        cap = int(app.s.panel_max_deck_rows)
        row_h = real_rows[0]["row"].winfo_reqheight() + 2
        assert p.deck_view.winfo_reqheight() <= cap * row_h + 2, "viewport not capped"
        _mx, _my, _mw, mh = app.rect
        assert app.root.winfo_reqheight() <= mh, "panel taller than the monitor"
    finally:
        p.deck_rows, p._counts = real_rows, real_counts
        p._set_expanded(False)
        p.hide()


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
    """Pops must not take the foreground from another process's window.

    KNOW WHAT THIS IS WORTH. Mutation testing (strip the NOACTIVATE style, swap
    show_no_activate() for deiconify()) says this test catches NONE of it on a
    desktop where another app owns the foreground: Windows won't grant our
    process the foreground either, so a thoroughly broken overlay still can't
    steal it here, and this passes. It has teeth only when the helper actually
    wins the foreground (an idle desktop, CI).

    What genuinely guards the invariant is test_windows_are_no_activate (the
    style, which mutation testing does catch) and test_overlay_never_calls_
    deiconify. This stays because it's the only end-to-end, cross-process check
    of the real thing — but don't mistake it for the safety net.
    """
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

        # Best effort: tab into the "game". Windows only grants SetForegroundWindow
        # to the process that already owns the foreground, so this fails whenever
        # the developer is typing in their editor — it is NOT a precondition.
        deadline = time.time() + 5
        while time.time() < deadline and u.GetForegroundWindow() != game:
            u.SetForegroundWindow(game)    # user tabs into their game
            pump(app, 0.25)

        before = u.GetForegroundWindow()
        _assert_not_ours(before, "we owned the foreground before a single pop fired")

        app.annoying = True
        for _ in range(3):
            app.next_now()
            pump(app, 0.8)

        # THE guarantee, and it doesn't need the helper to have won the
        # foreground: whoever is in front — the helper, or the editor the
        # developer is typing in — must still be in front, and it must not be
        # us. Demanding "the helper keeps focus" made this skip on any desktop
        # that wouldn't hand over focus, i.e. always, silently.
        after = u.GetForegroundWindow()
        _assert_not_ours(after, "a pop stole focus from the game!")
        if after == game:
            assert before == game        # the full scenario did run
    finally:
        helper.terminate()


def _assert_not_ours(hwnd, msg):
    """Judge OUR behaviour, not the machine's.

    'the foreground isn't the game' lumps together two unrelated events: we
    stole focus (the bug this test exists for) and something else did (a
    notification, the console). Asking Windows *who owns* the foreground window
    separates them, so a failure here always means we're guilty.
    """
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    assert pid.value != os.getpid(), msg


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
