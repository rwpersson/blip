# Roadmap: personal tool → shippable product

Status legend: ☐ todo · ◐ in progress · ☑ done

The app *works*. What's missing is everything that assumes a second user exists:
someone without Python, without your file paths, on a different monitor setup, who
will never open `pop.py` to change a constant.

Ordered so each phase unblocks the next. Phases 0–3 are the real "can I ship this
at all" work; 4+ is what makes it good.

---

## Phase 0 — Foundations (half a day)

Nothing here is glamorous; everything after it is harder without it.

- ☐ `git init` + `.gitignore` (`audio/`, `sounds/`, `state.json`, `__pycache__/`, `dist/`, `build/`)
- ☐ `requirements.txt` / `pyproject.toml` — right now `edge-tts` is an undeclared dependency
- ☐ `LICENSE` + attribution for word data
- ☑ `CLAUDE.md` context doc
- ☐ Decide the product shape (see **Open decisions**) — this changes Phases 3 & 6

## Phase 1 — Architecture (1–2 days)

`pop.py` is 1230 lines doing Win32 interop, audio, scheduling, and four windows.
It's at the size where every new feature risks the focus/click-through invariants.

- ☐ Split into a package:
  ```
  chinesepop/
    __main__.py        app entry
    app.py             orchestration only
    settings.py        load/save/migrate user settings
    decks.py           deck load + schema validation
    scheduler.py       SRS
    platform/win32.py  ctypes: no-activate, click-through, hotkeys, DPI
    audio/player.py    MCI + winsound playback
    audio/tts.py       TTS provider interface (see Phase 3)
    audio/cues.py      chime synthesis
    ui/card.py  ui/flash.py  ui/panel.py  ui/settings_window.py
  ```
- ☐ Replace bare `except: pass` with real logging → `%APPDATA%\ChinesePop\logs\`
  (you cannot debug a stranger's crash without this)
- ☐ Commit a real test suite (port the throwaway scripts: focus-steal, click-through,
  scheduler, censor, chime cadence) + `pytest` + GitHub Actions

## Phase 2 — Data model (1 day)

- ☐ **Move user data out of the install dir** → `%APPDATA%\ChinesePop\`
  (settings, state, custom decks). Installed under `Program Files`, today's writes fail.
- ☐ **Content-addressed audio**: key clips by `hash(say_text + voice + rate)` instead of
  a global int id. Fixes the id-collision landmine when users import decks, dedupes
  identical words across decks, and makes voice changes cache-safe.
- ☐ Versioned schemas + migration for `state.json` and deck files (`"schema": 1`)
- ☐ Deck validation with human-readable errors (bad pinyin/tones counts, dup hanzi,
  missing fields) — third-party decks *will* be malformed
- ☐ Settings file (JSON) replacing the module constants

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
- ☐ **Deck manager** — enable/disable, create/edit words in-app, import/export,
  CSV + Anki `.apkg` import
- ☐ **Rebindable hotkeys** + conflict detection (today `Ctrl+Alt+C/J/K/M` are hardcoded
  and silently fail if taken)
- ☐ **Multi-monitor + DPI awareness** — `winfo_screenwidth()` is the primary monitor
  only; on a HiDPI or multi-head setup the card lands wrong or renders blurry.
  Needs `SetProcessDpiAwarenessContext` + a monitor picker.
- ☐ **Content filter** — a "hide swears" toggle. Shipping a deck of profanity with no
  opt-out is a support problem (and an app-store one).
- ☐ Tray icon (show/hide/quit/pause) — more discoverable than a hidden panel
- ☐ Pause when a fullscreen app is foreground / do-not-disturb

## Phase 5 — Learning quality (1–2 days)

- ☐ Real SRS (**FSRS** or SM-2) now that the recall hotkeys provide grades; keep the
  current exposure-based mode as "passive mode" for when you don't want to press keys
- ☐ Stats/progress view (words learned, streak, per-deck, retention)
- ☐ Leech detection (words you keep missing → surface differently, not just more often)
- ☐ Example sentences (the one high-value learning feature never built)

## Phase 6 — Packaging & release (1–2 days)

- ☐ **PyInstaller** build (one-folder), icon, version info — users will not install Python
- ☐ Installer (Inno Setup) **or** portable zip; per-user install avoids admin
- ☐ Code signing, or document the SmartScreen warning (unsigned = scary first-run)
- ☐ Auto-update check
- ☐ Crash reporting: "copy log" button
- ☐ CI: build + test on tag; publish releases

## Phase 7 — Polish & distribution

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
