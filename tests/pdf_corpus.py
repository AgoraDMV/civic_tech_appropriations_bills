"""Shared discovery + caching for corpus-wide PDF tests.

Both the amount-recall cross-check (test_pdf_xml_amount_recall.py) and the diff
smoke suite (test_pdf_corpus_smoke.py) iterate over the bill PDFs. `cached_pages`
extracts each PDF at most once per session (in-memory) and persists the result
to disk so later `pytest` runs skip pdfplumber entirely — extraction of a large
omnibus is ~130s, so the disk cache is the main developer-loop speedup.

Set TEST_BILL to a bill name (or substring, e.g. "4366") to restrict both
suites to that bill for a fast TDD loop.
"""

from __future__ import annotations

import hashlib
import os
import pickle
from functools import lru_cache
from pathlib import Path

import pdfplumber

from parsers.pdf_text import Page, extract_clean_pages

BILLS_DIR = Path(__file__).parent.parent / "bills"

# Persistent extraction cache. Gitignored (test_data/* is ignored). Keyed by PDF
# path + mtime via the filename, so a changed PDF maps to a different file and
# the stale entry is simply never read.
CACHE_DIR = Path(__file__).parent.parent / "test_data" / "extract_cache"

# Optional single-bill filter for a fast TDD loop. Substring match on the bill
# directory name, so TEST_BILL=4366 selects 118-hr-4366.
_TEST_BILL = os.environ.get("TEST_BILL") or None


def _cache_file(pdf_path: Path) -> Path:
    mtime_ns = pdf_path.stat().st_mtime_ns
    digest = hashlib.sha1(f"{pdf_path.resolve()}::{mtime_ns}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{pdf_path.stem}-{digest}.pkl"


@lru_cache(maxsize=None)
def cached_pages(pdf_path: Path) -> list[Page]:
    """Extract cleaned pages, cached in memory (per session) and on disk (across runs)."""
    cache_file = _cache_file(pdf_path)
    if cache_file.exists():
        try:
            with cache_file.open("rb") as f:
                return pickle.load(f)
        except (pickle.PickleError, EOFError, ValueError):
            pass  # corrupt/partial cache — fall through and re-extract

    pages = extract_clean_pages(pdf_path)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(".pkl.tmp")
    with tmp.open("wb") as f:
        pickle.dump(pages, f)
    tmp.replace(cache_file)  # atomic; safe under xdist and interrupted runs
    return pages


@lru_cache(maxsize=None)
def page_count(pdf_path: Path) -> int:
    """Page count without text extraction (parses the page tree only)."""
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def full_text(pages: list[Page]) -> str:
    """Join every cleaned line across all pages into one string."""
    return "\n".join(page.text for page in pages)


def _selected(bill_name: str) -> bool:
    return _TEST_BILL is None or _TEST_BILL in bill_name


def dual_format_versions() -> list[tuple[str, Path, Path]]:
    """(bill_name, xml_path, pdf_path) for every version present in both formats."""
    out: list[tuple[str, Path, Path]] = []
    for bill_dir in sorted(BILLS_DIR.iterdir()):
        if not bill_dir.is_dir() or not _selected(bill_dir.name):
            continue
        for xml in sorted(bill_dir.glob("*.xml")):
            pdf = xml.with_suffix(".pdf")
            if pdf.exists():
                out.append((bill_dir.name, xml, pdf))
    return out


def adjacent_pdf_pairs() -> list[tuple[str, Path, Path]]:
    """(bill_name, old_pdf, new_pdf) for each adjacent version pair within a bill."""
    out: list[tuple[str, Path, Path]] = []
    for bill_dir in sorted(BILLS_DIR.iterdir()):
        if not bill_dir.is_dir() or not _selected(bill_dir.name):
            continue
        pdfs = sorted(bill_dir.glob("*.pdf"))
        for i in range(len(pdfs) - 1):
            out.append((bill_dir.name, pdfs[i], pdfs[i + 1]))
    return out
