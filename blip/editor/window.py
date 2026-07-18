"""The editor window: decks | cards | card form.

An ordinary ttk app — native widgets, takes focus, resizable. None of the overlay's
Win32 trickery belongs here.

Two rules this UI follows:
  * auto-fill is a *suggestion* — it fills empty fields and never overwrites what
    you typed, because pypinyin can disagree with a careful reading;
  * audio never blocks the UI — it's synthesized on a worker with status feedback.
"""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import decks as decks_mod
from .. import win32
from ..logging_setup import get
from .controller import EditorController

log = get("editor.window")

FIELDS = [("term", "Term *"), ("reading", "Reading"), ("tones", "Tones"),
          ("meaning", "Meaning *"), ("note", "Note"), ("alt", "Also"),
          ("say", "Say (TTS override)")]
CATEGORIES = ("", *decks_mod.CATEGORIES)


class EditorWindow:
    def __init__(self, settings):
        self.c = EditorController(settings)
        self.deck = None
        self.word = None            # None => the form is a new card

        self.root = tk.Tk()
        self.root.title("Blip — Deck Editor")
        self.vars = {k: tk.StringVar() for k, _ in FIELDS}
        self.status = tk.StringVar(value="Ready")
        self._build()
        win32.fit_window(self.root, min_w=1040, min_h=620)   # scales with DPI
        self._load_decks()

    # ------------------------------ layout ----------------------------------
    def _build(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="New deck", command=self._new_deck).pack(side="left")
        ttk.Button(bar, text="Import…", command=self._import).pack(side="left", padx=4)
        ttk.Button(bar, text="Export…", command=self._export).pack(side="left")
        ttk.Button(bar, text="Delete deck", command=self._delete_deck).pack(side="left", padx=4)
        ttk.Button(bar, text="Creator decks…",
                   command=self._catalog).pack(side="right")

        panes = ttk.PanedWindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # decks
        left = ttk.Frame(panes)
        ttk.Label(left, text="Decks").pack(anchor="w")
        self.deck_list = tk.Listbox(left, exportselection=False, width=22)
        self.deck_list.pack(fill="both", expand=True)
        self.deck_list.bind("<<ListboxSelect>>", lambda e: self._select_deck())
        panes.add(left, weight=1)

        # cards
        mid = ttk.Frame(panes)
        head = ttk.Frame(mid)
        head.pack(fill="x")
        ttk.Label(head, text="Cards").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self._refresh_cards())
        ttk.Entry(head, textvariable=self.search, width=14).pack(side="right")
        ttk.Label(head, text="Filter:").pack(side="right", padx=(0, 4))
        self.card_list = tk.Listbox(mid, exportselection=False, width=30)
        self.card_list.pack(fill="both", expand=True)
        self.card_list.bind("<<ListboxSelect>>", lambda e: self._select_card())
        ttk.Button(mid, text="+ New card", command=self._new_card).pack(fill="x", pady=(4, 0))
        panes.add(mid, weight=1)

        # form
        right = ttk.Frame(panes, padding=(10, 0))
        self.form_title = ttk.Label(right, text="New card", font=("", 11, "bold"))
        self.form_title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        r = 1
        for key, label in FIELDS:
            ttk.Label(right, text=label).grid(row=r, column=0, sticky="w", pady=2)
            if key == "note":
                # notes are long; give them room
                self.note_text = tk.Text(right, height=4, width=42, wrap="word")
                self.note_text.grid(row=r, column=1, columnspan=2, sticky="we", pady=2)
            else:
                e = ttk.Entry(right, textvariable=self.vars[key], width=44)
                e.grid(row=r, column=1, columnspan=2, sticky="we", pady=2)
                if key == "term":
                    # suggest a reading as soon as they leave the term field
                    e.bind("<FocusOut>", lambda ev: self._autofill(only_empty=True))
            r += 1
        ttk.Label(right, text="Category").grid(row=r, column=0, sticky="w", pady=2)
        self.cat = ttk.Combobox(right, values=CATEGORIES, state="readonly", width=18)
        self.cat.grid(row=r, column=1, sticky="w", pady=2)
        r += 1

        btns = ttk.Frame(right)
        btns.grid(row=r, column=0, columnspan=3, sticky="we", pady=(10, 0))
        ttk.Button(btns, text="Auto-fill", command=lambda: self._autofill(False)).pack(side="left")
        ttk.Button(btns, text="▶ Play", command=self._play).pack(side="left", padx=4)
        ttk.Button(btns, text="Save card", command=self._save).pack(side="left")
        ttk.Button(btns, text="Delete", command=self._delete_card).pack(side="left", padx=4)
        right.columnconfigure(1, weight=1)
        panes.add(right, weight=2)

        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w", padding=(6, 3)).pack(fill="x", side="bottom")

    # ------------------------------ data ------------------------------------
    def _load_decks(self, select_id=None):
        self.deck_list.delete(0, "end")
        for d in self.c.decks:
            self.deck_list.insert("end", f"{d['name']}  ({len(d['words'])})")
        if self.c.decks:
            idx = 0
            if select_id:
                idx = next((i for i, d in enumerate(self.c.decks)
                            if d["id"] == select_id), 0)
            self.deck_list.selection_clear(0, "end")
            self.deck_list.selection_set(idx)
            self._select_deck()

    def _select_deck(self):
        sel = self.deck_list.curselection()
        if not sel:
            return
        self.deck = self.c.decks[sel[0]]
        self._refresh_cards()
        self._new_card()

    def _visible_words(self):
        q = self.search.get().strip().lower()
        words = self.deck["words"] if self.deck else []
        if not q:
            return words
        return [w for w in words
                if q in decks_mod.word_term(w).lower()
                or q in str(w.get("meaning", "")).lower()
                or q in decks_mod.word_reading(w).lower()]

    def _refresh_cards(self):
        self.card_list.delete(0, "end")
        for w in self._visible_words():
            self.card_list.insert(
                "end", f"{decks_mod.word_term(w)} — {w.get('meaning','')[:28]}")

    def _select_card(self):
        sel = self.card_list.curselection()
        if not sel:
            return
        self.word = self._visible_words()[sel[0]]
        self.form_title.configure(text=f"Editing: {decks_mod.word_term(self.word)}")
        self.vars["term"].set(decks_mod.word_term(self.word))
        self.vars["reading"].set(decks_mod.word_reading(self.word))
        for k in ("tones", "meaning", "alt", "say"):
            self.vars[k].set(self.word.get(k, ""))
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", self.word.get("note", ""))
        self.cat.set(self.word.get("cat", ""))
        ready = self.c.card_audio_ready(self.word, self.deck)
        self._say("Audio ready" if ready else "No audio yet — Save to generate it")

    def _new_card(self):
        self.word = None
        self.card_list.selection_clear(0, "end")
        self.form_title.configure(text="New card")
        for v in self.vars.values():
            v.set("")
        self.note_text.delete("1.0", "end")
        self.cat.set("")

    def _fields(self):
        f = {k: v.get() for k, v in self.vars.items()}
        f["note"] = self.note_text.get("1.0", "end").strip()
        f["cat"] = self.cat.get()
        return f

    # ------------------------------ actions ---------------------------------
    def _say(self, msg):
        self.status.set(msg)

    def _autofill(self, only_empty=True):
        if not self.deck:
            return
        term = self.vars["term"].get().strip()
        if not term:
            return
        reading, tones = self.c.autofill(term, self.deck.get("language", "zh-CN"))
        if not reading:
            if not only_empty:
                self._say("No auto-fill available for this deck's language")
            return
        # never clobber what the author typed — pypinyin is a suggestion
        if reading and (not only_empty or not self.vars["reading"].get().strip()):
            self.vars["reading"].set(reading)
        if tones and (not only_empty or not self.vars["tones"].get().strip()):
            self.vars["tones"].set(tones)
        if not only_empty:
            self._say(f"Auto-filled: {reading}" + (f"  ·  {tones}" if tones else ""))

    def _save(self):
        if not self.deck:
            return
        fields = self._fields()
        problems = self.c.validate_card(fields)
        if any(p.endswith("required") for p in problems):
            messagebox.showwarning("Missing fields", "\n".join(problems),
                                   parent=self.root)
            return
        term = fields["term"].strip()
        dup_deck, _ = self.c.duplicate_of(
            term, self.deck, exclude_id=self.word["id"] if self.word else None)
        if dup_deck is not None:
            where = "this deck" if dup_deck is self.deck else f"“{dup_deck['name']}”"
            if not messagebox.askyesno(
                    "Duplicate", f"“{term}” is already in {where}.\nAdd it anyway?",
                    parent=self.root):
                return
            if dup_deck is self.deck:
                return          # decks.add_word would reject it regardless
        try:
            word = self.c.save_card(self.deck, fields, self.word["id"] if self.word else None)
        except ValueError as e:
            messagebox.showerror("Couldn't save", str(e), parent=self.root)
            return
        self.word = word
        self._refresh_cards()
        self._load_deck_counts()
        note = "  (" + "; ".join(problems) + ")" if problems else ""
        self._say(f"Saved “{decks_mod.word_term(word)}” — generating audio…{note}")
        self.c.generate_audio_async(
            word, self.deck,
            lambda ok, att, err: self.root.after(
                0, self._audio_done, decks_mod.word_term(word), ok, att, err))

    def _audio_done(self, term, ok, attempted, err):
        if err:
            self._say(f"Saved “{term}”, but audio failed — check the log "
                      f"(offline?). The card still works, silently.")
        elif attempted == 0:
            self._say(f"Saved “{term}” — audio already existed")
        else:
            self._say(f"Saved “{term}” — {ok}/{attempted} clip(s) generated")

    def _play(self):
        if not self.word:
            self._say("Save the card first, then you can hear it")
            return
        if not self.c.play_term(self.word, self.deck):
            self._say("No audio for this card yet — Save to generate it")

    def _delete_card(self):
        if not (self.word and self.deck):
            return
        term = decks_mod.word_term(self.word)
        if not messagebox.askyesno("Delete card", f"Delete “{term}”?",
                                   parent=self.root):
            return
        self.c.delete_card(self.deck, self.word["id"])
        self._refresh_cards()
        self._load_deck_counts()
        self._new_card()
        self._say(f"Deleted “{term}”")

    def _load_deck_counts(self):
        sel = self.deck_list.curselection()
        self.deck_list.delete(0, "end")
        for d in self.c.decks:
            self.deck_list.insert("end", f"{d['name']}  ({len(d['words'])})")
        if sel:
            self.deck_list.selection_set(sel[0])

    def _new_deck(self):
        name = _ask_string(self.root, "New deck", "Deck name:")
        if not name:
            return
        try:
            deck = self.c.create_deck(name)
        except ValueError as e:
            messagebox.showerror("Couldn't create deck", str(e), parent=self.root)
            return
        self._load_decks(select_id=deck["id"])
        self._say(f"Created “{deck['name']}”")

    def _delete_deck(self):
        if not self.deck:
            return
        if not messagebox.askyesno(
                "Delete deck",
                f"Delete “{self.deck['name']}” and its {len(self.deck['words'])} "
                f"card(s)?\n\nYour progress for it stays in state.json.",
                parent=self.root):
            return
        name = self.deck["name"]
        try:
            self.c.delete_deck(self.deck)
        except Exception:
            messagebox.showerror("Couldn't delete", "See the log.", parent=self.root)
            return
        self.deck = None
        self._load_decks()
        self._say(f"Deleted “{name}”")

    def _export(self):
        if not self.deck:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            initialfile=f"{self.deck['id']}.json",
            filetypes=[("Deck (JSON)", "*.json"), ("Spreadsheet (CSV)", "*.csv")])
        if not path:
            return
        from ..importers import export
        try:
            if path.lower().endswith(".csv"):
                export.to_csv_file(self.deck, path)
            else:
                export.to_json_file(self.deck, path)
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=self.root)
            return
        self._say(f"Exported to {path}  (audio isn't bundled — it's regenerated "
                  f"on the other machine)")

    def _catalog(self):
        # A Toplevel, not a subprocess: the editor already owns a Tk root and
        # both windows want focus, so they can share it (one root per process).
        from ..catalog_ui import CatalogWindow
        CatalogWindow(parent=self.root, on_installed=self._after_catalog)

    def _after_catalog(self, deck_ids):
        self.c.decks = decks_mod.load_all()
        self._load_decks()
        self._say(f"Installed {len(deck_ids)} creator deck(s) — they're in your "
                  "rotation now")

    def _import(self):
        from .import_wizard import ImportWizard
        ImportWizard(self.root, self.c, on_done=self._after_import)

    def _after_import(self, deck, report):
        self.c.decks = decks_mod.load_all()
        self._load_decks(select_id=deck["id"])
        self._say(f"Imported {report['added']} card(s) into “{deck['name']}”"
                  + (f", skipped {report['skipped_existing']} already there"
                     if report["skipped_existing"] else "")
                  + " — generating audio in the background")

    def run(self):
        self.root.mainloop()


def _ask_string(parent, title, prompt):
    from tkinter import simpledialog
    return simpledialog.askstring(title, prompt, parent=parent)
