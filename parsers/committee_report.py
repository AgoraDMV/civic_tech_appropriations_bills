"""Reader for Senate appropriations committee reports (external validation ground truth).

A committee report is not a bill: it is narrative + tabular account listings, not the
appropriations XML hierarchy. We read it from the govinfo HTML `<pre>` dump rather than
the PDF, because that dump is GPO's authoritative ASCII layout with preserved column
alignment — fixed-width column slicing instead of PDF coordinate reconstruction.

This reader targets the **3-line account summary blocks** that recur through the
narrative:

    INDUSTRIAL TECHNOLOGY SERVICES

    Appropriations, 2024....................................    $212,000,000
    Budget estimate, 2025...................................     212,000,000
    Committee recommendation................................     225,000,000

The ALL-CAPS heading names an account; the "Committee recommendation" line carries the
amount the reported bill should appropriate, in actual dollars (no unit conversion).
Those (heading, amount) pairs feed `validation_cjs.json` (see scripts/build_validation_cjs.py).
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

_PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_COMMITTEE_REC_RE = re.compile(r"^Committee recommendation\.{2,}\s+\$?([\d,]+)\s*$")
# A title heading in the narrative is two centered lines: the Roman numeral alone, then
# (after a blank) the department/agency name. The one-line "TITLE N--NAME" form appears
# only later in the comparative statement, so matching the bare numeral keeps title
# tracking anchored to the narrative the summary blocks live in.
_TITLE_NUMERAL_RE = re.compile(r"^TITLE [IVXLC]+$")
# A comparative-statement data row: an item label joined by leader dots to a tail of
# right-aligned numeric columns. The non-greedy label stops at the first dot run (its own
# leader), leaving the columns — including blank cells, which render as their own dot runs.
_COMPARATIVE_ROW_RE = re.compile(r"^(\s*.*?\S)\.{2,}\s+(.*\d.*)$")
_BLANK_CELL_RE = re.compile(r"^\.{2,}$")
_NUMERIC_CELL_RE = re.compile(r"^[+\-]?\(?-?[\d,]+\)?$")
# Qualifier lines sit between an account heading and its summary rows. They are ALL-CAPS
# (so they would otherwise pass the heading test) but name a funding mechanism, not an
# account. GPO renders them with or without the enclosing parentheses, so match on the
# leading keyword. Examples: "(INCLUDING TRANSFER OF FUNDS)", "INCLUDING TRANSFERS OF
# FUNDS", "(LIMITATION ON ADMINISTRATIVE EXPENSES)", "(INCLUDING RESCISSION OF FUNDS)".
_QUALIFIER_RE = re.compile(r"^\(?(?:INCLUDING|LIMITATION|RESCISSION)\b")


@dataclass(frozen=True)
class ComparativeRow:
    """One data row of the comparative statement (amounts in thousands of dollars)."""

    item: str  # item label as printed (e.g. "Operations and administration")
    committee_recommendation_thousands: int  # 3rd numeric column


@dataclass(frozen=True)
class ReportAccount:
    """One account-level ground-truth row recovered from a report summary block."""

    heading: str  # ALL-CAPS account name as printed
    committee_recommendation: int  # dollars (actual, not thousands)
    title: str | None = None  # the enclosing title/agency name (e.g. "DEPARTMENT OF JUSTICE")


def extract_pre_text(html: str) -> str:
    """Return the text inside the report's single `<pre>` block, HTML-unescaped."""
    m = _PRE_RE.search(html)
    if not m:
        return ""
    return _html.unescape(m.group(1))


def parse_summary_blocks(text: str) -> list[ReportAccount]:
    """Extract 3-line account summary blocks from the report `<pre>` text.

    Each block is anchored by its `Committee recommendation....N` line; the account
    heading is the nearest preceding ALL-CAPS line.
    """
    lines = text.split("\n")
    accounts: list[ReportAccount] = []
    current_title: str | None = None
    for i, line in enumerate(lines):
        if _TITLE_NUMERAL_RE.match(line.strip()):
            current_title = _title_name_after(lines, i) or current_title
            continue
        m = _COMMITTEE_REC_RE.match(line.strip())
        if not m:
            continue
        amount = int(m.group(1).replace(",", ""))
        heading = _heading_before(lines, i)
        if heading:
            accounts.append(
                ReportAccount(
                    heading=heading,
                    committee_recommendation=amount,
                    title=current_title,
                )
            )
    return accounts


def _title_name_after(lines: list[str], idx: int) -> str | None:
    """Return the title/agency name on the first heading line after a `TITLE N` numeral."""
    for j in range(idx + 1, min(idx + 4, len(lines))):
        if lines[j].strip():
            return lines[j].strip() if _is_heading(lines[j]) else None
    return None


def parse_comparative_statement(text: str) -> list[ComparativeRow]:
    """Extract committee-recommendation amounts from the comparative-statement table.

    Each data row is `<item><leader dots>  <2024>  <budget>  <committee rec>  <Δ>  <Δ>`,
    amounts in thousands, blank cells rendered as dot runs. The committee recommendation
    is the 3rd numeric column. Rows whose 3rd column is blank or a parenthetical memo (a
    transfer, non-add) are skipped. Summary-block lines carry a single amount, not three
    columns, so they do not match — the table can be fed the whole report text.
    """
    rows: list[ComparativeRow] = []
    for line in text.split("\n"):
        m = _COMPARATIVE_ROW_RE.match(line)
        if not m:
            continue
        cells = _parse_cells(m.group(2))
        if len(cells) >= 3 and cells[2] is not None:
            rows.append(
                ComparativeRow(
                    item=m.group(1).strip(),
                    committee_recommendation_thousands=cells[2],
                )
            )
    return rows


def _parse_cells(tail: str) -> list[int | None]:
    """Tokenize a comparative-statement column tail into ints, with None for blank cells.

    Parenthetical values (e.g. a transfer like "(-5,000)") are treated as blank: they are
    non-add memo lines, not a committee recommendation."""
    cells: list[int | None] = []
    for tok in tail.split():
        if _BLANK_CELL_RE.match(tok) or tok.startswith("("):
            cells.append(None)
        elif _NUMERIC_CELL_RE.match(tok):
            value = int(re.sub(r"[^\d]", "", tok))
            cells.append(-value if tok.startswith("-") else value)
        else:
            cells.append(None)  # wrapped label fragment or other non-cell token
    return cells


def _is_qualifier(line: str) -> bool:
    """True if a line is a funding-mechanism qualifier (e.g. INCLUDING TRANSFER OF FUNDS),
    parenthesized or not, rather than an account heading."""
    s = line.strip()
    return s.startswith("(") or bool(_QUALIFIER_RE.match(s))


def _is_heading(line: str) -> bool:
    """True if a line is an ALL-CAPS account heading (not a dotted data row or qualifier)."""
    s = line.strip()
    if not s or "...." in s or _is_qualifier(s):
        return False
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def _heading_before(lines: list[str], idx: int) -> str | None:
    """Walk back from a summary block to its ALL-CAPS heading, skipping the dotted
    summary rows, blank lines, and qualifier lines."""
    for j in range(idx - 1, max(idx - 8, -1), -1):
        s = lines[j].strip()
        if not s or "...." in s or _is_qualifier(s):
            continue
        if _is_heading(lines[j]):
            return s
        break
    return None
