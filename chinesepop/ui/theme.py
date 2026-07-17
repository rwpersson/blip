"""Palette and typography.

Two rules worth keeping:

1. **BG doubles as the transparency color-key.** The text layers key it out, so it
   must match the panel colour or anti-aliased glyph edges fringe against the game.
   Nothing else may use exactly this value as a visible fill.

2. **Only the tone colours get to shout.** They're *functional* — you're supposed to
   read tone from hue at a glance — so everything else (category, badges, meaning)
   stays muted. Earlier the card ran four competing colour systems at once (bright
   category pill + tone colours + green meaning + gold badge) and read as confetti.
"""

BORDER = "#2b3040"      # a hair darker than the panel: an edge, not a frame
BG = "#1b1e27"          # also the transparency color-key — see module docstring
FG = "#f4f6fa"
ACCENT = "#ffb454"      # reading fallback when tones don't line up
SUB = "#8b95a5"         # notes / secondary
MEAN = "#cfd6e2"        # meaning: near-white, not a fifth colour
BTN = "#262b38"
BTN_HI = "#333a4a"
HALO = "#0b0e16"        # dark navy, not pure black — depth rather than a sticker

# Category is signalled by a small dot, not a filled pill, so the tone colours
# stay the loudest thing on the card.
CAT_COLORS = {
    "slang":  "#ff7597",
    "gaming": "#7aa2ff",
    "common": "#8bd450",
    "hsk":    "#5ad1c9",
    "idiom":  "#c792ea",
    "swear":  "#ff5c5c",
}

# Standard-ish tone colors. These are the one place loud is correct.
TONE_COLORS = {"1": "#ff6b6b", "2": "#ffd166", "3": "#06d6a0",
               "4": "#4d96ff", "·": "#8b95a5", "5": "#8b95a5"}

STATUS_OK = "#8bd450"
STATUS_WARN = "#ffb454"
STATUS_STOP = "#ff5c5c"
NEW_BADGE = "#ffd166"

# --- typography -------------------------------------------------------------
# One face for everything meant YaHei was rendering the English too, and its Latin
# glyphs are mediocre. Pair them: a real UI face for prose, a CJK face for the term.
UI_FONT_STACK = ("Segoe UI Variable Text", "Segoe UI", "Tahoma")


def ui_font(root=None):
    """First installed UI face — never assume Segoe UI exists."""
    try:
        from tkinter import font as tkfont
        available = set(tkfont.families(root))
        for name in UI_FONT_STACK:
            if name in available:
                return name
    except Exception:
        pass
    return "Segoe UI"


# --- spacing ----------------------------------------------------------------
# An 8px rhythm; mixed 12/14 padding is what makes a layout feel accidental.
PAD = 8
PAD_L = 16
CARD_RADIUS = 12
