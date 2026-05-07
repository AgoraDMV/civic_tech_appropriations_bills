"""Line-level diff for PDF bill versions, parallel to diff_bill.py for XML.

Produces a `PdfDiff` of `PdfHunk` records. Each hunk carries a v1/v2 page+line
range, the nearest preceding anchor on each side (TITLE / SEC. / account), the
two text variants, and amount pairs when dollar amounts changed.

The classifier distinguishes:
- `added` — present only in v2
- `removed` — present only in v1
- `moved` — body similar but anchor differs (renumbered SEC. or moved account)
- `modified` — everything else changed

Reuses amount extraction (`extract_amounts`, `match_amounts`) and text
similarity (`_text_similarity`) from diff_bill.py.
"""

from __future__ import annotations

import bisect
import difflib
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from diff_bill import _text_similarity, match_amounts
from parsers.pdf_anchors import Anchor, extract_anchors
from parsers.pdf_text import Page

ChangeType = Literal["added", "removed", "modified", "moved"]
PageLineRange = tuple[int, int, int, int]  # (start_page, start_line, end_page, end_line)

# A hunk's anchor is "moved" only if the bodies are highly similar AND the
# anchors differ; otherwise the anchor change is incidental and the hunk is a
# normal modification. 0.6 matches diff_bill's _MOVE_THRESHOLD.
_MOVE_SIMILARITY_THRESHOLD = 0.6


@dataclass(frozen=True)
class PdfHunk:
    change_type: ChangeType
    v1_anchor: Anchor | None
    v2_anchor: Anchor | None
    v1_range: PageLineRange | None
    v2_range: PageLineRange | None
    v1_text: str
    v2_text: str
    amount_pairs: tuple[tuple[int | None, int | None], ...] = ()


@dataclass(frozen=True)
class PdfDiff:
    hunks: tuple[PdfHunk, ...]

    @property
    def summary(self) -> dict[str, int]:
        return dict(Counter(h.change_type for h in self.hunks))


# ---- Internal helpers --------------------------------------------------------


@dataclass(frozen=True)
class _IndexedLine:
    text: str
    page_number: int
    line_number: int | None  # None when source PDF didn't number this line


def _flatten(pages: list[Page]) -> list[_IndexedLine]:
    """Flatten pages into a single ordered list of (text, page, line) records."""
    flat: list[_IndexedLine] = []
    for page in pages:
        for line in page.lines:
            flat.append(_IndexedLine(line.text, page.page_number, line.line_number))
    return flat


def _range_from_lines(lines: list[_IndexedLine]) -> PageLineRange | None:
    """Compute (start_page, start_line, end_page, end_line) from indexed lines.

    Falls back to a sentinel `-1` when source line numbers are unknown so the
    range remains a 4-tuple of ints; the renderer can spot `-1` as "unnumbered".
    """
    if not lines:
        return None
    first, last = lines[0], lines[-1]
    return (
        first.page_number,
        first.line_number if first.line_number is not None else -1,
        last.page_number,
        last.line_number if last.line_number is not None else -1,
    )


def _nearest_preceding_anchor(anchors: list[Anchor], page: int, line: int, max_page_distance: int = 2) -> Anchor | None:
    """Binary-search for the largest anchor at or before (page, line).

    `max_page_distance` caps how far back to look. The nearest anchor on the
    same page is always preferred; otherwise we accept up to N pages back. If
    the only candidate is further than that, return None — the renderer treats
    this as the degraded "anchor unresolved" case.
    """
    if not anchors or line < 0:
        return None
    keys = [(a.page_number, a.line_number) for a in anchors]
    idx = bisect.bisect_right(keys, (page, line)) - 1
    if idx < 0:
        return None
    candidate = anchors[idx]
    if page - candidate.page_number > max_page_distance:
        return None
    return candidate


def _amount_pairs_when_changed(v1_text: str, v2_text: str) -> tuple[tuple[int | None, int | None], ...]:
    """Return non-trivial amount pairs (i.e. excluding pairs that are unchanged)."""
    pairs = match_amounts(v1_text, v2_text)
    nontrivial = tuple((old, new) for old, new in pairs if old != new)
    return nontrivial


