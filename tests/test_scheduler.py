"""Scheduler: batching, graduation, per-deck state, recall feedback."""
import time

from chinesepop import decks as decks_mod
from chinesepop.scheduler import Scheduler, last_deck, save_last_deck


def test_focuses_a_small_batch(settings, state_path):
    """The point of the batch: don't spray all N words at the user."""
    settings.set("active_set_size", 2)
    words = [{"id": str(i), "hanzi": f"w{i}", "meaning": "m"} for i in range(20)]
    s = Scheduler(words, "d", settings, state_path)
    seen = {s.next()["id"] for _ in range(10)}
    assert len(seen) <= 2


def test_no_immediate_repeat(settings, state_path, words):
    s = Scheduler(words, "d", settings, state_path)
    picks = [s.next()["id"] for _ in range(12)]
    assert all(a != b for a, b in zip(picks, picks[1:]))


def test_graduates_and_pulls_in_new_words(settings, state_path):
    settings.set("active_set_size", 2)
    settings.set("graduate_at", 3)
    words = [{"id": str(i), "hanzi": f"w{i}", "meaning": "m"} for i in range(10)]
    s = Scheduler(words, "d", settings, state_path)
    for _ in range(40):
        s.next()
    learning, known, total = s.stats()
    assert known > 0                       # something graduated
    assert learning <= 2                   # batch stays capped
    assert total == 10


def test_progress_is_per_deck_and_persists(settings, state_path, words):
    a = Scheduler(words, "deck-a", settings, state_path)
    for _ in range(4):
        a.next()
    b = Scheduler(words, "deck-b", settings, state_path)
    # deck-b is untouched by deck-a's progress
    assert all(b.exposures(w["id"]) == 0 for w in words)
    b.next()
    # reloading deck-a sees its own saved progress
    a2 = Scheduler(words, "deck-a", settings, state_path)
    assert sum(a2.exposures(w["id"]) for w in words) == 4


def test_rate_got_pushes_out_miss_brings_back(settings, state_path, words):
    s = Scheduler(words, "d", settings, state_path)
    w = s.next()
    wid = w["id"]
    s.st[wid]["e"] = 5

    s.rate(wid, True)                      # knew it -> toward learned, far out
    assert s.st[wid]["e"] == 8
    assert s.st[wid]["due"] > time.time()

    s.rate(wid, False)                     # didn't -> knocked back, due now
    assert s.st[wid]["e"] == 5
    assert s.st[wid]["due"] == 0.0


def test_rate_ignores_unknown_word(settings, state_path, words):
    s = Scheduler(words, "d", settings, state_path)
    s.rate("nope", True)                   # must not raise


def test_last_deck_roundtrip(state_path):
    assert last_deck(state_path) is None
    save_last_deck("week-3", state_path)
    assert last_deck(state_path) == "week-3"
