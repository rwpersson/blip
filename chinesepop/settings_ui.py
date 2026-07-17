"""Settings window — the change that makes this a product rather than a script.

Standalone (`python -m chinesepop.settings_ui`) and launchable from the overlay
panel and the editor. Standalone for the same reason the editor is: it's an
ordinary window that wants focus, and the overlay's windows must never take it.

The form is **spec-driven** — SPEC below is the single list of what's tunable, so
adding a setting means adding one line here and one default in settings.py, not
writing widget code.
"""
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from . import decks as decks_mod
from . import hotkeys as hk
from . import paths, settings as settings_mod, win32
from .logging_setup import get, setup

log = get("settings_ui")

# (key, label, kind, extra, help)
#   kind: int | float | bool | str | choice | hotkey
SPEC = [
    ("Timing", [
        ("interval_seconds", "Seconds between words", "int", (5, 600),
         "How often a card pops up."),
        ("display_seconds", "Card stays for (0 = until next)", "int", (0, 120), ""),
        ("first_popup_after", "First card after (s)", "int", (0, 120), ""),
        ("autostart", "Start automatically on launch", "bool", None, ""),
    ]),
    ("Audio", [
        ("play_audio", "Sound on at launch", "bool", None,
         "Toggle any time with the panel or Ctrl+Alt+M."),
        ("word_repeats", "Say the word this many times", "int", (1, 6), ""),
        ("say_tones", "Read the tones aloud", "bool", None, ""),
        ("say_meaning", "Read the meaning aloud", "bool", None,
         "Lets you learn with your eyes on the game."),
        ("repeat_gap", "Gap between repeats (s)", "float", (0.0, 3.0), ""),
        ("voice", "Voice (word)", "str", None,
         "Changing this re-synthesizes the affected clips on next launch."),
        ("rate", "Speed (word)", "str", None, "e.g. -15% — slower is clearer."),
        ("tones_voice", "Voice (tone read-out)", "str", None, ""),
        ("meaning_voice", "Voice (meaning)", "str", None, ""),
    ]),
    ("Learning", [
        ("active_set_size", "Words in progress at once", "int", (1, 60),
         "Smaller = more repetition of fewer words = faster memorising."),
        ("graduate_at", "Exposures before 'learned'", "int", (1, 40), ""),
        ("reveal_quiz", "Hide the answer briefly (recall beat)", "bool", None,
         "You try to recall before it reveals. Skipped on a word's first sight."),
        ("reveal_delay", "Hide the answer for (s)", "float", (0.5, 10.0), ""),
    ]),
    ("Attention", [
        ("chime_on", "Play an attention chime", "bool", None,
         "Fires after a random run of cards, with a random sound, so you can't "
         "tune it out."),
        ("chime_every_min", "…at soonest, every N cards", "int", (1, 30), ""),
        ("chime_every_max", "…at latest, every N cards", "int", (1, 60), ""),
        ("annoying_mode", "Fullscreen flash (annoying mode)", "bool", None, ""),
        ("flash_prob", "Chance a normal card flashes", "float", (0.0, 1.0), ""),
        ("flash_new_until", "Always flash words seen ≤ N times", "int", (0, 20),
         "Puts the flashes where the learning is."),
        ("annoy_text_alpha", "Flash text opacity", "float", (0.1, 1.0), ""),
        ("annoy_hanzi_frac", "Flash size (share of screen width)", "float",
         (0.2, 1.0), ""),
    ]),
    ("Appearance", [
        ("card_width", "Card width (px)", "int", (200, 1200), ""),
        ("card_alpha", "Card panel opacity", "float", (0.1, 1.0),
         "The panel only — the text stays solid."),
        ("card_radius", "Corner rounding (px, 0 = square)", "int", (0, 40), ""),
        ("margin", "Margin from screen edge (px)", "int", (0, 300), ""),
        ("hanzi_size", "Term size", "int", (12, 160), ""),
        ("pinyin_size", "Reading size", "int", (8, 80), ""),
        ("halo_thickness", "Outline thickness", "int", (0, 6),
         "The dark halo that keeps text readable over any game."),
        ("font", "Term font", "str", None,
         "Must include the language's glyphs. Prose uses the system UI font."),
    ]),
    ("Display", [
        ("dpi_aware", "Sharp text on scaled displays", "bool", None,
         "Off = Windows stretches the overlay and it looks blurry."),
        ("monitor", "Show the overlay on", "choice", "monitors", ""),
    ]),
    ("Content", [
        ("hide_swears", "Hide swear words", "bool", None,
         "Skips the whole 'swear' category."),
        ("enabled_decks", "Decks in rotation", "decks", None,
         "Nothing ticked = all decks."),
    ]),
    ("Hotkeys", [
        ("panel", "Show/hide panel", "hotkey", None, ""),
        ("mute", "Silent mode", "hotkey", None, ""),
        ("got", "I knew it", "hotkey", None, ""),
        ("miss", "I didn't know it", "hotkey", None, ""),
    ]),
]


