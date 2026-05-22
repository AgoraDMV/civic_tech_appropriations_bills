"""Synthetic-injection recall: does sneaked-in language get detected AND shown?

The threat model is someone slipping new text into a bill at the last minute (a
rider, earmark, or clause). This test turns the structural guarantee of the diff
engine into an executable check: we start from a real v1 (HR 8752 reported), inject
uniquely-tokenized phrases at distinct locations to build a synthetic v2, run
`diff_pdfs`, and assert each sentinel surfaces in two places:

  1. Detection: some hunk carries the sentinel in its changed-side text.
  2. Display: the sentinel appears in the rendered HTML.

The sentinels are nonsense tokens (`ZZQ...`) so they can't collide with real bill
text and survive HTML escaping unchanged. All scenarios are expected to pass; a
failure is a real detection-or-display gap, to be documented in
plans/pdf-text-diff-findings.md rather than worked around.
"""

from __future__ import annotations

import pytest
from recall_text import normalize_for_recall

from diff_pdf import PdfDiff, diff_pdfs
from formatters.adapters import pdf_diff_to_view
from formatters.diff_html import format_diff_html
from parsers.pdf_anchors import extract_anchors
from parsers.pdf_text import Line, Page

# ---- Injection helpers (operate on the frozen Page/Line dataclasses) ---------


def _page_line_index(pages: list[Page], page_number: int, line_number: int) -> int:
    """Index of the line with `line_number` within page `page_number`'s tuple."""
    page = next(p for p in pages if p.page_number == page_number)
    for i, ln in enumerate(page.lines):
        if ln.line_number == line_number:
            return i
    raise ValueError(f"line {line_number} not found on page {page_number}")


def _inject(pages: list[Page], page_number: int, at_index: int, new_lines: list[Line]) -> list[Page]:
    """Return a new page list with `new_lines` spliced into `page_number` at `at_index`."""
    out: list[Page] = []
    for p in pages:
        if p.page_number == page_number:
            lines = list(p.lines)
            lines[at_index:at_index] = new_lines
            p = Page(p.page_number, tuple(lines))
        out.append(p)
    return out


def _append_page(pages: list[Page], page_number: int, lines: list[Line]) -> list[Page]:
    return [*pages, Page(page_number, tuple(lines))]


def _insert_page_before(pages: list[Page], before_page_number: int, page_number: int, lines: list[Line]) -> list[Page]:
    """Insert a new page into the list immediately before `before_page_number`.

    A standalone page keeps the injected `SEC.` anchor's (page, line) key unique
    and its document order correct (anchors are sorted by line number *within* a
    page, so a high synthetic line number on a real page would sort wrong).
    """
    idx = next(i for i, p in enumerate(pages) if p.page_number == before_page_number)
    return [*pages[:idx], Page(page_number, tuple(lines)), *pages[idx:]]


# ---- Scenario builders -------------------------------------------------------


