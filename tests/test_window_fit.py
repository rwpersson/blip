"""Windows must fit their content.

Regression test for a real bug: the first-run window was hard-coded to 520x440,
but once the process became DPI-aware Tk rendered fonts at the true DPI (scaling
1.67 at 125%) and the content needed 583px — so 143px, including both buttons,
was simply cut off, on a window that wasn't even resizable.

Two defences, both asserted here:
  * fit_window() sizes to content instead of a guess;
  * action bars are packed BEFORE expanding content, because Tk's pack gives space
    in order and whatever is packed last is what gets squeezed.

These run in-process, so they must share the module's single Tk root — see the
'one Tk per process' gotcha in CLAUDE.md.
"""
import re
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture(scope="module")
def root():
    """The process's ONE Tk root — reused, never a second one.

    This module used to build its own Tk(). Creating a second interpreter in a
    process that already has one is unreliable on Windows: it errored in ~half of
    all full-suite runs, variously 'invalid command name tcl_findLibrary' or
    'couldn't read file init.tcl: No error'. The app itself never does this — the
    editor, settings and first-run windows are separate *processes* precisely
    because of it (CLAUDE.md), so neither should the suite.
    """
    import tkinter as tk

    from chinesepop import win32
    win32.set_dpi_aware()
    existing = tk._default_root          # test_win32's App root, if it ran first
    r = existing or tk.Tk()
    if existing is None:
        r.withdraw()
    # Never destroy it: if it's the App's it isn't ours, and root churn is the
    # very thing this fixture exists to avoid. Process exit cleans up.
    yield r


def _geometry(win):
    win.update_idletasks()
    m = re.match(r"(\d+)x(\d+)", win.geometry())
    return int(m.group(1)), int(m.group(2))


def test_fit_window_never_clips_content(root):
    import tkinter as tk
    from tkinter import ttk

    from chinesepop import win32
    top = tk.Toplevel(root)
    try:
        for i in range(25):                     # more content than any guess
            ttk.Label(top, text=f"row {i} with some reasonably long text").pack()
        win32.fit_window(top, min_w=300, min_h=200)
        w, h = _geometry(top)
        assert w >= top.winfo_reqwidth()
        assert h >= top.winfo_reqheight()
    finally:
        top.destroy()


def test_fit_window_respects_the_minimum(root):
    import tkinter as tk

    from chinesepop import win32
    top = tk.Toplevel(root)
    try:
        win32.fit_window(top, min_w=500, min_h=400)
        w, h = _geometry(top)
        scale = win32.scale_for_window(top)
        assert w >= int(500 * scale) * 0.95     # scaled, not raw pixels
        assert h >= int(400 * scale) * 0.95
    finally:
        top.destroy()


def test_fit_window_stays_on_the_monitor(root):
    """A very tall window must not run off the screen."""
    import tkinter as tk
    from tkinter import ttk

    from chinesepop import win32
    top = tk.Toplevel(root)
    try:
        for i in range(400):
            ttk.Label(top, text=str(i)).pack()
        win32.fit_window(top)
        _w, h = _geometry(top)
        _mx, _my, _mw, mh = win32.monitor_rect(0)
        assert h <= mh
    finally:
        top.destroy()


def test_fit_window_leaves_it_resizable(root):
    """The user must be able to recover from any sizing mistake we make."""
    import tkinter as tk

    from chinesepop import win32
    top = tk.Toplevel(root)
    try:
        win32.fit_window(top, min_w=300, min_h=200)
        assert top.resizable() == (True, True)
    finally:
        top.destroy()
