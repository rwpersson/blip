# Blip — project context

Always-on-top desktop flashcard overlay for passively learning a language while
gaming. A card pops up on a timer, speaks the word, and disappears — without ever
stealing focus or the cursor. Windows-only.

**Direction** (decided; drives everything — see ROADMAP.md):

- **Free & open-source** (MIT), shipped via GitHub Releases.
- **Anki-like content model**: users author their own cards, get audio generated for
  them automatically, and import decks from elsewhere (CSV, Anki `.apkg`). The
  bundled Chinese decks are a starting point, not the product.
- **TTS = edge-tts**, deliberately. Piper was evaluated and **rejected by ear**: its
  only fast zh voice is female + espeak-phonemized, and the pinyin-phonemized one runs
  5.3 s/clip (~81 min to build the library). Tone clarity is the product. See ROADMAP
  Phase 3 for the numbers — don't re-litigate this without listening first.
  Known cost: generating needs network (playback is cached/offline), and the endpoint
  is undocumented. The provider interface in `audio/tts.py` is the mitigation; keep it
  clean so an engine swap stays contained.
- **Generic language overlay**: decks declare their own `language`/`voice`; tones and
  readings are optional Chinese niceties, not the core model. Chinese stays the
  flagship (tone colors, tone read-out) but isn't hardcoded.
- **Audio is content-addressed** (done, Phase 2): the filename is
  `hash(text + voice + rate)`, never the word id. This is what lets people author and
  import cards — two users can both author id `421`, and Anki ids can arrive from a
  foreign system, without anyone clobbering anyone's audio. Deck sharing = sharing a
  small JSON; the recipient synthesizes locally. **Word ids now only need to be
  unique within a deck** (they identify progress in state.json, nothing else).

## Run / test / regenerate

```
python -m blip                   # run the overlay (or run.bat)
python -m blip.editor            # deck editor / importer (standalone)
python -m blip.catalog_ui        # browse/install creator decks (standalone)
python -m blip.quiz_ui [deck_id] # Test Mode: multiple-choice quiz (standalone)
python -m blip.settings_ui       # settings (standalone)
python -m blip.firstrun          # the welcome window (auto-shown on run 1)
python -m pytest tests -q              # the suite MUST stay green
python generate_audio.py               # fill in any missing audio
python generate_audio.py --force       # rebuild ALL audio (after a voice change)
python new_deck.py "Week 5"            # scaffold decks/week-5.json
python expand_wordbank.py --deck week-5   # add words from its NEW list
```

## Current state (keep this updated)

- **Decks**: the app ships a neutral **Starter** (`decks/starter.json`, 20 common
  words, no swears) that's active out of the box, plus a **creator-deck catalog**
  (`catalog/*.json`, NOT auto-loaded): 1st Week (226), Week 2 (75), Week 3 (62),
  Week 4 (57), Week 5 (55) = 475 words the user installs opt-in. Personal study
  decks are no longer baked in active for everyone — see "Creator decks" below.
  Deck schema 1 (`term`/`reading`).
- **Audio**: **content-addressed** — `audio/<hash>.mp3` where the hash covers
  `text + voice + rate` (see `audio/clips.py`). **1051 clips, ~15 MB** (dedup keeps
  it small: shared tone read-outs mean +55 words only added 127 clips, not 165).
- **Voices**: word = `zh-CN-YunyangNeural` @ `-15%` (clear news-anchor male, chosen so
  tones are audible); English tone/meaning read-out = `en-US-GuyNeural`.
- **Cues**: `sounds/*.wav` — 4 chimes + got/miss, synthesized at runtime from the
  stdlib (`wave`+`math`), no assets shipped.
- `state.json` holds **real user progress** — never delete it casually; tests must
  use a tmp path (see `tests/conftest.py`).

## Layout

