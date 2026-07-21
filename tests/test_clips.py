"""Content-addressed audio.

These pin the properties that make user-authored and imported decks safe:
ids no longer decide filenames, identical speech shares one file, and changing a
voice re-keys instead of serving stale audio.
"""
from blip.audio import clips


def test_key_is_stable_and_depends_on_everything_spoken():
    a = clips.clip_key("你好", "v1", "-15%")
    assert a == clips.clip_key("你好", "v1", "-15%")          # deterministic
    assert a != clips.clip_key("你好吗", "v1", "-15%")        # text
    assert a != clips.clip_key("你好", "v2", "-15%")          # voice
    assert a != clips.clip_key("你好", "v1", "-10%")          # rate


def test_same_word_different_ids_shares_one_clip(settings, tmp_path):
    """The point: an authored/imported card with a foreign id must not get its
    own duplicate audio, and must not collide with anyone else's."""
    a = {"id": "01", "term": "牛逼", "meaning": "awesome"}
    b = {"id": "9999-anki-import", "term": "牛逼", "meaning": "awesome"}
    pa = clips.paths_for(a, settings, audio_dir=tmp_path)
    pb = clips.paths_for(b, settings, audio_dir=tmp_path)
    assert pa == pb


def test_different_words_sharing_an_id_do_not_collide(settings, tmp_path):
    """Two users both author id 421 — the old id-keyed scheme served them each
    other's audio. Content addressing makes that impossible."""
    a = {"id": "421", "term": "牛逼", "meaning": "awesome"}
    b = {"id": "421", "term": "加油", "meaning": "go for it"}
    pa = clips.paths_for(a, settings, audio_dir=tmp_path)
    pb = clips.paths_for(b, settings, audio_dir=tmp_path)
    assert pa[clips.WORD] != pb[clips.WORD]


def test_filename_does_not_contain_the_id(settings, tmp_path):
    w = {"id": "12345", "term": "牛逼", "meaning": "awesome"}
    p = clips.paths_for(w, settings, audio_dir=tmp_path)
    assert "12345" not in p[clips.WORD].name


def test_deck_voice_overrides_the_default(settings, tmp_path):
    """Decks carry their own language, so a deck voice must re-key the clip."""
    w = {"id": "1", "term": "猫", "meaning": "cat"}
    default = clips.paths_for(w, settings, audio_dir=tmp_path)
    jp = clips.paths_for(w, settings, {"voice": "ja-JP-KeitaNeural"},
                         audio_dir=tmp_path)
    assert default[clips.WORD] != jp[clips.WORD]


def test_changing_voice_rekeys(settings, tmp_path):
    w = {"id": "1", "term": "牛逼", "meaning": "awesome"}
    before = clips.paths_for(w, settings, audio_dir=tmp_path)[clips.WORD]
    settings.set("voice", "zh-CN-YunxiNeural")
    after = clips.paths_for(w, settings, audio_dir=tmp_path)[clips.WORD]
    assert before != after


def test_say_override_drives_the_audio(settings, tmp_path):
    """666 must be spoken as 六六六 — the clip follows `say`, not the term."""
    w = {"id": "1", "term": "666", "say": "六六六", "meaning": "nice"}
    spoken = {"id": "2", "term": "六六六", "meaning": "nice"}
    assert (clips.paths_for(w, settings, audio_dir=tmp_path)[clips.WORD]
            == clips.paths_for(spoken, settings, audio_dir=tmp_path)[clips.WORD])


def test_meaning_clip_uses_the_censored_text(settings, tmp_path):
    """The spoken meaning must key off the censored text, or the swear would be
    synthesized and cached."""
    swear = {"id": "1", "term": "王八蛋", "meaning": "bastard"}
    clean = {"id": "2", "term": "x", "meaning": "scoundrel"}
    assert (clips.paths_for(swear, settings, audio_dir=tmp_path)[clips.MEANING]
            == clips.paths_for(clean, settings, audio_dir=tmp_path)[clips.MEANING])


def test_disabled_readouts_produce_no_clip(settings, tmp_path):
    w = {"id": "1", "term": "牛逼", "tones": "2-1", "meaning": "awesome"}
    assert clips.TONES in clips.paths_for(w, settings, audio_dir=tmp_path)
    settings.set("say_tones", False)
    settings.set("say_meaning", False)
    p = clips.paths_for(w, settings, audio_dir=tmp_path)
    assert clips.TONES not in p and clips.MEANING not in p
    assert clips.WORD in p


def test_orphans_finds_stale_clips_after_a_voice_change(settings, tmp_path):
    deck = {"id": "d", "voice": None,
            "words": [{"id": "1", "term": "牛逼", "meaning": "awesome"}]}
    before = clips.paths_for(deck["words"][0], settings, deck, tmp_path)
    for name in clips.expected_files([deck], settings, tmp_path):
        (tmp_path / name).write_bytes(b"x")
    assert clips.orphans([deck], settings, tmp_path) == []

    # Changing the CHINESE voice re-keys only the word clip; the English
    # meaning read-out uses meaning_voice and stays valid — so a voice change
    # costs one clip per word, not a full rebuild.
    settings.set("voice", "zh-CN-SomeOtherNeural")
    stale = clips.orphans([deck], settings, tmp_path)
    assert [p.name for p in stale] == [before[clips.WORD].name]

    after = clips.paths_for(deck["words"][0], settings, deck, tmp_path)
    assert after[clips.MEANING] == before[clips.MEANING]     # untouched
    assert after[clips.WORD] != before[clips.WORD]           # re-keyed


def test_fast_mode_adds_a_faster_word_clip_only_when_enabled(settings, tmp_path):
    """Fast mode speaks the word at a quicker rate — a separate content-addressed
    clip, generated only when fast mode is on so it costs nothing otherwise."""
    w = {"id": "1", "term": "你好", "reading": "nǐ hǎo", "tones": "3-3",
         "meaning": "hi"}
    assert clips.WORD_FAST not in clips.paths_for(w, settings, audio_dir=tmp_path)

    settings.set("fast_mode", True)
    paths = clips.paths_for(w, settings, audio_dir=tmp_path)
    assert clips.WORD_FAST in paths
    # a distinct file from the normal word (different rate -> different hash)
    assert paths[clips.WORD_FAST] != paths[clips.WORD]
    # and it's the rate fast mode declares
    assert paths[clips.WORD_FAST] == clips.clip_path(
        "你好", settings.voice, settings.fast_rate, tmp_path)
