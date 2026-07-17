# Chinese Pop — project context

Always-on-top desktop flashcard overlay for passively learning Chinese while
gaming. A card pops up on a timer, speaks the word, and disappears. Windows-only.
Currently a personal tool being hardened into a shippable product (see ROADMAP.md).

## Run / test / regenerate

```
python -m chinesepop                   # run (or run.bat)
python -m pytest tests -q              # the suite MUST stay green
python generate_audio.py               # fill in any missing audio
python generate_audio.py --force       # rebuild ALL audio (after a voice change)
python new_deck.py "Week 5"            # scaffold decks/week-5.json
python expand_wordbank.py --deck week-5   # add words from its NEW list
```

## Current state (keep this updated)

- **Decks** (`decks/*.json`, loaded in filename order): 1st Week (226), Week 2 (75),
  Week 3 (62), Week 4 (57) = **420 words**, ids `01`–`420`.
- **Audio**: `audio/<id>.mp3`, `<id>_tones.mp3`, `<id>_meaning.mp3` — **1259 clips, ~22 MB**.
- **Voices**: word = `zh-CN-YunyangNeural` @ `-15%` (clear news-anchor male, chosen so
  tones are audible); English tone/meaning read-out = `en-US-GuyNeural`.
- **Cues**: `sounds/*.wav` — 4 chimes + got/miss, synthesized at runtime from the
  stdlib (`wave`+`math`), no assets shipped.
- `state.json` holds **real user progress** — never delete it casually; tests must
  use a tmp path (see `tests/conftest.py`).

## Layout

```
chinesepop/
  __main__.py     entry (python -m chinesepop)
  app.py          orchestration: timing, show/reveal flow, decks, input
  settings.py     defaults + user settings file + migration
  decks.py        deck load/validate + the word field accessors
  scheduler.py    spaced-repetition-lite + state I/O
  text.py         tone read-out + profanity censor (pure, unit-tested)
  win32.py        ALL ctypes: no-activate, click-through, show/hide
  hotkeys.py      global RegisterHotKey listener thread
  paths.py        where user data lives (dev = in-tree, frozen = %APPDATA%)
  logging_setup.py
  audio/  player.py (MCI+winsound, the play sequence) · tts.py (provider
          interface: Edge now, Piper in Phase 3) · cues.py (synthesized chimes)
  ui/     card.py · flash.py · panel.py · render.py (outlined text) · theme.py
tests/            pytest; test_win32.py drives real windows
generate_audio.py · new_deck.py · expand_wordbank.py    (thin CLIs)
```

| Data | Shape |
|---|---|
| `decks/<id>.json` | `{"name":…, "language":"zh-CN", "voice":null, "words":[…]}` |
| word | `{id,hanzi,pinyin,tones,cat,meaning,note,alt?,say?}` |
| `state.json` | `{"schema":3,"decks":{<id>:{"words":{id:{e,due,intro}},"last":id}},"last_deck":…}` |

**Read words via `decks.word_term/word_reading/word_tones/word_say`**, never
`w["hanzi"]` — that's what makes the Phase-2 generic rename a one-file change.

`cat` ∈ `hsk | slang | swear | gaming | idiom | common` (drives the pill color).
`say` overrides the TTS text when `hanzi` has latin/digits (`666` → `六六六`).

## How it works

- **Scheduler** (`Scheduler`): spaced-repetition-lite, **no grading needed**. Keeps an
  active batch (`ACTIVE_SET_SIZE`=12) of in-progress words, re-shows each on an
  expanding interval (`SCHEDULE_MIN`), and "graduates" it at `GRADUATE_AT`=9
  exposures, pulling in a new word. Progress is **per deck** in `state.json`.
  `rate(id, got)` is the one-key recall feedback hook.
- **Card**: two stacked windows — a semi-transparent backing panel (`CARD_ALPHA`) and
  a fully-opaque text layer. That's the only way to get a see-through panel with
  crisp text (Tk `-alpha` dims a whole window uniformly).
- **Flash** ("annoying mode"): fullscreen transparent overlay showing huge
  hanzi/pinyin/tones, synced to each spoken repeat via audio-thread events
  (`word_on`/`word_off`/`english`) → `_fx_q` → `_poll_fx` on the Tk thread.
- **Anti-habituation**: random-interval chime (`CHIME_EVERY_MIN..MAX` cards, random
  sound), flashes only on *some* pops (`FLASH_PROB`) but **always** for weak/new words
  (`FLASH_NEW_UNTIL`), study-first (first exposure shows the answer; recall-delay
  only from the 2nd), and recall hotkeys.
