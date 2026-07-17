"""Win32 interop: the overlay's whole reason for working.

Every function here exists because of a specific bug. Read CLAUDE.md
"hard-won gotchas" before changing any of it, and re-run tests/test_win32.py
(which proves focus is never stolen from another process).

The invariants:
  * Our windows are WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW so they render on top but
    never take keyboard focus — a pop must not pull you out of a game.
  * The style must land BEFORE the window first maps, so prevent_focus_steal()
    deliberately avoids update_idletasks(): mapping even a moment early makes the
    window flash to the foreground once.
  * Never deiconify(). Show with ShowWindow(SW_SHOWNOACTIVATE), hide with SW_HIDE;
    Tk's own map/unmap can activate.
  * Display-only windows add WS_EX_TRANSPARENT so the cursor passes through to
    the game.
"""
import ctypes
from ctypes import windll, wintypes

_user32 = windll.user32

_user32.GetParent.restype = wintypes.HWND
_user32.GetParent.argtypes = [wintypes.HWND]
_GetWL = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
_SetWL = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
_GetWL.restype = ctypes.c_ssize_t
_GetWL.argtypes = [wintypes.HWND, ctypes.c_int]
_SetWL.restype = ctypes.c_ssize_t
_SetWL.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.UINT]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x0001, 0x0002, 0x0004
SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x0010, 0x0020
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4


def hwnd_now(win):
    """HWND without update_idletasks() — must NOT map the window yet."""
    wid = win.winfo_id()
    return _user32.GetParent(wid) or wid


def hwnd_of(win):
    win.update_idletasks()
    return hwnd_now(win)


def _set_noactivate(hwnd):
    ex = _GetWL(hwnd, GWL_EXSTYLE)
    _SetWL(hwnd, GWL_EXSTYLE,
           ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
    _user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                         | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def prevent_focus_steal(win):
    """Mark a window no-activate. Call IMMEDIATELY after creating it.

    Two traps, both of which have bitten us:

    1. Tk creates a *wrapper* top-level when the window first maps, and that
       wrapper — not `winfo_id()` — is what Windows manages for focus. Styling
       only `winfo_id()` leaves the real window activatable. So we realize the
       window here (update_idletasks) and style the wrapper too.
    2. Realizing a *visible* window maps and activates it — the flash-to-
       foreground bug. So withdraw first: a withdrawn window realizes (creating
       the wrapper we need) without ever showing or taking focus.

    Order matters: withdraw -> realize -> style. Show later with
    show_no_activate(), never deiconify().
    """
    try:
        win.withdraw()             # must be hidden before we realize it
    except Exception:
        pass
    win.update_idletasks()         # let Tk build its wrapper toplevel
    wid = win.winfo_id()
    _set_noactivate(wid)
    parent = _user32.GetParent(wid)
    if parent:
        _set_noactivate(parent)    # the handle Windows actually focuses


def make_click_through(win):
    """The window ignores the mouse entirely; clicks reach the game beneath."""
    hwnd = hwnd_of(win)
    ex = _GetWL(hwnd, GWL_EXSTYLE)
    _SetWL(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT
           | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    _user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                         | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def raise_without_focus(win):
    hwnd = hwnd_of(win)
    _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def show_no_activate(win):
    _user32.ShowWindow(hwnd_of(win), SW_SHOWNOACTIVATE)


def hide_window(win):
    _user32.ShowWindow(hwnd_of(win), SW_HIDE)


def foreground_window():
    return _user32.GetForegroundWindow()


def set_foreground(hwnd):
    if hwnd:
        _user32.SetForegroundWindow(hwnd)


def ex_style(win_or_hwnd):
    """Extended style — used by tests to assert the invariants."""
    hwnd = win_or_hwnd if isinstance(win_or_hwnd, int) else hwnd_of(win_or_hwnd)
    return _GetWL(hwnd, GWL_EXSTYLE)