class SettingsWindow:
    def __init__(self, parent=None, on_saved=None):
        self.s = settings_mod.load()
        self.on_saved = on_saved
        self.vars = {}
        self.deck_vars = {}
        self.owns_root = parent is None
        self.root = tk.Tk() if self.owns_root else tk.Toplevel(parent)
        self.root.title("Chinese Pop — Settings")
        self.status = tk.StringVar(value="Changes apply next time Chinese Pop starts")
        self._monitors = win32.monitors()
        self._build()
        # never hard-code: DPI scaling makes a hand-picked size clip (see fit_window)
        win32.fit_window(self.root, min_w=580, min_h=560)

    def _build(self):
        # Status bar and buttons are packed BEFORE the notebook: pack allocates in
        # order, so anything packed after expanding content is what gets clipped.
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w",
                  padding=(6, 3)).pack(fill="x", side="bottom")
        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self._close).pack(side="right", padx=4)
        ttk.Button(bar, text="Restore defaults",
                   command=self._defaults).pack(side="left")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        for group, items in SPEC:
            tab = ttk.Frame(nb, padding=10)
            nb.add(tab, text=group)
            self._build_group(tab, group, items)

    def _build_group(self, tab, group, items):
        for r, (key, label, kind, extra, helptext) in enumerate(items):
            ttk.Label(tab, text=label).grid(row=r * 2, column=0, sticky="w", pady=(4, 0))
            widget = self._make_widget(tab, group, key, kind, extra)
            widget.grid(row=r * 2, column=1, sticky="w", padx=8, pady=(4, 0))
            if helptext:
                ttk.Label(tab, text=helptext, foreground="#666",
                          wraplength=460, justify="left").grid(
                    row=r * 2 + 1, column=0, columnspan=2, sticky="w")
        tab.columnconfigure(1, weight=1)

    def _make_widget(self, tab, group, key, kind, extra):
        is_hotkey = kind == "hotkey"
        current = (self.s.hotkeys.get(key, "") if is_hotkey else self.s.get(key))

        if kind == "bool":
            var = tk.BooleanVar(value=bool(current))
            self.vars[key] = (var, kind)
            return ttk.Checkbutton(tab, variable=var)

        if kind == "decks":
            frame = ttk.Frame(tab)
            enabled = set(self.s.get("enabled_decks") or [])
            for d in decks_mod.load_all():
                v = tk.BooleanVar(value=d["id"] in enabled)
                self.deck_vars[d["id"]] = v
                ttk.Checkbutton(frame, text=f"{d['name']} ({len(d['words'])})",
                                variable=v).pack(anchor="w")
            return frame

        if kind == "choice" and extra == "monitors":
            names = [f"{i}: {m['width']}×{m['height']}"
                     + (" (primary)" if m["primary"] else "")
                     for i, m in enumerate(self._monitors)]
            var = tk.StringVar(value=names[min(int(current or 0), len(names) - 1)])
            self.vars[key] = (var, "monitor")
            cb = ttk.Combobox(tab, textvariable=var, values=names, state="readonly",
                              width=26)
            return cb

        if kind in ("int", "float"):
            var = tk.StringVar(value=str(current))
            self.vars[key] = (var, kind)
            lo, hi = extra
            return ttk.Spinbox(tab, textvariable=var, from_=lo, to=hi, width=10,
                               increment=1 if kind == "int" else 0.05)

        var = tk.StringVar(value=str(current or ""))
        self.vars[key] = (var, "hotkey" if is_hotkey else "str")
        row = ttk.Frame(tab)
        ttk.Entry(row, textvariable=var, width=26).pack(side="left")
        if is_hotkey:
            # A binding another app owns just fails silently at registration, so
            # let people find that out here rather than wondering why F13 does
            # nothing mid-game.
            lbl = ttk.Label(row, text="")
            lbl.pack(side="left", padx=6)
            ttk.Button(row, text="Test",
                       command=lambda k=key, v=var, l=lbl: self._test_hotkey(v, l)
                       ).pack(side="left")
        return row

    def _test_hotkey(self, var, label):
        spec = var.get().strip()
        try:
            hk.parse(spec)
        except ValueError as e:
            label.configure(text="invalid", foreground="#b00")
            self.status.set(str(e))
            return
        if hk.is_available(spec):
            label.configure(text="available ✓", foreground="#070")
            self.status.set(f"{spec} is free to use")
        else:
            label.configure(text="in use ✗", foreground="#b00")
            self.status.set(f"{spec} is already taken by another app — pick another")

    # ------------------------------ save ------------------------------------
    def _collect(self):
        out, hotkeys, problems = {}, dict(self.s.hotkeys), []
        for key, (var, kind) in self.vars.items():
            raw = var.get()
            try:
                if kind == "bool":
                    out[key] = bool(raw)
                elif kind == "int":
                    out[key] = int(float(raw))
                elif kind == "float":
                    out[key] = float(raw)
                elif kind == "monitor":
                    out[key] = int(str(raw).split(":")[0])
                elif kind == "hotkey":
                    spec = str(raw).strip()
                    if spec:
                        hk.parse(spec)          # raises if nonsense
                    hotkeys[key] = spec
                else:
                    out[key] = str(raw)
            except ValueError:
                problems.append(f"{key}: {raw!r} isn't valid")
        out["hotkeys"] = hotkeys
        out["enabled_decks"] = [i for i, v in self.deck_vars.items() if v.get()]
        return out, problems

    def _save(self):
        values, problems = self._collect()
        if problems:
            messagebox.showerror("Can't save", "\n".join(problems), parent=self.root)
            return
        if values["chime_every_min"] > values["chime_every_max"]:
            messagebox.showerror("Can't save",
                                 "Chime 'soonest' must not exceed 'latest'.",
                                 parent=self.root)
            return
        for key, value in values.items():
            self.s.set(key, value)

        dupes = hk.conflicts(self.s)
        if dupes:
            first = next(iter(dupes.items()))
            if not messagebox.askyesno(
                    "Duplicate hotkey",
                    f"{first[0]} is bound to {' and '.join(first[1])}.\n"
                    f"Only one will work. Save anyway?", parent=self.root):
                return
        self.s.save()
        log.info("settings saved to %s", paths.settings_file())
        if self.on_saved:
            self.on_saved(self.s)
        messagebox.showinfo(
            "Saved", "Settings saved.\n\nRestart Chinese Pop for them to take effect.",
            parent=self.root)
        self._close()

    def _defaults(self):
        if not messagebox.askyesno("Restore defaults",
                                   "Reset every setting to its default?",
                                   parent=self.root):
            return
        self.s = settings_mod.Settings()
        self.s.save()
        messagebox.showinfo("Restored", "Defaults restored. Reopen Settings to see "
                                        "them.", parent=self.root)
        self._close()

    def _close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def open_settings():
    """Launch Settings as its own process.

    The overlay calls this rather than opening a Toplevel: its windows are
    no-activate by design, and a settings dialog needs focus. Separate processes
    keep that contradiction from ever biting.
    """
    try:
        subprocess.Popen([sys.executable, "-m", "chinesepop.settings_ui"],
                         cwd=str(paths.APP_DIR))
        return True
    except Exception:
        log.exception("could not launch the settings window")
        return False


def main():
    setup()
    paths.ensure_dirs()
    s = settings_mod.load()
    if s.dpi_aware:
        win32.set_dpi_aware()       # before any window, or the text is blurry
    SettingsWindow().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
