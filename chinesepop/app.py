"""Orchestration: timing, the show/reveal flow, decks, and input.

Owns the state machine; the windows are dumb views and Win32 lives in win32.py.

The show flow, per pop:
  * pick a word (scheduler) -> decide flash/chime -> render -> play audio
  * study-first: a word's FIRST exposure shows the answer immediately (you can't
    recall what you've never seen); the recall-delay only applies from the 2nd
  * annoying mode: weak/new words ALWAYS flash, others flash unpredictably, so
    the pops can't be tuned out. Audio-thread events drive the flash timing.
"""
import queue
import random
import tkinter as tk

from . import decks as decks_mod
from . import hotkeys as hk
from . import scheduler as sched_mod
from . import win32
from .audio import cues, player
from .logging_setup import get
from .ui import theme
from .ui.card import Card
from .ui.flash import Flash
from .ui.panel import Panel

log = get("app")

STOPPED, RUNNING, PAUSED = "stopped", "running", "paused"


class App:
    def __init__(self, decks, settings):
        self.decks = decks
        self.s = settings
        self.state = STOPPED
        self.current = None
        self.annoying = settings.annoying_mode
        self.sound_on = settings.play_audio
        player.set_audio(self.sound_on)

        self._next_job = self._hide_job = self._reveal_job = None
        self._is_new = False
        self._flashing = False
        self._chime_countdown = self._roll_chime()
        self._fx_q = queue.Queue()

        self.deck_index = self._initial_deck()
        d = self.decks[self.deck_index]
        self.sched = sched_mod.Scheduler(d["words"], d["id"], settings)
        sched_mod.save_last_deck(d["id"])

        # focus is handed back to whatever the user was in after launch
        self._prev_fg = win32.foreground_window()

        # the panel IS the root window; card/flash are Toplevels
        self.root = tk.Tk()
        self.root.title("Chinese Pop")
        self.root.overrideredirect(True)
        win32.prevent_focus_steal(self.root)     # BEFORE it first maps
        self.root.attributes("-topmost", True)
        self.root.configure(bg=theme.BORDER)
        self.root.withdraw()
        self._apply_dpi()
        self.rect = win32.monitor_rect(settings.monitor)

        self.panel = Panel(self.root, settings, decks, {
            "play": self.toggle_play, "stop": self.stop, "next": self.next_now,
            "replay": self.replay, "annoy": self.toggle_annoy,
            "mute": self.toggle_mute, "quit": self.quit,
            "select_deck": self.select_deck,
            "settings": self.open_settings, "editor": self.open_editor,
            "catalog": self.open_catalog, "quiz": self.open_quiz,
        })
        self.card = Card(self.root, settings)
        self.flash = Flash(self.root, settings)
        self._bar_h = self.panel.place(self.rect)
        self.panel.set_annoy(self.annoying)
        self.panel.set_sound(self.sound_on)
        self._refresh_decks()

    def _apply_dpi(self):
        """Declaring DPI awareness stops Windows bitmap-stretching us (which is
        what makes the card blurry at 125%/150%), but it also means nothing is
        scaled for us any more — so scale the fonts and pixel sizes ourselves,
        or everything comes out tiny on a HiDPI screen."""
        if not self.s.dpi_aware:
            return
        scale = win32.scale_for_window(self.root)
        self.scale = scale
        if abs(scale - 1.0) < 0.01:
            return
        try:
            # Tk sizes fonts in points; this is pixels-per-point.
            self.root.tk.call("tk", "scaling", win32.dpi_for_window(self.root) / 72.0)
        except tk.TclError:
            log.exception("could not set Tk scaling")
        for key in ("card_width", "margin"):     # pixel dimensions
            self.s.set(key, int(self.s[key] * scale))
        log.info("display scale %.2fx — scaled fonts and card geometry", scale)

    # ---------- decks ----------
    @property
    def deck(self):
        """The active deck — carries its own language/voice, so it must be passed
        to anything that synthesizes or plays audio."""
        return self.decks[self.deck_index]

    def _initial_deck(self):
        if self.s.active_deck:
            for i, d in enumerate(self.decks):
                if d["id"] == self.s.active_deck:
                    return i
        last = sched_mod.last_deck()
        for i, d in enumerate(self.decks):
            if d["id"] == last:
                return i
        return 0

    def _refresh_decks(self):
        state = sched_mod.read_state().get("decks", {})
        counts = []
        for i, d in enumerate(self.decks):
            if i == self.deck_index:
                _, known, total = self.sched.stats()
            else:
                known = sched_mod.deck_known_count(d["id"], self.s.graduate_at, state)
                total = len(d["words"])
            counts.append((known, total))
        self.panel.set_decks(self.deck_index, counts)

    def select_deck(self, index):
        if index == self.deck_index:
            return
        self.deck_index = index
        d = self.decks[index]
        self.sched = sched_mod.Scheduler(d["words"], d["id"], self.s)
        sched_mod.save_last_deck(d["id"])
        self.current = None
        self.hide_card()
        self._refresh_decks()
        log.info("switched to deck %s", d["id"])
        if self.state == RUNNING:
            self._cancel_next()
            self._tick()

    # ---------- cues ----------
    def _roll_chime(self):
        return random.randint(self.s.chime_every_min, self.s.chime_every_max)

    def _chime_due(self):
        """True once per random run of cards — an unpredictable cue can't be
        tuned out the way a per-card one would be."""
        if not self.s.chime_on:
            return False
        self._chime_countdown -= 1
        if self._chime_countdown <= 0:
            self._chime_countdown = self._roll_chime()
            return True
        return False

    # ---------- the pop ----------
    def _show(self, word):
        self._cancel(self._hide_job)
        self._hide_job = None
        self._cancel_reveal()
        self.flash.hide()
        self.current = word

        e = self.sched.exposures(word["id"])
        self._is_new = e <= 1
        weak = e <= self.s.flash_new_until
        self._flashing = self.annoying and (
            weak or random.random() < self.s.flash_prob)
        chiming = self._chime_due()
        _, known, total = self.sched.stats()

        self.card.render_prompt(word, self._is_new, e, known, total)
        if self._flashing:
            # card is filled with the answer but stays hidden until the English
            # read-out; audio events drive the flash.
            self.card.render_answer(word, self.rect)
            self.flash.render(word, self.rect)
            player.play_word(word, self.s, self.deck, on_event=self._fx_emit,
                             chime=chiming)
        else:
            self.card.place(self.rect)
            self.card.show()
            player.play_word(word, self.s, self.deck, chime=chiming)
            if self.s.reveal_quiz and self.s.reveal_delay > 0 and not self._is_new:
                self._reveal_job = self.root.after(
                    int(self.s.reveal_delay * 1000), lambda w=word: self._reveal(w))
            else:
                self.card.render_answer(word, self.rect)

        if self.s.display_seconds > 0:
            self._hide_job = self.root.after(
                self.s.display_seconds * 1000, self.hide_card)

    def _reveal(self, word):
        self._reveal_job = None
        if self.current is word:
            self.card.render_answer(word, self.rect)

    def _tick(self):
        if self.state != RUNNING:
            return
        self._show(self.sched.next())
        self._refresh_decks()
        self._next_job = self.root.after(self.s.interval_seconds * 1000, self._tick)

    # ---------- audio -> UI events ----------
    def _fx_emit(self, kind):
        self._fx_q.put(kind)          # called from the audio thread

    def _poll_fx(self):
        try:
            while True:
                kind = self._fx_q.get_nowait()
                if not self._flashing:
                    continue
                if kind == "word_on":
                    self.card.hide()          # flash replaces the card
                    self.flash.show(self.rect)
                elif kind == "word_off":
                    self.flash.hide()
                elif kind == "english":
                    self.flash.hide()
                    self.card.show()
        except queue.Empty:
            pass
        self.root.after(30, self._poll_fx)

    # ---------- actions ----------
    def toggle_play(self):
        self.pause() if self.state == RUNNING else self.play()

    def play(self):
        self.state = RUNNING
        self._cancel_next()
        self._tick()
        self._status()

    def pause(self):
        if self.state == RUNNING:
            self.state = PAUSED
            self._cancel_next()
            self._status()

    def stop(self):
        self.state = STOPPED
        self._cancel_next()
        self.hide_card()
        self._status()

    def next_now(self):
        self.state = RUNNING
        self._cancel_next()
        self._tick()
        self._status()

    def replay(self):
        if self.current:
            player.play_word(self.current, self.s, self.deck)

    def toggle_annoy(self):
        self.annoying = not self.annoying
        if not self.annoying:
            self.flash.hide()
        self.panel.set_annoy(self.annoying)

    def toggle_mute(self):
        self.sound_on = not self.sound_on
        player.set_audio(self.sound_on)
        self.panel.set_sound(self.sound_on)

    def open_settings(self):
        """Launch Settings as a separate process — it needs focus, and our
        windows must never take it."""
        from .settings_ui import open_settings
        open_settings()

    def open_editor(self):
        import subprocess
        import sys
        from . import paths
        try:
            subprocess.Popen([sys.executable, "-m", "chinesepop.editor"],
                             cwd=str(paths.APP_DIR))
        except Exception:
            log.exception("could not launch the deck editor")

    def open_catalog(self):
        """Browse and install creator decks — its own focus-hungry process."""
        from .catalog_ui import open_catalog
        open_catalog()

    def open_quiz(self):
        """Test Mode — its own focus-hungry process. Pass the current deck so
        'Current deck' in the pool picker means the one being studied.

        Pause the overlay first: the user is switching their attention to the
        quiz, so pops shouldn't keep firing behind it, and a word mid-readout
        should go quiet. They resume with Play when they're done."""
        self.pause()                 # stop scheduling new pops (no-op if not running)
        player.cancel()              # silence a word being read right now
        self.hide_card()             # clear any card still on screen
        from .quiz_ui import open_quiz
        open_quiz(self.decks[self.deck_index]["id"])

    def rate_current(self, got):
        if not self.current:
            return
        self.sched.rate(self.current["id"], got)
        player.play_cue("got" if got else "miss")
        self._refresh_decks()

    def hide_card(self):
        self._cancel(self._hide_job)
        self._hide_job = None
        self._cancel_reveal()
        self.flash.hide()
        self.card.hide()

    def quit(self):
        player.stop()
        self.root.destroy()

    # ---------- plumbing ----------
    def _status(self):
        self.panel.set_status(self.state, self.s.interval_seconds)

    def _cancel(self, job):
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _cancel_next(self):
        self._cancel(self._next_job)
        self._next_job = None

    def _cancel_reveal(self):
        self._cancel(self._reveal_job)
        self._reveal_job = None

    # ---------- hotkeys ----------
    def _poll_hotkey(self):
        try:
            while True:
                hid = self._hotkeys.q.get_nowait()
                if hid == hk.PANEL:
                    self.panel.toggle()
                elif hid == hk.MUTE:
                    self.toggle_mute()
                elif hid == hk.GOT:
                    self.rate_current(True)
                elif hid == hk.MISS:
                    self.rate_current(False)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_hotkey)

    def _check_hotkeys(self):
        """A hotkey another app already owns just fails to register. Say so —
        silently dead shortcuts are the worst kind."""
        dead = [hk.NAMES.get(hid, hid) for hid, ok in self._hotkeys.ok.items()
                if not ok]
        if dead:
            binds = ", ".join(f"{n} ({self.s.hotkeys.get(n, '?')})" for n in dead)
            log.warning("These hotkeys are taken by another app: %s. "
                        "Rebind them in Settings.", binds)
        # Without the panel hotkey there's no way to control or quit, so force
        # the panel visible rather than leaving the user stranded.
        if self._hotkeys.ok.get(hk.PANEL) is False:
            log.warning("panel hotkey unavailable; leaving the panel visible")
            self.panel.show(self.rect)

    def run(self):
        self._status()
        if self._prev_fg:
            self.root.after(80, lambda: win32.set_foreground(self._prev_fg))

        self._hotkeys = hk.HotkeyListener(hk.build(self.s))
        self._hotkeys.start()
        self.root.after(400, self._check_hotkeys)
        self.root.after(80, self._poll_hotkey)
        self.root.after(30, self._poll_fx)

        if self.s.panel_hint_seconds > 0:
            self.panel.show(self.rect)
            self.root.after(int(self.s.panel_hint_seconds * 1000),
                            lambda: self._hotkeys.ok.get(hk.PANEL) is not False
                            and self.panel.hide())
        if self.s.autostart:
            self.root.after(self.s.first_popup_after * 1000, self.play)
        self.root.mainloop()
