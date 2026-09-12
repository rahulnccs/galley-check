"""Parse a .pdf manuscript into the Document model.

A PDF stores positioned characters, not paragraphs, so this rebuilds the
reading order before any check runs:

  * detects a two-column layout and reads the left column before the right;
  * drops running headers, footers, and page numbers that repeat across pages;
  * joins wrapped lines back into paragraphs and repairs words split by a
    hyphen at a line end;
  * treats short lines set in a larger or bold font as headings.

Text extracted from a PDF is never as clean as a Word file, so checks that
depend on exact wording are best run on the .docx when one exists.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass

from ..model.document import Document, Paragraph
from .docx_parser import _section_for_heading

try:
    import pdfplumber
except ImportError:  # pragma: no cover - reported to the user by the caller
    pdfplumber = None

LINE_TOLERANCE = 3.0        # points; words within this vertical distance share a line
MARGIN_FRACTION = 0.07      # top/bottom band searched for running heads and feet
LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
             "\ufb04": "ffl", "\u2010": "-", "\u00ad": ""}


@dataclass
class Line:
    text: str
    trimmed: str        # text without a margin line number
    numbered: bool      # a margin line number was found and removed
    top: float
    bottom: float
    x0: float
    x1: float
    size: float
    bold: bool
    page: int
    column: int


def _clean(text: str) -> str:
    for bad, good in LIGATURES.items():
        text = text.replace(bad, good)
    return re.sub(r"[ \u00a0]+", " ", text).strip()


def _column_split(words, page_width: float) -> float | None:
    """Return the x of a two-column gutter, or None for a single column."""
    body = [w for w in words if w["x1"] - w["x0"] > 0]
    if len(body) < 60:
        return None
    best = None
    for frac in (0.46, 0.48, 0.50, 0.52, 0.54):
        split = page_width * frac
        crossing = sum(1 for w in body if w["x0"] < split - 2 and w["x1"] > split + 2)
        left = sum(1 for w in body if w["x1"] <= split)
        right = sum(1 for w in body if w["x0"] >= split)
        if crossing <= max(2, 0.01 * len(body)) and min(left, right) > 0.25 * len(body):
            score = min(left, right)
            if best is None or score > best[1]:
                best = (split, score)
    return best[0] if best else None


def _lines_on_page(page, page_no: int) -> list[Line]:
    words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False)
    if not words:
        return []
    split = _column_split(words, page.width)
    lines: list[Line] = []
    for column, group in enumerate(
            [words] if split is None
            else [[w for w in words if w["x1"] <= split + 2],
                  [w for w in words if w["x0"] > split - 2]]):
        rows: list[list[dict]] = []
        for w in sorted(group, key=lambda w: (round(w["top"], 1), w["x0"])):
            if rows and abs(w["top"] - rows[-1][0]["top"]) <= LINE_TOLERANCE:
                rows[-1].append(w)
            else:
                rows.append([w])
        for row in rows:
            row.sort(key=lambda w: w["x0"])
            text = _clean(" ".join(w["text"] for w in row))
            if not text:
                continue
            sizes = [w.get("size", 10) or 10 for w in row]
            fonts = " ".join(str(w.get("fontname", "")) for w in row).lower()
            trimmed, numbered = _strip_margin_number(row, text)
            lines.append(Line(
                text=text, trimmed=trimmed, numbered=numbered, top=row[0]["top"], bottom=max(w["bottom"] for w in row),
                x0=min(w["x0"] for w in row), x1=max(w["x1"] for w in row),
                size=statistics.median(sizes),
                bold=("bold" in fonts or "black" in fonts or "heavy" in fonts),
                page=page_no, column=column))
    return lines


MARGIN_NUMBER_GAP = 8.0     # points between a margin number and the text it labels


def _strip_margin_number(row: list[dict], text: str) -> tuple[str, bool]:
    """Drop a line number printed in the margin (common in submitted drafts)."""
    if len(row) >= 2:
        first, second = row[0], row[1]
        if first["text"].isdigit() and second["x0"] - first["x1"] > MARGIN_NUMBER_GAP:
            return _clean(" ".join(w["text"] for w in row[1:])), True
        last, prev = row[-1], row[-2]
        if last["text"].isdigit() and last["x0"] - prev["x1"] > MARGIN_NUMBER_GAP:
            return _clean(" ".join(w["text"] for w in row[:-1])), True
    return text, False


_DIGITS = re.compile(r"\d+")


def _strip_running_heads(pages: list[list[Line]], heights: list[float]) -> list[list[Line]]:
    """Remove headers, footers, and page numbers that repeat across pages."""
    if len(pages) < 3:
        return pages
    counts: Counter[str] = Counter()
    for page_lines, height in zip(pages, heights):
        margin = height * MARGIN_FRACTION
        seen = {_DIGITS.sub("#", ln.text.lower())
                for ln in page_lines
                if ln.top < margin or ln.bottom > height - margin}
        counts.update(seen)
    repeated = {k for k, n in counts.items() if n >= max(3, 0.4 * len(pages))}
    out = []
    for page_lines, height in zip(pages, heights):
        margin = height * MARGIN_FRACTION
        out.append([ln for ln in page_lines
                    if not ((ln.top < margin or ln.bottom > height - margin)
                            and (_DIGITS.sub("#", ln.text.lower()) in repeated
                                 or ln.text.strip().isdigit()))])
    return out


_SENTENCE_END = re.compile(r"[.!?:;)\]\"\u201d]\s*$")
_LIST_START = re.compile(r"^\s*(?:[-\u2022\u25cf*]|\(?[a-z0-9]{1,3}[.)])\s+")


def _is_heading(line: Line, body_size: float) -> bool:
    if len(line.text) > 120 or not line.text:
        return False
    if _section_for_heading(line.text):
        return True
    bigger = line.size > body_size * 1.12
    return (bigger or line.bold) and len(line.text) < 80 and not line.text.endswith(".")


def _new_paragraph(prev: Line, line: Line, gap_threshold: float, col_left: float,
                   col_right: float) -> bool:
    if line.page != prev.page or line.column != prev.column:
        # Only continue across a page or column break if the text clearly runs on.
        return _SENTENCE_END.search(prev.text) is not None and prev.x1 < col_right - 25
    if line.top - prev.bottom > gap_threshold:
        return True
    if line.x0 > col_left + 6:                       # indented first line
        return True
    if _LIST_START.match(line.text):
        return True
    # A short previous line that ended a sentence means the paragraph ended.
    return bool(_SENTENCE_END.search(prev.text)) and prev.x1 < col_right - 40


def _join(base: str, addition: str) -> str:
    if base.endswith("-") and addition[:1].islower():
        return base[:-1] + addition          # word split across lines
    return f"{base} {addition}"


def parse_pdf(path: str) -> Document:
    if pdfplumber is None:
        raise ValueError("PDF support needs pdfplumber (pip install pdfplumber)")

    with pdfplumber.open(path) as pdf:
        pages = [_lines_on_page(page, i) for i, page in enumerate(pdf.pages)]
        heights = [page.height for page in pdf.pages]
        widths = [page.width for page in pdf.pages]

    pages = _strip_running_heads(pages, heights)
    lines = [ln for page_lines in pages for ln in page_lines]
    if not lines:
        raise ValueError("No text found. This PDF is probably a scan, which needs OCR first")

    if sum(ln.numbered for ln in lines) >= 0.25 * len(lines):
        for ln in lines:
            ln.text = ln.trimmed
        lines = [ln for ln in lines if ln.text]

    body_size = statistics.median([ln.size for ln in lines]) or 10
    gaps = [b.top - a.bottom for a, b in zip(lines, lines[1:])
            if a.page == b.page and a.column == b.column and 0 <= b.top - a.bottom < 40]
    gap_threshold = (statistics.median(gaps) + 2.5) if gaps else 6.0
    page_width = statistics.median(widths)
    col_left = min(ln.x0 for ln in lines)
    col_right = max(ln.x1 for ln in lines if ln.x1 < page_width * 0.99)

    doc = Document(path=str(path))
    section = "front_matter"
    buffer: list[Line] = []

    def flush():
        nonlocal buffer
        if not buffer:
            return
        text = buffer[0].text
        for prev, line in zip(buffer, buffer[1:]):
            text = _join(text, line.text)
        doc.paragraphs.append(Paragraph(
            index=len(doc.paragraphs), text=_clean(text),
            style="Heading" if len(buffer) == 1 and _is_heading(buffer[0], body_size)
            else "Body",
            section=section, is_heading=False))
        buffer = []

    for line in lines:
        heading = _is_heading(line, body_size)
        if heading:
            flush()
            named = _section_for_heading(line.text)
            if named:
                section = named
            doc.paragraphs.append(Paragraph(
                index=len(doc.paragraphs), text=line.text, style="Heading",
                section=section, is_heading=True))
            continue
        if buffer and _new_paragraph(buffer[-1], line, gap_threshold, col_left, col_right):
            flush()
        buffer.append(line)
    flush()
    return doc
