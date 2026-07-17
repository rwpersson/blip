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

## Phase 2 — Data model (1 day) — **now a hard blocker**

The Anki-style direction (users author + import cards, see Phase 5) makes this
non-negotiable: **global integer ids cannot survive user-created or imported
cards.** Two users both author id `421` and get each other's audio; an Anki import
brings ids from a foreign system entirely. Do this before anyone has decks in the wild.

- ☑ Settings file (JSON) replacing the module constants
- ☑ Deck validation with human-readable errors — third-party decks *will* be malformed
- ☑ `paths.py` routes user data to `%APPDATA%\ChinesePop\` once frozen
  (dev stays in-tree). Still to verify under a real installed build.
- ☐ **Content-addressed audio** — key clips by `hash(say_text + voice + rate)`
  instead of a word id. This is the keystone:
  - ids stop being global, so authored/imported cards can't collide
  - identical words across decks share one clip (free dedupe)
  - a voice change re-keys instead of corrupting the cache
  - **sharing a deck becomes sharing a small JSON** — no media bundle, no
    redistribution question, because audio is synthesized on the recipient's machine
- ☐ Versioned schemas + migration for `state.json` (v3) and deck files
- ☐ Generic field rename `hanzi`→`term`, `pinyin`→`reading` + deck `language`/`voice`
  (contained to `decks.py`; the app already reads via accessors)

## Phase 3 — TTS: move to Piper (1–2 days)

Removes the edge-tts licensing risk and makes the app fully offline.

- ☐ TTS provider interface: `synthesize(text, voice, rate) -> bytes`
- ☐ `PiperProvider` — bundle a `zh_CN` model; keep `EdgeProvider` as a dev-only option
- ☐ Quality pass: Piper needs tuning to match Yunyang's tone clarity (rate/model choice).
      **Verify by ear before committing** — tone clarity is the whole point of the app.
- ☐ First-run synthesis with a progress UI + resumable cache (~1300 clips)
- ☐ Fall back gracefully when a voice/model is missing (text-only, don't crash)

## Phase 4 — Product UX (2–3 days)

Everything a stranger needs that you don't, because you edit the source.

- ☐ **Settings window** — every constant becomes a control (interval, repeats, sizes,
  colors, alpha, chime/flash odds, batch size). This is the single biggest "it's a
  product now" change.
- ☐ **First-run wizard** — pick decks, set interval, test the overlay, explain the
  hotkeys and the fullscreen caveat
- ☐ **Deck manager** — enable/disable decks, reorder (authoring/import is Phase 5)
- ☐ **Rebindable hotkeys** + conflict detection (today `Ctrl+Alt+C/J/K/M` are hardcoded
  and silently fail if taken)
- ☐ **Multi-monitor + DPI awareness** — `winfo_screenwidth()` is the primary monitor
  only; on a HiDPI or multi-head setup the card lands wrong or renders blurry.
  Needs `SetProcessDpiAwarenessContext` + a monitor picker.
- ☐ **Content filter** — a "hide swears" toggle. Shipping a deck of profanity with no
  opt-out is a support problem (and an app-store one).
- ☐ Tray icon (show/hide/quit/pause) — more discoverable than a hidden panel
- ☐ Pause when a fullscreen app is foreground / do-not-disturb

## Phase 5 — User content: author, generate, import (3–4 days) ★ core direction

The Anki-like half of the product: **users make their own cards, get audio for them
automatically, and bring in decks from elsewhere.** Depends on Phase 2
(content-addressed audio) and Phase 3 (Piper: offline synthesis means a new card gets
audio in a second, with no account, no network, no licensing question).

**Authoring**
- ☐ Deck editor: create/rename/delete decks, add/edit/delete cards, live validation
- ☐ **Audio on save** — synthesize just the new/edited card's clips immediately with a
  small progress indicator; never a full batch pass
- ☐ **Auto-fill reading + tones** for Chinese via `pypinyin` (MIT): the user types
  你好, we derive `nǐ hǎo` + `3-3`. Removes the tedious part of authoring and is why
  tone data stays optional/derivable in the schema.
- ☐ Duplicate detection across decks on add (we already validate; surface it in the UI)

**Import**
- ☐ **CSV/TSV first** — covers most "I have a word list" cases; column-mapping step
  (which column is term / reading / meaning / note) + preview before commit
- ☐ **Anki `.apkg`** — the real ask. Notes:
  - `.apkg` is a ZIP: `collection.anki2` (SQLite), sometimes `collection.anki21`,
    and newer exports use **zstd-compressed `.anki21b`** — handle or reject clearly
  - `notes.flds` packs fields joined by `\x1f`; field *names* come from the notetype
    JSON, so there is no fixed schema → **a field-mapping UI is mandatory**
  - fields contain **HTML** and `[sound:file.mp3]` / `<img>` refs — strip them
  - media is a JSON name→number map plus numbered files
  - **Prefer re-synthesizing over importing their media**: one consistent voice, no
    redistribution question, smaller. Offer "use bundled audio" only as an option.
- ☐ **Export** a deck (JSON, and CSV) — trivial once audio isn't bundled
- ☐ Import from a URL/file drop; a shared-deck index is a stretch goal

## Phase 6 — Learning quality (1–2 days)

- ☐ Real SRS (**FSRS** or SM-2) now that the recall hotkeys provide grades; keep the
  current exposure-based mode as "passive mode" for when you don't want to press keys
- ☐ Stats/progress view (words learned, streak, per-deck, retention)
- ☐ Leech detection (words you keep missing → surface differently, not just more often)
- ☐ Example sentences (the one high-value learning feature never built)

## Phase 7 — Packaging & release (1–2 days)

- ☐ **PyInstaller** build (one-folder), icon, version info — users will not install Python
- ☐ Installer (Inno Setup) **or** portable zip; per-user install avoids admin
- ☐ Code signing, or document the SmartScreen warning (unsigned = scary first-run)
- ☐ Auto-update check
- ☐ Crash reporting: "copy log" button
- ☐ CI: build + test on tag; publish releases

## Phase 8 — Polish & distribution

- ☐ README with GIFs/screenshots, landing page or itch.io/GitHub Releases
- ☐ Onboarding docs: fullscreen-exclusive caveat, antivirus false-positives (PyInstaller)
- ☐ Accessibility: font scaling, colorblind-safe tone palette (red/green tones today)
- ☐ Opt-in telemetry only, if at all

---

## Decisions (locked)

1. **Free & open-source.** GitHub Releases. Keeps legal risk low; no code signing
   required for v1 (document the SmartScreen warning instead).
2. **TTS = Piper** (MIT, offline, bundled zh_CN model, generated on device). Removes
   the edge-tts risk entirely and makes the app work offline with no account.
   `edge-tts` stays as an optional dev-only generator behind the provider interface.
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
- **Exclusive-fullscreen games** can hide any overlay; must be documented, not fixed.
- **Regression risk** in the Win32 invariants listed in `CLAUDE.md` — keep the tests.
