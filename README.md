# Chinese Pop 🀄

A tiny always-on-top flashcard that pops up in the corner of your screen every
minute while you game. Each pop shows a random Chinese word or slang term with:

- the characters (汉字) + any alternate form
- **pinyin** and **tone numbers**
- an English meaning
- a short **nuance / slang note** (why it's used, how it hits, gotchas)
- **spoken audio** — the word is spoken **3×**, then the tones are read aloud in
  English (e.g. "second tone, first tone") so you can drill the tone pattern

Words are organized into **decks** (like Anki). It ships with three:
**1st Week** (226), **Week 2** (75) and **Week 3** (62), across six categories
(colored pills): `slang` · `gaming` · `swear` · `hsk` (advanced vocab) ·
`idiom` (chengyu) · `common`. Each deck tracks its own progress; pick a deck
from the list on the control panel, and it resumes the last deck you used on
relaunch. See **Decks** below to make your own.

### How it helps you memorize (passively)

- **Spaced learning batch** — instead of spraying all 226 words at you, it
  drills a small active batch (~12 at a time) on **expanding intervals**: a new
  word comes back quickly, then less and less often as it sinks in. Once a word
  has been seen enough it "graduates" (counts as learned) and a new one enters
  the batch. No grading needed — it's driven purely by exposure, so it stays
  passive. The card shows `seen 3× · 40/226 learned`.
- **Study first, test later** — the *first* time a word appears it's shown in
  full with a `✦ NEW` badge (you can't recall what you've never seen). From the
  **second** exposure on, the recall-delay kicks in: the characters + audio come
  first, the meaning and pinyin stay hidden (`🤔 recall it…`) for a few seconds
  so your brain *tries* to recall before the answer appears (the "testing
  effect").
- **Spoken meaning** — after the word and tones, the English meaning is read
  aloud too, so you can learn with your eyes entirely on the game.
- **Big, outlined word** — the characters are large and drawn with a dark halo
  (`HALO_COLOR`) so they stay crisp over any game background, even through the
  see-through panel.
- **Tone-colored pinyin** — each syllable is colored by its tone
  (1 red · 2 gold · 3 green · 4 blue · neutral gray) to drill tones at a glance.
- **Anti-habituation** — the danger with any recurring popup is that your brain
  learns to tune it out. Three defenses keep it fresh:
  - a **random-interval chime** — after a random run of cards
    (`CHIME_EVERY_MIN`–`CHIME_EVERY_MAX`) a random chime plays (not every card,
    which would just become background); it pulls your eyes back;
  - **unpredictable flashes** — with annoying mode on, only *some* pops flash
    (`FLASH_PROB`), weighted toward words you haven't learned yet
    (`FLASH_NEW_UNTIL`), so you can't pre-filter them;
  - **one-key recall** — while a word shows, press **`Ctrl+Alt+J`** ("I knew it",
    shows it less) or **`Ctrl+Alt+K`** ("I didn't", brings it back soon). One
    keypress turns a passive glance into active recall and steers the spacing.
    Each gives an audible confirmation.

Per-deck progress is saved to `state.json`, so closing and reopening picks up
exactly where you left off in each deck. Delete it to reset all progress.

The **control panel is hidden by default** — press **`Ctrl+Alt+C`** (a global
hotkey that works even while your game has focus) to show or hide it. It also
appears briefly at launch as a reminder. The flashcards keep popping whether the
panel is showing or not.

| Button | Does |
|---|---|
| ▶ Play / ⏸ Pause | Start the cycle / freeze it (card stays up) |
| ⏹ Stop | Halt and hide the card |
| ⏭ Next | Jump to a new word right now |
| 🔊 Replay | Replay the current word's audio |
| 😈 Annoy | Toggle **annoying mode** (see below) |
| 🔊 Sound / 🔇 Silent | Toggle **silent mode** — no audio at all (also `Ctrl+Alt+M`) |
| ✕ | Quit |

**Silent mode** turns off all sound (the spoken word, tones, meaning, chimes and
cues). Flashcards and the fullscreen flash still work — the flash just uses timed
beats instead of the audio — so you can study visually with no noise. Toggle it
with the panel button or the global **`Ctrl+Alt+M`** hotkey; start silent by
default with `PLAY_AUDIO = False`.

The panel lists your **decks** with per-deck progress (e.g. `▸ 1st Week (40/226)`);
click any one to switch to it. The active deck is remembered across restarts.

Drag the panel by its title to reposition it. The **flashcard itself is
display-only and fully click-through** — all controls live on the panel — so the
cursor passes straight through the card to your game (see below).

Change the hotkey (or its brief launch reminder) via `PANEL_HOTKEY_*` /
`PANEL_HINT_SECONDS` in the CONFIG block of `pop.py`.

### 😈 Annoying mode

When on (`ANNOYING_MODE`, default true, toggle with the panel button), the
hanzi + pinyin + tones **flash huge across the whole screen** in sync with each
of the 3 spoken repeats (flash ×3), then it drops back to the normal card for
the English tone/meaning read-out. The flash **background is transparent** (your
game stays fully visible — only the giant text shows) and, like the card, it's
**click-through and never takes focus**, so your cursor still reaches the game
even while the letters are covering the screen. Tune how big the characters get
with `ANNOY_HANZI_FRAC`.

## Requirements

- Windows + Python 3 (tested on 3.14)
- `edge-tts` for generating the audio (one-time, needs internet):

  ```
  pip install edge-tts
  ```

Playback and the popup use only built-in Windows features (MCI + tkinter) — no
other dependencies.

## Run it

Double-click **`run.bat`**, or from a terminal:

```
python pop.py
```

On first launch it generates any missing audio into `audio/`, then a card pops
up every 60 seconds and speaks the word. After the audio is generated once, it
works fully offline. Use the control bar (top-right) to Play / Pause / Stop /
skip. Delete `state.json` any time to reset the shuffle back to the start.

## Tuning

Open `pop.py` and edit the `CONFIG` block near the top:

| Setting | Meaning |
|---|---|
| `INTERVAL_SECONDS` | How often a new word appears |
| `DISPLAY_SECONDS` | How long the card stays before auto-hiding (`0` = stays until next) |
| `PLAY_AUDIO` | Start in silent mode? (toggle live with the panel button / `Ctrl+Alt+M`) |
| `WORD_REPEATS` | How many times the word is spoken each pop (default 3) |
| `SAY_TONES` | Read the tones aloud in English after the word (default on) |
| `SAY_MEANING` | Read the English meaning aloud after the tones (default on) |
| `REPEAT_GAP` | Seconds of silence between repeats |
| `REVEAL_QUIZ` / `REVEAL_DELAY` | Recall beat: hide the answer for N seconds (`REVEAL_QUIZ=False` to always show it) |
| `ACTIVE_SET_SIZE` | How many words are drilled at once (default 12) |
| `GRADUATE_AT` | Exposures before a word counts as learned (default 9) |
| `SCHEDULE_MIN` | Expanding re-show intervals, in minutes |
| `CHIME_ON` / `CHIME_EVERY_MIN` / `CHIME_EVERY_MAX` | Attention chime, and the random card-gap between chimes |
| `FLASH_PROB` / `FLASH_NEW_UNTIL` | Odds a pop flashes; words this new always flash |
| `RECALL_HOTKEYS` / `GOT_*` / `MISS_*` | Enable the recall keys and rebind them |
| `AUTOSTART` | Set `False` to launch paused (press ▶ Play yourself) |
| `CARD_ALPHA` | Opacity of the card **panel** only — text stays fully solid (lower = more see-through) |
| `CARD_WIDTH`, `TONE_COLORS`, colors, `FONT` | Appearance |

The word is spoken by a clear male news-anchor voice (`zh-CN-YunyangNeural`),
slowed a little (`RATE`) so the tones are easy to hear; the English read-outs use
`en-US-GuyNeural`. Prefer a different voice or speed? Edit `VOICE` / `RATE`
(Chinese word) or `TONES_VOICE` / `MEANING_VOICE` (English) at the top of
`generate_audio.py`, then run `python generate_audio.py --force`.

**Swears are censored** in the English translation: the meaning is shown with the
swear asterisked (`b*****d`) and the spoken audio never says it (a clean word is
substituted). The censor list lives in `_PROFANITY` in `generate_audio.py`.

## Decks

Each deck is a file in `decks/`: `decks/<id>.json` = `{"name": ..., "words": [...]}`.
The app loads every deck, ordered by filename (prefix ids like `2-`, `3-` to
control the order), and you switch between them by clicking a deck in the list on the
control panel. Progress is tracked per deck in `state.json`.

**Make a new deck:**

```
python new_deck.py "Week 3"          # -> decks/week-3.json
```

**Add words to a deck** — put entries in the `NEW` list in `expand_wordbank.py`,
then:

```
python expand_wordbank.py --deck week-3
python generate_audio.py             # make audio for the new words
```

Each word entry looks like:

```json
{ "hanzi": "牛逼", "alt": "NB", "pinyin": "niú bī", "tones": "2-1",
  "cat": "slang", "meaning": "awesome; badass", "note": "..." }
```

- **No `id` needed** — `expand_wordbank.py` assigns one that's globally unique
  across all decks (so audio never collides), and skips any `hanzi` already in
  any deck, so it's safe to re-run.
- `alt`, `say` are optional. Use `say` when `hanzi` contains letters/numbers so
  the TTS speaks the Chinese instead (e.g. `666` → `say: "六六六"`).
- `cat` is one of `slang`, `gaming`, `swear`, `hsk`, `idiom`, `common` (colors
  the little pill).
- Set `ACTIVE_DECK` in `pop.py` to the deck id you want to start on (`""` = the
  first deck).

## It won't steal your cursor / focus

The popup and control bar are created as Windows **no-activate tool windows**
(`WS_EX_NOACTIVATE`): they render on top but never take keyboard focus, so a pop
can't pull you out of a game while you're playing. On launch the app also hands
focus straight back to whatever you were using, so even starting it mid-game is
seamless. Quit with the ✕ button on the control panel.

On top of that, the **flashcard is fully click-through** (`WS_EX_TRANSPARENT`):
your mouse passes right through it to the game underneath, so it can never
intercept a click or steal your cursor — handy for cursor-driven games. All
interaction happens on the little control panel in the top-right corner, which
stays clickable as normal.

## Note on fullscreen games

The overlay floats over normal and **borderless-windowed** games. True
*exclusive fullscreen* can hide any overlay — if you don't see the pop, switch
that game to Borderless/Windowed mode.
