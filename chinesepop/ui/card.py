"""The flashcard.

Two stacked windows, because Tk's -alpha dims a whole window uniformly and we
want a see-through panel with crisp text:

  * backing — a solid panel at CARD_ALPHA (the game shows through it)
  * text    — fully opaque, sitting exactly on top, with theme.BG color-keyed
              away so only the glyphs/pills render

Both are click-through and no-activate: the card is display-only, so the cursor
always reaches the game. Every control lives on the panel instead.
"""
import tkinter as tk

from .. import decks as decks_mod
from .. import win32
from ..text import censor_display
from . import render, theme


class Card:
    def __init__(self, root, settings):
        self.root = root
        self.s = settings
        f = settings.font

        # --- layer 1: semi-transparent backing panel ---
        self.back = tk.Toplevel(root, bg=theme.BORDER)
        self.back.overrideredirect(True)
        win32.prevent_focus_steal(self.back)      # before it ever maps
        self.back.attributes("-topmost", True)
        try:
            self.back.attributes("-alpha", settings.card_alpha)
        except tk.TclError:
            pass
        self.back.withdraw()
        tk.Frame(self.back, bg=theme.BG).pack(fill="both", expand=True,
                                              padx=1, pady=1)

        # --- layer 2: opaque text, transparent background ---
        self.text = tk.Toplevel(root, bg=theme.BG)
        self.text.overrideredirect(True)
        win32.prevent_focus_steal(self.text)
        self.text.attributes("-topmost", True)
        try:
            self.text.attributes("-transparentcolor", theme.BG)
        except tk.TclError:
            pass
        self.text.withdraw()

        body = tk.Frame(self.text, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        top = tk.Frame(body, bg=theme.BG)
        top.pack(fill="x", padx=14, pady=(12, 0))
        self.cat_lbl = tk.Label(top, text="", bg=theme.BG, fg=theme.BG,
                                font=(f, 9, "bold"), padx=8, pady=1)
        self.cat_lbl.pack(side="left")
        self.new_lbl = tk.Label(top, text="", bg=theme.BG, fg=theme.NEW_BADGE,
                                font=(f, 9, "bold"))
        self.new_lbl.pack(side="left", padx=(6, 0))
        self.count_lbl = tk.Label(top, text="", bg=theme.BG, fg=theme.SUB,
                                  font=(f, 9))
        self.count_lbl.pack(side="right")

        self.term_cv = tk.Canvas(body, bg=theme.BG, highlightthickness=0, bd=0)
        self.term_cv.pack(anchor="w", padx=12, pady=(2, 0))
        self.alt_lbl = tk.Label(body, text="", bg=theme.BG, fg=theme.SUB,
                                font=(f, 10), justify="left")
        self.alt_lbl.pack(anchor="w", padx=14)
        self.reading_cv = tk.Canvas(body, bg=theme.BG, highlightthickness=0, bd=0)
        self.reading_cv.pack(anchor="w", padx=12, pady=(6, 0))
        wrap = settings.card_width - 28
        self.meaning_lbl = tk.Label(body, text="", bg=theme.BG, fg=theme.MEAN,
                                    font=(f, 13, "bold"), justify="left",
                                    wraplength=wrap)
        self.meaning_lbl.pack(anchor="w", padx=14, pady=(6, 0))
        self.note_lbl = tk.Label(body, text="", bg=theme.BG, fg=theme.SUB,
                                 font=(f, 10), justify="left", wraplength=wrap)
        self.note_lbl.pack(anchor="w", padx=14, pady=(6, 0))
        tk.Frame(body, bg=theme.BG, height=12).pack()

        win32.make_click_through(self.back)
        win32.make_click_through(self.text)

    # ---------- rendering ----------
    def render_prompt(self, word, is_new, seen, known, total):
        """Characters + counters only; the answer stays hidden for the recall beat."""
        cat = word.get("cat", "common")
        self.cat_lbl.configure(text=f" {cat.upper()} ", fg="#12141a",
                               bg=theme.CAT_COLORS.get(cat, theme.SUB))
        self.new_lbl.configure(text="✦ NEW" if is_new else "")
        self.count_lbl.configure(text=f"seen {seen}×   ·   {known}/{total} learned")
        render.draw_row(self.term_cv, [(decks_mod.word_term(word), theme.FG)],
                        self.s.hanzi_size, self.s.font, self.s.halo_thickness)
        self.alt_lbl.configure(text="")
        render.draw_row(self.reading_cv, [], self.s.pinyin_size, self.s.font)
        self.meaning_lbl.configure(text="🤔  recall it…", fg=theme.SUB)
        self.note_lbl.configure(text="")

    def render_answer(self, word):
        alt = word.get("alt")
        self.alt_lbl.configure(text=f"also: {alt}" if alt else "")
        render.draw_row(self.reading_cv, render.reading_segments(word),
                        self.s.pinyin_size, self.s.font, self.s.halo_thickness)
        self.meaning_lbl.configure(text=censor_display(word.get("meaning", "")),
                                   fg=theme.MEAN)
        self.note_lbl.configure(text=word.get("note", ""))
        self.place()          # height changed — re-anchor

    # ---------- geometry / visibility ----------
    def place(self):
        """Size the backing to the text layer and center both at the top."""
        self.text.update_idletasks()
        w = self.text.winfo_reqwidth()
        h = self.text.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        x = (sw - w) // 2
        y = self.s.margin
        self.back.geometry(f"{w}x{h}+{x}+{y}")
        self.text.geometry(f"+{x}+{y}")

    def show(self):
        win32.show_no_activate(self.back)      # panel first, text on top
        win32.show_no_activate(self.text)
        win32.raise_without_focus(self.back)
        win32.raise_without_focus(self.text)

    def hide(self):
        win32.hide_window(self.text)
        win32.hide_window(self.back)