def _build_synthetic_v2(v1_pages: list[Page]) -> list[Page]:
    """Apply all injection scenarios to a copy of v1, returning synthetic v2 pages.

    Each scenario plants one nonsense sentinel at a distinct location, exercising
    a different code path in diff_pdf. Injections are keyed by (page, line) lookup
    on the current page list, so they're order-independent.
    """
    pages = list(v1_pages)
    anchors = extract_anchors(pages)
    sections = [a for a in anchors if a.kind == "section"]
    proc = next(a for a in anchors if a.kind == "account" and a.text.startswith("PROCUREMENT"))
    last_page_no = max(p.page_number for p in pages)

    # Scenario 1 — new section appended at the end of the document (clean `added`).
    pages = _append_page(
        pages,
        last_page_no + 1,
        [
            Line(1, "SEC. 999. None of the funds made available by this Act may be"),
            Line(2, "used for the ZZQALPHA demonstration program described in this"),
            Line(3, "section."),
        ],
    )

    # Scenario 2 — new section inserted mid-document, on its own page, just before
    # the first existing SEC. anchor. New anchor key => `added` hunk.
    pages = _insert_page_before(
        pages,
        sections[0].page_number,
        900,
        [
            Line(1, "SEC. 998. None of the funds appropriated by this Act may be used"),
            Line(2, "to implement the ZZQBRAVO initiative without prior approval of the"),
            Line(3, "Committees on Appropriations."),
        ],
    )

    # Scenario 3 — small clause inserted into an existing section body (stays well
    # above the 0.4 similarity floor => `modified`, with the sentinel inline).
    sec102 = sections[1]
    idx = _page_line_index(pages, sec102.page_number, sec102.line_number)
    pages = _inject(
        pages,
        sec102.page_number,
        idx + 1,
        [Line(None, "Provided further, That $1 shall be available for the ZZQCHARLIE program: ")],
    )

    # Scenario 4 — large insertion into a small account block, enough to drop the
    # block below the 0.4 split threshold and exercise the removed+added split path.
    idx = _page_line_index(pages, proc.page_number, proc.line_number)
    bulk = [
        Line(
            None, f"Provided further, That additional ZZQDELTA appropriations are made available under paragraph {n}: "
        )
        for n in range(60)
    ]
    pages = _inject(pages, proc.page_number, idx + 1, bulk)

    # Scenario 5 — insertion into the preamble (before the first anchor) => the
    # preamble block is `modified` and carries the sentinel.
    pages = _inject(
        pages,
        1,
        1,
        [Line(None, "Be it enacted that the ZZQECHO clause is hereby inserted into this measure. ")],
    )

    return pages


# ---- Fixture: build synthetic v2 once and diff it ----------------------------


@pytest.fixture(scope="module")
def injected_diff(hr8752_v1_pages) -> PdfDiff:
    v2 = _build_synthetic_v2(hr8752_v1_pages)
    return diff_pdfs(hr8752_v1_pages, v2)


@pytest.fixture(scope="module")
def injected_html(injected_diff: PdfDiff) -> str:
    view = pdf_diff_to_view(injected_diff, bill_type="hr", bill_number=8752, congress=118)
    return format_diff_html(view)


# ---- Cases: (sentinel, allowed change types) ---------------------------------

_CASES = [
    pytest.param("ZZQALPHA", {"added"}, id="new-section-end"),
    pytest.param("ZZQBRAVO", {"added"}, id="new-section-mid"),
    pytest.param("ZZQCHARLIE", {"modified"}, id="small-clause"),
    # Large insertion lands as `added` after the split, or `modified` if the block
    # stays above 0.4 — the sentinel surfacing is what matters, not which side.
    pytest.param("ZZQDELTA", {"added", "modified"}, id="large-insertion-split"),
    pytest.param("ZZQECHO", {"modified"}, id="preamble"),
]


def _hunks_with_sentinel(diff: PdfDiff, sentinel: str) -> list:
    """Hunks whose changed-side text contains the sentinel (normalized)."""
    norm = normalize_for_recall(sentinel)
    out = []
    for h in diff.hunks:
        side = normalize_for_recall(h.v2_text) if h.v2_text else ""
        if norm in side:
            out.append(h)
    return out


@pytest.mark.parametrize("sentinel,allowed_types", _CASES)
class TestInjectionRecall:
    def test_detected_in_a_hunk(self, sentinel: str, allowed_types: set[str], injected_diff: PdfDiff):
        hits = _hunks_with_sentinel(injected_diff, sentinel)
        assert hits, f"{sentinel}: not found in any hunk's changed text — injection went undetected"
        types = {h.change_type for h in hits}
        assert types & allowed_types, f"{sentinel}: found in hunks of type {types}, expected one of {allowed_types}"

    def test_shown_in_html(self, sentinel: str, allowed_types: set[str], injected_html: str):
        assert sentinel in injected_html, f"{sentinel}: detected but not rendered in HTML — change would be hidden"
