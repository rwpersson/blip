"""First run.

A stranger's first launch currently does nothing visible for two seconds and then
a card appears from nowhere, with no hint that a panel or hotkeys exist. This is a
short, skippable welcome that tells them the three things they can't guess:
where the panel is, that it's hidden behind a hotkey, and that the first launch
has to synthesize audio.

Deliberately its own process/window (like Settings and the editor) — it wants
focus, and the overlay's windows must never take it.
"""
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from . import paths, settings as settings_mod, win32
from .logging_setup import get, setup

log = get("firstrun")


def is_first_run():
    """No settings file yet == we've never run here."""
    return not paths.settings_file().exists()


def mark_done(s=None):
    """Writing settings is what makes it 'not first run' next time."""
    (s or settings_mod.load()).save()


class WelcomeWindow:
    def __init__(self, deck_count=0, word_count=0, clips_needed=0):
        self.s = settings_mod.load()
        self.deck_count = deck_count
        self.word_count = word_count
        self.clips_needed = clips_needed
        self.start = True
        self.root = tk.Tk()
        self.root.title("Welcome to Blip")
        self._build()
        # Size to content rather than guessing: at 125% scaling this window needs
        # ~583px, and the hard-coded 440 cut the buttons off entirely.
        win32.fit_window(self.root, min_w=520, min_h=420)

    def _build(self):
        pad = {"padx": 18, "pady": 6}
        # The action bar is packed FIRST, side="bottom". Tk's pack gives space in
        # order, so a bar packed last is the first thing squeezed when content
        # overflows — which is how these buttons vanished. Pinned now.
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", side="bottom", padx=18, pady=14)
        ttk.Button(bar, text="Start", command=self._start).pack(side="right")
        ttk.Button(bar, text="Open Settings…",
                   command=self._settings).pack(side="right", padx=6)
        # New users start on a small sampler; the fuller decks are opt-in.
        ttk.Button(bar, text="Get more decks…",
                   command=self._catalog).pack(side="left")

        ttk.Label(self.root, text="💬  Blip",
                  font=("", 16, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        ttk.Label(self.root, wraplength=470, justify="left",
                  text="A flashcard pops up in the corner while you game, says the "
                       "word, and disappears. It never steals your cursor or pulls "
                       "focus out of a game.").pack(anchor="w", **pad)

        box = ttk.LabelFrame(self.root, text="Three things worth knowing",
                             padding=10)
        box.pack(fill="x", padx=18, pady=8)
        hk = self.s.hotkeys
        for line in (
            f"The control panel is hidden. Press  {hk['panel'].upper()}  to show it.",
            f"{hk['mute'].upper()} silences it instantly. "
            f"{hk['got'].upper()} / {hk['miss'].upper()} = 'I knew it' / 'I didn't'.",
            "It shows over fullscreen games. If one hides it, use Borderless.",
        ):
            ttk.Label(box, text="•  " + line, wraplength=440,
                      justify="left").pack(anchor="w", pady=2)

        if self.clips_needed:
            warn = ttk.LabelFrame(self.root, text="First launch takes a minute",
                                  padding=10)
            warn.pack(fill="x", padx=18, pady=4)
            ttk.Label(warn, wraplength=440, justify="left",
                      text=f"{self.clips_needed} audio clips need to be generated "
                           f"for {self.word_count} words (needs internet, once). "
                           f"After that it works offline and cards are silent until "
                           f"it finishes.").pack(anchor="w")

        opts = ttk.Frame(self.root)
        opts.pack(fill="x", padx=18, pady=8)
        self.interval = tk.StringVar(value=str(self.s.interval_seconds))
        row = ttk.Frame(opts)
        row.pack(anchor="w", pady=3)
        ttk.Label(row, text="Show a word every").pack(side="left")
        ttk.Spinbox(row, textvariable=self.interval, from_=5, to=600,
                    width=5).pack(side="left", padx=6)
        ttk.Label(row, text="seconds").pack(side="left")

        self.hide_swears = tk.BooleanVar(value=self.s.hide_swears)
        ttk.Checkbutton(opts, text="Hide swear words (some creator decks include them)",
                        variable=self.hide_swears).pack(anchor="w", pady=3)
        self.annoying = tk.BooleanVar(value=self.s.annoying_mode)
        ttk.Checkbutton(
            opts, text="Flash new words big across the screen (recommended)",
            variable=self.annoying).pack(anchor="w", pady=3)

        ttk.Label(self.root, foreground="#666", wraplength=470, justify="left",
                  text="You're starting with a small sampler deck. “Get more "
                       "decks…” adds curated ones (HSK, slang, gaming, and more) "
                       "whenever you like. Everything here is in Settings later.").pack(
            anchor="w", padx=18, pady=(0, 4))

    def _collect(self):
        try:
            self.s.set("interval_seconds", int(float(self.interval.get())))
        except ValueError:
            pass                       # keep the default rather than block Start
        self.s.set("hide_swears", bool(self.hide_swears.get()))
        self.s.set("annoying_mode", bool(self.annoying.get()))
        self.s.save()

    def _start(self):
        self._collect()
        self.root.destroy()

    def _settings(self):
        self._collect()
        try:
            subprocess.Popen([sys.executable, "-m", "blip.settings_ui"],
                             cwd=str(paths.APP_DIR))
        except Exception:
            log.exception("could not open settings")
        self.root.destroy()

    def _catalog(self):
        # Keep the welcome open behind it — picking decks isn't leaving setup.
        self._collect()
        from . import catalog_ui
        catalog_ui.open_catalog()

    def run(self):
        self.root.mainloop()
        return self.s


def show(deck_count=0, word_count=0, clips_needed=0):
    """Blocking welcome. Returns the (possibly updated) settings."""
    return WelcomeWindow(deck_count, word_count, clips_needed).run()


def main():
    setup()
    paths.ensure_dirs()
    if settings_mod.load().dpi_aware:
        win32.set_dpi_aware()
    show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
