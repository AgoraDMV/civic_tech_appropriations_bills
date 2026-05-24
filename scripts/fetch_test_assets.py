"""Fetch external test assets that fetch_bills.py cannot produce.

A few slow tests read files sourced directly from govinfo rather than the
Congress.gov bill API. They are public domain (17 U.S.C. 105) but large
binaries, so they are gitignored and fetched on demand here, keeping the
test corpus reproducible without committing PDFs.

Currently:
- test_data/BILLS-118s4795rs.pdf - the reported-in-Senate (watermarked) print
  of S.4795, read by tests/test_pdf_watermark_recall.py.

Usage:
  uv run python scripts/fetch_test_assets.py        # fetch any missing assets
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GOVINFO = "https://www.govinfo.gov/content/pkg"

# (destination path relative to the repo root, govinfo URL)
ASSETS: list[tuple[str, str]] = [
    ("test_data/BILLS-118s4795rs.pdf", f"{_GOVINFO}/BILLS-118s4795rs/pdf/BILLS-118s4795rs.pdf"),
]


def fetch_asset(dest_rel: str, url: str) -> bool:
    """Download url to dest_rel (relative to repo root) if missing.

    Returns True when a file was written, False when it was already present.
    """
    dest = _ROOT / dest_rel
    if dest.exists():
        print(f"  already present: {dest_rel}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (govinfo, https)
        dest.write_bytes(resp.read())
    print(f"  saved: {dest_rel}")
    return True


def main() -> None:
    for dest_rel, url in ASSETS:
        fetch_asset(dest_rel, url)


if __name__ == "__main__":
    main()
