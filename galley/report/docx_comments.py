"""Write Galley's findings into a copy of the manuscript as Word comments.

The author's file is never modified: a copy is saved alongside it, with a
comment in the margin at each problem, exactly where a co-author would put one.

Word anchors a comment to whole runs, not to characters, so a run holding the
text we want to point at is split first. If a clean split isn't possible, the
comment falls back to the runs that overlap the text, and then to the paragraph.
"""
from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph as DocxParagraph

from ..model.document import SEVERITY_ORDER, Document, Issue
from ..parsers.docx_parser import _iter_block_paragraphs

AUTHOR = "Galley"
INITIALS = "GC"
LABEL = {"error": "Error", "warning": "Warning", "info": "Note"}
WHITESPACE = re.compile(r"[\s\u00a0]+")


def _runs_of(paragraph: DocxParagraph) -> list:
    """Every run in the paragraph, including runs inside hyperlinks."""
    runs = list(paragraph.runs)
    if runs:
        return runs
    return [r for r in paragraph._p.iter(qn("w:r"))]


def _normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace, keeping a map from each kept character to its index."""
    out, index = [], []
    previous_space = False
    for i, ch in enumerate(text):
        if WHITESPACE.match(ch):
            if previous_space or not out:
                continue
            out.append(" ")
            index.append(i)
            previous_space = True
        else:
            out.append(ch)
            index.append(i)
            previous_space = False
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def _split_run(run_el, offset: int) -> bool:
    """Split a run in two at `offset` characters. Returns False if not possible."""
    texts = run_el.findall(qn("w:t"))
    if len(texts) != 1 or texts[0].text is None:
        return False                      # tabs, breaks, fields: leave alone
    text = texts[0].text
    if not 0 < offset < len(text):
        return False
    clone = copy.deepcopy(run_el)
    texts[0].text = text[:offset]
    texts[0].set(qn("xml:space"), "preserve")
    clone_text = clone.findall(qn("w:t"))[0]
    clone_text.text = text[offset:]
    clone_text.set(qn("xml:space"), "preserve")
    run_el.addnext(clone)
    return True


def _runs_for_span(paragraph: DocxParagraph, start: int, end: int) -> list:
    """Return the runs covering characters [start, end) of the paragraph text."""
    runs = _runs_of(paragraph)
    if not runs:
        return []
    # Split at the end first, so the start offset stays valid.
    for boundary in (end, start):
        position = 0
        for run_el in [r._r if hasattr(r, "_r") else r for r in _runs_of(paragraph)]:
            length = len("".join(t.text or "" for t in run_el.findall(qn("w:t"))))
            if position < boundary < position + length:
                _split_run(run_el, boundary - position)
                break
            position += length

    selected, position = [], 0
    for run in _runs_of(paragraph):
        run_el = run._r if hasattr(run, "_r") else run
        length = len("".join(t.text or "" for t in run_el.findall(qn("w:t"))))
        if position < end and position + length > start and length:
            selected.append(run)
        position += length
    return selected


def _anchor_runs(paragraph: DocxParagraph, anchor: str | None) -> list:
    runs = _runs_of(paragraph)
    if not runs:
        return []
    if not anchor:
        return [runs[0], runs[-1]]
    raw = "".join("".join(t.text or "" for t in
                          (r._r if hasattr(r, "_r") else r).findall(qn("w:t")))
                  for r in runs)
    flat, index = _normalize(raw)
    wanted, _ = _normalize(anchor)
    if not wanted:
        return [runs[0], runs[-1]]
    at = flat.find(wanted)
    if at == -1:                                   # try the first few words
        head = " ".join(wanted.split()[:4])
        at = flat.find(head) if head else -1
        if at == -1:
            return [runs[0], runs[-1]]
        wanted = head
    start, end = index[at], index[at + len(wanted) - 1] + 1
    return _runs_for_span(paragraph, start, end) or [runs[0], runs[-1]]


def _comment_text(issue: Issue) -> str:
    text = f"{LABEL[issue.severity]}: {issue.message}"
    if issue.suggestion:
        text += f"\n{issue.suggestion}"
    return text


def annotate(doc: Document, issues: list[Issue], out_path: str | Path,
             severities: tuple[str, ...] = ("error", "warning", "info")) -> Path:
    """Save a copy of the manuscript with a Word comment at each issue.

    Returns the path written. The original file is left untouched.
    """
    source, out_path = Path(doc.path), Path(out_path)
    if source.resolve() == out_path.resolve():
        raise ValueError("The commented copy must not overwrite the original file")
    shutil.copyfile(source, out_path)

    d = docx.Document(str(out_path))
    paragraphs = [DocxParagraph(el, d) for el, _ in _iter_block_paragraphs(d.element.body)]

    wanted = [i for i in issues if i.severity in severities]
    wanted.sort(key=lambda i: (i.para_index if i.para_index is not None else -1,
                               SEVERITY_ORDER[i.severity]))
    written = 0
    for issue in wanted:
        index = issue.para_index
        if index is None or not (0 <= index < len(paragraphs)):
            index = next((n for n, p in enumerate(paragraphs) if p.text.strip()), None)
            if index is None:
                continue
        runs = _anchor_runs(paragraphs[index], issue.anchor)
        if not runs:
            continue
        try:
            d.add_comment(runs, _comment_text(issue), author=AUTHOR, initials=INITIALS)
            written += 1
        except (ValueError, IndexError):
            continue                      # a comment we can't place is not fatal
    d.save(str(out_path))
    return out_path


def default_output_path(source: str | Path) -> Path:
    source = Path(source)
    return source.with_name(f"{source.stem}_commented{source.suffix}")
