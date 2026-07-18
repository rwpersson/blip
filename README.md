# Blip

A tiny always-on-top flashcard that pops up in the corner of your screen while
you game (or work), speaks a word, and disappears — **without ever taking your
cursor or pulling focus out of what you're doing**. It's for learning a language
in the background, a glance at a time.

Blip is **language-agnostic**: every deck declares its own language and voice, so
it works for anything edge-tts can speak. Chinese is the flagship — the bundled
decks are Chinese, and the tone colors and spoken tone read-out are Chinese
niceties — but none of that is hardcoded.

Free and open-source (MIT).

Each pop shows:

- the word (large, outlined so it stays crisp over any game background)
- its **reading** (for Chinese, tone-colored pinyin) and any alternate form
- a meaning
- a short **nuance / slang note** — why it's used, how it hits, gotchas
- **spoken audio** — the word is spoken a few times; for Chinese the tones are
  then read aloud in English ("second tone, first tone") and the meaning too, so
  you can learn with your eyes entirely on your game

### How it helps you memorize (passively)

- **Spaced-repetition-lite, no grading** — it drills a small active batch
  (~12 words) on **expanding intervals**: a new word returns quickly, then less
  and less often as it sinks in, "graduating" once you've seen it enough while a
  new word takes its place. It's driven purely by exposure, so it stays passive.
- **Study first, test later** — the *first* time a word appears it's shown in
  full (`✦ NEW`). From the second exposure on, a recall delay hides the answer
  for a few seconds (`🤔 recall it…`) so your brain *tries* to remember before
  the answer appears — the testing effect, without you doing anything.
- **Tone-colored readings** — for Chinese, each syllable is colored by its tone
  (1 red · 2 gold · 3 green · 4 blue · neutral gray) to drill tones at a glance.
- **Anti-habituation** — the danger with any recurring popup is that your brain
  learns to tune it out, so three defenses keep it fresh: a **random-interval
  chime** pulls your eyes back; **unpredictable flashes** (weighted toward words
  you haven't learned) mean you can't pre-filter them; and **one-key recall** —
  press **`Ctrl+Alt+J`** ("I knew it") or **`Ctrl+Alt+K`** ("I didn't") while a
  word shows to turn a passive glance into active recall and steer the spacing.

Progress is saved per deck, so closing and reopening picks up exactly where you
left off.

### Test Mode

Passive learning, but sometimes you want to check yourself. **🧠 Test Mode** (on
the panel) opens a quick multiple-choice quiz: a word, four reading + meaning
options, pick the right one. Choose how many questions and whether to draw from
all your decks or just the one you're studying; it plays each word aloud as the
answer is revealed. Opening it pauses the overlay automatically.

## The control panel

The panel is **hidden by default** — press **`Ctrl+Alt+C`** (a global hotkey that
works even while your game has focus) to show or hide it. The flashcards keep
popping whether it's showing or not. Drag it by its title to reposition.

| Button | Does |
|---|---|
| ▶ Play / ⏸ Pause | Start the cycle / freeze it |
| ⏭ Skip | Jump to a new word now |
| 🔁 Replay | Say the current word again |
| ⏹ Stop | Halt and hide the card |
| 😈 Annoy | Toggle **annoying mode** (see below) |
| 🔊 Sound / 🔇 Silent | Toggle all audio (also `Ctrl+Alt+M`) |
| 📚 Get decks | Browse and install the creator decks |
| ✏ Make cards | Open the deck editor / importer |
| 🧠 Test Mode | Quiz yourself |
| ⚙ Settings | Timing, sound, appearance, hotkeys |
| ✕ | Quit |

**Silent mode** turns off all sound (word, tones, meaning, chimes). The
flashcards and the fullscreen flash still work — the flash just uses timed beats
instead of audio — so you can study visually with no noise.

### 😈 Annoying mode

When on, the word + reading + tones **flash huge across the whole screen** in
sync with each spoken repeat, then drop back to the normal card for the read-out.
The flash background is transparent (your game stays fully visible — only the
giant text shows) and, like the card, it's **click-through and never takes
focus**, so your cursor still reaches the game even while the letters cover it.

## Decks

Blip is Anki-like: **you author your own cards, audio is generated for them
automatically, and you can import decks from elsewhere.**

A fresh install studies a small neutral **Starter** deck. Everything else is
opt-in — **📚 Get decks** opens a catalog of bundled creator decks (Chinese: HSK,
slang, gaming, idioms, swears, ~475 words across five decks) that you preview and
install individually or all at once. Installing copies the deck in and
synthesizes its audio.

- **Make your own** — **✏ Make cards** opens a standalone editor. Add cards and
  it auto-fills the reading and tones (Chinese, via pypinyin) and generates the
  audio; you can override anything. Create, edit, and delete decks and cards.
- **Import** — CSV/TSV (it sniffs the delimiter and guesses the column mapping)
  or Anki `.apkg`. Media isn't imported — Blip re-synthesizes audio in one
  consistent voice, so there's nothing to redistribute.
- **Share** a deck by sharing its small JSON; the recipient synthesizes locally.

Audio is **content-addressed** — a clip's filename is a hash of its text, voice
and speed, never a word id — so two people can author the same id, an Anki import
can bring foreign ids, and nothing ever collides. A word you already have costs
nothing to add again.

## Settings

Everything — timing, how often a word pops, audio, appearance, the hotkeys — is
in the **⚙ Settings** window (`python -m blip.settings_ui`, or the panel button).
Changes apply next launch. The defaults live in `blip/settings.py`; a user
`settings.json` overrides them.

## Requirements

- Windows + Python 3 (tested on 3.14)
- `edge-tts` for generating audio (one-time per clip, needs internet):

  ```
  pip install edge-tts
  ```

Playback and the overlay use only built-in Windows features (MCI + tkinter) — no
other runtime dependencies. Audio is cached, so after it's generated once the app
works fully offline.

## Run it

Double-click **`run.bat`**, or from a terminal:

```
python -m blip
```

On first launch a welcome window appears and any missing audio is generated into
`audio/`; after that a card pops up on a timer and speaks the word.

## It won't steal your cursor or focus

The overlay windows are Windows **no-activate tool windows**
(`WS_EX_NOACTIVATE`): they draw on top but never take keyboard focus, so a pop
can't pull you out of a game. On top of that the **flashcard is fully
click-through** (`WS_EX_TRANSPARENT`) — your mouse passes straight through it to
the game underneath, so it can never intercept a click. All interaction happens
on the control panel, which stays clickable as normal.

## Fullscreen games

The overlay floats over windowed, borderless, **and fullscreen** games —
confirmed in Minecraft and PUBG. A genuinely *exclusive* fullscreen game (some
older DX titles) can still hide any overlay; if a pop never appears, switch that
game to Borderless or Windowed. That's a limitation of every overlay, not
something Blip can fix.

## License

MIT.