- **Hotkeys** (global, work while a game has focus): `Ctrl+Alt+C` panel,
  `Ctrl+Alt+M` silent, `Ctrl+Alt+J` knew it, `Ctrl+Alt+K` didn't.

## Hard-won gotchas — do not regress these

These each cost real debugging. Verify them after touching windowing/audio.

1. **Focus stealing — Tk's wrapper window.** Windows must be
   `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`. The trap: Tk creates a **wrapper
   top-level when the window first maps**, and *that* handle — not `winfo_id()` —
   is what Windows manages for focus. Styling only `winfo_id()` leaves the real
   window activatable. The card/flash accidentally escaped this because
   `make_click_through()` runs later and re-applies the style to the real handle;
   the **panel** doesn't get that call, so it was silently activatable for a long
   time (clicking a button could pull focus off the game).
   `prevent_focus_steal()` therefore does **withdraw → update_idletasks → style
   both `winfo_id()` and `GetParent()`**. Withdrawing first is what makes realizing
   safe: realizing a *visible* window maps and activates it (the old flash-to-
   foreground bug). `tests/test_win32.py::test_windows_are_no_activate` asserts this
   on every window — keep it.
2. **Never `deiconify()`.** Show with `ShowWindow(SW_SHOWNOACTIVATE)`; hide with
   `SW_HIDE`. Tk's own map/unmap can activate the window.
3. **Click-through** = `WS_EX_TRANSPARENT` (+ layered). The card and flash are
   display-only so the cursor always reaches the game; **all** controls live on the panel.
4. **Color-key transparency** uses `C_BG` as the key. Text anti-aliases against it, so
   the key must equal the panel color or you get fringing. `-transparentcolor` and
   `-alpha` can coexist (that's how the flash gets a transparent bg + semi-solid text).
5. **Console encoding**: Windows console is cp1252 and *crashes* printing Chinese —
   every script does `sys.stdout.reconfigure(encoding="utf-8")`. A print crash once
   silently aborted a whole generation run.
6. **MP3 playback** is Windows MCI (`mpegvideo` alias) — no dependency. WAV cues use
   `winsound`. `_play_token` cancels a superseded audio sequence.
7. **Global hotkeys** must be registered *and* message-pumped on the **same thread**
   (`HotkeyListener`); `WM_HOTKEY`'s `wParam` is the hotkey id. If registration fails
   the panel is forced visible so the user can still quit.
8. **Silent mode** keeps the flash working by substituting timed beats
   (`SILENT_WORD_SECS`) for audio playback — don't early-return out of the event loop.
9. Tk `attributes()` can return a `Tcl_Obj`, not `str` — compare with `str(...)`.
10. The card auto-sizes to content; anchor it by its **measured** width or it spills
    off-screen.

## Testing

`python -m pytest tests -q` — keep it green.

`tests/test_win32.py` is the important one: it drives **real windows** and asserts on
**real Win32 state**, because pure-logic tests cannot prove the two things the app
lives or dies on — that a pop never steals focus, and that the cursor passes through
the card. It spawns a **separate-process** window (`helper_window.py`) as a stand-in
for your game and checks `GetForegroundWindow()` never moves. That test is what caught
gotcha #1. Pump `root.update()` in a loop rather than calling `mainloop()`.

Isolation: always point `state_file` at a tmp path (`conftest.py` does) — the real
`state.json` is the user's progress.

## Conventions

- Config lives in `settings.py` (`DEFAULTS`) and a user `settings.json`; there's no
  UI for it yet (ROADMAP Phase 4). Add new knobs to `DEFAULTS`, never as constants.
- Log, don't swallow: no bare `except: pass` — use `log.exception(...)`. You can't
  debug a stranger's crash otherwise.
- Word ids are **globally unique across decks** because audio is keyed by id.
  ⚠️ This breaks if users ever import third-party decks — see ROADMAP Phase 2
  (content-addressed audio).
- Swears: `meaning` is stored uncensored; `censor_display()` asterisks it for the card
  and `censor_speech()` swaps in a clean word so TTS never voices it (`_PROFANITY` in
  `generate_audio.py`).
- After adding words: `python generate_audio.py`. After changing a voice: `--force`.
- Reset `expand_wordbank.py`'s `NEW` list back to the empty template once words are
  committed to a deck.
