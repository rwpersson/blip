"""The control panel — the only interactive surface.

Hidden by default (it gets in the way while gaming); summoned with a global
hotkey. It's no-activate like everything else, so clicking a button never pulls
focus off the game, but it is NOT click-through — otherwise the buttons wouldn't
work.

This owns widgets only; the app owns behaviour and passes callbacks in.
"""
import tkinter as tk

from .. import win32
from . import theme


class Panel:
    def __init__(self, root, settings, decks, actions):
        """actions: dict of name -> callback (play, stop, next, replay, annoy,
        mute, quit, select_deck(index))."""
        self.root = root
        self.s = settings
        self.decks = decks
        self.a = actions
        self.visible = False
        f = theme.ui_font(root)      # the panel is prose, not CJK

        outer = tk.Frame(root, bg=theme.BORDER)
        outer.pack(fill="both", expand=True)
        bar = tk.Frame(outer, bg=theme.BG)
        bar.pack(fill="both", expand=True, padx=1, pady=1)

        title = tk.Label(bar, text="🀄 Chinese Pop", bg=theme.BG, fg=theme.FG,
                         font=(f, 10, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(8, 0))
        self.status_lbl = tk.Label(bar, text="", bg=theme.BG, fg=theme.SUB,
                                   font=(f, 9))
        self.status_lbl.grid(row=0, column=1, columnspan=5, sticky="e",
                             padx=(0, 12), pady=(8, 0))

        # deck list — click one to switch (no cycling)
        deck_box = tk.Frame(bar, bg=theme.BG)
        deck_box.grid(row=1, column=0, columnspan=6, sticky="we", padx=10, pady=2)
        tk.Label(deck_box, text="DECKS", bg=theme.BG, fg=theme.SUB,
                 font=(f, 8, "bold")).pack(anchor="w", padx=2)
        self.deck_labels = []
        for i in range(len(decks)):
            lbl = tk.Label(deck_box, text="", bg=theme.BG, fg=theme.SUB,
                           font=(f, 9, "bold"), cursor="hand2", anchor="w",
                           padx=6, pady=2)
            lbl.pack(fill="x", pady=1)
            lbl.bind("<Button-1>", lambda e, idx=i: self.a["select_deck"](idx))
            self.deck_labels.append(lbl)

        btns = tk.Frame(bar, bg=theme.BG)
        btns.grid(row=2, column=0, columnspan=6, sticky="we", padx=8, pady=(2, 8))
        self.play_btn = self._btn(btns, "▶ Play", self.a["play"], wide=True)
        self.play_btn.pack(side="left", padx=2)
        self._btn(btns, "⏹ Stop", self.a["stop"]).pack(side="left", padx=2)
        self._btn(btns, "⏭ Next", self.a["next"]).pack(side="left", padx=2)
        self._btn(btns, "🔊 Replay", self.a["replay"]).pack(side="left", padx=2)
        self.annoy_btn = self._btn(btns, "😈 Annoy", self.a["annoy"])
        self.annoy_btn.pack(side="left", padx=2)
        self.mute_btn = self._btn(btns, "🔊 Sound", self.a["mute"])
        self.mute_btn.pack(side="left", padx=2)
        self._btn(btns, "⚙", self.a["settings"]).pack(side="left", padx=2)
        self._btn(btns, "📝", self.a["editor"]).pack(side="left", padx=2)
        self._btn(btns, "✕", self.a["quit"]).pack(side="left", padx=2)

        hk = settings.hotkeys
        hint = f"{hk['panel']} hide/show   ·   {hk['mute']} silent"
        if settings.recall_hotkeys:
            hint += f"   ·   {hk['got']} knew it   ·   {hk['miss']} didn't"
        tk.Label(bar, text=hint.title(), bg=theme.BG, fg=theme.SUB,
                 font=(f, 8)).grid(row=3, column=0, columnspan=6, sticky="w",
                                   padx=12, pady=(0, 8))

        for w in (bar, title):        # drag by the title
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

    def _btn(self, parent, text, cmd, wide=False):
        b = tk.Label(parent, text=text, bg=theme.BTN, fg=theme.FG,
                     font=(theme.ui_font(self.root), 9, "bold"),
                     padx=(10 if wide else 8),
                     pady=4, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=theme.BTN_HI))
        b.bind("<Leave>", lambda e: b.configure(bg=theme.BTN))
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
        for i, (lbl, (known, total)) in enumerate(zip(self.deck_labels, counts)):
            name = self.decks[i]["name"]
            if i == deck_index:
                lbl.configure(text=f"▸ {name}  ({known}/{total})",
                              fg=theme.FG, bg=theme.BTN)
            else:
                lbl.configure(text=f"   {name}  ({known}/{total})",
                              fg=theme.SUB, bg=theme.BG)

    def set_status(self, state, interval):
        if state == "running":
            self.play_btn.configure(text="⏸ Pause")
            dot, txt = theme.STATUS_OK, f"Playing · every {interval}s"
        elif state == "paused":
            self.play_btn.configure(text="▶ Play")
            dot, txt = theme.STATUS_WARN, "Paused"
        else:
            self.play_btn.configure(text="▶ Play")
            dot, txt = theme.STATUS_STOP, "Stopped"
        self.status_lbl.configure(text=f"● {txt}", fg=dot)

    def set_annoy(self, on):
        self.annoy_btn.configure(text="😈 Annoy: ON" if on else "😈 Annoy: OFF")

    def set_sound(self, on):
        self.mute_btn.configure(text="🔊 Sound" if on else "🔇 Silent")

    # ---------- visibility ----------
    def place(self, rect=None):
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

    def toggle(self):
        self.hide() if self.visible else self.show()
