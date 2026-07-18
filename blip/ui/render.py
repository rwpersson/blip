"""Outlined text drawing.

The card panel is see-through, so plain text washes out over a bright game. Every
glyph gets a dark halo drawn 8 ways around it. Outlines are drawn for ALL segments
before any fill, otherwise a later segment's outline paints over its neighbour's fill.
"""
from tkinter import font as tkfont

from .. import decks as decks_mod
from . import theme

_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1))


def _font(family, size):
    return tkfont.Font(family=family, size=size, weight="bold")


def draw_row(canvas, segments, size, family, thickness=2, pad=3):
    """Left-aligned row of (text, color) segments, each haloed. Sizes the canvas."""
    canvas.delete("all")
    if not segments:
        canvas.configure(width=1, height=1)
        return
    f = _font(family, size)
    font = (family, size, "bold")
    t = thickness
    widths = [f.measure(s) for s, _ in segments]
    canvas.configure(width=sum(widths) + pad * 2 + t * 2,
                     height=f.metrics("linespace") + pad * 2 + t * 2)
    y = pad + t
    xs, x = [], pad + t
    for w in widths:
        xs.append(x)
        x += w
    for (s, _), x0 in zip(segments, xs):
        for dx, dy in _OFFSETS:
            canvas.create_text(x0 + dx * t, y + dy * t, text=s, fill=theme.HALO,
                               font=font, anchor="nw")
    for (s, color), x0 in zip(segments, xs):
        canvas.create_text(x0, y, text=s, fill=color, font=font, anchor="nw")


def draw_centered(canvas, cx, cy, segments, size, family):
    """Segments centered horizontally at (cx, cy). Returns the line height."""
    f = _font(family, size)
    font = (family, size, "bold")
    widths = [f.measure(s) for s, _ in segments]
    t = max(2, size // 22)
    x = cx - sum(widths) / 2
    xs, xx = [], x
    for w in widths:
        xs.append(xx)
        xx += w
    for (s, _), x0 in zip(segments, xs):
        for dx, dy in _OFFSETS:
            canvas.create_text(x0 + dx * t, cy + dy * t, text=s, fill=theme.HALO,
                               font=font, anchor="w")
    for (s, color), x0 in zip(segments, xs):
        canvas.create_text(x0, cy, text=s, fill=color, font=font, anchor="w")
    return f.metrics("linespace")


def reading_segments(word):
    """Tone-colored (text, color) segments for a word's reading + tone list.

    Falls back to a single accent color when the tone count doesn't match the
    syllable count (loanwords, or a deck with sloppy data).
    """
    syls = str(decks_mod.word_reading(word)).split()
    tones_raw = str(decks_mod.word_tones(word))
    tones = tones_raw.replace(" ", "").split("-")
    colored = len(syls) == len(tones)
    segs = []
    for i, syl in enumerate(syls):
        col = theme.TONE_COLORS.get(tones[i], theme.ACCENT) if colored else theme.ACCENT
        segs.append((syl, col))
        if i < len(syls) - 1:
            segs.append(("  ", theme.SUB))
    if tones_raw:
        segs.append((f"    ·  {tones_raw}", theme.SUB))
    return segs
