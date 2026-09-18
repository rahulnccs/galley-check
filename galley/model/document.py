"""The document model: one clean structure that every check reads from.

Parsers (docx now, LaTeX later) convert a manuscript into a `Document`.
Checks never touch the original file, so adding a new input format only
means writing a new parser.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Canonical section names the parser assigns to paragraphs.
REFERENCES = "references"
FIGURE_LEGENDS = "figure_legends"


@dataclass
class Paragraph:
    index: int                  # position in the document (0-based)
    text: str                   # visible text (tracked deletions excluded)
    style: str                  # Word style name, e.g. "Heading 1", "Normal"
    section: str                # canonical section, e.g. "results", "references"
    is_heading: bool = False
    in_table: bool = False
    in_bibliography_field: bool = False  # inside a Zotero/EndNote/Mendeley bibliography
    is_list_item: bool = False          # part of a Word auto-numbered/bulleted list
    footnote_ids: list[int] = field(default_factory=list)   # notes anchored here
    superscript_spans: list[tuple[int, int]] = field(default_factory=list)
    italic_spans: list[tuple[int, int]] = field(default_factory=list)

    def superscripts(self) -> list[str]:
        return [self.text[a:b] for a, b in self.superscript_spans]


@dataclass
class Citation:
    """An in-text citation inserted by a reference manager (Word field code)."""
    para_index: int
    text: str                   # what the reader sees, e.g. "(Doe et al., 2021)" or "[3]"
    source: str                 # "zotero" | "mendeley" | "endnote"
    raw: Optional[str] = None   # the hidden field instruction (CSL JSON / EndNote XML)


@dataclass
class Issue:
    """One problem found by a check."""
    check: str                  # e.g. "figures"
    severity: str               # "error" | "warning" | "info"
    message: str
    para_index: Optional[int] = None
    anchor: Optional[str] = None       # exact text to attach a Word comment to
    suggestion: Optional[str] = None


SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Note:
    """A footnote or endnote, which some styles use instead of a reference list."""
    id: int
    text: str
    kind: str                   # "footnote" | "endnote"


@dataclass
class Document:
    path: str
    paragraphs: list[Paragraph] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    notes: dict[int, Note] = field(default_factory=dict)

    def paragraph(self, index: int) -> Paragraph:
        return self.paragraphs[index]

    def is_reference_paragraph(self, p: Paragraph) -> bool:
        return p.section == REFERENCES or p.in_bibliography_field
