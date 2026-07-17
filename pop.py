"""
Chinese Pop — an always-on-top flashcard that pops up in the corner every minute
while you game, shows a random word / slang term with pinyin, tones, meaning and
a nuance note, and speaks it aloud.

A small control bar stays on screen so you can Play / Pause / Stop / skip.
Words are drilled in a small spaced-repetition batch (see Scheduler): each is
re-shown on an expanding interval and "graduates" once seen enough, then a new
word enters. The answer is briefly hidden for a recall beat, the meaning + tones
are read aloud, and pinyin is tone-colored. Progress persists to state.json.

Run:  python pop.py     (or double-click run.bat)
"""
import ctypes
import json
import math
import queue
import random
import struct
import sys
import threading
import time
import wave
import winsound
from ctypes import windll, wintypes
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ------------------------------- CONFIG ------------------------------------
INTERVAL_SECONDS = 25     # how often a new word pops up
DISPLAY_SECONDS = 22      # how long the card stays before auto-hiding (0 = stay)
FIRST_POPUP_AFTER = 2     # seconds after launch before the first popup
PLAY_AUDIO = True         # start with sound on? (toggle live: panel / Ctrl+Alt+M)
SILENT_WORD_SECS = 1.2    # in silent mode, how long each flash "beat" lasts
WORD_REPEATS = 3          # how many times to speak the word each pop
SAY_TONES = True          # after the word, read the tones aloud in English
SAY_MEANING = True        # after the tones, read the English meaning aloud
REPEAT_GAP = 0.35         # seconds of silence between repeats
AUTOSTART = True          # begin the cycle automatically on launch
ACTIVE_DECK = ""          # deck id (decks/<id>.json) to start on; "" = the first

# Spaced learning: drill a small active batch, expanding intervals as a word is
# seen, and "graduate" it once it's been seen enough (then a new word enters).
ACTIVE_SET_SIZE = 12      # how many words are "in progress" at once
GRADUATE_AT = 9           # exposures before a word counts as learned
SCHEDULE_MIN = [0.25, 1, 3, 7, 15, 30, 60, 180, 720, 1440]  # re-show delay (min)

# Reveal-delay quiz: show the characters + play audio, hide the answer briefly
# so you attempt to recall it, then reveal (the "testing effect").
REVEAL_QUIZ = True
REVEAL_DELAY = 3.0        # seconds the answer stays hidden

# Annoying mode: flash the hanzi/pinyin/tones HUGE across the whole screen in
# sync with each spoken repeat (3x), then drop back to the normal card for the
# English read-out. The flash background is transparent (game stays visible) and
# click-through, so your cursor still reaches the game. Toggle on the panel.
ANNOYING_MODE = True
ANNOY_HANZI_FRAC = 0.78   # how much of the screen width the characters may fill
ANNOY_TEXT_ALPHA = 0.50   # opacity of the huge flashing text (1.0 = solid)

# --- Anti-habituation (so the pops don't become wallpaper you tune out) ---
# Attention chime: after a RANDOM number of cards, a RANDOM chime plays (not
# every card — that would just become background too).
CHIME_ON = True
CHIME_EVERY_MIN = 3       # soonest a chime fires (in cards since the last one)
CHIME_EVERY_MAX = 8       # latest it fires — a fresh random count is picked each time
# When annoying mode is on, only SOME pops flash — unpredictably, and weighted
# toward the words you haven't learned yet, so you can't pre-filter them.
FLASH_PROB = 0.28         # chance a normal pop does the fullscreen flash
FLASH_NEW_UNTIL = 3       # words seen this many times or fewer ALWAYS flash
# One-key recall: global hotkeys to rate the word you just saw (feeds spacing).
RECALL_HOTKEYS = True
GOT_HOTKEY_VK, GOT_LABEL = 0x4A, "Ctrl+Alt+J"     # "I knew it"  -> show it less
MISS_HOTKEY_VK, MISS_LABEL = 0x4B, "Ctrl+Alt+K"   # "I didn't"   -> bring it back
MUTE_HOTKEY_VK, MUTE_LABEL = 0x4D, "Ctrl+Alt+M"   # toggle silent mode

CARD_WIDTH = 360
CARD_ALPHA = 0.62         # opacity of the card PANEL only (text stays fully solid)
MARGIN = 24               # gap from the screen edges

# The control panel is hidden by default and toggled with a GLOBAL hotkey that
# works even while your game has focus. (mods: 1=Alt 2=Ctrl 4=Shift 8=Win)
PANEL_HOTKEY_MODS = 0x0002 | 0x0001   # Ctrl + Alt
PANEL_HOTKEY_VK = 0x43                # 'C'  ->  Ctrl+Alt+C toggles the panel
PANEL_HOTKEY_LABEL = "Ctrl+Alt+C"
PANEL_HINT_SECONDS = 4    # briefly show the panel at launch as a reminder (0=off)

# Standard-ish tone colors (readable on the dark card).
TONE_COLORS = {"1": "#ff6b6b", "2": "#ffd166", "3": "#06d6a0",
               "4": "#4d96ff", "·": "#9aa4b2", "5": "#9aa4b2"}

# The word (hanzi) and pinyin are drawn with a dark outline "halo" so they stay
# legible over any game background, even through the see-through panel.
HANZI_SIZE = 50           # big, dominant characters
PINYIN_SIZE = 17
HALO_COLOR = "#04060c"    # outline drawn behind the word/pinyin
HALO_THICKNESS = 2        # outline width in px

