"""Bringing decks in from elsewhere.

Every importer returns the same shape so the UI can treat them identically:

    ImportResult(fields, rows, source)

`fields` are the source's own column/field names, `rows` are dicts keyed by them.
The caller then supplies a **mapping** ({our field: their field}) and calls
`build_words()`. That two-step exists because neither CSV nor Anki has a fixed
schema — the user must say which column is the term and which is the meaning.
"""
from .common import ImportResult, build_words  # noqa: F401
