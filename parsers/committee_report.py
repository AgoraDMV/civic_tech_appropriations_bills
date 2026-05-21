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
# Qualifier lines sit between an account heading and its summary rows. They are ALL-CAPS
# (so they would otherwise pass the heading test) but name a funding mechanism, not an
# account. GPO renders them with or without the enclosing parentheses, so match on the
# leading keyword. Examples: "(INCLUDING TRANSFER OF FUNDS)", "INCLUDING TRANSFERS OF
# FUNDS", "(LIMITATION ON ADMINISTRATIVE EXPENSES)", "(INCLUDING RESCISSION OF FUNDS)".
_QUALIFIER_RE = re.compile(r"^\(?(?:INCLUDING|LIMITATION|RESCISSION)\b")


@dataclass(frozen=True)
class ReportAccount:
    """One account-level ground-truth row recovered from a report summary block."""

    heading: str  # ALL-CAPS account name as printed
    committee_recommendation: int  # dollars (actual, not thousands)


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
    for i, line in enumerate(lines):
        m = _COMMITTEE_REC_RE.match(line.strip())
        if not m:
            continue
        amount = int(m.group(1).replace(",", ""))
        heading = _heading_before(lines, i)
        if heading:
            accounts.append(ReportAccount(heading=heading, committee_recommendation=amount))
    return accounts


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