# Colors
C_BORDER = "#3a4152"
C_BG     = "#1b1e27"
C_FG     = "#f2f4f8"
C_ACCENT = "#ffb454"   # pinyin
C_SUB    = "#9aa4b2"   # note / secondary text
C_MEAN   = "#8bd450"   # meaning
C_BTN    = "#2a2f3d"
C_BTN_HI = "#3a4152"
CAT_COLORS = {
    "slang":  "#ff7597",
    "gaming": "#7aa2ff",
    "common": "#8bd450",
    "hsk":    "#5ad1c9",
    "idiom":  "#c792ea",
    "swear":  "#ff5c5c",
}
FONT = "Microsoft YaHei UI"   # has Chinese glyphs on Windows
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "audio"
DECKS_DIR = ROOT / "decks"
STATE_FILE = ROOT / "state.json"

try:
    from generate_audio import censor_display   # asterisk swears in shown meaning
except Exception:
    def censor_display(text):
        return text


def load_decks():
    """Each decks/*.json is a deck: {"name": ..., "words": [...]}. Returns a list
    of {"id": <filename stem>, "name": ..., "words": [...]} sorted by filename."""
    decks = []
    for f in sorted(DECKS_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, list):        # tolerate a bare word list
            data = {"name": f.stem, "words": data}
        decks.append({"id": f.stem,
                      "name": data.get("name", f.stem),
                      "words": data.get("words", [])})
    return decks


def _read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(data):
    try:
        STATE_FILE.write_text(json.dumps(data, ensure_ascii=False),
                              encoding="utf-8")
    except Exception:
        pass


# --------------------- keep the popup from stealing focus ------------------
# Mark our windows as WS_EX_NOACTIVATE tool windows so Windows renders them on
# top but never gives them foreground/keyboard focus. That means the popup can't
# grab your cursor, steal focus, or minimize an exclusive-fullscreen game when
# it appears. We also never withdraw/deiconify (which can trigger activation) —
# the card is "hidden" by parking it off-screen instead.
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

_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_HWND_TOPMOST = -1
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOZORDER = 0x0001, 0x0002, 0x0004
_SWP_NOACTIVATE, _SWP_FRAMECHANGED = 0x0010, 0x0020


def _hwnd_now(win):
    # HWND without update_idletasks() — must NOT map the window yet, or it would
    # activate before we get a chance to mark it no-activate.
    wid = win.winfo_id()
    return _user32.GetParent(wid) or wid


def _hwnd_of(win):
    win.update_idletasks()
    return _hwnd_now(win)


def _set_noactivate(hwnd):
    ex = _GetWL(hwnd, _GWL_EXSTYLE)
    _SetWL(hwnd, _GWL_EXSTYLE,
           ex | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW | _WS_EX_TOPMOST)
    _user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                         _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER
                         | _SWP_NOACTIVATE | _SWP_FRAMECHANGED)


def prevent_focus_steal(win):
    # Apply immediately (no update_idletasks) so the window is no-activate BEFORE
    # its first map — otherwise it flashes to the foreground once on creation.
    wid = win.winfo_id()
    parent = _user32.GetParent(wid)
    _set_noactivate(wid)
    if parent:
        _set_noactivate(parent)


def raise_without_focus(win):
    # Re-assert top-most without ever activating the window.
    hwnd = _hwnd_of(win)
    _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                         _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)


_SW_HIDE = 0
_SW_SHOWNOACTIVATE = 4
_user32.ShowWindow.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


def show_no_activate(win):
    # Show a (withdrawn/hidden) window WITHOUT giving it focus.
    _user32.ShowWindow(_hwnd_of(win), _SW_SHOWNOACTIVATE)


def hide_window(win):
    _user32.ShowWindow(_hwnd_of(win), _SW_HIDE)


# --------------------------- global hotkey listener ------------------------
_WM_HOTKEY = 0x0312
_MOD_NOREPEAT = 0x4000
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                   wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT]


class HotkeyListener(threading.Thread):
    """Registers system-wide hotkeys on its own thread and pumps its message
    loop; each press pushes its hotkey id to a queue for the Tk thread. Global,
    so they fire even while another app (your game) holds focus.

    hotkeys: list of (id, mods, vk). self.ok maps id -> registered?"""

    def __init__(self, hotkeys):
        super().__init__(daemon=True)
        self.hotkeys = hotkeys
        self.q = queue.Queue()
        self.ok = {}
        self._ready = threading.Event()

    def run(self):
        for hid, mods, vk in self.hotkeys:
            self.ok[hid] = bool(
                _user32.RegisterHotKey(None, hid, mods | _MOD_NOREPEAT, vk))
        self._ready.set()
        if not any(self.ok.values()):
            return
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY:
                self.q.put(int(msg.wParam))   # wParam = the hotkey id

    def wait_ready(self, timeout=1.5):
        self._ready.wait(timeout)
        return self.ok


# ------------------------------- sound cues --------------------------------
# Short WAV cues generated with the stdlib (no assets/deps). Played via winsound.
SOUNDS_DIR = ROOT / "sounds"
_HK_PANEL, _HK_GOT, _HK_MISS, _HK_MUTE = 1, 2, 3, 4   # hotkey ids


def _wav(path, segments, rate=44100):
    """segments: list of (list-of-freqs, seconds, volume). Notes in a segment
    are summed (a chord); a plucked decay envelope is applied to each."""
    frames = bytearray()
    for freqs, dur, vol in segments:
        n = int(dur * rate)
        for i in range(n):
            t = i / rate
            env = math.exp(-4.0 * t / dur)
            s = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            frames += struct.pack("<h", int(max(-1, min(1, s * env * vol)) * 32767))
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


# Several distinct chimes so the cue itself varies and stays hard to tune out.
_CHIME_SPECS = {
    "chime1": [([1318.5], 0.10, 0.5), ([1568.0], 0.16, 0.5)],           # E6->G6
    "chime2": [([2093.0], 0.20, 0.45)],                                 # high C7 ping
    "chime3": [([1046.5], 0.08, 0.5), ([1318.5], 0.08, 0.5),
               ([1568.0], 0.14, 0.5)],                                  # C-E-G arp
    "chime4": [([880.0, 1318.5], 0.22, 0.4)],                           # A5+E6 bell
    "got":    [([1046.5], 0.09, 0.5), ([1567.98], 0.16, 0.5)],          # up = yes
    "miss":   [([659.25], 0.12, 0.5), ([415.30], 0.22, 0.5)],           # down = no
}
_CHIMES = ["chime1", "chime2", "chime3", "chime4"]