def _classify_replace(
    v1_text: str,
    v2_text: str,
    v1_anchor: Anchor | None,
    v2_anchor: Anchor | None,
) -> ChangeType:
    """A SequenceMatcher 'replace' opcode is moved iff body is similar and anchors differ."""
    if v1_anchor and v2_anchor and v1_anchor.text != v2_anchor.text:
        if _text_similarity(v1_text, v2_text) >= _MOVE_SIMILARITY_THRESHOLD:
            return "moved"
    return "modified"


def _reconcile_moves(hunks: list[PdfHunk], threshold: float = _MOVE_SIMILARITY_THRESHOLD) -> list[PdfHunk]:
    """Pair `removed`+`added` hunks whose bodies are highly similar into `moved` hunks.

    SequenceMatcher's line-level alignment routinely splits a renumbered section
    (e.g. SEC. 414 in v1 → SEC. 413 in v2 at a different absolute position) into
    a delete on one side and an insert on the other. This pass walks all
    remove/add pairs, computes text similarity, and greedily merges pairs above
    `threshold` into a single moved hunk.

    Mirrors `diff_bill.reconcile_moves` for the XML pipeline.
    """
    removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
    added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]
    if not removed_idx or not added_idx:
        return hunks

    candidates: list[tuple[float, int, int]] = []
    for ri in removed_idx:
        for ai in added_idx:
            sim = _text_similarity(hunks[ri].v1_text, hunks[ai].v2_text)
            if sim >= threshold:
                candidates.append((sim, ri, ai))
    if not candidates:
        return hunks

    candidates.sort(reverse=True)
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    moved_pairs: list[tuple[int, int]] = []
    for _, ri, ai in candidates:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        moved_pairs.append((ri, ai))

    consumed = claimed_r | claimed_a
    result: list[PdfHunk] = []
    moved_lookup = {ri: ai for ri, ai in moved_pairs}
    for i, h in enumerate(hunks):
        if i in moved_lookup:
            removed = h
            added = hunks[moved_lookup[i]]
            result.append(
                PdfHunk(
                    change_type="moved",
                    v1_anchor=removed.v1_anchor,
                    v2_anchor=added.v2_anchor,
                    v1_range=removed.v1_range,
                    v2_range=added.v2_range,
                    v1_text=removed.v1_text,
                    v2_text=added.v2_text,
                    amount_pairs=_amount_pairs_when_changed(removed.v1_text, added.v2_text),
                )
            )
        elif i in consumed:
            continue  # 'added' side already emitted as part of its 'removed' pair
        else:
            result.append(h)
    return result


# ---- Public entry point ------------------------------------------------------


def diff_pdfs(v1_pages: list[Page], v2_pages: list[Page]) -> PdfDiff:
    """Diff two extracted PDF page sequences and return a PdfDiff."""
    v1_indexed = _flatten(v1_pages)
    v2_indexed = _flatten(v2_pages)
    v1_anchors = extract_anchors(v1_pages)
    v2_anchors = extract_anchors(v2_pages)

    matcher = difflib.SequenceMatcher(
        a=[line.text for line in v1_indexed],
        b=[line.text for line in v2_indexed],
        autojunk=False,
    )

    hunks: list[PdfHunk] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        v1_lines = v1_indexed[i1:i2]
        v2_lines = v2_indexed[j1:j2]
        v1_range = _range_from_lines(v1_lines)
        v2_range = _range_from_lines(v2_lines)
        v1_text = "\n".join(ln.text for ln in v1_lines)
        v2_text = "\n".join(ln.text for ln in v2_lines)

        v1_anchor = _nearest_preceding_anchor(v1_anchors, v1_range[0], v1_range[1]) if v1_range else None
        v2_anchor = _nearest_preceding_anchor(v2_anchors, v2_range[0], v2_range[1]) if v2_range else None

        if op == "insert":
            change_type: ChangeType = "added"
        elif op == "delete":
            change_type = "removed"
        else:  # replace
            change_type = _classify_replace(v1_text, v2_text, v1_anchor, v2_anchor)

        amount_pairs = _amount_pairs_when_changed(v1_text, v2_text) if op == "replace" else ()

        hunks.append(
            PdfHunk(
                change_type=change_type,
                v1_anchor=v1_anchor,
                v2_anchor=v2_anchor,
                v1_range=v1_range,
                v2_range=v2_range,
                v1_text=v1_text,
                v2_text=v2_text,
                amount_pairs=amount_pairs,
            )
        )

    return PdfDiff(hunks=tuple(_reconcile_moves(hunks)))
