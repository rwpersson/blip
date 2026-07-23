"""Editor logic, with no Tk in it.

Everything the editor does that could be wrong — validating a card, deciding
whether a term collides, saving, kicking off audio — lives here so it can be
tested without a window. The Tk layer stays dumb.
"""
import threading

from .. import decks as decks_mod
from .. import lang
from ..audio import clips, player, tts
from ..logging_setup import get

log = get("editor")


class EditorController:
    def __init__(self, settings):
        self.s = settings
        self.decks = decks_mod.load_all()

    # ---------- decks ----------
    def deck_by_id(self, deck_id):
        return next((d for d in self.decks if d["id"] == deck_id), None)

    def create_deck(self, name, language="zh-CN"):
        name = (name or "").strip()
        if not name:
            raise ValueError("a deck needs a name")
        deck_id = decks_mod.slugify(name)
        if self.deck_by_id(deck_id):
            raise ValueError(f"a deck called {name!r} already exists")
        deck = decks_mod.create(name, language=language)
        decks_mod.save(deck)
        self.decks.append(deck)
        self.decks.sort(key=lambda d: d["id"])
        return deck

    def delete_deck(self, deck):
        path = deck.get("source")
        if path:
            try:
                path.unlink()
            except Exception:
                log.exception("could not delete %s", path)
                raise
        self.decks = [d for d in self.decks if d is not deck]

    def set_archived(self, deck, archived):
        """Archive/un-archive a deck (the Blipfeed⇄Blip flag). Archived decks stay
        listed here but drop out of the overlay's review rotation next launch."""
        decks_mod.set_archived(deck, archived)
        return deck

    # ---------- cards ----------
    def autofill(self, term, language):
        """(reading, tones) suggestion for the form — never forced on the user."""
        return lang.derive_reading(term, language)

    def duplicate_of(self, term, deck, exclude_id=None):
        """Where else this term already lives, so we can warn instead of silently
        creating a second card for the same word."""
        for d in self.decks:
            for w in d["words"]:
                if decks_mod.word_term(w) != term:
                    continue
                if d is deck and w.get("id") == exclude_id:
                    continue
                return d, w
        return None, None

    def validate_card(self, fields):
        problems = []
        if not (fields.get("term") or "").strip():
            problems.append("Term is required")
        if not (fields.get("meaning") or "").strip():
            problems.append("Meaning is required")
        reading = (fields.get("reading") or "").strip()
        tones = (fields.get("tones") or "").strip()
        if reading and tones:
            n_syl, n_tone = len(reading.split()), len(tones.replace(" ", "").split("-"))
            if n_syl != n_tone:
                problems.append(
                    f"{n_syl} syllable(s) but {n_tone} tone(s) — tone colors will "
                    f"fall back until they match")
        return problems

    def save_card(self, deck, fields, word_id=None):
        """Create or update, then persist the deck. Returns the stored word."""
        data = {k: (v or "").strip() for k, v in fields.items()}
        data = {k: v for k, v in data.items() if v}
        if word_id:
            word = decks_mod.update_word(deck, word_id, data)
            # update_word only sets what's given; clear fields the user emptied
            for k in ("reading", "tones", "note", "alt", "say", "cat"):
                if k not in data:
                    word.pop(k, None)
        else:
            word = decks_mod.add_word(deck, data, autofill=False)
        decks_mod.save(deck)
        return word

    def delete_card(self, deck, word_id):
        ok = decks_mod.delete_word(deck, word_id)
        if ok:
            decks_mod.save(deck)
        return ok

    # ---------- audio ----------
    def card_audio_ready(self, word, deck):
        specs = clips.specs_for(word, self.s, deck)
        return bool(specs) and all(p.exists() and p.stat().st_size
                                   for _k, _t, p, _v, _r in specs)

    def generate_audio_async(self, word, deck, done):
        """Synthesize this card's clips off the UI thread. `done(ok, attempted,
        error)` is called from the worker — the caller marshals back to Tk."""
        def _run():
            try:
                ok, attempted = tts.generate_word(word, self.s, deck)
                done(ok, attempted, None)
            except Exception as e:            # never kill the editor over audio
                log.exception("audio generation failed")
                done(0, 0, e)
        threading.Thread(target=_run, daemon=True).start()

    def play_term(self, word, deck):
        """Preview just the term clip (not the whole word+tones+meaning sequence)."""
        path = clips.paths_for(word, self.s, deck).get(clips.WORD)
        if not path or not path.exists():
            return False
        threading.Thread(target=player.play_file, args=(path,), daemon=True).start()
        return True

    # ---------- import ----------
    def import_words(self, deck, words, generate_audio=True, progress=None):
        """Add parsed words to a deck, skipping ones already there. Returns a report."""
        added, skipped = [], 0
        for w in words:
            try:
                added.append(decks_mod.add_word(deck, w, autofill=False))
            except ValueError:                # duplicate term in this deck
                skipped += 1
        decks_mod.save(deck)
        report = {"added": len(added), "skipped_existing": skipped}
        if generate_audio and added:
            self._generate_many_async(added, deck, progress)
        return report, added

    def _generate_many_async(self, words, deck, progress=None):
        def _run():
            for i, w in enumerate(words, 1):
                try:
                    tts.generate_word(w, self.s, deck)
                except Exception:
                    log.exception("audio failed for %s", decks_mod.word_term(w))
                if progress:
                    progress(i, len(words))
        threading.Thread(target=_run, daemon=True).start()
