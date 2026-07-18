"""Standalone deck editor: `python -m blip.editor`.

Deliberately a separate program from the overlay. Authoring isn't something you do
mid-game, and it's an ordinary interactive window — it *wants* focus, which is the
exact opposite of every invariant in win32.py. Keeping them apart means the editor
can't regress the overlay's focus/click-through behaviour.
"""
