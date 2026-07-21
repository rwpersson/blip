"""Audio generation must run in the BACKGROUND, after the overlay is up.

Regression guard for a real bug: generating hundreds of clips synchronously
before the window appeared made a fresh launch look hung for minutes — and if
you closed it mid-way nothing was cached, so the next launch started over. The
fix moves generation to a daemon thread; these check it stays there and drives
the panel's progress indicator on and off.

Pure logic — a fake app records the marshalled calls, no Tk root here.
"""
import logging
import threading
import time

from blip import __main__ as main_mod


class _FakeRoot:
    def after(self, _delay, fn, *args):
        fn(*args)                       # run marshalled calls synchronously


class _FakePanel:
    def __init__(self):
        self.gen = []

    def set_generating(self, active):
        self.gen.append(active)


class _FakeApp:
    def __init__(self):
        self.root = _FakeRoot()
        self.panel = _FakePanel()


def _wait_for_gen_thread():
    for _ in range(300):
        if not any(t.name == "audio-gen" and t.is_alive()
                   for t in threading.enumerate()):
            return
        time.sleep(0.01)


def test_generation_runs_off_the_main_thread_and_drives_the_indicator(monkeypatch):
    ran = {}

    def fake_generate(decks, settings, progress=None):
        ran["thread"] = threading.current_thread().name
        for i in (1, 2, 3):
            progress(i, 3, {"id": i})
        return 3, 3

    monkeypatch.setattr(main_mod.tts, "generate", fake_generate)
    app = _FakeApp()
    main_mod._generate_audio_in_background(["deck"], object(), app,
                                           logging.getLogger("test"))
    _wait_for_gen_thread()
    assert ran.get("thread") == "audio-gen", "generation didn't run on the worker"
    assert app.panel.gen[0] is True, "indicator not shown when generation started"
    assert app.panel.gen[-1] is False, "indicator not cleared when generation ended"


def test_nothing_to_generate_shows_no_indicator(monkeypatch):
    monkeypatch.setattr(main_mod.tts, "generate",
                        lambda decks, settings, progress=None: (0, 0))
    app = _FakeApp()
    main_mod._generate_audio_in_background(["deck"], object(), app,
                                           logging.getLogger("test"))
    _wait_for_gen_thread()
    assert True not in app.panel.gen        # never announced when there's no work


def test_a_crash_in_generation_never_escapes_the_worker(monkeypatch):
    def boom(decks, settings, progress=None):
        raise RuntimeError("network died")

    monkeypatch.setattr(main_mod.tts, "generate", boom)
    app = _FakeApp()
    # must not raise on the calling thread, and the worker must swallow it
    main_mod._generate_audio_in_background(["deck"], object(), app,
                                           logging.getLogger("test"))
    _wait_for_gen_thread()                   # thread exits cleanly, no crash
