"""
Generate the spoken audio for every word in every deck.

    python generate_audio.py            # fill in anything missing
    python generate_audio.py --force    # rebuild everything (after a voice change)
    python generate_audio.py --prune    # also delete clips nothing references

Clips are content-addressed (see chinesepop/audio/clips.py), so this only ever
synthesizes speech that doesn't already exist — identical words across decks share
a file, and changing a voice re-keys just the affected clips rather than the lot.

This is a thin CLI over chinesepop.audio.tts — the voices, the profanity filter
and the clip layout all live in the package, so there's one source of truth.
"""
import sys

from chinesepop import decks as decks_mod
from chinesepop import paths, settings as settings_mod
from chinesepop.audio import tts
from chinesepop.logging_setup import get, setup


def main():
    setup()
    log = get("generate_audio")
    paths.ensure_dirs()
    force = "--force" in sys.argv

    s = settings_mod.load()
    decks = decks_mod.load_all()
    if not decks:
        log.error("No decks found in %s",
                  ", ".join(str(d) for d in paths.decks_dirs()))
        return 1

    provider = tts.get_provider(s.tts_provider)
    if not provider.available():
        log.error("TTS provider %r is unavailable. `pip install edge-tts`?",
                  provider.name)
        return 1

    def progress(i, total, word):
        log.info("  [%s/%s] %s -> %s", i, total,
                 decks_mod.word_term(word), word["id"])

    log.info("Generating audio (provider=%s, voice=%s, rate=%s)%s ...",
             provider.name, s.voice, s.rate, " [FORCE]" if force else "")
    ok, total = tts.generate(decks, s, force=force, progress=progress)
    if total == 0:
        log.info("All audio already present. Nothing to do.")
    else:
        log.info("Done: %s/%s generated. Files in %s", ok, total, paths.audio_dir())

    if "--prune" in sys.argv:
        n, freed = tts.prune(decks, s)
        log.info("Pruned %s unreferenced clip(s), freed %.1f MB",
                 n, freed / 1_000_000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
