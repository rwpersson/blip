# Roadmap: personal tool → shippable product

Status legend: ☐ todo · ◐ in progress · ☑ done

The app *works*. What's missing is everything that assumes a second user exists:
someone without Python, without your file paths, on a different monitor setup, who
will never open a `.py` file to change a constant — and who wants to make their own
cards and bring in decks from elsewhere.

Ordered so each phase unblocks the next. Phases 2–3 are what "can I ship this at
all" hinges on; **Phase 5 (user content) is the core product direction** and is why
Phase 2 can't be skipped.

---

## Phase 0 — Foundations ☑ DONE

Nothing here is glamorous; everything after it is harder without it.

- ☑ `git init` + `.gitignore` (`audio/`, `sounds/`, `state.json`, `__pycache__/`, `dist/`, `build/`)
- ☑ `requirements.txt` — right now `edge-tts` is an undeclared dependency
- ☑ `LICENSE` (MIT) + attribution for word data
- ☑ `CLAUDE.md` context doc
- ☑ Decide the product shape (see **Open decisions**) — this changes Phases 3 & 6

## Phase 1 — Architecture ☑ DONE

`pop.py` had reached 1230 lines doing Win32 interop, audio, scheduling and four
windows at once — every new feature risked the focus/click-through invariants.
Split into `chinesepop/` (see CLAUDE.md for the layout).

- ☑ Package split; behaviour in `app.py`, all ctypes isolated in `win32.py`
- ☑ Replace bare `except: pass` with real logging (`logs/`, `%APPDATA%` once frozen)
- ☑ Test suite: **33 tests**, incl. driving real windows and a separate-process
  window proving focus is never stolen
- ☐ GitHub Actions to run the suite on push
  (note: `test_win32.py` needs a desktop session — headless CI will skip it)

**Found in passing:** a real focus bug — Tk creates a wrapper toplevel at map time
and *that* handle is the one Windows focuses, so the control panel was silently
activatable (clicking a button could steal focus from the game). See CLAUDE.md
gotcha #1.

## Phase 2 — Data model ☑ DONE

The Anki-style direction (users author + import cards, see Phase 5) makes this
non-negotiable: **global integer ids cannot survive user-created or imported
cards.** Two users both author id `421` and get each other's audio; an Anki import
brings ids from a foreign system entirely. Do this before anyone has decks in the wild.