def ensure_sounds():
    SOUNDS_DIR.mkdir(exist_ok=True)
    for name, spec in _CHIME_SPECS.items():
        p = SOUNDS_DIR / f"{name}.wav"
        if not p.exists() or p.stat().st_size == 0:
            try:
                _wav(p, spec)
            except Exception:
                pass


def play_sound(name, block=False):
    if not _audio_on:
        return
    p = SOUNDS_DIR / f"{name}.wav"
    if not p.exists():
        return
    flags = winsound.SND_FILENAME | (0 if block else winsound.SND_ASYNC)
    try:
        winsound.PlaySound(str(p), flags)
    except Exception:
        pass


def make_click_through(win):
    # WS_EX_TRANSPARENT (on a layered window) makes the whole window ignore the
    # mouse entirely — clicks/hover pass straight through to the game beneath.
    hwnd = _hwnd_of(win)
    ex = _GetWL(hwnd, _GWL_EXSTYLE)
    _SetWL(hwnd, _GWL_EXSTYLE, ex | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
           | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
    _user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                         _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER
                         | _SWP_NOACTIVATE | _SWP_FRAMECHANGED)


# ----------------------------- audio playback ------------------------------
# Play MP3 via Windows' built-in MCI (winmm) — no extra dependency needed.
_mci = windll.winmm.mciSendStringW

# Runtime sound switch (silent mode). Starts from the PLAY_AUDIO config default;
# toggled live from the panel / hotkey. When off, NO sound plays at all.
_audio_on = PLAY_AUDIO


def set_audio(on):
    global _audio_on
    _audio_on = bool(on)

# Runtime sound switch (silent mode). Starts from the PLAY_AUDIO config default;
# toggled live from the panel / hotkey. When off, NO sound plays at all.
_audio_on = PLAY_AUDIO


def set_audio(on):
    global _audio_on
    _audio_on = bool(on)


_play_token = 0   # bumped on each new play so a stale sequence stops itself


def _play_file(path):
    if not path.exists():
        return
    _mci("close chpop", None, 0, None)
    _mci(f'open "{path}" type mpegvideo alias chpop', None, 0, None)
    _mci("play chpop wait", None, 0, None)
    _mci("close chpop", None, 0, None)


def play_audio(word, on_event=None, chime=False):
    """Speak the word WORD_REPEATS times, then read tones + meaning aloud.
    If chime, play a short (random) attention cue first.

    on_event(kind) is called (from the audio thread) at sync points:
      "word_on"  — a word repeat just started playing
      "word_off" — that repeat finished
      "english"  — moving on to the English tone/meaning read-out
    """
    silent = not _audio_on
    if silent and on_event is None:
        return                       # nothing to play and no flash to drive
    global _play_token
    _play_token += 1
    token = _play_token
    word_path = AUDIO_DIR / f"{word['id']}.mp3"
    tones_path = AUDIO_DIR / f"{word['id']}_tones.mp3"
    meaning_path = AUDIO_DIR / f"{word['id']}_meaning.mp3"

    def emit(kind):
        if on_event:
            on_event(kind)

    def _run():
        if chime and not silent:      # unpredictable attention ping, then a beat
            play_sound(random.choice(_CHIMES), block=True)
            time.sleep(0.08)
        for i in range(max(1, WORD_REPEATS)):
            if token != _play_token:      # a newer play superseded us
                return
            emit("word_on")
            if silent:
                time.sleep(SILENT_WORD_SECS)   # keep the flash timed, but quiet
            else:
                _play_file(word_path)
            emit("word_off")
            if i < WORD_REPEATS - 1:
                time.sleep(REPEAT_GAP)
        if token != _play_token:
            return
        emit("english")
        if silent:
            return
        if SAY_TONES:
            time.sleep(REPEAT_GAP)
            _play_file(tones_path)
        if SAY_MEANING and token == _play_token:
            time.sleep(REPEAT_GAP)
            _play_file(meaning_path)

    threading.Thread(target=_run, daemon=True).start()