```
blip/
  __main__.py     entry (python -m blip)
  app.py          orchestration: timing, show/reveal flow, decks, input
  settings.py     defaults + user settings file + migration
  decks.py        deck load/validate + the word field accessors
  catalog.py      creator-deck catalog: entries/install/uninstall (no Tk — tested)
  catalog_ui.py   the catalog browser window (standalone process)
  quiz.py         Test Mode logic: build_quiz -> Questions (no Tk — tested)
  quiz_ui.py      the Test Mode quiz window (standalone process)
  scheduler.py    spaced-repetition-lite + state I/O
  text.py         tone read-out + profanity censor (pure, unit-tested)
  win32.py        ALL ctypes: no-activate, click-through, show/hide
  hotkeys.py      global RegisterHotKey listener thread
  paths.py        where user data lives (dev = in-tree, frozen = %APPDATA%)
  logging_setup.py
  lang.py         reading/tone auto-fill (pypinyin) — the only zh-specific bit
  audio/  clips.py (content-addressed clip keys — SOURCE OF TRUTH) ·
          player.py (MCI+winsound, the play sequence) · tts.py (provider
          interface + generate_word for authoring) · cues.py (synthesized chimes)
  importers/  common.py (mapping, clean(), build_words) · csv_import.py ·
          anki_import.py (.apkg) · export.py
  ui/     card.py · flash.py · panel.py · render.py (outlined text) · theme.py
  editor/ controller.py (ALL the logic, no Tk — test this) · window.py ·
          import_wizard.py · __main__.py
tests/            pytest; test_win32.py drives real windows
generate_audio.py · new_deck.py · expand_wordbank.py    (thin CLIs)
```

| Data | Shape |
|---|---|
| `decks/<id>.json` | `{"schema":1,"name":…,"language":"zh-CN","voice":null,"words":[…]}` |
| word | `{id, term, reading?, tones?, cat, meaning, note, alt?, say?}` |
| `state.json` | `{"schema":3,"decks":{<id>:{"words":{id:{e,due,intro}},"last":id}},"last_deck":…}` |

**Read words via `decks.word_term/word_reading/word_tones/word_say`**, never
`w["term"]`/`w["hanzi"]` — the accessors still tolerate the old `hanzi`/`pinyin`
names, which is what keeps imported/third-party decks working.

`audio/clips.py` is the **single source of truth** for what audio a word needs and
where it lives: `tts.py` generates from `specs_for()`, `player.py` plays from
`paths_for()`, so generation and playback can't disagree about a filename. Anything
that touches audio goes through it — never build a path by hand.

## Creator decks (the catalog)

Shipping the author's personal study decks baked in and active for everyone is the
opposite of the "author your own" direction, so they don't. Two bundled tiers:

- `decks/` (`paths.bundled_decks_dir()`) — the **Starter**, active out of the box so
  a fresh install is never empty. Just the one neutral sampler.
- `catalog/` (`paths.bundled_catalog_dir()`) — the **creator decks**, a library
  `decks.load_all()` never touches. A deck goes active only when the user installs
  it: `catalog.install(id, settings, progress=...)` copies the JSON into
  `user_dir()/decks` and synthesizes its audio.

Decided (don't re-litigate without a reason):
- **Bundled, not fetched.** The deck JSON is ~130 KB total — nothing next to a
  PyInstaller runtime — so it ships in the package. No hosting, works offline, no
  second undocumented-endpoint dependency alongside edge-tts. `catalog.py` is written
  so a `RemoteCatalog` could slot in later, but there's no reason yet.
- **Audio is generated on install, never shipped** (same as everything — audio is
  content-addressed, gitignored, made locally). Install degrades gracefully: offline
  just leaves clips missing (silent cards) to be filled on a later launch;
  `tts.generate` never raises.
- **`catalog_ui.py` is its own process** (like the editor/settings) — a focus-hungry
  ttk window, the opposite of the overlay's no-activate rule. Install runs on a worker
  thread (a 226-word deck's audio hits the network) and marshals progress back with
  `root.after`. From the editor it opens as a **Toplevel** instead (that process
  already owns a root — one root per process).
- **The running overlay doesn't hot-reload.** It loads decks at startup, so a
  newly installed deck appears next launch, not live. The install message says so —
  don't change it to imply an instant switch without actually wiring a reload.
- Entry points: first-run ("Get more decks…"), the panel ("📚 Get decks"), and the
  editor ("Creator decks…"). `catalog.py` is pure logic and unit-tested
  (`tests/test_catalog.py`); the window is a thin shell.

## Test Mode (the quiz)

Active self-testing to complement the passive overlay: a word, four
`(reading, meaning)` options, pick the right one. Panel button "🧠 Test Mode".

- `quiz.py` is pure/seedable (`build_quiz(words) -> [Question]`, tested): distinct
  targets, distractors sampled from other words, and a distractor **never shares
  the target's meaning** (that would make two answers right). Meanings are run
  through `censor_display` so swears are asterisked here too. Degrades: a 3-word
  pool gives 3-option questions; <2 answerable words gives no quiz.
- `quiz_ui.py` is standalone (`python -m blip.quiz_ui [deck_id]`) — a
  focus-wanting window, fine because the user is testing, not gaming. Pool picker
  (All decks / current deck via `scheduler.last_deck()` or argv; a **question-count
  spinbox** persisted as `quiz_length`) → question → results, three screens swapped
  on one root.
- **Audio on reveal**: answering plays the term's pronunciation once (`_play_word`
  → `player.play_file` on a daemon thread). Clips are keyed by voice, so the target
  word carries its deck's voice (`quiz.tag_deck` tags `_voice`, `Question.word`
  holds the source word); a missing clip is a silent no-op.
