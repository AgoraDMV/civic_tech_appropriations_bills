"""Shared text normalization for recall tests.

Comparison across recall tests is whitespace-normalized substring matching:
permissive on purpose, since the goal is recall (did the text survive?), not
byte-exact reproduction.
"""

from __future__ import annotations

import re

from parsers.pdf_text import normalize_glyphs

_WS = re.compile(r"\s+")
# Real compounds like `Child-Rescue` that wrap at a line boundary surface as
# `Child- Rescue` after extraction. The `parse_lines` lowercase guard preserves
# the hyphen but can't tell a soft wrap from a compound at the wrap point, so a
# space leaks in. Positional disambiguation was attempted (see git history) but
# couldn't reliably distinguish all-caps soft hyphens from compounds. Collapse
# the artifact at compare-time only — the diff layer is unaffected.
_WRAPPED_COMPOUND = re.compile(r"(\w)- (\w)")


def normalize_for_recall(text: str) -> str:
    """Glyph-normalize, collapse whitespace, and rejoin wrapped compounds."""
    canonical = _WS.sub(" ", normalize_glyphs(text)).strip()
    return _WRAPPED_COMPOUND.sub(r"\1-\2", canonical)
