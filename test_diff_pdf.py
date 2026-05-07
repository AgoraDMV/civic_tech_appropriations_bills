"""Unit tests for diff_pdf — line-level PDF diff with anchor labeling."""

from __future__ import annotations

from diff_pdf import diff_pdfs
from parsers.pdf_anchors import Anchor
from parsers.pdf_text import Line, Page


def _page(page_number: int, *lines: tuple[int | None, str]) -> Page:
    return Page(page_number, tuple(Line(ln, txt) for ln, txt in lines))


def _hunks_by_type(hunks):
    return {h.change_type: h for h in hunks}


class TestNoChanges:
    def test_identical_single_page(self):
        v1 = [_page(1, (1, "alpha"), (2, "beta"))]
        v2 = [_page(1, (1, "alpha"), (2, "beta"))]
        result = diff_pdfs(v1, v2)
        assert result.hunks == ()


class TestAddedHunk:
    def test_appended_line_becomes_added_hunk(self):
        v1 = [_page(1, (1, "alpha"), (2, "beta"))]
        v2 = [_page(1, (1, "alpha"), (2, "beta"), (3, "gamma"))]
        hunks = diff_pdfs(v1, v2).hunks
        assert len(hunks) == 1
        h = hunks[0]
        assert h.change_type == "added"
        assert h.v1_range is None
        assert h.v2_range == (1, 3, 1, 3)
        assert h.v1_text == ""
        assert h.v2_text == "gamma"


class TestRemovedHunk:
    def test_dropped_line_becomes_removed_hunk(self):
        v1 = [_page(1, (1, "alpha"), (2, "beta"), (3, "gamma"))]
        v2 = [_page(1, (1, "alpha"), (2, "beta"))]
        hunks = diff_pdfs(v1, v2).hunks
        assert len(hunks) == 1
        h = hunks[0]
        assert h.change_type == "removed"
        assert h.v1_range == (1, 3, 1, 3)
        assert h.v2_range is None


class TestModifiedHunk:
    def test_replaced_line_becomes_modified_hunk(self):
        v1 = [_page(1, (1, "alpha"), (2, "beta"))]
        v2 = [_page(1, (1, "alpha"), (2, "BETA"))]
        hunks = diff_pdfs(v1, v2).hunks
        assert len(hunks) == 1
        h = hunks[0]
        assert h.change_type == "modified"
        assert h.v1_text == "beta"
        assert h.v2_text == "BETA"


class TestPageLineCitations:
    def test_citation_spans_multiple_lines_within_page(self):
        v1 = [_page(2, (1, "x"), (14, "old line a"), (15, "old line b"), (25, "y"))]
        v2 = [_page(2, (1, "x"), (14, "new line a"), (15, "new line b"), (25, "y"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.v1_range == (2, 14, 2, 15)
        assert h.v2_range == (2, 14, 2, 15)

    def test_citation_spans_pages(self):
        v1 = [_page(2, (24, "a"), (25, "b")), _page(3, (1, "c"))]
        v2 = [_page(2, (24, "a"), (25, "B")), _page(3, (1, "C"))]
        # Two replaced lines that happen to be on different pages.
        # difflib may emit one or two hunks depending on alignment;
        # the union of their ranges spans the two pages.
        hunks = diff_pdfs(v1, v2).hunks
        v1_pages = {h.v1_range[0] for h in hunks if h.v1_range}
        v1_pages |= {h.v1_range[2] for h in hunks if h.v1_range}
        assert v1_pages == {2, 3}


class TestAnchorLabeling:
    def test_nearest_preceding_section_anchor(self):
        # SEC. 101 at L1, hunk at L5 — anchor should resolve to SEC. 101.
        v1 = [_page(4, (1, "SEC. 101. body text"), (2, "more"), (5, "old change"))]
        v2 = [_page(4, (1, "SEC. 101. body text"), (2, "more"), (5, "new change"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.v1_anchor == Anchor(4, 1, "section", "SEC. 101")
        assert h.v2_anchor == Anchor(4, 1, "section", "SEC. 101")

    def test_unresolvable_anchor_returns_none(self):
        # No SEC. / TITLE / account anywhere on the page.
        v1 = [_page(47, (18, "old typographic edit"))]
        v2 = [_page(47, (18, "new typographic edit"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.v1_anchor is None
        assert h.v2_anchor is None


class TestNumericClassification:
    def test_dollar_amount_change_populates_amount_pairs(self):
        v1 = [_page(2, (14, "appropriated $281,358,000 for"))]
        v2 = [_page(2, (14, "appropriated $249,708,000 for"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.amount_pairs == ((281358000, 249708000),)

    def test_no_amount_change_leaves_pairs_empty(self):
        v1 = [_page(2, (14, "the program shall be operated"))]
        v2 = [_page(2, (14, "the program may be operated"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.amount_pairs == ()


class TestMovedClassification:
    def test_renumbered_section_classified_as_moved(self):
        # Same body text, different SEC. number — classic renumber.
        # A SEC. anchor must precede each hunk for moved-detection to fire.
        v1 = [_page(63, (17, "SEC. 414. None of the funds may be used to enforce X"))]
        v2 = [_page(65, (4, "SEC. 413. None of the funds may be used to enforce X"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.change_type == "moved"
        assert h.v1_anchor and h.v1_anchor.text == "SEC. 414"
        assert h.v2_anchor and h.v2_anchor.text == "SEC. 413"


class TestReconcileMoves:
    def test_remove_then_add_at_distant_position_pairs_as_moved(self):
        # v1 has SEC. 414 mid-document; v2 drops it and adds SEC. 413 with the
        # same body at a later position (with shared anchoring lines preserved
        # so SequenceMatcher cleanly emits delete + insert, not replace).
        body = "SEC. 414. None of the funds may be used to enforce X policy"
        body_renumbered = "SEC. 413. None of the funds may be used to enforce X policy"
        v1 = [
            _page(63, (1, "shared header"), (17, body), (20, "shared tail")),
        ]
        v2 = [
            _page(63, (1, "shared header"), (20, "shared tail")),
            _page(65, (4, body_renumbered)),
        ]
        result = diff_pdfs(v1, v2)
        moved = [h for h in result.hunks if h.change_type == "moved"]
        assert len(moved) == 1
        assert moved[0].v1_anchor and moved[0].v1_anchor.text == "SEC. 414"
        assert moved[0].v2_anchor and moved[0].v2_anchor.text == "SEC. 413"


class TestPdfDiffSummary:
    def test_summary_counts_by_change_type(self):
        v1 = [_page(1, (1, "alpha"), (2, "beta"), (3, "gamma"))]
        v2 = [_page(1, (1, "alpha"), (2, "BETA"), (3, "gamma"), (4, "delta"))]
        result = diff_pdfs(v1, v2)
        assert result.summary == {"modified": 1, "added": 1}
