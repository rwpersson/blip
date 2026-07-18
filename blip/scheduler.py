"""Spaced-repetition-lite.

Keeps a small active batch of words in progress, re-shows each on an expanding
interval, and "graduates" it once it's been seen enough — then a new word enters
the batch. Driven purely by exposure count, so it needs no grading and stays
fully passive; rate() is the optional one-key recall feedback hook.

Progress is stored per deck under state["decks"][deck_id].
"""
import json
import random
import time

from . import paths
from .logging_setup import get

log = get("scheduler")
STATE_SCHEMA = 3


def read_state(path=None):
    path = path or paths.state_file()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        log.exception("state file unreadable, starting fresh: %s", path)
        return {}


def write_state(data, path=None):
    path = path or paths.state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        log.exception("could not write state to %s", path)


def last_deck(path=None):
    return read_state(path).get("last_deck")


def save_last_deck(deck_id, path=None):
    st = read_state(path)
    st["last_deck"] = deck_id
    st["schema"] = STATE_SCHEMA
    write_state(st, path)


def deck_known_count(deck_id, graduate_at, state=None, path=None):
    """Learned count for a deck we don't have a live Scheduler for."""
    state = state if state is not None else read_state(path).get("decks", {})
    words = state.get(deck_id, {}).get("words", {})
    return sum(1 for w in words.values() if w.get("e", 0) >= graduate_at)


class Scheduler:
    def __init__(self, words, deck_id, settings, state_path=None):
        self.deck_id = deck_id
        self.s = settings
        self._path = state_path
        self.by_id = {w["id"]: w for w in words}
        self.order = [w["id"] for w in words]
        self.total = len(self.order)
        self.last = None
        self.st = {i: {"e": 0, "due": 0.0, "intro": False} for i in self.order}
        self._load()

    def _load(self):
        slot = read_state(self._path).get("decks", {}).get(self.deck_id, {})
        for i, s in slot.get("words", {}).items():
            if i in self.st:
                self.st[i] = {"e": int(s.get("e", 0)),
                              "due": float(s.get("due", 0.0)),
                              "intro": bool(s.get("intro", False))}
        self.last = slot.get("last")

    def _save(self):
        data = read_state(self._path)
        data["schema"] = STATE_SCHEMA
        data.setdefault("decks", {})[self.deck_id] = {
            "words": {i: {"e": s["e"], "due": round(s["due"], 1),
                          "intro": s["intro"]}
                      for i, s in self.st.items() if s["intro"]},
            "last": self.last,
        }
        write_state(data, self._path)

    def _learning(self):
        return [i for i in self.order
                if self.st[i]["intro"] and self.st[i]["e"] < self.s.graduate_at]

    def _fill_batch(self):
        while len(self._learning()) < self.s.active_set_size:
            fresh = [i for i in self.order if not self.st[i]["intro"]]
            if not fresh:
                break
            pick = random.choice(fresh)
            self.st[pick]["intro"] = True
            self.st[pick]["due"] = 0.0        # due immediately

    def _interval(self, e):
        sched = self.s.schedule_min
        return sched[min(max(e, 1), len(sched)) - 1] * 60.0

    def next(self):
        now = time.time()
        self._fill_batch()
        pool = [i for i in self.order if self.st[i]["intro"]] or self.order[:]
        random.shuffle(pool)                       # randomize ties
        pool.sort(key=lambda i: (self.st[i]["due"], self.st[i]["e"]))
        choice = pool[0]
        if choice == self.last and len(pool) > 1:  # avoid back-to-back repeat
            choice = pool[1]
        s = self.st[choice]
        s["e"] += 1
        s["due"] = now + self._interval(s["e"])
        self.last = choice
        self._save()
        return self.by_id[choice]

    def exposures(self, wid):
        return self.st.get(wid, {}).get("e", 0)

    def rate(self, wid, got):
        """Recall feedback: got it -> jump toward learned and push it far out;
        missed -> knock it back and make it due again immediately."""
        s = self.st.get(wid)
        if not s:
            return
        s["intro"] = True
        if got:
            s["e"] = min(self.s.graduate_at, s["e"] + 3)
            s["due"] = time.time() + self._interval(self.s.graduate_at)
        else:
            s["e"] = max(0, s["e"] - 3)
            s["due"] = 0.0
        self._save()

    def stats(self):
        known = sum(1 for i in self.order
                    if self.st[i]["e"] >= self.s.graduate_at)
        return len(self._learning()), known, self.total
