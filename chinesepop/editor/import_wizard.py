"""Import wizard: pick a file → map its fields → preview → import.

The mapping step isn't optional politeness: an Anki note's fields are whatever its
notetype called them ("Simplified", "Expression", "Front"), and a CSV's columns are
whatever someone typed. We guess, then show the user exactly what they'll get
before anything is written.
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import decks as decks_mod
from ..importers import anki_import, common, csv_import
from ..logging_setup import get

log = get("editor.import")

NONE = "— none —"
MAPPABLE = [("term", "Term *"), ("reading", "Reading"), ("meaning", "Meaning *"),
            ("note", "Note"), ("tones", "Tones"), ("cat", "Category")]


class ImportWizard(tk.Toplevel):
    def __init__(self, parent, controller, on_done=None):
        super().__init__(parent)
        self.c = controller
        self.on_done = on_done
        self.result = None
        self.mapping_vars = {}
        self.title("Import cards")
        self.geometry("760x560")
        self.transient(parent)
        self.grab_set()
        self.status = tk.StringVar(value="Choose a file to import")
        self._build()
        self._pick_file()

    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.file_lbl = ttk.Label(top, text="No file chosen", font=("", 10, "bold"))
        self.file_lbl.pack(side="left")
        ttk.Button(top, text="Choose file…", command=self._pick_file).pack(side="right")

        # Anki files can hold many decks; let the user narrow it down
        self.deck_row = ttk.Frame(self, padding=(8, 0))
        ttk.Label(self.deck_row, text="Anki deck:").pack(side="left")
        self.src_deck = ttk.Combobox(self.deck_row, state="readonly", width=40)
        self.src_deck.pack(side="left", padx=4)
        self.src_deck.bind("<<ComboboxSelected>>", lambda e: self._reparse())

        mapf = ttk.LabelFrame(self, text="Which column is which?", padding=8)
        mapf.pack(fill="x", padx=8, pady=6)
        for i, (key, label) in enumerate(MAPPABLE):
            ttk.Label(mapf, text=label).grid(row=i // 3, column=(i % 3) * 2,
                                             sticky="w", padx=(0, 4), pady=2)
            var = tk.StringVar(value=NONE)
            cb = ttk.Combobox(mapf, textvariable=var, state="readonly", width=18)
            cb.grid(row=i // 3, column=(i % 3) * 2 + 1, sticky="w", padx=(0, 12), pady=2)
            cb.bind("<<ComboboxSelected>>", lambda e: self._preview())
            self.mapping_vars[key] = (var, cb)

        prevf = ttk.LabelFrame(self, text="Preview (first 8)", padding=6)
        prevf.pack(fill="both", expand=True, padx=8)
        cols = ("term", "reading", "tones", "meaning", "cat")
        self.tree = ttk.Treeview(prevf, columns=cols, show="headings", height=8)
        for c in cols:
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=110 if c != "meaning" else 240, anchor="w")
        self.tree.pack(fill="both", expand=True)

        opts = ttk.Frame(self, padding=(8, 6))
        opts.pack(fill="x")
        self.autofill = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Auto-fill missing reading/tones",
                        variable=self.autofill,
                        command=self._preview).pack(side="left")
        self.gen_audio = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Generate audio after import",
                        variable=self.gen_audio).pack(side="left", padx=10)

        dest = ttk.Frame(self, padding=(8, 0))
        dest.pack(fill="x")
        ttk.Label(dest, text="Into deck:").pack(side="left")
        self.dest = ttk.Combobox(dest, state="readonly", width=32)
        self.dest.pack(side="left", padx=4)
        ttk.Label(dest, text="or new:").pack(side="left")
        self.new_deck = tk.StringVar()
        ttk.Entry(dest, textvariable=self.new_deck, width=22).pack(side="left", padx=4)
        self._refresh_dest()

        btns = ttk.Frame(self, padding=8)
        btns.pack(fill="x")
        self.import_btn = ttk.Button(btns, text="Import", command=self._do_import,
                                     state="disabled")
        self.import_btn.pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w",
                  padding=(6, 3)).pack(fill="x", side="bottom")

    def _refresh_dest(self):
        self.dest["values"] = [d["name"] for d in self.c.decks]

    # ------------------------------ parsing ---------------------------------
    def _pick_file(self):
        path = filedialog.askopenfilename(
            parent=self, title="Import cards",
            filetypes=[("All supported", "*.csv *.tsv *.txt *.apkg *.json"),
                       ("Spreadsheet", "*.csv *.tsv *.txt"),
                       ("Anki deck", "*.apkg"), ("Chinese Pop deck", "*.json")])
        if not path:
            if not self.result:
                self.destroy()
            return
        self.path = Path(path)
        self.file_lbl.configure(text=self.path.name)
        self.deck_row.pack_forget()
        if self.path.suffix.lower() == ".apkg":
            try:
                names = anki_import.list_decks(self.path)
            except anki_import.AnkiImportError as e:
                messagebox.showerror("Can't read this file", str(e), parent=self)
                return
            if names:
                self.deck_row.pack(fill="x", after=self.file_lbl.master)
                self.src_deck["values"] = ["(all decks)"] + names
                self.src_deck.set("(all decks)")
        self._reparse()

    def _reparse(self):
        try:
            if self.path.suffix.lower() == ".apkg":
                pick = self.src_deck.get()
                deck_name = None if pick in ("", "(all decks)") else pick
                self.result = anki_import.parse(self.path, deck_name=deck_name)
            elif self.path.suffix.lower() == ".json":
                self.result = _parse_our_json(self.path)
            else:
                self.result = csv_import.parse(self.path)
        except anki_import.AnkiImportError as e:
            messagebox.showerror("Can't read this file", str(e), parent=self)
            return
        except Exception as e:
            log.exception("import parse failed")
            messagebox.showerror("Can't read this file", str(e), parent=self)
            return

        fields = [NONE] + list(self.result.fields)
        guess = common.guess_mapping(self.result.fields)
        for key, (var, cb) in self.mapping_vars.items():
            cb["values"] = fields
            var.set(guess.get(key, NONE))
        self.status.set(" · ".join(self.result.notes) or
                        f"{len(self.result.rows)} row(s)")
        if not self.new_deck.get():
            self.new_deck.set(self.path.stem.replace("_", " ").title())
        self._preview()

    def _mapping(self):
        return {k: v.get() for k, (v, _) in self.mapping_vars.items()
                if v.get() and v.get() != NONE}

    def _preview(self):
        self.tree.delete(*self.tree.get_children())
        if not self.result:
            return
        mapping = self._mapping()
        if "term" not in mapping:
            self.import_btn.configure(state="disabled")
            self.status.set("Pick which column holds the Term")
            return
        words, report = common.build_words(
            self.result, mapping, autofill=self.autofill.get())
        for w in words[:8]:
            self.tree.insert("", "end", values=(
                w.get("term", ""), w.get("reading", ""), w.get("tones", ""),
                (w.get("meaning", "") or "")[:60], w.get("cat", "")))
        self._words = words
        self.import_btn.configure(state="normal" if words else "disabled")
        msg = f"{report['imported']} card(s) ready"
        if report["skipped_no_term"]:
            msg += f" · {report['skipped_no_term']} row(s) had no term"
        if report["duplicates_in_file"]:
            msg += f" · {report['duplicates_in_file']} duplicate(s) in the file"
        if report["unrecognised_categories"]:
            msg += (f" · {report['unrecognised_categories']} unknown categor(y/ies) "
                    f"dropped")
        self.status.set(msg)

    # ------------------------------ commit ----------------------------------
    def _do_import(self):
        if not getattr(self, "_words", None):
            return
        name = self.new_deck.get().strip()
        deck = None
        if self.dest.get():
            deck = next((d for d in self.c.decks if d["name"] == self.dest.get()), None)
        if deck is None:
            if not name:
                messagebox.showwarning("Where to?", "Choose a deck or name a new one.",
                                       parent=self)
                return
            try:
                deck = self.c.create_deck(name)
            except ValueError as e:
                messagebox.showerror("Couldn't create deck", str(e), parent=self)
                return
        report, added = self.c.import_words(
            deck, self._words, generate_audio=self.gen_audio.get(),
            progress=lambda i, n: self.after(
                0, self.status.set, f"Generating audio… {i}/{n}"))
        if self.on_done:
            self.on_done(deck, report)
        messagebox.showinfo(
            "Imported",
            f"Added {report['added']} card(s) to “{deck['name']}”."
            + (f"\nSkipped {report['skipped_existing']} already in the deck."
               if report["skipped_existing"] else "")
            + ("\n\nAudio is generating in the background."
               if self.gen_audio.get() and added else ""),
            parent=self)
        self.destroy()


def _parse_our_json(path):
    """Importing a deck someone shared with us — just JSON, since audio is
    synthesized locally rather than bundled."""
    import json
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    words = data.get("words", data if isinstance(data, list) else [])
    rows = []
    for w in words:
        rows.append({"term": decks_mod.word_term(w),
                     "reading": decks_mod.word_reading(w),
                     "tones": w.get("tones", ""), "meaning": w.get("meaning", ""),
                     "note": w.get("note", ""), "cat": w.get("cat", "")})
    return common.ImportResult(["term", "reading", "tones", "meaning", "note", "cat"],
                               rows, Path(path).name,
                               [f"{len(rows)} card(s) from a Chinese Pop deck"])
