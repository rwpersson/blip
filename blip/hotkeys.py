"""System-wide hotkeys.

The app never holds focus, so ordinary key bindings are useless — every shortcut
must be a global RegisterHotKey. Gotcha: the hotkey must be registered AND its
message loop pumped on the *same* thread, so both live in this thread's run().
WM_HOTKEY's wParam carries the hotkey id.
"""
import ctypes
import queue
import threading
from ctypes import windll, wintypes

from .logging_setup import get

log = get("hotkeys")
_user32 = windll.user32

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008

_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                   wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT]

# hotkey ids
PANEL, GOT, MISS, MUTE = 1, 2, 3, 4

_MOD_NAMES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
              "shift": MOD_SHIFT, "win": MOD_WIN}


def parse(spec):
    """'ctrl+alt+c' -> (mods, vk). Raises ValueError on nonsense."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty hotkey: {spec!r}")
    *mod_names, key = parts
    mods = 0
    for m in mod_names:
        if m not in _MOD_NAMES:
            raise ValueError(f"unknown modifier {m!r} in {spec!r}")
        mods |= _MOD_NAMES[m]
    if len(key) == 1:
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit():
        vk = 0x70 + int(key[1:]) - 1            # F1..F24
    else:
        raise ValueError(f"unsupported key {key!r} in {spec!r}")
    return mods, vk


class HotkeyListener(threading.Thread):
    """hotkeys: list of (id, mods, vk). self.ok maps id -> registered?"""

    def __init__(self, hotkeys):
        super().__init__(daemon=True)
        self.hotkeys = hotkeys
        self.q = queue.Queue()
        self.ok = {}
        self._ready = threading.Event()

    def run(self):
        for hid, mods, vk in self.hotkeys:
            ok = bool(_user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk))
            self.ok[hid] = ok
            if not ok:
                log.warning("hotkey id=%s already taken by another app", hid)
        self._ready.set()
        if not any(self.ok.values()):
            log.error("no hotkeys could be registered")
            return
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.q.put(int(msg.wParam))

    def wait_ready(self, timeout=1.5):
        self._ready.wait(timeout)
        return self.ok


NAMES = {PANEL: "panel", GOT: "got", MISS: "miss", MUTE: "mute"}


def build(settings):
    """Turn the settings hotkey map into (id, mods, vk) tuples."""
    specs = settings.hotkeys
    out = []
    wanted = [(PANEL, "panel"), (MUTE, "mute")]
    if settings.recall_hotkeys:
        wanted += [(GOT, "got"), (MISS, "miss")]
    for hid, name in wanted:
        spec = specs.get(name)
        if not spec:
            continue
        try:
            mods, vk = parse(spec)
        except ValueError:
            log.exception("bad hotkey for %s: %r", name, spec)
            continue
        out.append((hid, mods, vk))
    return out


def is_available(spec, exclude=()):
    """Can we actually register this combo right now?

    The only honest way to know is to try: another app may already own it, and
    RegisterHotKey just fails. Registering and immediately releasing is cheap and
    is what the settings UI uses to tell you *before* you save a dead binding.
    """
    try:
        mods, vk = parse(spec)
    except ValueError:
        return False
    probe_id = 0x4000                       # an id we never use for real
    if not _user32.RegisterHotKey(None, probe_id, mods | MOD_NOREPEAT, vk):
        return False
    _user32.UnregisterHotKey(None, probe_id)
    return True


def conflicts(settings):
    """Bindings that are duplicated within our own map. Returns {spec: [names]}."""
    seen = {}
    for name, spec in (settings.hotkeys or {}).items():
        if not spec:
            continue
        try:
            key = parse(spec)
        except ValueError:
            continue
        seen.setdefault(key, []).append(name)
    return {settings.hotkeys[names[0]]: names
            for names in seen.values() if len(names) > 1}
