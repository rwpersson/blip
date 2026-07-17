# Chinese Pop — project context

Always-on-top desktop flashcard overlay for passively learning Chinese while
gaming. A card pops up on a timer, speaks the word, and disappears. Windows-only.
Currently a personal tool being hardened into a shippable product (see ROADMAP.md).

## Run / regenerate

```
python pop.py                          # run (or run.bat)
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
- `pop.py` is ~1230 lines and monolithic. `state.json` holds real user progress —
  **never delete it casually** (tests must use a temp path or restore it).

## Files

| File | Role |
|---|---|
| `pop.py` | Everything: config, Win32 interop, audio, scheduler, all UI |
| `generate_audio.py` | edge-tts generation + `tones_to_text` + profanity censor |
| `expand_wordbank.py` | Add words from its `NEW` list to a deck (auto global ids) |
| `new_deck.py` | Scaffold an empty deck |
| `decks/<id>.json` | `{"name":…, "words":[{id,hanzi,pinyin,tones,cat,meaning,note,alt?,say?}]}` |
| `state.json` | `{"decks":{<deck_id>:{"words":{id:{e,due,intro}},"last":id}}, "last_deck":…}` |

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

1. **Focus stealing.** Windows must be `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`, and the
   style must be applied **before the window first maps** — `prevent_focus_steal()`
   deliberately does *not* call `update_idletasks()`, because mapping the window even
   a moment before the style lands makes it flash to the foreground once.
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

There is no committed test suite yet (a Phase-1 item). Historically everything was
verified with throwaway scripts driving the real app: pump `root.update()` instead of
`mainloop()`, assert on `IsWindowVisible`/`WindowFromPoint`/ex-styles, and spawn a
**separate-process** window to prove focus is never stolen from another app. Synthesize
hotkeys with `keybd_event` to test them end-to-end. Keep that rigor — the Win32
behavior above is not covered by unit tests of pure logic.

## Conventions

- Config is module-level constants at the top of `pop.py` (a Phase-2 item: move to a
  real settings file + UI).
- Word ids are **globally unique across decks** because audio is keyed by id.
  ⚠️ This breaks if users ever import third-party decks — see ROADMAP Phase 2
  (content-addressed audio).
- Swears: `meaning` is stored uncensored; `censor_display()` asterisks it for the card
  and `censor_speech()` swaps in a clean word so TTS never voices it (`_PROFANITY` in
  `generate_audio.py`).
- After adding words: `python generate_audio.py`. After changing a voice: `--force`.
- Reset `expand_wordbank.py`'s `NEW` list back to the empty template once words are
  committed to a deck.
