"""Test Mode quiz builder — the logic, deterministic via seed."""
from blip import quiz


def _w(term, reading, meaning, cat="common", wid=None):
    return {"id": wid or term, "term": term, "reading": reading, "tones": "",
            "cat": cat, "meaning": meaning, "note": ""}


POOL = [
    _w("甲", "jiǎ", "first"),
    _w("乙", "yǐ", "second"),
    _w("丙", "bǐng", "third"),
    _w("丁", "dīng", "fourth"),
    _w("戊", "wù", "fifth"),
    _w("己", "jǐ", "sixth"),
]


def test_every_question_is_well_formed():
    qs = quiz.build_quiz(POOL, length=6, n_options=4, seed=1)
    assert len(qs) == 6
    for q in qs:
        assert len(q.options) == 4
        assert 0 <= q.answer < 4
        # the correct option's meaning matches the prompt term
        target = next(w for w in POOL if w["term"] == q.term)
        assert q.correct == (target["reading"], target["meaning"])
        # no duplicate options
        assert len(set(q.options)) == 4


def test_length_caps_the_number_of_questions():
    qs = quiz.build_quiz(POOL, length=3, seed=1)
    assert len(qs) == 3
    # distinct targets
    assert len({q.term for q in qs}) == 3


def test_options_shrink_when_the_pool_is_small():
    small = POOL[:3]
    qs = quiz.build_quiz(small, length=3, n_options=4, seed=2)
    assert qs and all(len(q.options) == 3 for q in qs)   # 3 words -> 3 options


def test_pool_too_small_yields_no_quiz():
    assert quiz.build_quiz(POOL[:1]) == []
    assert quiz.build_quiz([]) == []


def test_words_without_a_meaning_are_skipped():
    pool = POOL + [_w("空", "kōng", "   ")]      # blank meaning
    qs = quiz.build_quiz(pool, length=20, seed=3)
    assert all(q.term != "空" for q in qs)                  # never a prompt
    assert all(("kōng", "") not in q.options for q in qs)   # never an option


def test_distractors_never_share_the_targets_meaning():
    # two words with the SAME meaning must not both appear as pickable "correct"
    pool = [_w("好", "hǎo", "good"), _w("良", "liáng", "good"),
            _w("坏", "huài", "bad"), _w("恶", "è", "evil"), _w("优", "yōu", "fine")]
    qs = quiz.build_quiz(pool, length=20, n_options=4, seed=4)
    for q in qs:
        target_meaning = q.correct[1]
        same = [o for o in q.options if o[1] == target_meaning]
        assert len(same) == 1, "an option duplicates the correct meaning"


def test_swear_meanings_are_censored_in_options():
    pool = [_w("X", "x", "fuck you", cat="swear"),
            _w("Y", "y", "hello"), _w("Z", "z", "goodbye"), _w("W", "w", "thanks")]
    qs = quiz.build_quiz(pool, length=20, seed=5)
    joined = " ".join(m for q in qs for _r, m in q.options)
    assert "fuck" not in joined.lower()
    assert "f***" in joined


def test_seed_is_deterministic():
    a = quiz.build_quiz(POOL, seed=7)
    b = quiz.build_quiz(POOL, seed=7)
    assert [(q.term, q.options, q.answer) for q in a] == \
           [(q.term, q.options, q.answer) for q in b]


def test_tag_deck_does_not_mutate_the_source():
    deck = {"name": "Wk", "voice": "some-voice", "words": [_w("甲", "jiǎ", "first")]}
    tagged = quiz.tag_deck(deck)
    assert tagged[0]["_deck"] == "Wk"
    assert tagged[0]["_voice"] == "some-voice"    # for locating audio
    assert "_deck" not in deck["words"][0]        # original untouched
    assert "_voice" not in deck["words"][0]


def test_question_carries_its_source_word_for_audio():
    """Test Mode plays the term on reveal, so each Question must reference the
    word it was built from (with the deck's voice tag)."""
    deck = {"name": "Wk", "voice": None,
            "words": [_w("甲", "jiǎ", "first"), _w("乙", "yǐ", "second"),
                      _w("丙", "bǐng", "third")]}
    qs = quiz.build_quiz(quiz.tag_deck(deck), seed=1)
    assert qs
    for q in qs:
        assert q.word is not None
        assert quiz.decks_mod.word_term(q.word) == q.term
        assert "_voice" in q.word
