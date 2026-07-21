"""The control panel — the only interactive surface.

Hidden by default (it gets in the way while gaming); summoned with a global
hotkey. It's no-activate like everything else, so clicking a button never pulls
focus off the game, but it is NOT click-through — otherwise the buttons wouldn't
work.

Layout notes, all of which were bugs in the first version:
  * grouped by *job* — playback, toggles, app — instead of nine identical buttons
    in one row, where the primary action looked the same as the destructive one;
  * Play is the only filled button: one primary action, everything else recedes,
    and it sits full-width on its own row so it reads as *the* action;
  * every row's buttons FILL the width evenly (`_fill_row`, grid + `uniform`) —
    left-packed buttons left ~250px of dead space on the right of every row;
  * every button has a WORD. "📝" cannot tell anyone it means "make your own
    flashcards", and the transport controls say Skip/Replay/Stop, not bare glyphs;
  * Quit lives in the title bar, away from the controls you actually press.

This owns widgets only; the app owns behaviour and passes callbacks in.
"""
import tkinter as tk

from .. import win32
from . import theme


class _Tooltip:
    """Tk has no tooltips. Icon-ish buttons need them."""

    def __init__(self, widget, text, font):
        self.widget, self.text, self.font = widget, text, font
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        # no-activate: a tooltip must never take focus off the game either
        win32.prevent_focus_steal(self.tip)
        tk.Label(self.tip, text=self.text, bg="#0f1219", fg=theme.FG,
                 font=(self.font, 8), padx=6, pady=3,
                 highlightthickness=1, highlightbackground=theme.BORDER).pack()
        self.tip.geometry(f"+{x}+{y}")
        win32.show_no_activate(self.tip)
        # The panel is WS_EX_TOPMOST too; showing the tooltip doesn't raise it
        # within that band, so it renders *behind* the panel. Re-insert it at the
        # top of the topmost band — without activating it (that's the whole point).
        win32.raise_without_focus(self.tip)

    def _hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Panel:
    def __init__(self, root, settings, decks, actions):
        """actions: dict of name -> callback (play, stop, next, replay, annoy,
        mute, settings, editor, quit, select_deck(index))."""
        self.root = root
        self.s = settings
        self.decks = decks
        self.a = actions
        self.visible = False
        self._state, self._interval, self._generating = "stopped", 0, False
        self.f = f = theme.ui_font(root)
        P = theme.PAD

        outer = tk.Frame(root, bg=theme.BORDER)
        outer.pack(fill="both", expand=True)
        bar = tk.Frame(outer, bg=theme.BG)
        bar.pack(fill="both", expand=True, padx=1, pady=1)

        # --- title row: identity, live status, and the one destructive action ---
        top = tk.Frame(bar, bg=theme.BG)
        top.pack(fill="x", padx=P + 4, pady=(P, 2))
        tk.Label(top, text="Blip", bg=theme.BG, fg=theme.FG,
                 font=(f, 10, "bold")).pack(side="left")
        quit_btn = tk.Label(top, text="✕", bg=theme.BG, fg=theme.SUB,
                            font=(f, 9, "bold"), padx=5, cursor="hand2")
        quit_btn.pack(side="right")
        quit_btn.bind("<Button-1>", lambda e: self.a["quit"]())
        quit_btn.bind("<Enter>", lambda e: quit_btn.configure(fg=theme.STATUS_STOP))
        quit_btn.bind("<Leave>", lambda e: quit_btn.configure(fg=theme.SUB))
        # No tooltip: ✕ is the universal close glyph and needs no label. (Other
        # buttons keep theirs; _Tooltip now raises above the panel — see _show.)
        self.status_lbl = tk.Label(top, text="", bg=theme.BG, fg=theme.SUB,
                                   font=(f, 8))
        self.status_lbl.pack(side="right", padx=(0, P))

        self._rule(bar)

        # --- decks: only the current one, until you ask for the rest ------------
        # You study one deck for days, so the list is a rare interaction — but it's
        # also the only part of this panel that grows without bound (people import
        # decks). Collapsed it costs one row; expanded it's capped and scrolls, so
        # a 40-deck import can't push the buttons off the bottom of the screen.
        self.expanded = False
        self.deck_index = 0
        self._counts = [(0, len(d.get("words", []))) for d in decks]
        self._rect = None
        deck_box = tk.Frame(bar, bg=theme.BG)
        deck_box.pack(fill="x", padx=P, pady=(2, P))
        self.deck_view = tk.Canvas(deck_box, bg=theme.BG, highlightthickness=0,
                                   bd=0, takefocus=0)
        self.deck_view.pack(fill="x")
        self.deck_list = tk.Frame(self.deck_view, bg=theme.BG)
        self._list_id = self.deck_view.create_window((0, 0), window=self.deck_list,
                                                     anchor="nw")
        self.deck_rows = [self._deck_row(self.deck_list, i)
                          for i in range(len(decks))]
        self.deck_view.bind("<Configure>", self._fit_list)
        self._bind_wheel(self.deck_view)

        self._rule(bar)

        # Buttons FILL their row (evenly) instead of clustering on the left with
        # dead space to the right — the row is as wide as the hint line, so a
        # couple of left-packed buttons left ~250px empty. Each row spreads its
        # buttons edge to edge; the icon buttons get words while they're at it.

        # --- play: the one primary action, full width and prominent ---
        prow = tk.Frame(bar, bg=theme.BG)
        prow.pack(fill="x", padx=P, pady=(P, 2))
        self.play_btn = self._btn(prow, "▶  Play", self.a["play"], primary=True,
                                  tip="Start / pause the cards")
        self.play_btn.pack(fill="x", expand=True, padx=2)

        # --- transport: three equal buttons across the row ---
        self._fill_row((
            ("⏭  Skip",   self.a["next"],   "Skip to the next word"),
            ("🔁  Replay", self.a["replay"], "Say this word again"),
            ("⏹  Stop",   self.a["stop"],   "Stop and hide the card"),
        ), bar, P)

        # --- toggles ---
        self.annoy_btn, self.mute_btn = self._fill_row((
            ("😈 Annoy", self.a["annoy"], "Flash words big across the screen"),
            ("🔊 Sound", self.a["mute"],  "Mute everything"),
        ), bar, P)

        # --- deck sources: get curated decks, or author your own ---
        self._fill_row((
            ("📚 Get decks", self.a["catalog"],
             "Browse and install the creator decks (HSK, slang, gaming…)"),
            ("✏  Make cards", self.a["editor"],
             "Create your own cards, or import a deck (Anki, CSV)"),
        ), bar, P)

        # --- app actions ---
        self._fill_row((
            ("🧠 Test Mode", self.a["quiz"],
             "Quiz yourself: pick the right reading + meaning"),
            ("⚙  Settings", self.a["settings"],
             "Timing, sound, appearance, hotkeys"),
        ), bar, P, pady=(2, P))

        self._rule(bar)
        hk = settings.hotkeys
        hint = f"{self._key(hk['panel'])} hide  ·  {self._key(hk['mute'])} silent"
        if settings.recall_hotkeys:
            hint += (f"  ·  {self._key(hk['got'])} knew it"
                     f"  ·  {self._key(hk['miss'])} didn't")
        tk.Label(bar, text=hint, bg=theme.BG, fg=theme.SUB, font=(f, 7)).pack(
            anchor="w", padx=P + 6, pady=(4, P))

        for w in (bar, top):          # drag by the chrome, not the controls
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

    # ---------- pieces ----------
    @staticmethod
    def _key(spec):
        """'ctrl+alt+c' -> 'Ctrl+Alt+C'. .title() mangles hotkeys."""
        return "+".join(p.capitalize() for p in str(spec).split("+"))

    def _rule(self, parent):
        tk.Frame(parent, bg=theme.BORDER, height=1).pack(fill="x", padx=theme.PAD)

    def _fill_row(self, specs, parent, pad, pady=2):
        """A row of equal-width buttons spanning the full width — grid with a
        `uniform` group so every column is the same size (pack+expand would size
        each to its text, leaving them subtly ragged). No dead space on the right."""
        row = tk.Frame(parent, bg=theme.BG)
        row.pack(fill="x", padx=pad, pady=pady)
        made = []
        for col, (text, cmd, tip) in enumerate(specs):
            b = self._btn(row, text, cmd, tip=tip)
            b.grid(row=0, column=col, sticky="ew", padx=2)
            row.columnconfigure(col, weight=1, uniform="btn")
            made.append(b)
        return made

    def _deck_row(self, parent, i):
        row = tk.Frame(parent, bg=theme.BG, cursor="hand2")
        row.pack(fill="x", pady=1)
        head = tk.Frame(row, bg=theme.BG)
        head.pack(fill="x")
        name = tk.Label(head, text="", bg=theme.BG, fg=theme.SUB,
                        font=(self.f, 9, "bold"), anchor="w")
        name.pack(side="left", padx=(6, 0))
        # Only on the current deck: it's the whole affordance for "there are
        # others". It shipped as a 7px glyph — the dimmest thing on the panel —
        # and went unnoticed, so it gets a word and a readable size like every
        # other control here.
        chev = tk.Label(head, text="", bg=theme.BG, fg=theme.FG,
                        font=(self.f, 8, "bold"))
        chev.pack(side="right", padx=(6, 6))
        count = tk.Label(head, text="", bg=theme.BG, fg=theme.SUB, font=(self.f, 7))
        count.pack(side="right")
        bar = tk.Canvas(row, height=3, bg=theme.BG, highlightthickness=0, bd=0,
                        takefocus=0)
        bar.pack(fill="x", padx=6, pady=(1, 2))
        bar.bind("<Configure>", lambda e, idx=i: self._bar_configured(idx))
        parts = (row, head, name, count, chev, bar)
        for w in parts:
            w.bind("<Button-1>", lambda e, idx=i: self._deck_click(idx))
            w.bind("<Enter>", lambda e, idx=i: self._hover(idx, True))
            w.bind("<Leave>", lambda e, idx=i: self._hover(idx, False))
            self._bind_wheel(w)
        return {"row": row, "head": head, "name": name, "count": count,
                "chev": chev, "bar": bar, "parts": parts}

    def _deck_click(self, i):
        """Collapsed, only the current deck is on screen, so any click means
        'show me the others'. Expanded, a click is a choice."""
        if len(self.deck_rows) < 2:
            return                      # nothing to expand into
        if not self.expanded:
            self._set_expanded(True)
            return
        if i != self.deck_index:
            self.a["select_deck"](i)
        self._set_expanded(False)

    def _set_expanded(self, on):
        self.expanded = on
        if not on:
            self.deck_view.yview_moveto(0)
        self._sync_decks()
        self.place(self._rect)          # height changed: re-anchor and re-round

    def _hover(self, i, on):
        r = self.deck_rows[i]
        if i == self.deck_index:
            return                      # the active row already has a background
        bg = theme.BTN if on else theme.BG
        for w in (r["row"], r["head"], r["name"], r["count"], r["chev"]):
            w.configure(bg=bg)
        r["bar"].configure(bg=bg)

    def _bind_wheel(self, w):
        w.bind("<MouseWheel>", self._wheel)

    def _wheel(self, e):
        if self.expanded:
            self.deck_view.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def _fit_list(self, e):
        self.deck_view.itemconfigure(self._list_id, width=e.width)

    def _sync_decks(self):
        """Pack the rows that should be visible, then size the viewport."""
        show = self.deck_rows if self.expanded else [self.deck_rows[self.deck_index]]
        for i, r in enumerate(self.deck_rows):
            r["row"].pack_forget()
            # here, not in set_decks(): expanding doesn't go through set_decks(),
            # and a chevron pointing the wrong way is a lie about what a click does.
            # With one deck there's nothing to open, so it promises nothing.
            mine = i == self.deck_index and len(self.deck_rows) > 1
            n = len(self.deck_rows) - 1
            r["chev"].configure(text="" if not mine else (
                "▴  close" if self.expanded
                else f"▾  {n} more deck{'s' if n > 1 else ''}"))
        for r in show:                  # re-pack in order; pack_forget appends
            r["row"].pack(fill="x", pady=1)
        self.deck_list.update_idletasks()
        need = self.deck_list.winfo_reqheight()
        row_h = max(self.deck_rows[0]["row"].winfo_reqheight() + 2, 1)
        cap = int(self.s.panel_max_deck_rows) * row_h
        self.deck_view.configure(
            height=min(need, cap) if self.expanded else need,
            scrollregion=(0, 0, 0, need), yscrollincrement=row_h)
        if self.expanded:               # don't open with the current deck off-view
            top = self.deck_index * row_h
            if top + row_h > cap:
                self.deck_view.yview_moveto(min(top / max(need, 1), 1.0))
        for i, r in enumerate(self.deck_rows):
            if r["row"].winfo_ismapped():
                known, total = self._counts[i]
                self._draw_progress(r["bar"], known, total, i == self.deck_index,
                                    r["bar"].cget("bg"))

    def _btn(self, parent, text, cmd, primary=False, tip=""):
        bg = theme.BTN_PRIMARY if primary else theme.BTN
        b = tk.Label(parent, text=text, bg=bg,
                     fg=theme.BTN_PRIMARY_FG if primary else theme.FG,
                     font=(self.f, 9, "bold"), padx=10, pady=5, cursor="hand2")
        b._bg = bg
        b._hi = theme.BTN_PRIMARY_HI if primary else theme.BTN_HI
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=b._hi))
        b.bind("<Leave>", lambda e: b.configure(bg=b._bg))
        if tip:
            _Tooltip(b, tip, self.f)
        return b

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root, e.y_root
        self._ox, self._oy = self.root.winfo_x(), self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{self._ox + (e.x_root - self._dx)}"
                           f"+{self._oy + (e.y_root - self._dy)}")

    # ---------- state ----------
    def set_decks(self, deck_index, counts):
        """counts: list of (known, total) per deck."""
        self.deck_index = deck_index
        self._counts = list(counts)
        for i, (r, (known, total)) in enumerate(zip(self.deck_rows, counts)):
            active = i == deck_index
            name = self.decks[i]["name"]
            r["name"].configure(text=("▸ " if active else "   ") + name,
                                fg=theme.FG if active else theme.SUB)
            r["count"].configure(text=f"{known}/{total}",
                                 fg=theme.SUB if not active else theme.FG)
            bg = theme.BTN if active else theme.BG
            for w in (r["row"], r["head"], r["name"], r["count"], r["chev"]):
                w.configure(bg=bg)
            r["bar"].configure(bg=bg)
        self._sync_decks()

    def _bar_configured(self, i):
        """Tk tells us when a bar has a real width — no polling. An after() retry
        here left timers queued against a hidden panel, and destroying a root with
        callbacks still pending is what wedges Tcl (see 'Tk root churn' in
        CLAUDE.md); it also cost a full redraw every 50ms for nothing."""
        if i >= len(self._counts):
            return
        r = self.deck_rows[i]
        known, total = self._counts[i]
        self._draw_progress(r["bar"], known, total, i == self.deck_index,
                            r["bar"].cget("bg"))

    def _draw_progress(self, cv, known, total, active, bg):
        cv.configure(bg=bg)
        cv.delete("all")
        w = cv.winfo_width()
        if w <= 1:
            return                      # <Configure> will call back once it's laid out
        cv.create_rectangle(0, 0, w, 3, fill=theme.TRACK, width=0)
        if total:
            fill = int(w * min(known / total, 1.0))
            if fill > 0:
                cv.create_rectangle(
                    0, 0, fill, 3,
                    fill=theme.ACCENT if active else theme.PROGRESS_IDLE, width=0)

    def set_status(self, state, interval):
        self._state, self._interval = state, interval
        self._refresh_status()

    def set_generating(self, active):
        """Show a background-audio-generation indicator in the status line. Called
        True when generation starts, False when it finishes. Steady text (no live
        count — that's in the console/log) so it doesn't resize the panel per clip;
        re-anchor once when it appears/clears in case the panel is already open."""
        self._generating = bool(active)
        self._refresh_status()
        if self.visible:
            self.place()

    def _refresh_status(self):
        if self._state == "running":
            self.play_btn.configure(text="⏸  Pause")
            dot, txt = theme.STATUS_OK, f"every {self._interval}s"
        elif self._state == "paused":
            self.play_btn.configure(text="▶  Play")
            dot, txt = theme.STATUS_WARN, "paused"
        else:
            self.play_btn.configure(text="▶  Play")
            dot, txt = theme.STATUS_STOP, "stopped"
        if self._generating:
            txt += "  ·  ⏳ audio…"
        self.status_lbl.configure(text=f"● {txt}", fg=dot)

    def set_annoy(self, on):
        self.annoy_btn.configure(text="😈 Annoy" if on else "😈 Annoy: off",
                                 fg=theme.FG if on else theme.SUB)

    def set_sound(self, on):
        self.mute_btn.configure(text="🔊 Sound" if on else "🔇 Silent",
                                fg=theme.FG if on else theme.SUB)

    # ---------- visibility ----------
    def place(self, rect=None):
        # Remembered: expanding the deck list re-places the panel, and it has to
        # land on the same monitor rather than the primary one.
        self._rect = rect = rect or self._rect
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        mx, my, mw, _mh = rect or (0, 0, self.root.winfo_screenwidth(),
                                   self.root.winfo_screenheight())
        self.root.geometry(f"+{mx + mw - w - self.s.margin}+{my + self.s.margin}")
        if self.s.get("card_radius"):
            win32.round_window(self.root, int(self.s.card_radius), size=(w, h))
        return h

    def show(self, rect=None):
        self.place(rect)
        win32.show_no_activate(self.root)
        self.visible = True

    def hide(self):
        win32.hide_window(self.root)
        self.visible = False
        if self.expanded:               # always come back up compact
            self.expanded = False
            self.deck_view.yview_moveto(0)
            self._sync_decks()

    def toggle(self):
        self.hide() if self.visible else self.show()
