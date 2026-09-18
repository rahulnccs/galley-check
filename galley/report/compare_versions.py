"""Compare two versions of a manuscript and highlight what changed.

Takes the old and the revised .docx, works out which sentences differ, and
saves a copy of the revised file with the changed text highlighted. This is
what you send a reviewer alongside a revision, and what you read yourself to
see what a co-author actually altered.

Comparison is at sentence level rather than character level. Word's own Compare
works character by character, which produces unreadable output when sentences
are reordered or rewritten. A sentence here is unchanged, edited, or added, and
that is the granularity people think in.

The revised file is never modified: a copy is written.
"""
from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import docx
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph as DocxParagraph

from ..model.document import Document
from ..parsers.docx_parser import _iter_block_paragraphs
from .docx_comments import _runs_for_span, _normalize

# Sentence boundaries: a period, question or exclamation mark followed by a
# space and a capital, keeping common abbreviations intact.
SENTENCE_END = re.compile(
    r"(?<![A-Z][a-z]\.)(?<!\b[A-Z]\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)"
    r"(?<!\bFig\.)(?<!\bcf\.)(?<!\bet al\.)(?<=[.!?])\s+(?=[A-Z\u201c(])")
WORD = re.compile(r"[\w\u00c0-\u024f'\u2019-]+")
SIMILAR_ENOUGH = 0.55      # below this, a sentence counts as new, not edited


@dataclass
class Change:
    kind: str               # "added" | "edited"
    para_index: int         # index in the revised document
    sentence: str
    similarity: float = 0.0


def split_sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(text) if s.strip()]


def _key(sentence: str) -> str:
    return " ".join(WORD.findall(sentence.lower()))


def compare(old: Document, revised: Document) -> list[Change]:
    """Sentences in `revised` that are new or altered relative to `old`."""
    old_sentences = {}
    for p in old.paragraphs:
        for s in split_sentences(p.text):
            old_sentences.setdefault(_key(s), s)

    changes: list[Change] = []
    old_keys = list(old_sentences)
    for p in revised.paragraphs:
        if not p.text or p.is_heading:
            continue
        for sentence in split_sentences(p.text):
            key = _key(sentence)
            if not key or key in old_sentences:
                continue
            close = difflib.get_close_matches(key, old_keys, n=1,
                                              cutoff=SIMILAR_ENOUGH)
            if close:
                ratio = difflib.SequenceMatcher(None, key, close[0]).ratio()
                changes.append(Change("edited", p.index, sentence, ratio))
            else:
                changes.append(Change("added", p.index, sentence))
    return changes


def summarize(old: Document, revised: Document, changes: list[Change]) -> str:
    old_count = sum(len(split_sentences(p.text)) for p in old.paragraphs if p.text)
    new_count = sum(len(split_sentences(p.text)) for p in revised.paragraphs if p.text)
    added = sum(1 for c in changes if c.kind == "added")
    edited = sum(1 for c in changes if c.kind == "edited")
    return (f"{old_count} sentences in the old version, {new_count} in the "
            f"revised one. {added} added, {edited} edited, "
            f"{new_count - added - edited} unchanged.")


def highlight(revised: Document, changes: list[Change], out_path: str | Path,
              color: WD_COLOR_INDEX = WD_COLOR_INDEX.YELLOW) -> Path:
    """Write a copy of the revised file with each changed sentence highlighted."""
    source, out_path = Path(revised.path), Path(out_path)
    if source.resolve() == out_path.resolve():
        raise ValueError("The highlighted copy must not overwrite the original")
    shutil.copyfile(source, out_path)

    d = docx.Document(str(out_path))
    paragraphs = [DocxParagraph(el, d)
                  for el, _ in _iter_block_paragraphs(d.element.body)]

    by_paragraph: dict[int, list[Change]] = {}
    for c in changes:
        by_paragraph.setdefault(c.para_index, []).append(c)

    for index, items in by_paragraph.items():
        if not 0 <= index < len(paragraphs):
            continue
        paragraph = paragraphs[index]
        for change in items:
            _highlight_sentence(paragraph, change.sentence, color)
    d.save(str(out_path))
    return out_path


def _highlight_sentence(paragraph: DocxParagraph, sentence: str,
                        color: WD_COLOR_INDEX) -> bool:
    raw = "".join("".join(t.text or "" for t in
                          (r._r if hasattr(r, "_r") else r).findall(qn("w:t")))
                  for r in paragraph.runs)
    flat, index = _normalize(raw)
    wanted, _ = _normalize(sentence)
    if not wanted:
        return False
    at = flat.find(wanted)
    if at == -1:
        head = " ".join(wanted.split()[:8])
        at = flat.find(head) if head else -1
        if at == -1:
            return False
        wanted = head
    start, end = index[at], index[at + len(wanted) - 1] + 1
    runs = _runs_for_span(paragraph, start, end)
    for run in runs:
        if hasattr(run, "font"):
            run.font.highlight_color = color
    return bool(runs)


def default_output_path(revised: str | Path) -> Path:
    revised = Path(revised)
    return revised.with_name(f"{revised.stem}_changes{revised.suffix}")
