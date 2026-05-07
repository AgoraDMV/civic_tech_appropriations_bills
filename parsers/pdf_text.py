"""Naïve PDF text extraction. Phase 1 baseline — no cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class Page:
    page_number: int  # 1-based
    text: str


def extract_clean_pages(pdf_path: Path) -> list[Page]:
    with pdfplumber.open(pdf_path) as pdf:
        return [Page(i + 1, page.extract_text() or "") for i, page in enumerate(pdf.pages)]
