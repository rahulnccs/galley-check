"""Core engine: parse a manuscript and run the selected checks."""
from __future__ import annotations

from pathlib import Path

from .checks.registry import OFFLINE_CHECKS
from .model.document import Document, Issue
from .parsers.docx_parser import parse_docx

SUPPORTED = {".docx": "Word document", ".pdf": "PDF"}


def load(path: str | Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(str(path))
    if suffix == ".pdf":
        from .parsers.pdf_parser import parse_pdf   # imported lazily; pdfplumber is heavy
        return parse_pdf(str(path))
    raise ValueError(f"{suffix or 'This file'} isn't supported "
                     f"(use a Word document or a PDF)")


def run_checks(doc: Document, only: list[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    for name, check in OFFLINE_CHECKS.items():
        if only is None or name in only:
            issues.extend(check(doc))
    return issues
