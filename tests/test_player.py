"""Fast-mode audio selection — the pure part of the play sequence.

play_word itself spins a thread and drives MCI, but which clips it *chooses* is
pure, so that's tested here: fast mode is word-only and prefers the sped-up clip,
falling back to the normal word until the fast clip has been generated.
"""
from blip.audio import clips, player


def test_normal_mode_plays_word_tones_meaning(tmp_path):
    p = {clips.WORD: tmp_path / "w.mp3",
         clips.TONES: tmp_path / "t.mp3",
         clips.MEANING: tmp_path / "m.mp3"}
    word, tones, meaning = player._select_paths(p, fast=False)
    assert (word, tones, meaning) == (p[clips.WORD], p[clips.TONES], p[clips.MEANING])


def test_fast_mode_is_word_only(tmp_path):
    fast = tmp_path / "wf.mp3"
    fast.write_bytes(b"x")                        # the fast clip exists
    p = {clips.WORD: tmp_path / "w.mp3", clips.WORD_FAST: fast,
         clips.TONES: tmp_path / "t.mp3", clips.MEANING: tmp_path / "m.mp3"}
    word, tones, meaning = player._select_paths(p, fast=True)
    assert word == fast                           # uses the sped-up clip
    assert tones is None and meaning is None       # no tones/meaning in fast mode


def test_fast_mode_falls_back_to_the_normal_word_until_the_fast_clip_exists(tmp_path):
    p = {clips.WORD: tmp_path / "w.mp3",
         clips.WORD_FAST: tmp_path / "missing.mp3"}   # not on disk yet
    word, tones, meaning = player._select_paths(p, fast=True)
    assert word == p[clips.WORD]                   # audible immediately, not silent
    assert tones is None and meaning is None
