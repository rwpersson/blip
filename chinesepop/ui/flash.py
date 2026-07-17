"""Fullscreen "annoying mode" flash.

Huge term + reading + tones across the whole screen, synced to each spoken repeat.
The background is color-keyed away entirely so the game stays fully visible — only
the giant text renders — and the window is click-through, so even while the letters
cover the screen your cursor still reaches the game.

Layout is sized so both a single tall character and a 4-character idiom fit on
screen (top and bottom), which is why the term is capped at 36% of screen height
and the reading is spaced off the font SIZE rather than the taller line-height.
"""
import tkinter as tk

from .. import decks as decks_mod
from .. import win32
from . import render, theme


class Flash:
    def __init__(self, root, settings):
        self.root = root
        self.s = settings
        self.win = tk.Toplevel(root, bg=theme.BG)
        self.win.overrideredirect(True)
        win32.prevent_focus_steal(self.win)
        self.win.attributes("-topmost", True)
        try:
            # color-key removes the background; alpha makes the text a little
            # see-through. The two attributes coexist deliberately.
            self.win.attributes("-transparentcolor", theme.BG)
            self.win.attributes("-alpha", settings.annoy_text_alpha)
        except tk.TclError:
            pass
        self.win.withdraw()
        self.cv = tk.Canvas(self.win, bg=theme.BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        win32.make_click_through(self.win)

    def render(self, word):
        cv = self.cv
        cv.delete("all")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        cv.configure(width=sw, height=sh)
        term = decks_mod.word_term(word)
        n = max(1, len(str(term)))
        size = int(min(sw * self.s.annoy_hanzi_frac / n, sh * 0.36))
        read_size = max(40, int(size * 0.24))
        cx, cy = sw // 2, int(sh * 0.36)
        render.draw_centered(cv, cx, cy, [(term, theme.FG)], size, self.s.font)
        render.draw_centered(cv, cx, cy + int(size * 0.55) + read_size,
                             render.reading_segments(word), read_size, self.s.font)

    def show(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        win32.show_no_activate(self.win)
        win32.raise_without_focus(self.win)

    def hide(self):
        win32.hide_window(self.win)