- ☑ Settings file (JSON) replacing the module constants
- ☑ Deck validation with human-readable errors — third-party decks *will* be malformed
- ☑ `paths.py` routes user data to `%APPDATA%\ChinesePop\` once frozen
  (dev stays in-tree). Still to verify under a real installed build.
- ☑ **Content-addressed audio** (`audio/clips.py`) — clips keyed by
  `hash(text + voice + rate)`. ids no longer decide filenames, so authored/imported
  cards can't collide; identical speech shares one file; a voice change re-keys only
  the affected clips. Sharing a deck = sharing a small JSON.
- ☑ Deck schema 1 + generic fields (`term`/`reading`, deck `language`/`voice`);
  accessors still read the old `hanzi`/`pinyin` so foreign decks keep working
- ☑ `migrate.py` — renamed the existing 1259 clips in place (**no re-synthesis**) and
  rewrote the decks. Real result: **1259 → 924 clips, 22 MB → 16 MB**, because 335
  were duplicate tone read-outs.
- ☑ `generate_audio.py --prune` removes clips nothing references
- ☐ Verify `%APPDATA%` user-data routing under a real frozen build (needs Phase 7)
- ☐ `state.json` migration is trivial today (v3 is additive); revisit if the shape
  changes again

## Phase 3 — TTS ☑ EVALUATED → **staying on edge-tts**

Piper was evaluated properly (installed, models downloaded, A/B synthesized) and
**rejected by ear**. Recording the measurements so nobody re-litigates this blind:

| | huayan | chaowen | **edge-tts Yunyang** |
|---|---|---|---|
| phonemizer | espeak (`cmn`) | pinyin + tones (`g2pw`) | — |
| speed/clip | 0.06 s | **5.28 s** | ~0.5 s (network) |
| extra deps | none | `transformers`, `g2pw`, `unicode_rbnf`, `sentence_stream` | none |
| offline | ✅ | ❌ pulls a BERT model from HF on first use | ❌ to generate |
| gender | female | — | male |
| **verdict** | rejected | rejected | **chosen — best tones** |

Piper's only two usable zh voices both fail: `huayan` is female + espeak-phonemized;
`chaowen` at 5.28 s/clip means ~81 min to build the library and a 5 s wait to hear a
card you just authored — which would gut Phase 5's authoring UX and the offline
promise that justified Piper in the first place.

- ☑ TTS provider interface (`audio/tts.py`) — the seam survives and is the mitigation
- ☑ Graceful degradation: a failed/missing clip logs and shows a quiet card, never crashes
- ☐ **Risk to manage**: edge-tts talks to an undocumented Edge endpoint that Microsoft
  can change or block. If that happens, existing users are fine (clips are cached
  forever) but new ones can't generate. Mitigations, in order of cost:
  - keep the provider interface clean (done) so a swap is contained
  - offer `PiperProvider` as an **optional offline fallback** (huayan) — insurance, not default
  - if it ever dies for real: revisit a bundled engine, or distribute a prebuilt
    clip pack for the shipped decks
- ☐ **Idea worth keeping** if we ever need Piper: skip `g2pw` entirely by feeding
  phonemes from the deck's own `reading`+`tones` (we already store them) via
  `phonemes_to_ids()`/`phoneme_ids_to_audio()`. Faster *and* more accurate than a
  polyphone guesser, since the author specified the reading. Pairs with the Phase-5
  `pypinyin` auto-fill.

## Phase 4 — Product UX ☑ DONE (tray moved to Phase 7)

Everything a stranger needs that you don't, because you edit the source.

- ☑ **Settings window** — `python -m chinesepop.settings_ui`, also a ⚙ button on the
  panel. Spec-driven (`SPEC` in settings_ui.py): 39 settings across 8 tabs, so adding
  one is a single line. Launches as its own process — it needs focus, the overlay
  must never take it.
- ☑ **First-run welcome** (`firstrun.py`) — shown *before* the ~900-clip first
  synthesis, so a silent screen is explained rather than mysterious. Tells you the
  three things you can't guess (the panel is hidden; the hotkeys; fullscreen is
  fine), and offers interval / hide-swears / annoying-mode up front. Its own
  process, like Settings.
- ☑ **Deck manager** — enable/disable decks (Settings ▸ Content). ☐ reorder
- ☑ **Rebindable hotkeys** + conflict detection: a **Test** button probes whether the
  combo is actually free (RegisterHotKey is the only honest check), duplicates within
  our own map are caught on save, and dead bindings are now logged by name at startup
  instead of failing silently.
- ☑ **DPI awareness** — was affecting *this* machine: at 125% scaling Tk saw 1536×960
  for a real 1920×1200 screen and Windows bitmap-stretched the overlay (blurry). Now
  per-monitor aware, with fonts and pixel settings scaled to match.
- ☑ **Multi-monitor** — `win32.monitors()` enumerates real screens; the overlay is
  placed on `settings.monitor` (picker in Settings), falling back if it's unplugged.
- ☑ **Content filter** — `hide_swears` drops that category (420→374 words here), and
  `enabled_decks` picks what's in rotation. Filters copy rather than mutate, so the
  editor still sees every card; a deck emptied by a filter is dropped rather than
  stalling the scheduler.
- → **Tray icon: moved to Phase 7.** It needs an .ico asset, which packaging
  needs anyway, so they're one job. Discoverability is covered meanwhile by the
  first-run welcome, the launch peek at the panel, and the console line.
- ✗ ~~Pause when a fullscreen app is foreground~~ — **dropped**: the overlay
  demonstrably works over fullscreen Minecraft and PUBG, so this would break the
  main use case rather than protect it. The premise ("fullscreen hides overlays")
  was wrong for modern Windows.

## Phase 5 — User content: author, generate, import ☑ DONE ★

The Anki-like half of the product: **users make their own cards, get audio for them
automatically, and bring in decks from elsewhere.** Phase 2 is what makes it safe —
content-addressed audio means an authored or imported card can't collide with
anyone's, and a new card's audio is free if that exact clip already exists.

Note: authoring a card needs network for its first synthesis (edge-tts, Phase 3).
Acceptable — it's one short request per new card, and playback is cached forever.

**Authoring**
- ☑ **Deck editor** — standalone `python -m chinesepop.editor`: decks | cards | form,
  filter, create/delete decks + cards, export. Logic lives in `editor/controller.py`
  (no Tk) so it's testable; the window is dumb.
- ☑ **Audio on save** — one card, on a worker thread with status feedback; free when
  the clip already exists. A failure leaves a silent card, never a crash.
- ☑ **Auto-fill reading + tones** via `pypinyin` (`lang.py`): 你好 → `nǐ hǎo` + `3-3`,
  and it resolves polyphones from context (银行 `yín háng`, not `xíng`). Treated as a
  suggestion the author can override.
- ☑ Duplicate detection — the editor warns *which deck* already has the term

**Import**
- ☑ **CSV/TSV** — sniffs delimiter/encoding (BOM, cp1252, gb18030), guesses the
  mapping, positional fallback with no header
- ☑ **Anki `.apkg`** — implemented; the traps, all handled:
  - `.apkg` is a ZIP: `collection.anki2` (SQLite), sometimes `collection.anki21`,
    and newer exports use **zstd-compressed `.anki21b`** — handle or reject clearly
  - `notes.flds` packs fields joined by `\x1f`; field *names* come from the notetype
    JSON, so there is no fixed schema → **a field-mapping UI is mandatory**
  - fields contain **HTML** and `[sound:file.mp3]` / `<img>` refs — strip them
  - media is a JSON name→number map plus numbered files
  - media is **not** imported: we re-synthesize for one consistent voice and no
    redistribution question
  - imported tags are normalised onto our categories (`hsk1`→`hsk`) or dropped —
    otherwise the imported deck fails validation
- ☑ **Export** a deck (JSON + Excel-safe CSV) — trivial, since audio isn't bundled
- ☑ Import wizard: file → mapping (pre-guessed) → live preview → target deck
- ☑ Import a shared Chinese Pop deck (`.json`) — sharing is just the JSON
- ☐ Import from a URL/file drop; a shared-deck index is a stretch goal

**Creator-deck catalog** ☑ DONE

The author's personal decks are no longer baked in active for everyone. A fresh
install studies a neutral **Starter** (20 words); the five week decks moved to a
bundled `catalog/` the user browses and installs opt-in (`catalog.py` +
`catalog_ui.py`, reachable from first-run, the panel, and the editor).
- ☑ Bundled, not fetched — deck JSON is ~130 KB, so no hosting / offline / no 2nd
  network dependency. `catalog.py` leaves room for a `RemoteCatalog` later.
- ☑ Audio synthesized on install, never shipped; degrades gracefully offline.
- ☐ Later: a *remote* catalog so decks can be added without an app release; a
  community deck index (ties into the URL-import stretch goal above).

## Phase 6 — Learning quality (1–2 days)

- ☐ Real SRS (**FSRS** or SM-2) now that the recall hotkeys provide grades; keep the
  current exposure-based mode as "passive mode" for when you don't want to press keys
- ☐ Stats/progress view (words learned, streak, per-deck, retention)
- ☐ Leech detection (words you keep missing → surface differently, not just more often)
- ☐ Example sentences (the one high-value learning feature never built)

## Phase 7 — Packaging & release (1–2 days)

- ☐ **App icon** (.ico) — needed by PyInstaller *and* by the tray icon; do them together
- ☐ **Tray icon** — show/hide panel, pause, quit (moved from Phase 4)
- ☐ **PyInstaller** build (one-folder), icon, version info — users will not install Python
- ☐ Installer (Inno Setup) **or** portable zip; per-user install avoids admin
- ☐ Code signing, or document the SmartScreen warning (unsigned = scary first-run)
- ☐ Auto-update check
- ☐ Crash reporting: "copy log" button
- ☐ CI: build + test on tag; publish releases

## Phase 8 — Polish & distribution

- ☐ README with GIFs/screenshots, landing page or itch.io/GitHub Releases
- ☐ Onboarding docs: antivirus false-positives (PyInstaller), the rare
  exclusive-fullscreen caveat
- ☐ Accessibility: font scaling, colorblind-safe tone palette (red/green tones today)
- ☐ Opt-in telemetry only, if at all

---

## Decisions (locked)

1. **Free & open-source.** GitHub Releases. Keeps legal risk low; no code signing
   required for v1 (document the SmartScreen warning instead).
2. **TTS = edge-tts.** *(Reversed after evaluation — see Phase 3.)* Piper was the plan,
   but its Chinese voices lost the listening test: the fast one (`huayan`) is female
   and espeak-phonemized, and the pinyin-phonemized one (`chaowen`) costs **5.3 s per
   clip** — ~81 min to build the library, and a 5-second wait to hear a card you just
   authored. Tone clarity is the entire point of the app, so quality wins.
   Consequences accepted: **needs network to generate** (playback is cached and
   offline), and the endpoint is undocumented and could change under us. Mitigated by
   the provider interface + graceful degradation (see Phase 3).
3. **Generic language overlay.** Decks declare their own `language` + `voice`; tones
   and readings become optional, Chinese-specific niceties rather than the core model.
   Chinese stays the flagship (tone colors, tone read-out) — it just isn't hardcoded.
4. **Windows-only for v1.** The overlay is deeply Win32. Isolate it in
   `platform/win32.py` so a future port is possible, but don't pay for it now.
5. **Generate audio on device** (Piper) rather than shipping 22 MB — decided by #2.
   First run does a one-time synthesis pass with a progress UI.

### What "generic" changes

Deck/word fields become language-neutral in **Phase 2** (with a migration):

| Today | Becomes | Notes |
|---|---|---|
| `hanzi` | `term` | the thing being learned |
| `pinyin` | `reading` | romanization/pronunciation; optional |
| `tones` | `tones` | optional, Chinese-only; drives tone colors + read-out |
| — | deck `language`, `voice` | picks the TTS voice per deck |

Phase 1 keeps the current field names and contains all deck I/O in `decks.py`, so the
rename is a single-file change later.

## Known risks

- **edge-tts licensing** — the one thing that can actually stop a release (Phase 3).
- **Global word ids** — decks are not portable until audio is content-addressed (Phase 2).
- **Antivirus/SmartScreen** false positives on unsigned PyInstaller binaries.
- **Truly exclusive-fullscreen games** (older DX titles) can hide any overlay.
  Rare in practice — fullscreen Minecraft/PUBG are fine — but document it.
- **Regression risk** in the Win32 invariants listed in `CLAUDE.md` — keep the tests.
