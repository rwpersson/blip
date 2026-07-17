"""Palette.

BG doubles as the color-key for transparency: the text layers key it out, so it
must match the panel color or anti-aliased glyph edges fringe against the game.
Nothing else may use exactly this value as a visible fill.
"""

BORDER = "#3a4152"
BG = "#1b1e27"          # also the transparency color-key — see module docstring
FG = "#f2f4f8"
ACCENT = "#ffb454"      # pinyin fallback
SUB = "#9aa4b2"         # notes / secondary
MEAN = "#8bd450"        # meaning
BTN = "#2a2f3d"
BTN_HI = "#3a4152"
HALO = "#04060c"        # outline behind the word, for legibility over any game

CAT_COLORS = {
    "slang":  "#ff7597",
    "gaming": "#7aa2ff",
    "common": "#8bd450",
    "hsk":    "#5ad1c9",
    "idiom":  "#c792ea",
    "swear":  "#ff5c5c",
}

# Standard-ish tone colors, readable on a dark card.
TONE_COLORS = {"1": "#ff6b6b", "2": "#ffd166", "3": "#06d6a0",
               "4": "#4d96ff", "·": "#9aa4b2", "5": "#9aa4b2"}

STATUS_OK = "#8bd450"
STATUS_WARN = "#ffb454"
STATUS_STOP = "#ff5c5c"
NEW_BADGE = "#ffd166"
