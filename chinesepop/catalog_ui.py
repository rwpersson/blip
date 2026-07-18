"""Browse and install the creator decks — a standalone window.

Like the editor and settings, this is its OWN process (`python -m
chinesepop.catalog_ui`): it's an ordinary ttk window that wants focus, the exact
opposite of the overlay's no-activate invariants. Keeping it out of the overlay's
process means it can't regress them.

All the logic is in catalog.py (tested); this is the shell. Installing runs on a
worker thread — synthesizing a 226-word deck's audio hits the network and would
freeze the UI otherwise — and marshals progress back to Tk with after().
"""
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import catalog
from . import paths, settings as settings_mod, win32
from .logging_setup import get, setup

log = get("catalog_ui")

# Human labels for the category dots in a deck's breakdown.
_CAT_LABEL = {"hsk": "HSK", "slang": "slang", "swear": "swears",
              "gaming": "gaming", "idiom": "idioms", "common": "common"}


class CatalogWindow:
    def __init__(self, parent=None, on_installed=None):
        self.s = settings_mod.load()
        self.on_installed = on_installed
        self.owns_root = parent is None
        self.root = tk.Tk() if self.owns_root else tk.Toplevel(parent)
        self.root.title("Chinese Pop — Creator Decks")
        self.status = tk.StringVar(value="")
        self.busy = False
        self._rows = {}                 # deck id -> {button, status label}
        self._build()
        win32.fit_window(self.root, min_w=560, min_h=520)

    # ---------- layout ----------
    def _build(self):
        # Status + action bar packed BEFORE the scrolling list: pack allocates in
        # order, so a bar packed last is the first thing squeezed off-screen.
        self.status_lbl = ttk.Label(self.root, textvariable=self.status,
                                    relief="sunken", anchor="w", padding=(6, 3))
        self.status_lbl.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(self.root, mode="determinate")

        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.pack(fill="x", side="bottom")
        self.install_all_btn = ttk.Button(bar, text="Install all",
                                          command=self._install_all)
        self.install_all_btn.pack(side="left")
        ttk.Button(bar, text="Close", command=self._close).pack(side="right")

        head = ttk.Frame(self.root, padding=(12, 12, 12, 4))
        head.pack(fill="x")
        ttk.Label(head, text="Creator decks",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(head, foreground="#666", wraplength=520, justify="left",
                  text="Curated decks you can add to your rotation. Installing "
                       "copies the deck in and generates its audio (needs a "
                       "connection the first time). Remove any you don't want.").pack(
            anchor="w", pady=(2, 0))

        # scrolling list of deck cards
        outer = ttk.Frame(self.root, padding=(8, 4, 8, 8))
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.list_frame = ttk.Frame(canvas)
        self.list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._win = canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(self._win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        self._populate()

    def _populate(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._rows.clear()
        entries = catalog.entries()
        if not entries:
            ttk.Label(self.list_frame, foreground="#666",
                      text="No creator decks are bundled with this build.").pack(
                anchor="w", padx=4, pady=8)
            self.install_all_btn.state(["disabled"])
            return
        any_missing = False
        for e in entries:
            any_missing = any_missing or not e.installed
            self._deck_card(e)
        self.install_all_btn.state(["!disabled" if any_missing else "disabled"])

    def _deck_card(self, e):
        card = ttk.Frame(self.list_frame, relief="solid", borderwidth=1,
                         padding=10)
        card.pack(fill="x", padx=4, pady=4)
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text=e.name,
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        breakdown = "  ·  ".join(f"{n} {_CAT_LABEL.get(c, c)}"
                                 for c, n in e.categories.items())
        ttk.Label(card, text=f"{e.word_count} words", foreground="#444").grid(
            row=0, column=0, sticky="e")
        ttk.Label(card, text=breakdown, foreground="#666").grid(
            row=1, column=0, sticky="w", pady=(2, 0))
        preview = "  ".join(e.sample)
        if e.word_count > len(e.sample):
            preview += "  …"
        ttk.Label(card, text=preview, font=("Microsoft YaHei UI", 11),
                  foreground="#333").grid(row=2, column=0, sticky="w", pady=(4, 0))

        btns = ttk.Frame(card)
        btns.grid(row=0, column=1, rowspan=3, sticky="e", padx=(8, 0))
        state = ttk.Label(btns, text="", foreground="#2a7d2a")
        state.pack(side="top")
        btn = ttk.Button(btns, width=11)
        btn.pack(side="top", pady=(4, 0))
        self._rows[e.id] = {"btn": btn, "state": state}
        self._set_row(e.id, e.installed)

    def _set_row(self, deck_id, installed):
        row = self._rows[deck_id]
        if installed:
            row["state"].configure(text="✓ installed")
            row["btn"].configure(text="Remove",
                                 command=lambda i=deck_id: self._remove(i))
        else:
            row["state"].configure(text="")
            row["btn"].configure(text="Install",
                                 command=lambda i=deck_id: self._install(i))

    # ---------- actions ----------
    def _install(self, deck_id):
        self._run_install([deck_id], f"Installing {deck_id}…")

    def _install_all(self):
        missing = [e.id for e in catalog.entries() if not e.installed]
        if not missing:
            return
        self._run_install(missing, f"Installing {len(missing)} decks…")

    def _run_install(self, deck_ids, msg):
        if self.busy:
            return
        self.busy = True
        self._set_busy(True)
        self.status.set(msg)
        self.progress.pack(fill="x", side="bottom", before=self.status_lbl)
        self.progress.configure(value=0, maximum=1)

        def worker():
            done = []
            try:
                for deck_id in deck_ids:
                    catalog.install(deck_id, self.s, progress=self._on_progress)
                    done.append(deck_id)
            except Exception as ex:                 # never leave the UI wedged
                log.exception("install failed")
                self.root.after(0, self._install_done, done, ex)
                return
            self.root.after(0, self._install_done, done, None)

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, i, total, word):
        # Called from the worker thread; hop to Tk before touching widgets.
        self.root.after(0, self._show_progress, i, total)

    def _show_progress(self, i, total):
        self.progress.configure(value=i, maximum=max(total, 1))
        self.status.set(f"Generating audio… {i}/{total}")

    def _install_done(self, done, err):
        self.progress.pack_forget()
        self.busy = False
        self._set_busy(False)
        for deck_id in done:
            if deck_id in self._rows:
                self._set_row(deck_id, True)
        self._refresh_install_all()
        if err:
            self.status.set("Install finished with an error — check the log. "
                            "Decks were added; audio can fill in on next launch.")
        elif done:
            # The running overlay loaded its decks at startup and won't hot-reload,
            # so be honest rather than imply an instant switch.
            self.status.set(f"Installed {len(done)} deck(s) — they'll be in your "
                            "rotation next time Chinese Pop starts.")
        if done and self.on_installed:
            self.on_installed(done)

    def _remove(self, deck_id):
        name = next((e.name for e in catalog.entries() if e.id == deck_id), deck_id)
        if not messagebox.askyesno(
                "Remove deck",
                f"Remove “{name}” from your decks?\n\nYour progress on it stays in "
                "state.json, and you can reinstall it any time.",
                parent=self.root):
            return
        if catalog.uninstall(deck_id):
            self._set_row(deck_id, False)
            self._refresh_install_all()
            self.status.set(f"Removed “{name}”.")

    def _refresh_install_all(self):
        any_missing = any(not e.installed for e in catalog.entries())
        self.install_all_btn.state(["!disabled" if any_missing else "disabled"])

    def _set_busy(self, busy):
        state = "disabled" if busy else "!disabled"
        self.install_all_btn.state([state])
        for row in self._rows.values():
            row["btn"].state([state])

    def _close(self):
        if self.busy and not messagebox.askyesno(
                "Still installing", "Audio is still generating. Close anyway?",
                parent=self.root):
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def open_catalog():
    """Launch the catalog browser as its own process (focus-hungry ttk window;
    the overlay's windows must stay no-activate, so never a Toplevel of it)."""
    import subprocess
    try:
        subprocess.Popen([sys.executable, "-m", "chinesepop.catalog_ui"],
                         cwd=str(paths.APP_DIR))
        return True
    except Exception:
        log.exception("could not launch the catalog window")
        return False


def main():
    setup()
    paths.ensure_dirs()
    s = settings_mod.load()
    if s.dpi_aware:
        win32.set_dpi_aware()           # before any window, or the text is blurry
    CatalogWindow().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
