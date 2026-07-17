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


# ------------------------------- DPI ---------------------------------------
# Without this the process is DPI-*unaware*: Windows renders us at 96 DPI and
# bitmap-stretches the result, so on any scaled display (125%/150%, i.e. most
# laptops and 4K monitors) the card is visibly blurry and lands in the wrong
# place. Declaring per-monitor awareness fixes both — but then nothing is scaled
# for us any more, so the caller MUST scale fonts and pixel dimensions by
# scale_for_window(). Call before any window exists.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_BASE_DPI = 96.0


def set_dpi_aware():
    """True if we got per-monitor DPI awareness."""
    try:
        fn = _user32.SetProcessDpiAwarenessContext
        fn.restype = wintypes.BOOL
        fn.argtypes = [ctypes.c_void_p]
        if fn(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
            return True
    except (AttributeError, OSError):
        pass                      # pre-1703 Windows
    try:                          # older API: system-wide awareness
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PROCESS_PER_MONITOR_DPI_AWARE
        return True
    except (AttributeError, OSError):
        pass
    try:
        return bool(_user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def dpi_for_window(win):
    try:
        fn = _user32.GetDpiForWindow
        fn.restype = wintypes.UINT
        fn.argtypes = [wintypes.HWND]
        dpi = fn(hwnd_of(win))
        if dpi:
            return float(dpi)
    except (AttributeError, OSError):
        pass
    return _BASE_DPI


def scale_for_window(win):
    """1.0 at 100%, 1.5 at 150%. Multiply pixel sizes by this."""
    return dpi_for_window(win) / _BASE_DPI


# --------------------------- monitors --------------------------------------
# winfo_screenwidth() only ever describes the PRIMARY monitor, so on a multi-head
# setup the overlay always lands there — often not the screen you're gaming on.
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


_MONITORINFOF_PRIMARY = 0x1
_MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                      wintypes.HDC, ctypes.POINTER(_RECT),
                                      wintypes.LPARAM)


def monitors():
    """[{x, y, width, height, primary}] in virtual-desktop coordinates."""
    found = []

    def _cb(hmon, _hdc, _lprect, _lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            found.append({"x": r.left, "y": r.top,
                          "width": r.right - r.left,
                          "height": r.bottom - r.top,
                          "primary": bool(info.dwFlags & _MONITORINFOF_PRIMARY)})
        return True

    try:
        _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(_cb), 0)
    except OSError:
        pass
    if not found:                       # never leave the caller with nothing
        found = [{"x": 0, "y": 0,
                  "width": _user32.GetSystemMetrics(0),
                  "height": _user32.GetSystemMetrics(1), "primary": True}]
    found.sort(key=lambda m: (not m["primary"], m["x"], m["y"]))
    return found


def monitor_rect(index=0):
    mons = monitors()
    if not 0 <= index < len(mons):
        index = 0                       # a monitor that was unplugged
    m = mons[index]
    return m["x"], m["y"], m["width"], m["height"]


# ---------------------------- appearance ------------------------------------
_gdi32 = windll.gdi32
_gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
_gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
_user32.SetWindowRgn.restype = ctypes.c_int
_user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]


def round_window(win, radius, size=None):
    """Clip a window to a rounded rectangle.

    A hard rectangle is the thing that makes an overlay look pasted on. We do it
    with a window *region* rather than DWM's corner preference because DWM
    rounding doesn't apply to layered, override-redirect windows like ours —
    a region clips anything.

    Must be re-applied whenever the window resizes: the region is in pixels.
    """
    if radius <= 0:
        return
    hwnd = hwnd_of(win)
    if size:
        w, h = size
    else:
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
    if w <= 1 or h <= 1:
        return
    # +1: CreateRoundRectRgn's bottom/right are exclusive
    rgn = _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
    if rgn:
        _user32.SetWindowRgn(hwnd, rgn, True)   # window owns the region now


def unround_window(win):
    _user32.SetWindowRgn(hwnd_of(win), None, True)


def fit_window(win, min_w=0, min_h=0):
    """Size a normal window to the space its content actually needs.

    Never hard-code a pixel size for these windows. Once the process is DPI-aware
    Tk renders fonts at the real DPI (scaling 1.67 at 125%), so a size that looked
    right at 100% silently clips — that's exactly how the first-run window lost its
    buttons: 583px of content in a 440px non-resizable frame.

    Clamped to the monitor so a long window can't grow off-screen, and left
    resizable so the user can always recover.
    """
    win.update_idletasks()
    scale = scale_for_window(win)
    w = max(win.winfo_reqwidth(), int(min_w * scale))
    h = max(win.winfo_reqheight(), int(min_h * scale))
    _mx, _my, mw, mh = monitor_rect(0)
    w, h = min(w, int(mw * 0.95)), min(h, int(mh * 0.92))
    win.geometry(f"{w}x{h}")
    win.minsize(min(w, int(360 * scale)), min(h, int(240 * scale)))
    return w, h
