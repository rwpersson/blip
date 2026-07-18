"""The settings window is spec-driven, so the spec has to be true.

SPEC rows name settings by string. A key that doesn't exist in DEFAULTS produces
a row that silently does nothing — no crash, no complaint, just a control the
user changes and nothing happens. Nothing else checks this, and the spec is ~40
rows across 8 tabs.

Pure data: no Tk root here (see the one-root-per-process rule in CLAUDE.md).
"""
from blip.settings import DEFAULTS
from blip.settings_ui import SPEC


def _rows():
    for tab, rows in SPEC:
        for row in rows:
            yield tab, row


def test_every_row_names_a_real_setting():
    missing = []
    for tab, (key, _label, kind, _extra, _help) in _rows():
        # hotkeys live in a nested dict; everything else is top-level
        pool = DEFAULTS["hotkeys"] if kind == "hotkey" else DEFAULTS
        if key not in pool:
            missing.append(f"{tab}/{key}")
    assert not missing, f"settings rows that change nothing: {missing}"


def test_every_row_has_a_label():
    unlabelled = [f"{tab}/{key}" for tab, (key, label, *_r) in _rows()
                  if not label.strip()]
    assert not unlabelled


def test_numeric_rows_have_a_range_containing_the_default():
    """A default outside its own slider range means the window opens showing a
    value it won't let you pick again."""
    bad = []
    for tab, (key, _label, kind, extra, _help) in _rows():
        if kind in ("int", "float"):
            lo, hi = extra
            if not lo <= DEFAULTS[key] <= hi:
                bad.append(f"{tab}/{key}={DEFAULTS[key]} not in [{lo}, {hi}]")
    assert not bad, bad
