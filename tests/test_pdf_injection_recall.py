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
from parsers.pdf_text import Line, Page

# A line number guaranteed not to collide with the source PDF's printed numbers
# (GPO numbers are 1-2 digits, so the (page, line) anchor key stays unique).
_SAFE_LINE_NO = 900


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


# ---- Scenario builders -------------------------------------------------------


def _build_synthetic_v2(v1_pages: list[Page]) -> list[Page]:
    """Apply all injection scenarios to a copy of v1, returning synthetic v2 pages."""
    pages = list(v1_pages)
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