- **Opening it pauses the overlay** (`app.open_quiz`): `pause()` + `player.cancel()`
  + `hide_card()`, so pops stop and a word mid-readout goes quiet without the user
  pausing by hand. Resume is manual (Play). `player.cancel()` (vs `stop()`) bumps
  `_play_token` so the play_word thread bails between clips instead of marching on
  to the tones/meaning. Guarded by `test_opening_test_mode_pauses_the_overlay`.
- **Sizing gotcha**: the screens differ a lot in height (question ≈ 2× the pool),
  so it re-fits per screen with `_fit()` — `fit_window` only resizes, never
  repositions, so the window grows/shrinks in place without jumping. The Next
  button is packed disabled up front so answering doesn't add a row and jump the
  window mid-question.

## Authoring & import

**The editor is a separate program on purpose** (`python -m blip.editor`). It's
an ordinary ttk window that *wants* focus — the exact opposite of every invariant in
`win32.py`. Keeping it out of the overlay's process means it can't regress them.
`editor/controller.py` holds all the logic and imports no Tk, so it's tested directly;
`window.py` stays dumb.

Editing a **bundled** deck is copy-on-write: once installed the bundled dir is
read-only, so `save()` writes to `user_dir()/decks`, and `load_all()` lets a user deck
**override** a bundled one with the same id (otherwise you'd see the deck twice).

- `decks.create/add_word/update_word/delete_word/save` — user decks are written to
  `user_dir()/decks`, never the bundled dir (read-only once installed).
  `add_word` auto-fills reading/tones and rejects duplicate terms.
- `lang.derive_reading("银行")` → `("yín háng", "2-2")`. pypinyin resolves polyphones
  from context, which is why we don't need g2pw's BERT. **Auto-fill is a suggestion**
  — it can disagree with a careful reading (it neutralises 电子 to "diàn zi"), so the
  author must always be able to override.
- `tts.generate_word(word, settings, deck)` — audio for ONE card, for authoring.
  Free when the clip already exists (content-addressed).
- **Import is two-phase on purpose**: `parse()` → `ImportResult(fields, rows)`, then
  the caller supplies a mapping → `build_words()`. Neither CSV nor Anki has a fixed
  schema, so the user must confirm which column is the term.
  `guess_mapping()` pre-fills it.
- Gotchas already handled — don't undo them:
  - Anki fields are HTML with `[sound:…]`/`<img>`/`&nbsp;` → `common.clean()`
  - `.apkg` may hold `collection.anki21b`, which is **zstd**-compressed → we report
    that actionably instead of crashing
  - field *names* come from the notetype; newer files hide them in a protobuf, so we
    fall back to positional `Field N`
  - **imported tags are not our categories** ("hsk1" → `hsk`, unknown → dropped),
    or the imported deck fails validation
  - **media is deliberately not imported** — we re-synthesize, for one consistent
    voice and no redistribution question

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
  `Ctrl+Alt+M` silent, `Ctrl+Alt+F` fast, `Ctrl+Alt+J` knew it, `Ctrl+Alt+K` didn't.
- **Fast mode** (`⚡`, `app.toggle_fast` / panel / `Ctrl+Alt+F`): denser pace for
  covering more distinct words per hour (7h at 25s ≈ 106 new words, gated by the
  ~9-exposure graduation). It (a) pops on `fast_interval_seconds` (8) instead of
  `interval_seconds`, and (b) speaks **only the word**, at `fast_rate` (+40%). The
  speed-up is a faster edge-tts **rate**, not sped-up playback — edge-tts changes
  tempo while keeping pitch, so the tones survive (resampling would raise pitch and
  wreck them). The fast word is a **separate content-addressed clip** (keyed by
  rate), so `clips.specs_for` emits a `WORD_FAST` spec only when `fast_mode` is on;
  enabling fast kicks a background `tts.generate_async` top-up, and a pop plays the
  normal-rate word until its fast clip lands (`player._select_paths`). Persisted as
  `fast_mode` so it also gates generation next launch.

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
   on every window — keep it. **This applies to _every_ Toplevel, not just the
   obvious three.** Panel tooltips are windows too, created over the game on
   hover, so `_Tooltip._show()` calls `prevent_focus_steal()` + `show_no_activate()`
   like everything else (`test_tooltips_do_not_steal_focus`). Any new window =
   the same two calls. It *also* calls `raise_without_focus()`: everything here is
   `WS_EX_TOPMOST`, and `show_no_activate()` doesn't raise within that band — so a
   tooltip shown over the (topmost) panel renders **behind** it, invisibly. Raise
   it, without activating. `test_panel_tooltip_renders_above_the_panel` guards this
   (and fails if the raise is removed — verified by mutation, not assumed).
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
11. **DPI**: `win32.set_dpi_aware()` must run *before any window exists* (it's called
    in each `__main__`). Without it Windows renders us at 96 DPI and bitmap-stretches
    the result — blurry on any scaled display (this machine is 125%, so Tk reported
    1536×960 for a real 1920×1200 screen). *With* it, nothing is scaled for us, so
    `app._apply_dpi()` must scale Tk fonts and the pixel settings — otherwise
    everything comes out tiny. The two go together; never enable one alone.
12. **`winfo_screenwidth()` is the PRIMARY monitor only.** Place windows using
    `win32.monitor_rect(settings.monitor)`, which is threaded through as `app.rect`.
13. **ONE `Tk()` root per PROCESS — in the tests too.** An earlier version of this
    note claimed "a handful of module-scoped roots is fine (verified: `test_win32` +
    `test_window_fit` coexist in either order)". **That was wrong.** A second root in
    a live process errored `test_window_fit` in ~half of all full-suite runs, as
    either `invalid command name "tcl_findLibrary"` or `couldn't read file init.tcl:
    No error` — two faces of the same thing, which is why chasing the message
    misleads. It isn't create/destroy churn specifically; a *second interpreter* is
    the problem, alive or not. So: reuse `tk._default_root` if it exists
    (`test_window_fit`'s `root` fixture), never `destroy()` a root you didn't create,
    and don't destroy one at teardown either — let process exit do it. Note the app
    already obeys this: settings/editor/first-run are separate **processes**, which
    is the same rule, not a coincidence. Also never leave `after()` timers pending on
    a root (poll-for-layout retries did) — bind `<Configure>` and let Tk tell you
    when it laid the widget out.
14. **Rounded corners come from a window REGION** (`SetWindowRgn`), not DWM's corner
    preference — DWM rounding doesn't apply to layered, override-redirect windows.
    The region is in **pixels**, so it must be re-applied on every `place()`; the card
    resizes with its content. Only the *backing* panel is clipped: the text layer's
    background is colour-keyed away, so it has no corners to show.
15. **The overlay works over fullscreen games** (confirmed: Minecraft, PUBG). Don't
    add "pause when fullscreen" — it was on the roadmap and was dropped because it
    would break the main use case. Only genuinely *exclusive* fullscreen (older DX
    titles) can hide an overlay, and no app can fix that.
16. **Never hard-code a window size.** Use `win32.fit_window(win, min_w, min_h)`.
    Once the process is DPI-aware, Tk renders fonts at the real DPI (scaling 1.67 at
    125%), so a size chosen at 100% silently clips: the first-run window was 520x440
    for 583px of content and lost both its buttons. Also **pack action bars before
    expanding content** — pack allocates space in order, so a bar packed last is the
    first thing squeezed out. `tests/test_window_fit.py` guards both.
17. **Every button needs a word, and only one may be filled.** The panel shipped as
    nine identical buttons in one row; users could not tell what "📝" did (it meant
    *make your own flashcards*), and the primary action looked exactly like the
    destructive one. Group by job, label with text, fill exactly one button (Play),
    and put Quit away from the controls people press. `test_every_panel_button_has_a_word`
    guards the labels. Icon-only is only ever acceptable with a `_Tooltip`.
18. **The deck list is collapsed to the current deck** (`panel._set_expanded`). You
    study one deck for days, so switching is rare — but the list is the only part of
    the panel that grows without bound once people import decks. Collapsed it costs
    one row; expanded it's capped at `panel_max_deck_rows` and scrolls, so a 40-deck
    import can't push the buttons off the screen (`test_expanded_deck_list_cannot_
    outgrow_the_screen`). A **dropdown is not an option** — Tk menu/combobox popups
    are native windows that take focus and mouse capture, which is the one thing this
    app can never do. Any picker has to be drawn inside the panel.
19. **Assert on *our* behaviour, not the machine's.** The focus test asserted
    `foreground == game`, which also fails when a notification or the console grabs
    focus — nothing to do with us. It cried wolf ~1 run in 8. Ask `GetWindowThread
    ProcessId` who owns the foreground window: ours = a real failure, anyone else's
    = skip. Don't loosen the guarantee to hide an unrelated flake.
20. **Audio generates in the BACKGROUND, after the overlay is up** (`__main__.
    _generate_audio_in_background`). It used to run synchronously before
    `App().run()`; a fresh launch with hundreds of clips then showed no window for
    minutes and looked hung — and closing it mid-way cached nothing, so the next
    launch started over (a real user hit this loop). Now the window is up
    immediately and cards whose clips aren't ready play silently until they are.
    Two things this needs: generation writes each clip to a `.part` temp then
    `os.replace()`s it in, so a card mid-generation never plays a truncated file
    (`tts._synthesize_atomic`); and progress shows in the console, the log, and the
    panel status (`panel.set_generating`). Don't move generation back ahead of
    `run()`. Guarded by `tests/test_startup.py`.

## Testing

`python -m pytest tests -q` — keep it green.

`tests/test_win32.py` is the important one: it drives **real windows** and asserts on
**real Win32 state**, because pure-logic tests cannot prove the two things the app
lives or dies on — that a pop never steals focus, and that the cursor passes through
the card. It spawns a **separate-process** window (`helper_window.py`) as a stand-in
for your game and checks `GetForegroundWindow()` never moves. Pump `root.update()` in
a loop rather than calling `mainloop()`.

**But know what that foreground test is worth — it is not the safety net.** Mutation
testing (strip the NOACTIVATE style; swap `show_no_activate()` for `deiconify()`) found
it catches **none** of those regressions on a normal desktop: Windows won't grant *our*
process the foreground while another app owns it, so a thoroughly broken overlay can't
steal focus there either and the test passes vacuously. It only bites when the helper
actually wins the foreground (idle desktop / CI). What genuinely guards the invariant:

| Guard | Catches |
|---|---|
| `test_windows_are_no_activate` | the NOACTIVATE style going missing (incl. gotcha #1's wrapper) |
| `test_overlay_never_calls_deiconify` | gotcha #2 — static (AST), because nothing behavioural sees it |
| `test_pops_never_steal_focus…` | the real end-to-end thing, *when the desktop cooperates* |

Re-run the mutation check after touching `win32.py`: break each defense, confirm
something goes red. A test that cannot fail is decoration — this one silently was.
Same lesson elsewhere: `tests/test_settings_ui.py` exists because a typo'd key in the
spec-driven `SPEC` yields a control that changes nothing, with no error.

Isolation: always point `state_file` at a tmp path (`conftest.py` does) — the real
`state.json` is the user's progress.

## Conventions

- Config lives in `settings.py` (`DEFAULTS`) and a user `settings.json`; there's no
  UI for it yet (ROADMAP Phase 4). Add new knobs to `DEFAULTS`, never as constants.
- Log, don't swallow: no bare `except: pass` — use `log.exception(...)`. You can't
  debug a stranger's crash otherwise.
- Word ids are currently **globally unique across decks** because audio is keyed by
  id (`audio/<id>.mp3`). ⚠️ **This is on borrowed time**: authored + imported cards
  make it collide (two users both author id `421`; Anki brings foreign ids). Phase 2
  moves to content-addressed audio — don't add code that depends on id↔audio.
- Swears: `meaning` is stored uncensored; `censor_display()` asterisks it for the card
  and `censor_speech()` swaps in a clean word so TTS never voices it (`_PROFANITY` in
  `generate_audio.py`).
- After adding words: `python generate_audio.py`. After changing a voice: `--force`.
- Reset `expand_wordbank.py`'s `NEW` list back to the empty template once words are
  committed to a deck.