# ------------------------------ spaced scheduler ---------------------------
class Scheduler:
    """Spaced-repetition-lite. Keeps a small active batch of words in progress,
    re-shows each on an expanding interval as it's seen, and 'graduates' it once
    seen GRADUATE_AT times (a new word then enters the batch). No grading needed
    — spacing is driven purely by exposures, so it stays fully passive. Each
    deck's progress is stored separately under state.json["decks"][deck_id]."""

    def __init__(self, words, deck_id):
        self.deck_id = deck_id
        self.by_id = {w["id"]: w for w in words}
        self.order = [w["id"] for w in words]
        self.total = len(self.order)
        self.last = None
        self.st = {i: {"e": 0, "due": 0.0, "intro": False} for i in self.order}
        self._load()

    def _load(self):
        slot = _read_state().get("decks", {}).get(self.deck_id, {})
        for i, s in slot.get("words", {}).items():
            if i in self.st:
                self.st[i] = {"e": int(s.get("e", 0)),
                              "due": float(s.get("due", 0.0)),
                              "intro": bool(s.get("intro", False))}
        self.last = slot.get("last")

    def _save(self):
        data = _read_state()
        data.setdefault("decks", {})[self.deck_id] = {
            "words": {i: {"e": s["e"], "due": round(s["due"], 1),
                          "intro": s["intro"]}
                      for i, s in self.st.items() if s["intro"]},
            "last": self.last,
        }
        _write_state(data)

    def _learning(self):
        return [i for i in self.order
                if self.st[i]["intro"] and self.st[i]["e"] < GRADUATE_AT]

    def _fill_batch(self):
        # Bring the active batch up to size by introducing new (random) words.
        while len(self._learning()) < ACTIVE_SET_SIZE:
            fresh = [i for i in self.order if not self.st[i]["intro"]]
            if not fresh:
                break
            pick = random.choice(fresh)
            self.st[pick]["intro"] = True
            self.st[pick]["due"] = 0.0   # due immediately

    def _interval(self, e):
        return SCHEDULE_MIN[min(max(e, 1), len(SCHEDULE_MIN)) - 1] * 60.0

    def next(self):
        now = time.time()
        self._fill_batch()
        pool = [i for i in self.order if self.st[i]["intro"]] or self.order[:]
        random.shuffle(pool)                       # randomize ties
        pool.sort(key=lambda i: (self.st[i]["due"], self.st[i]["e"]))
        choice = pool[0]
        if choice == self.last and len(pool) > 1:  # avoid back-to-back repeat
            choice = pool[1]
        s = self.st[choice]
        s["e"] += 1
        s["due"] = now + self._interval(s["e"])
        self.last = choice
        self._save()
        return self.by_id[choice]

    def exposures(self, wid):
        return self.st.get(wid, {}).get("e", 0)

    def rate(self, wid, got):
        """Active recall feedback: 'got' it -> jump toward learned and push it
        far out; missed it -> knock it back and make it due again very soon."""
        s = self.st.get(wid)
        if not s:
            return
        s["intro"] = True
        if got:
            s["e"] = min(GRADUATE_AT, s["e"] + 3)
            s["due"] = time.time() + self._interval(GRADUATE_AT)
        else:
            s["e"] = max(0, s["e"] - 3)
            s["due"] = 0.0
        self._save()

    def stats(self):
        known = sum(1 for i in self.order if self.st[i]["e"] >= GRADUATE_AT)
        return len(self._learning()), known, self.total


