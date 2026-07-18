"""Test Mode logic: build a multiple-choice quiz from a pool of words.

Pure — no Tk, no I/O, seedable RNG — so it's unit-tested directly. `quiz_ui.py`
renders it. Each Question shows a term (the hanzi); the options are
(reading, meaning) pairs — one correct, the rest distractors sampled from other
words in the pool — and the user picks the one that matches the term.
"""
import random
from dataclasses import dataclass, field

from . import decks as decks_mod
from .text import censor_display

DEFAULT_LENGTH = 20
DEFAULT_OPTIONS = 4


@dataclass
class Question:
    term: str                       # the hanzi shown as the prompt
    options: list                   # list of (reading, meaning) pairs
    answer: int                     # index into options of the correct pair
    deck: str = ""                  # deck name, if known (for a small subtitle)

    @property
    def correct(self):
        return self.options[self.answer]


def answerable(words):
    """Words a quiz can use: they need both a term and a meaning. A reading is
    optional (some cards are latin/emoji), so an option may be meaning-only."""
    return [w for w in words if decks_mod.word_term(w) and w.get("meaning", "").strip()]


def _display(word):
    return (decks_mod.word_reading(word).strip(),
            censor_display(word.get("meaning", "").strip()))


def _make_question(target, pool, n_options, rng):
    correct = _display(target)
    t_mean = target.get("meaning", "").strip().lower()
    seen = {correct}
    distractors = []
    others = [w for w in pool if w is not target]
    rng.shuffle(others)
    for w in others:
        # a distractor with the SAME meaning would make two answers "correct"
        if w.get("meaning", "").strip().lower() == t_mean:
            continue
        opt = _display(w)
        if opt in seen:            # identical display (e.g. shared reading+meaning)
            continue
        seen.add(opt)
        distractors.append(opt)
        if len(distractors) == n_options - 1:
            break
    if not distractors:            # nothing to contrast against — unusable
        return None
    options = distractors + [correct]
    rng.shuffle(options)
    return Question(term=decks_mod.word_term(target), options=options,
                    answer=options.index(correct),
                    deck=target.get("_deck", ""))


def build_quiz(words, length=DEFAULT_LENGTH, n_options=DEFAULT_OPTIONS, seed=None):
    """A list of Question drawn from `words`.

    Targets are distinct (a shuffled slice of the pool, up to `length`). Options
    shrink gracefully: with a 3-word pool you get 3-way questions, not a crash.
    Returns [] if there aren't at least two answerable words to contrast.
    """
    rng = random.Random(seed)
    pool = answerable(words)
    if len(pool) < 2:
        return []
    n_options = max(2, min(n_options, len(pool)))
    order = pool[:]
    rng.shuffle(order)
    questions = []
    for target in order[:length]:
        q = _make_question(target, pool, n_options, rng)
        if q:
            questions.append(q)
    return questions


def tag_deck(deck):
    """Return a deck's words, each shallow-tagged with the deck name so a quiz
    over several decks can show where a card came from. Never mutates the loaded
    words — a filter/edit elsewhere must not see a stray `_deck` key."""
    name = deck.get("name", "")
    return [{**w, "_deck": name} for w in deck.get("words", [])]
