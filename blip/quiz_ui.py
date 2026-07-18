"""Test Mode — a multiple-choice quiz window.

Standalone, like the editor/settings/catalog (`python -m blip.quiz_ui
[deck_id]`). Unlike the overlay it *wants* focus — that's the point: the user is
testing themselves, not gaming — so it's an ordinary ttk window in its own
process, and doesn't touch the no-activate invariants.

Three screens on one root, swapped by clearing a container frame:
  1. pick a pool — All decks, or the deck you're currently studying;
  2. the quiz — a term, four (reading + meaning) options, instant feedback;
  3. results — score, and a way back to either the pool or a fresh test.

All quiz construction is in quiz.py (pure, tested); this is the shell.
"""
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import decks as decks_mod
from . import paths, quiz as quiz_mod, scheduler as sched_mod
from . import settings as settings_mod
from . import win32
from .audio import clips, player
from .logging_setup import get, setup

log = get("quiz_ui")


class QuizWindow:
    def __init__(self, current_deck_id=None):
        self.s = settings_mod.load()
        self.decks = decks_mod.apply_filters(decks_mod.load_all(), self.s)
        self.current_id = current_deck_id or sched_mod.last_deck()
        self.questions = []
        self.idx = 0
        self.score = 0
        self.answered = False

        self.root = tk.Tk()
        self.count_var = tk.IntVar(value=int(self.s.get("quiz_length", 20)))
        self.root.title("Blip — Test Mode")
        self.body = ttk.Frame(self.root, padding=16)
        self.body.pack(fill="both", expand=True)

        # a couple of larger fonts for the prompt term and options
        base = tkfont.nametofont("TkDefaultFont").cget("family")
        self.term_font = tkfont.Font(family="Microsoft YaHei UI", size=34, weight="bold")
        self.opt_font = tkfont.Font(family="Microsoft YaHei UI", size=13)
        self.head_font = tkfont.Font(family=base, size=15, weight="bold")

        self._show_pool_picker()     # sizes the window via _fit() (never hard-coded)

    # ---------- helpers ----------
    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _fit(self):
        # Re-fit per screen: the question screen is much taller than the pool or
        # results, and fit_window only resizes (never repositions), so the window
        # grows/shrinks in place without jumping. Modest floor so small screens
        # aren't a sea of whitespace.
        win32.fit_window(self.root, min_w=480, min_h=380)

    def _current_deck(self):
        return next((d for d in self.decks if d["id"] == self.current_id), None)

    # ---------- screen 1: pool ----------
    def _show_pool_picker(self):
        self._clear()
        ttk.Label(self.body, text="Test Mode", font=self.head_font).pack(anchor="w")
        ttk.Label(self.body, foreground="#666", wraplength=440, justify="left",
                  text="You'll see a word and pick its reading and meaning from "
                       "four choices. Choose a pool to test yourself on:").pack(
            anchor="w", pady=(4, 12))

        countrow = ttk.Frame(self.body)
        countrow.pack(fill="x", pady=(0, 12))
        ttk.Label(countrow, text="Number of questions:").pack(side="left")
        ttk.Spinbox(countrow, from_=5, to=200, increment=5, width=6,
                    textvariable=self.count_var).pack(side="left", padx=8)
        ttk.Label(countrow, foreground="#999",
                  text="(capped at the pool size)").pack(side="left")

        all_words = [w for d in self.decks for w in quiz_mod.tag_deck(d)]
        n_all = len(quiz_mod.answerable(all_words))
        ttk.Button(self.body, text=f"All decks   ·   {n_all} words",
                   command=lambda: self._start(all_words)).pack(fill="x", pady=4)

        cur = self._current_deck()
        if cur:
            cur_words = quiz_mod.tag_deck(cur)
            n_cur = len(quiz_mod.answerable(cur_words))
            ttk.Button(self.body,
                       text=f"Current deck: {cur['name']}   ·   {n_cur} words",
                       command=lambda: self._start(cur_words)).pack(fill="x", pady=4)
        else:
            ttk.Label(self.body, foreground="#999",
                      text="(No current deck to test — study one first.)").pack(
                anchor="w", pady=4)

        ttk.Label(self.body, foreground="#888", wraplength=440, justify="left",
                  text="Swears are censored, and hidden entirely if you've turned "
                       "them off in Settings.").pack(anchor="w", pady=(14, 0))
        ttk.Button(self.body, text="Close", command=self.root.destroy).pack(
            side="bottom", anchor="e", pady=(10, 0))
        self._fit()

    # ---------- screen 2: quiz ----------
    def _start(self, words):
        self._last_pool = words          # remembered for "Test again"
        try:
            length = max(1, int(self.count_var.get()))
        except (tk.TclError, ValueError):
            length = quiz_mod.DEFAULT_LENGTH        # blank/garbage spinbox
        self.s.set("quiz_length", length)           # remember for next time
        self.s.save()
        self.questions = quiz_mod.build_quiz(words, length=length, seed=None)
        if not self.questions:
            self._clear()
            ttk.Label(self.body, text="Not enough cards to build a test.",
                      font=self.head_font).pack(anchor="w", pady=10)
            ttk.Label(self.body, foreground="#666",
                      text="A quiz needs at least two cards with meanings.").pack(
                anchor="w")
            ttk.Button(self.body, text="Back", command=self._show_pool_picker).pack(
                anchor="w", pady=10)
            self._fit()
            return
        self.idx = 0
        self.score = 0
        self._show_question()

    def _show_question(self):
        self._clear()
        self.answered = False
        q = self.questions[self.idx]

        top = ttk.Frame(self.body)
        top.pack(fill="x")
        ttk.Label(top, text=f"Question {self.idx + 1} of {len(self.questions)}",
                  foreground="#666").pack(side="left")
        ttk.Label(top, text=f"Score {self.score}", foreground="#666").pack(side="right")
        if q.deck:
            ttk.Label(self.body, text=q.deck, foreground="#999").pack(anchor="w")

        ttk.Label(self.body, text=q.term, font=self.term_font).pack(pady=(14, 4))
        ttk.Label(self.body, foreground="#888",
                  text="Which reading and meaning is right?").pack(pady=(0, 12))

        self.opt_buttons = []
        for i, (reading, meaning) in enumerate(q.options):
            label = f"{reading}\n{meaning}" if reading else meaning
            b = tk.Button(self.body, text=label, font=self.opt_font,
                          justify="left", anchor="w", wraplength=420, padx=12,
                          pady=8, relief="solid", bd=1, cursor="hand2",
                          command=lambda i=i: self._answer(i))
            b.pack(fill="x", pady=3)
            self.opt_buttons.append(b)

        self.feedback = ttk.Label(self.body, text=" ", font=self.head_font)
        self.feedback.pack(anchor="w", pady=(10, 0))
        # Packed now (disabled) so its space is reserved — answering enables it
        # rather than adding a row, so the window doesn't jump mid-question.
        self.next_btn = ttk.Button(self.body, text="Next  ▶", command=self._next,
                                   state="disabled")
        self.next_btn.pack(anchor="e", pady=(8, 0))
        self._fit()

    def _answer(self, chosen):
        if self.answered:
            return
        self.answered = True
        q = self.questions[self.idx]
        for i, b in enumerate(self.opt_buttons):
            b.configure(state="disabled", cursor="arrow")
            if i == q.answer:
                b.configure(disabledforeground="#0a7d0a", bg="#e6f5e6")
            elif i == chosen:
                b.configure(disabledforeground="#b00020", bg="#f7e6e8")
        if chosen == q.answer:
            self.score += 1
            self.feedback.configure(text="✓ Correct", foreground="#0a7d0a")
        else:
            right = q.options[q.answer]
            shown = f"{right[0]} — {right[1]}" if right[0] else right[1]
            self.feedback.configure(text=f"✗  It's  {shown}", foreground="#b00020")
        last = self.idx == len(self.questions) - 1
        self.next_btn.configure(state="normal",
                                text="See results  ▶" if last else "Next  ▶")
        self._play_word(q)               # hear it, right or wrong

    def _play_word(self, q):
        """Play the term's pronunciation once, off the UI thread. Clips are keyed
        by voice, so pass the source deck's voice; a missing clip (never generated,
        offline) is a silent no-op."""
        word = q.word
        if not word:
            return
        try:
            deck = {"voice": word.get("_voice")}
            path = clips.paths_for(word, self.s, deck, paths.audio_dir()).get(clips.WORD)
        except Exception:
            log.exception("could not resolve audio for %s", q.term)
            return
        if path and path.exists():
            threading.Thread(target=player.play_file, args=(path,),
                             daemon=True).start()

    def _next(self):
        if self.idx < len(self.questions) - 1:
            self.idx += 1
            self._show_question()
        else:
            self._show_results()

    # ---------- screen 3: results ----------
    def _show_results(self):
        self._clear()
        n = len(self.questions)
        pct = round(100 * self.score / n) if n else 0
        ttk.Label(self.body, text="Test complete", font=self.head_font).pack(
            anchor="w")
        big = tkfont.Font(family="Segoe UI", size=40, weight="bold")
        ttk.Label(self.body, text=f"{self.score} / {n}", font=big).pack(pady=(16, 0))
        ttk.Label(self.body, text=f"{pct}%", foreground="#666").pack()
        msg = ("Nailed it." if pct == 100 else "Strong." if pct >= 80
               else "Getting there." if pct >= 50 else "Keep at it.")
        ttk.Label(self.body, text=msg, foreground="#888").pack(pady=(6, 18))

        row = ttk.Frame(self.body)
        row.pack()
        ttk.Button(row, text="Test again",
                   command=lambda: self._start_same()).pack(side="left", padx=4)
        ttk.Button(row, text="Change pool",
                   command=self._show_pool_picker).pack(side="left", padx=4)
        ttk.Button(row, text="Close", command=self.root.destroy).pack(side="left", padx=4)
        self._fit()

    def _start_same(self):
        # a fresh test from the same words (new shuffle + distractors)
        self._start(self._last_pool)

    def run(self):
        self.root.mainloop()


def open_quiz(current_deck_id=None):
    """Launch Test Mode as its own process (it wants focus; the overlay must not
    give it up). Passes the current deck so 'Current deck' is meaningful."""
    import subprocess
    args = [sys.executable, "-m", "blip.quiz_ui"]
    if current_deck_id:
        args.append(str(current_deck_id))
    try:
        subprocess.Popen(args, cwd=str(paths.APP_DIR))
        return True
    except Exception:
        log.exception("could not launch Test Mode")
        return False


def main():
    setup()
    paths.ensure_dirs()
    s = settings_mod.load()
    if s.dpi_aware:
        win32.set_dpi_aware()
    deck_id = sys.argv[1] if len(sys.argv) > 1 else None
    QuizWindow(deck_id).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