# --------------------------------- app -------------------------------------
class PopApp:
    STOPPED, RUNNING, PAUSED = "stopped", "running", "paused"

    def __init__(self, decks):
        self.decks = decks
        self.deck_index = self._initial_deck_index()
        d = self.decks[self.deck_index]
        self.sched = Scheduler(d["words"], d["id"])
        self._save_last_deck(d["id"])
        self.current = None
        self.state = self.STOPPED
        self._next_job = None
        self._hide_job = None
        self._reveal_job = None
        self._is_new = False
        self._flashing = False
        self._chime_countdown = random.randint(CHIME_EVERY_MIN, CHIME_EVERY_MAX)
        self.annoying = ANNOYING_MODE
        self.sound_on = _audio_on
        self._fx_q = queue.Queue()       # audio-thread -> UI flash events
        # Remember what had focus so we can hand it straight back after launch.
        self._prev_fg = _user32.GetForegroundWindow()

        # The control bar IS the root window; the flashcard is a Toplevel.
        self.root = tk.Tk()
        self.root.title("Chinese Pop")
        self.root.overrideredirect(True)
        prevent_focus_steal(self.root)   # no-activate BEFORE first map
        self.root.attributes("-topmost", True)
        self.root.configure(bg=C_BORDER)
        self.root.withdraw()

        self._build_control_bar()
        self._build_card()
        self._build_flash()
        self._place_control_bar()
        # Panel starts HIDDEN; the global hotkey toggles it (see run()).
        self._panel_visible = False

    # ---------- control bar ----------
    def _build_control_bar(self):
        outer = tk.Frame(self.root, bg=C_BORDER)
        outer.pack(fill="both", expand=True)
        bar = tk.Frame(outer, bg=C_BG)
        bar.pack(fill="both", expand=True, padx=1, pady=1)
        self.bar = bar

        title = tk.Label(bar, text="🀄 Chinese Pop", bg=C_BG, fg=C_FG,
                         font=(FONT, 10, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(8, 0))

        self.status_lbl = tk.Label(bar, text="", bg=C_BG, fg=C_SUB,
                                   font=(FONT, 9))
        self.status_lbl.grid(row=0, column=1, columnspan=5, sticky="e",
                             padx=(0, 12), pady=(8, 0))

        # deck list (click a deck to switch to it)
        deck_box = tk.Frame(bar, bg=C_BG)
        deck_box.grid(row=1, column=0, columnspan=6, sticky="we",
                      padx=10, pady=(2, 2))
        tk.Label(deck_box, text="DECKS", bg=C_BG, fg=C_SUB,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=2)
        self._deck_labels = []
        for i, d in enumerate(self.decks):
            lbl = tk.Label(deck_box, text="", bg=C_BG, fg=C_SUB,
                           font=(FONT, 9, "bold"), cursor="hand2", anchor="w",
                           padx=6, pady=2)
            lbl.pack(fill="x", pady=1)
            lbl.bind("<Button-1>", lambda e, idx=i: self._load_deck(idx))
            self._deck_labels.append(lbl)
        self._refresh_deck_label()

        btns = tk.Frame(bar, bg=C_BG)
        btns.grid(row=2, column=0, columnspan=6, sticky="we", padx=8, pady=(2, 8))

        self.play_btn = self._mk_btn(btns, "▶ Play", self.toggle_play, wide=True)
        self.play_btn.pack(side="left", padx=2)
        self._mk_btn(btns, "⏹ Stop", self.stop).pack(side="left", padx=2)
        self._mk_btn(btns, "⏭ Next", self.next_now).pack(side="left", padx=2)
        self._mk_btn(btns, "🔊 Replay", self.replay).pack(side="left", padx=2)
        self._annoy_btn = self._mk_btn(
            btns, "😈 Annoy: ON" if self.annoying else "😈 Annoy: OFF",
            self.toggle_annoy)
        self._annoy_btn.pack(side="left", padx=2)
        self._mute_btn = self._mk_btn(
            btns, "🔊 Sound" if self.sound_on else "🔇 Silent", self.toggle_mute)
        self._mute_btn.pack(side="left", padx=2)
        self._mk_btn(btns, "✕", self.quit).pack(side="left", padx=2)

        hint = f"{PANEL_HOTKEY_LABEL} hide/show   ·   {MUTE_LABEL} silent"
        if RECALL_HOTKEYS:
            hint += f"   ·   {GOT_LABEL} knew it   ·   {MISS_LABEL} didn't"
        tk.Label(bar, text=hint, bg=C_BG, fg=C_SUB, font=(FONT, 8)).grid(
            row=3, column=0, columnspan=6, sticky="w", padx=12, pady=(0, 8))

        # drag the bar by its title
        for w in (bar, title):
            w.bind("<Button-1>", lambda e: self._drag_start(e, self.root))
            w.bind("<B1-Motion>", lambda e: self._drag_move(e, self.root))

    def _mk_btn(self, parent, text, cmd, wide=False):
        b = tk.Label(parent, text=text, bg=C_BTN, fg=C_FG,
                     font=(FONT, 9, "bold"), padx=(10 if wide else 8), pady=4,
                     cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=C_BTN_HI))
        b.bind("<Leave>", lambda e: b.configure(bg=C_BTN))
        return b

    def _place_control_bar(self):
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"+{sw - w - MARGIN}+{MARGIN}")
        self._bar_h = self.root.winfo_reqheight()

    # ---------- flashcard (two layers: faint panel + fully-opaque text) ------
    def _build_card(self):
        # Layer 1 — backing: a semi-transparent solid panel. Whole-window alpha
        # only dims THIS layer, not the text on top of it.
        self.card = tk.Toplevel(self.root, bg=C_BORDER)
        self.card.overrideredirect(True)
        prevent_focus_steal(self.card)   # no-activate BEFORE first map
        self.card.attributes("-topmost", True)
        try:
            self.card.attributes("-alpha", CARD_ALPHA)
        except tk.TclError:
            pass
        self.card.withdraw()
        self._backing = tk.Frame(self.card, bg=C_BG)
        self._backing.pack(fill="both", expand=True, padx=1, pady=1)

        # Layer 2 — text: fully opaque, sits exactly on top of the panel. Its
        # C_BG background is color-keyed to transparent, so only the text and
        # pills show (crisp) over the faint panel behind them.
        self.text = tk.Toplevel(self.root, bg=C_BG)
        self.text.overrideredirect(True)
        prevent_focus_steal(self.text)
        self.text.attributes("-topmost", True)
        try:
            self.text.attributes("-transparentcolor", C_BG)
        except tk.TclError:
            pass
        self.text.withdraw()

        card = tk.Frame(self.text, bg=C_BG)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        top = tk.Frame(card, bg=C_BG)
        top.pack(fill="x", padx=14, pady=(12, 0))
        self.cat_lbl = tk.Label(top, text="", bg=C_BG, fg=C_BG,
                                font=(FONT, 9, "bold"), padx=8, pady=1)
        self.cat_lbl.pack(side="left")
        self.new_lbl = tk.Label(top, text="", bg=C_BG, fg="#ffd166",
                                font=(FONT, 9, "bold"))
        self.new_lbl.pack(side="left", padx=(6, 0))
        self.count_lbl = tk.Label(top, text="", bg=C_BG, fg=C_SUB, font=(FONT, 9))
        self.count_lbl.pack(side="right")

        # hanzi + pinyin are drawn on canvases so we can give them a readable
        # outline halo (and tone-color each pinyin syllable).
        self.hanzi_cv = tk.Canvas(card, bg=C_BG, highlightthickness=0, bd=0)
        self.hanzi_cv.pack(anchor="w", padx=12, pady=(2, 0))
        self.alt_lbl = tk.Label(card, text="", bg=C_BG, fg=C_SUB,
                                font=(FONT, 10), justify="left")
        self.alt_lbl.pack(anchor="w", padx=14)
        self.pinyin_cv = tk.Canvas(card, bg=C_BG, highlightthickness=0, bd=0)
        self.pinyin_cv.pack(anchor="w", padx=12, pady=(6, 0))
        self.meaning_lbl = tk.Label(card, text="", bg=C_BG, fg=C_MEAN,
                                    font=(FONT, 13, "bold"), justify="left",
                                    wraplength=CARD_WIDTH - 28)
        self.meaning_lbl.pack(anchor="w", padx=14, pady=(6, 0))
        self.note_lbl = tk.Label(card, text="", bg=C_BG, fg=C_SUB,
                                 font=(FONT, 10), justify="left",
                                 wraplength=CARD_WIDTH - 28)
        self.note_lbl.pack(anchor="w", padx=14, pady=(6, 0))

        tk.Frame(card, bg=C_BG, height=12).pack()   # bottom breathing room

        # The flashcard is display-only: make BOTH layers click-through so the
        # cursor passes straight to the game. All controls live on the top-right
        # panel instead (Play / Stop / Next / Replay).
        make_click_through(self.card)
        make_click_through(self.text)

    # ---------- fullscreen "annoying" flash ----------
    def _build_flash(self):
        # A transparent, click-through, no-activate fullscreen overlay. Its C_BG
        # background is color-keyed away, so only the huge text shows over the
        # game (which stays fully visible), and clicks pass straight through.
        self.flash = tk.Toplevel(self.root, bg=C_BG)
        self.flash.overrideredirect(True)
        prevent_focus_steal(self.flash)
        self.flash.attributes("-topmost", True)
        try:
            # Color-key removes the background entirely; the alpha makes the
            # remaining (text) pixels a little see-through.
            self.flash.attributes("-transparentcolor", C_BG)
            self.flash.attributes("-alpha", ANNOY_TEXT_ALPHA)
        except tk.TclError:
            pass
        self.flash.withdraw()
        self.flash_cv = tk.Canvas(self.flash, bg=C_BG, highlightthickness=0, bd=0)
        self.flash_cv.pack(fill="both", expand=True)
        make_click_through(self.flash)

    def _draw_centered(self, canvas, cx, cy, segments, size):
        """Draw (text, color) segments centered horizontally at (cx, cy) with a
        dark outline halo. Returns the line height."""
        f = tkfont.Font(family=FONT, size=size, weight="bold")
        font = (FONT, size, "bold")
        widths = [f.measure(s) for s, _ in segments]
        x = cx - sum(widths) / 2
        t = max(2, size // 22)
        offs = [(-t, 0), (t, 0), (0, -t), (0, t),
                (-t, -t), (t, -t), (-t, t), (t, t)]
        xs, xx = [], x
        for w in widths:
            xs.append(xx)
            xx += w
        for (s, _), x0 in zip(segments, xs):      # outlines first
            for dx, dy in offs:
                canvas.create_text(x0 + dx, cy + dy, text=s, fill=HALO_COLOR,
                                   font=font, anchor="w")
        for (s, color), x0 in zip(segments, xs):  # colored fills on top
            canvas.create_text(x0, cy, text=s, fill=color, font=font, anchor="w")
        return f.metrics("linespace")

    def _render_flash(self, word):
        cv = self.flash_cv
        cv.delete("all")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        cv.configure(width=sw, height=sh)
        n = max(1, len(str(word["hanzi"])))
        hz = int(min(sw * ANNOY_HANZI_FRAC / n, sh * 0.36))
        py = max(40, int(hz * 0.24))
        cx = sw // 2
        cy = int(sh * 0.36)          # positioned so the pinyin/tones fit below
        self._draw_centered(cv, cx, cy, [(word["hanzi"], C_FG)], hz)
        # tone-colored pinyin + tones underneath
        py_y = cy + int(hz * 0.55) + py
        syls = str(word["pinyin"]).split()
        tones = str(word["tones"]).replace(" ", "").split("-")
        colored = len(syls) == len(tones)
        segs = []
        for i, syl in enumerate(syls):
            col = TONE_COLORS.get(tones[i], C_ACCENT) if colored else C_ACCENT
            segs.append((syl, col))
            if i < len(syls) - 1:
                segs.append(("  ", C_SUB))
        segs.append((f"    ·  {word['tones']}", C_SUB))
        self._draw_centered(cv, cx, py_y, segs, py)

    def _draw_outlined(self, canvas, segments, size, pad=3):
        """Draw a row of (text, color) segments on a canvas, each with a dark
        outline halo so it stays readable over any background."""
        canvas.delete("all")
        if not segments:
            canvas.configure(width=1, height=1)
            return
        font = (FONT, size, "bold")
        f = tkfont.Font(family=FONT, size=size, weight="bold")
        t = HALO_THICKNESS
        widths = [f.measure(s) for s, _ in segments]
        h = f.metrics("linespace")
        canvas.configure(width=sum(widths) + pad * 2 + t * 2,
                         height=h + pad * 2 + t * 2)
        y = pad + t
        xs, x = [], pad + t
        for w in widths:
            xs.append(x)
            x += w
        offs = [(-t, 0), (t, 0), (0, -t), (0, t),
                (-t, -t), (t, -t), (-t, t), (t, t)]
        for (s, _), x0 in zip(segments, xs):      # all outlines first
            for dx, dy in offs:
                canvas.create_text(x0 + dx, y + dy, text=s, fill=HALO_COLOR,
                                   font=font, anchor="nw")
        for (s, color), x0 in zip(segments, xs):  # then colored fills on top
            canvas.create_text(x0, y, text=s, fill=color, font=font, anchor="nw")

    def _render_pinyin(self, word):
        syls = str(word["pinyin"]).split()
        tones = str(word["tones"]).replace(" ", "").split("-")
        colored = len(syls) == len(tones)
        segs = []
        for i, syl in enumerate(syls):
            col = TONE_COLORS.get(tones[i], C_ACCENT) if colored else C_ACCENT
            segs.append((syl, col))
            if i < len(syls) - 1:
                segs.append(("  ", C_SUB))
        segs.append((f"    ·  {word['tones']}", C_SUB))
        self._draw_outlined(self.pinyin_cv, segs, PINYIN_SIZE)

    def _render_prompt(self, word):
        # Show the characters + counters; hide the answer for the recall beat.
        self.current = word
        cat = word.get("cat", "common")
        self.cat_lbl.configure(text=f" {cat.upper()} ",
                               fg="#12141a", bg=CAT_COLORS.get(cat, C_SUB))
        self.new_lbl.configure(text="✦ NEW" if self._is_new else "")
        e = self.sched.exposures(word["id"])
        _, known, total = self.sched.stats()
        self.count_lbl.configure(text=f"seen {e}×   ·   {known}/{total} learned")
        self._draw_outlined(self.hanzi_cv, [(word["hanzi"], C_FG)], HANZI_SIZE)
        self.alt_lbl.configure(text="")
        self._draw_outlined(self.pinyin_cv, [], PINYIN_SIZE)   # clear/collapse
        self.meaning_lbl.configure(text="🤔  recall it…", fg=C_SUB)
        self.note_lbl.configure(text="")

    def _render_answer(self, word):
        self.alt_lbl.configure(text=f"also: {word['alt']}" if word.get("alt") else "")
        self._render_pinyin(word)
        self.meaning_lbl.configure(text=censor_display(word["meaning"]), fg=C_MEAN)
        self.note_lbl.configure(text=word["note"])
        self._place_card()   # height changed — re-anchor to the corner

    def _place_card(self):
        # The text layer sizes to its content; the backing panel is sized to
        # match, and both are positioned at the same spot (top-center).
        self.text.update_idletasks()
        w = self.text.winfo_reqwidth()
        h = self.text.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        x = (sw - w) // 2            # centered horizontally
        y = MARGIN                   # near the top edge
        self.card.geometry(f"{w}x{h}+{x}+{y}")
        self.text.geometry(f"+{x}+{y}")

    # ---------- dragging ----------
    def _drag_start(self, e, win):
        self._dx, self._dy = e.x_root, e.y_root
        self._ox, self._oy = win.winfo_x(), win.winfo_y()

    def _drag_move(self, e, win):
        win.geometry(f"+{self._ox + (e.x_root - self._dx)}"
                     f"+{self._oy + (e.y_root - self._dy)}")

    # ---------- core cycle ----------
    def _cancel_reveal(self):
        if self._reveal_job:
            self.root.after_cancel(self._reveal_job)
            self._reveal_job = None

    def _card_show(self):
        show_no_activate(self.card)      # panel first (no focus)
        show_no_activate(self.text)      # then the text layer
        raise_without_focus(self.card)
        raise_without_focus(self.text)   # text ends up on top

    def _card_hide(self):
        hide_window(self.text)
        hide_window(self.card)

    def _flash_show(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.flash.geometry(f"{sw}x{sh}+0+0")
        self._card_hide()                # the flash replaces the card while on
        show_no_activate(self.flash)
        raise_without_focus(self.flash)

    def _flash_hide(self):
        hide_window(self.flash)

    def _chime_due(self):
        # True once every random run of cards (then re-rolls the countdown).
        if not CHIME_ON:
            return False
        self._chime_countdown -= 1
        if self._chime_countdown <= 0:
            self._chime_countdown = random.randint(CHIME_EVERY_MIN, CHIME_EVERY_MAX)
            return True
        return False

    def _show(self, word):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self._cancel_reveal()
        self._flash_hide()
        self.current = word
        e = self.sched.exposures(word["id"])
        # First time you ever see a word you can't "recall" it — so study it
        # (show everything at once). The recall-delay only kicks in on repeats.
        self._is_new = e <= 1
        # Weak/new words always flash; others flash unpredictably (so you can't
        # pre-filter them). Chime fires after a random run of cards.
        weak = e <= FLASH_NEW_UNTIL
        self._flashing = self.annoying and (weak or random.random() < FLASH_PROB)
        chiming = self._chime_due()

        if self._flashing:
            # Fill the card with the full answer (shown later, during the English
            # read-out) and prep the fullscreen flash. Audio events drive both.
            self._render_prompt(word)
            self._render_answer(word)    # also re-anchors the card
            self._render_flash(word)
            play_audio(word, on_event=self._fx_emit, chime=chiming)
        else:
            self._render_prompt(word)
            self._place_card()
            self._card_show()
            play_audio(word, chime=chiming)
            if REVEAL_QUIZ and REVEAL_DELAY > 0 and not self._is_new:
                self._reveal_job = self.root.after(
                    int(REVEAL_DELAY * 1000), lambda w=word: self._reveal(w))
            else:
                self._render_answer(word)

        if DISPLAY_SECONDS > 0:
            self._hide_job = self.root.after(DISPLAY_SECONDS * 1000, self.hide_card)

    def _fx_emit(self, kind):
        # Called from the audio thread; hand off to the Tk thread via the queue.
        self._fx_q.put(kind)

    def _poll_fx(self):
        try:
            while True:
                kind = self._fx_q.get_nowait()
                if not self._flashing:
                    continue
                if kind == "word_on":
                    self._flash_show()
                elif kind == "word_off":
                    self._flash_hide()
                elif kind == "english":
                    self._flash_hide()
                    self._card_show()    # back to the normal card
        except queue.Empty:
            pass
        self.root.after(30, self._poll_fx)

    def _reveal(self, word):
        self._reveal_job = None
        if self.current is word:
            self._render_answer(word)

    def _tick(self):
        if self.state != self.RUNNING:
            return
        self._show(self.sched.next())
        self._refresh_deck_label()
        self._next_job = self.root.after(INTERVAL_SECONDS * 1000, self._tick)

    def _cancel_next(self):
        if self._next_job:
            self.root.after_cancel(self._next_job)
            self._next_job = None

    # ---------- button actions ----------
    def toggle_play(self):
        if self.state == self.RUNNING:
            self.pause()
        else:
            self.play()

    def play(self):
        self.state = self.RUNNING
        self._cancel_next()
        self._tick()               # show one now, then keep ticking
        self._refresh_status()

    def pause(self):
        if self.state == self.RUNNING:
            self.state = self.PAUSED
            self._cancel_next()    # freeze the timer, keep the card up
            self._refresh_status()

    def stop(self):
        self.state = self.STOPPED
        self._cancel_next()
        self.hide_card()
        self._refresh_status()

    def next_now(self):
        # jump to a new word immediately and (re)start the running cycle
        self.state = self.RUNNING
        self._cancel_next()
        self._tick()
        self._refresh_status()

    def replay(self):
        if self.current:
            play_audio(self.current)

    def hide_card(self):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self._cancel_reveal()
        self._flash_hide()
        hide_window(self.text)
        hide_window(self.card)

    def toggle_annoy(self):
        self.annoying = not self.annoying
        if not self.annoying:
            self._flash_hide()
        self._annoy_btn.configure(
            text="😈 Annoy: ON" if self.annoying else "😈 Annoy: OFF")

    def toggle_mute(self):
        self.sound_on = not self.sound_on
        set_audio(self.sound_on)
        self._mute_btn.configure(
            text="🔊 Sound" if self.sound_on else "🔇 Silent")

    def rate_current(self, got):
        # One-key recall feedback for the word currently showing.
        if not self.current:
            return
        self.sched.rate(self.current["id"], got)
        play_sound("got" if got else "miss")   # audible confirmation
        self._refresh_deck_label()

    # ---------- decks ----------
    def _initial_deck_index(self):
        # explicit config wins; otherwise resume the last-played deck; else first
        if ACTIVE_DECK:
            for i, d in enumerate(self.decks):
                if d["id"] == ACTIVE_DECK:
                    return i
        last = _read_state().get("last_deck")
        for i, d in enumerate(self.decks):
            if d["id"] == last:
                return i
        return 0

    def _save_last_deck(self, deck_id):
        st = _read_state()
        st["last_deck"] = deck_id
        _write_state(st)

    def _deck_known(self, deck, state):
        words = state.get(deck["id"], {}).get("words", {})
        return sum(1 for w in words.values() if w.get("e", 0) >= GRADUATE_AT)

    def _refresh_deck_label(self):
        # Update the clickable deck list; highlight the active one.
        state = _read_state().get("decks", {})
        for i, (lbl, d) in enumerate(zip(self._deck_labels, self.decks)):
            total = len(d["words"])
            if i == self.deck_index:
                _, known, _ = self.sched.stats()
                lbl.configure(text=f"▸ {d['name']}  ({known}/{total})",
                              fg=C_FG, bg=C_BTN)
            else:
                known = self._deck_known(d, state)
                lbl.configure(text=f"   {d['name']}  ({known}/{total})",
                              fg=C_SUB, bg=C_BG)

    def _load_deck(self, index):
        if index == self.deck_index:
            return
        self.deck_index = index
        d = self.decks[index]
        self.sched = Scheduler(d["words"], d["id"])
        self._save_last_deck(d["id"])
        self.current = None
        self.hide_card()
        self._refresh_deck_label()
        if self.state == self.RUNNING:   # jump straight into the new deck
            self._cancel_next()
            self._tick()

    def _refresh_status(self):
        if self.state == self.RUNNING:
            self.play_btn.configure(text="⏸ Pause")
            dot, txt = "#8bd450", f"Playing · every {INTERVAL_SECONDS}s"
        elif self.state == self.PAUSED:
            self.play_btn.configure(text="▶ Play")
            dot, txt = "#ffb454", "Paused"
        else:
            self.play_btn.configure(text="▶ Play")
            dot, txt = "#ff5c5c", "Stopped"
        self.status_lbl.configure(text=f"● {txt}", fg=dot)

    # ---------- control panel show/hide ----------
    def show_panel(self):
        self._place_control_bar()
        show_no_activate(self.root)
        self._panel_visible = True

    def hide_panel(self):
        hide_window(self.root)
        self._panel_visible = False

    def toggle_panel(self):
        self.hide_panel() if self._panel_visible else self.show_panel()

    def _poll_hotkey(self):
        try:
            while True:
                hid = self._hotkeys.q.get_nowait()
                if hid == _HK_PANEL:
                    self.toggle_panel()
                elif hid == _HK_GOT:
                    self.rate_current(True)
                elif hid == _HK_MISS:
                    self.rate_current(False)
                elif hid == _HK_MUTE:
                    self.toggle_mute()
        except queue.Empty:
            pass
        self.root.after(80, self._poll_hotkey)

    def _check_hotkey(self):
        # If the panel hotkey couldn't be registered, keep the panel visible so
        # the user still has a way to control/quit the app.
        if self._hotkeys.ok.get(_HK_PANEL) is False:
            print(f"⚠ Could not register {PANEL_HOTKEY_LABEL} (in use by another "
                  f"app?). Leaving the panel visible.")
            self.show_panel()

    def quit(self):
        try:
            _mci("close chpop", None, 0, None)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self._refresh_status()
        # Return focus to whatever the user was using (e.g. their game).
        if self._prev_fg:
            self.root.after(80, lambda: _user32.SetForegroundWindow(self._prev_fg))

        # Global hotkeys: panel toggle, silent-mode toggle, + the recall keys.
        hotkeys = [(_HK_PANEL, PANEL_HOTKEY_MODS, PANEL_HOTKEY_VK),
                   (_HK_MUTE, PANEL_HOTKEY_MODS, MUTE_HOTKEY_VK)]
        if RECALL_HOTKEYS:
            hotkeys.append((_HK_GOT, PANEL_HOTKEY_MODS, GOT_HOTKEY_VK))
            hotkeys.append((_HK_MISS, PANEL_HOTKEY_MODS, MISS_HOTKEY_VK))
        self._hotkeys = HotkeyListener(hotkeys)
        self._hotkeys.start()
        self.root.after(400, self._check_hotkey)
        self.root.after(80, self._poll_hotkey)
        self.root.after(30, self._poll_fx)   # audio-synced fullscreen flash
        if PANEL_HINT_SECONDS > 0:
            self.show_panel()
            self.root.after(int(PANEL_HINT_SECONDS * 1000),
                            lambda: self._hotkeys.ok.get(_HK_PANEL) is not False
                            and self.hide_panel())

        if AUTOSTART:
            self.root.after(FIRST_POPUP_AFTER * 1000, self.play)
        self.root.mainloop()


def main():
    ensure_sounds()
    try:
        from generate_audio import ensure_audio
        ok, total = ensure_audio(quiet=True)
        if total:
            print(f"Generated {ok}/{total} audio clips.")
    except Exception:
        pass

    decks = load_decks()
    if not decks:
        print("No decks found. Put deck files in the 'decks/' folder "
              "(see new_deck.py). Nothing to run.")
        return
    total = sum(len(d["words"]) for d in decks)
    names = ", ".join(d["name"] for d in decks)
    print(f"Chinese Pop running — {len(decks)} deck(s) [{names}], "
          f"{total} words total, batch of {ACTIVE_SET_SIZE}, every {INTERVAL_SECONDS}s.")
    print(f"Press {PANEL_HOTKEY_LABEL} to show/hide the panel; click the deck "
          f"name to switch decks (✕ to quit).")
    if RECALL_HOTKEYS:
        print(f"Recall while a word shows: {GOT_LABEL} = knew it, "
              f"{MISS_LABEL} = didn't (brings it back sooner).")
    PopApp(decks).run()


if __name__ == "__main__":
    main()
