"""Build test_data/validation_cjs.json from the CJS committee report.

External ground truth for the Commerce-Justice-Science jurisdiction (GitHub #8),
produced by the committee-report reader (#33). Mirrors the hand-curated
test_data/validation_leg_branch.json, but the source here is machine-parseable so this
script regenerates the fixture deterministically.

Ground-truth source: Senate Report 118-198 (the explanatory statement for S.4795), read
from its govinfo HTML <pre> dump. We extract the 3-line account summary blocks, whose
"Committee recommendation" line carries the amount the reported bill appropriates, in
actual dollars. Those amounts are validated against the parser's extraction from the
bill XML by tests/test_validate_extraction.py.

Inputs are fetched from govinfo (both gitignored locally):
  report:  https://www.govinfo.gov/content/pkg/CRPT-118srpt198/html/CRPT-118srpt198.htm
           -> test_data/CRPT-118srpt198.htm
  bill:    https://www.govinfo.gov/content/pkg/BILLS-118s4795rs/xml/BILLS-118s4795rs.xml
           -> bills/118-s-4795/1_reported-in-senate.xml

Usage:  uv run python scripts/build_validation_cjs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Run-from-anywhere: put the repo root (this file's parent's parent) on the path so the
# root-level source modules import. pytest gets this via pyproject's pythonpath; a plain
# `python scripts/...` invocation does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.committee_report import extract_pre_text, parse_summary_blocks  # noqa: E402

REPORT_HTML = Path("test_data/CRPT-118srpt198.htm")
OUTPUT = Path("test_data/validation_cjs.json")

BILL = "118-s-4795"
VERSION = "1_reported-in-senate.xml"
FY = "FY 2025"
CHAMBER = "senate"


def build() -> dict:
    html = REPORT_HTML.read_text(encoding="utf-8", errors="replace")
    accounts = parse_summary_blocks(extract_pre_text(html))
    rows = [
        {
            "bill": BILL,
            "version": VERSION,
            "fy": FY,
            "chamber": CHAMBER,
            "title": acc.title,  # enclosing agency, e.g. "DEPARTMENT OF JUSTICE"
            "excel_name": acc.heading,
            "expected_amount": acc.committee_recommendation,
        }
        for acc in accounts
    ]
    return {
        "source": "CRPT-118srpt198 (Senate Report 118-198), CJS explanatory statement for S.4795",
        "note": (
            "Commerce-Justice-Science FY2025 (Reported in Senate) account amounts, "
            "extracted from the committee report's 3-line summary blocks and validated "
            "against the bill XML. Committee-recommendation amounts are in actual dollars; "
            "`title` is the enclosing appropriations title/agency, used for agency-scoped "
            "recall (the amount must appear under the matching top-level node). External "
            "ground truth for GitHub #8 (jurisdiction breadth beyond Legislative Branch). "
            "Regenerate with scripts/build_validation_cjs.py."
        ),
        "accounts": rows,
    }


def main() -> None:
    if not REPORT_HTML.exists():
        raise SystemExit(f"Missing {REPORT_HTML}. Fetch it from govinfo (see this script's docstring).")
    data = build()
    OUTPUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(data['accounts'])} accounts.")


if __name__ == "__main__":
    main()
