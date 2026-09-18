"""Parse a .docx manuscript into the Document model.

Reads the underlying Word XML directly so that it can:
  * show the text as it reads with tracked changes accepted
    (insertions kept, deletions dropped);
  * see hidden field codes that reference managers (Zotero, Mendeley,
    EndNote) use to store citations, while reporting only the visible text;
  * include text inside tables, hyperlinks, and simple fields.
"""
from __future__ import annotations

import re
import zipfile

import docx
from lxml import etree
from docx.oxml.ns import qn

from ..model.document import (
    FIGURE_LEGENDS, REFERENCES, Citation, Document, Note, Paragraph,
)

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NOTE_PARTS = {"footnote": "word/footnotes.xml", "endnote": "word/endnotes.xml"}

# Headings we recognize, mapped to canonical section names.
SECTION_PATTERNS = [
    (r"abstract|summary", "abstract"),
    (r"introduction|background", "introduction"),
    # Plain and Cell Press (STAR Methods) headings both land in "methods".
    (r"(materials and )?methods|experimental procedures|star\s*methods"
     r"|method details|key resources? table"
     r"|experimental model( and subject details)?"
     r"|quantification and statistical analysis"
     r"|resource availability|lead contact|materials availability"
     r"|(data and code|data|code) availability( statement)?", "methods"),
    (r"results( and discussion)?", "results"),
    (r"discussion|conclusions?", "discussion"),
    (r"references|bibliography|literature cited|works cited|reference list",
     REFERENCES),
    (r"(supplementary |supplemental )?(figure|table)s?"
     r"(\s+(legends?|captions?|titles and legends))?"
     r"|legends to figures|figure legends and tables", FIGURE_LEGENDS),
    (r"acknowledge?ments?", "acknowledgments"),
    (r"authors?'? contributions?|declarations? of interests?|competing interests?"
     r"|conflicts? of interest", "back_matter"),
    (r"supplementary (information|material|materials|data)", "supplementary"),
]
_SECTION_RES = [(re.compile(rf"^\s*(\d+[.)]?\s*)?({p})\s*:?\s*$", re.I), name)
                for p, name in SECTION_PATTERNS]

W_TAGS_TEXT_BREAK = {"tab": "\t", "br": " ", "cr": " ", "noBreakHyphen": "-"}
# Private markers wrap superscript text so its position survives whitespace
# cleanup; they are removed once the spans are recorded.
SUP_OPEN, SUP_CLOSE = "\u0001", "\u0002"
ITALIC_OPEN, ITALIC_CLOSE = "\u0003", "\u0004"
SKIP_SUBTREES = {"del", "moveFrom", "pPr", "rPr", "instrText"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _classify_field(instr: str) -> str | None:
    s = instr.upper()
    if "ZOTERO_BIBL" in s or "EN.REFLIST" in s or "ADDIN MENDELEY BIBLIOGRAPHY" in s:
        return "bibliography"
    if "ZOTERO_ITEM" in s:
        return "zotero"
    if "EN.CITE" in s:
        return "endnote"
    if "CSL_CITATION" in s or "MENDELEY CITATION" in s:
        return "mendeley"
    return None


class _FieldTracker:
    """Tracks Word complex fields, which can span runs and even paragraphs."""

    def __init__(self):
        self.stack: list[dict] = []
        self.citations: list[Citation] = []

    def begin(self, para_index: int, instr: str = "", state: str = "instr"):
        self.stack.append({"instr": [instr] if instr else [], "result": [],
                           "state": state, "para": para_index, "kind": None})
        if state == "result":
            self.stack[-1]["kind"] = _classify_field(instr)

    def separate(self):
        if self.stack:
            f = self.stack[-1]
            f["state"] = "result"
            f["kind"] = _classify_field("".join(f["instr"]))

    def end(self):
        if not self.stack:
            return
        f = self.stack.pop()
        if f["kind"] is None:
            f["kind"] = _classify_field("".join(f["instr"]))
        if f["kind"] in ("zotero", "mendeley", "endnote"):
            self.citations.append(Citation(
                para_index=f["para"], text="".join(f["result"]).strip(),
                source=f["kind"], raw="".join(f["instr"]).strip()))

    @property
    def text_visible(self) -> bool:
        # Text inside a field's instruction part is hidden code, not content.
        return all(f["state"] == "result" for f in self.stack)

    @property
    def in_bibliography(self) -> bool:
        return any(f["kind"] == "bibliography" and f["state"] == "result"
                   for f in self.stack)

    def add_result_text(self, text: str):
        for f in self.stack:
            if f["state"] == "result":
                f["result"].append(text)


def _walk(el, para_index: int, fields: _FieldTracker, out: list[str], flags: dict):
    tag = _local(el.tag)
    if tag in SKIP_SUBTREES:
        if tag == "instrText" and fields.stack and fields.stack[-1]["state"] == "instr":
            fields.stack[-1]["instr"].append(el.text or "")
        return
    if tag in ("footnoteReference", "endnoteReference"):
        try:
            flags.setdefault("notes", []).append(int(el.get(qn("w:id"))))
        except (TypeError, ValueError):
            pass
        return
    if tag == "fldChar":
        kind = el.get(qn("w:fldCharType"))
        if kind == "begin":
            fields.begin(para_index)
        elif kind == "separate":
            fields.separate()
        elif kind == "end":
            fields.end()
        return
    if tag == "fldSimple":
        fields.begin(para_index, el.get(qn("w:instr")) or "", state="result")
        for child in el:
            _walk(child, para_index, fields, out, flags)
        fields.end()
        return
    if tag == "r":
        vert = el.find(f"{qn('w:rPr')}/{qn('w:vertAlign')}")
        superscript = vert is not None and vert.get(qn("w:val")) == "superscript"
        ital = el.find(f"{qn('w:rPr')}/{qn('w:i')}")
        italic = ital is not None and ital.get(qn("w:val")) not in ("0", "false")
        if superscript:
            out.append(SUP_OPEN)
        if italic:
            out.append(ITALIC_OPEN)
        for child in el:
            _walk(child, para_index, fields, out, flags)
        if italic:
            out.append(ITALIC_CLOSE)
        if superscript:
            out.append(SUP_CLOSE)
        return
    if tag == "t" or tag in W_TAGS_TEXT_BREAK:
        text = (el.text or "") if tag == "t" else W_TAGS_TEXT_BREAK[tag]
        if fields.text_visible:
            out.append(text)
            fields.add_result_text(text)
        if fields.in_bibliography:
            flags["bibliography"] = True
        return
    for child in el:
        _walk(child, para_index, fields, out, flags)


MARKERS = (SUP_OPEN, SUP_CLOSE, ITALIC_OPEN, ITALIC_CLOSE)


def _extract_spans(text: str) -> tuple[str, list[tuple[int, int]],
                                       list[tuple[int, int]]]:
    """Remove the formatting markers, returning the text and the spans.

    Superscript and italic are tracked independently; a run can be both.
    """
    clean: list[str] = []
    spans = {SUP_OPEN: [], ITALIC_OPEN: []}
    depth = {SUP_OPEN: 0, ITALIC_OPEN: 0}
    start = {SUP_OPEN: 0, ITALIC_OPEN: 0}
    closes = {SUP_CLOSE: SUP_OPEN, ITALIC_CLOSE: ITALIC_OPEN}
    length = 0
    for ch in text:
        if ch in (SUP_OPEN, ITALIC_OPEN):
            if depth[ch] == 0:
                start[ch] = length
            depth[ch] += 1
        elif ch in closes:
            key = closes[ch]
            depth[key] = max(0, depth[key] - 1)
            if depth[key] == 0 and length > start[key]:
                spans[key].append((start[key], length))
        else:
            clean.append(ch)
            length += 1
    return "".join(clean), spans[SUP_OPEN], spans[ITALIC_OPEN]


def _read_notes(path: str) -> dict[int, Note]:
    """Read footnotes and endnotes, which live outside the main document part."""
    notes: dict[int, Note] = {}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            for kind, part in NOTE_PARTS.items():
                if part not in names:
                    continue
                root = etree.fromstring(z.read(part))
                for el in root:
                    tag = _local(el.tag)
                    if tag not in ("footnote", "endnote"):
                        continue
                    note_type = el.get(f"{W_NS}type")
                    if note_type in ("separator", "continuationSeparator",
                                     "continuationNotice"):
                        continue
                    try:
                        note_id = int(el.get(f"{W_NS}id"))
                    except (TypeError, ValueError):
                        continue
                    text = re.sub(r"[ \u00a0]+", " ",
                                  "".join(el.itertext())).strip()
                    if text:
                        notes[note_id] = Note(note_id, text, kind)
    except (zipfile.BadZipFile, etree.XMLSyntaxError, KeyError):
        pass
    return notes


def _section_for_heading(text: str) -> str | None:
    for rx, name in _SECTION_RES:
        if rx.match(text):
            return name
    return None


def _iter_block_paragraphs(body):
    """Yield (paragraph_element, in_table) in document order, including table cells."""
    for child in body.iterchildren():
        tag = _local(child.tag)
        if tag == "p":
            yield child, False
        elif tag == "tbl":
            for p in child.iter(qn("w:p")):
                yield p, True
        elif tag == "sdt":  # content controls can wrap whole blocks
            for p in child.iter(qn("w:p")):
                yield p, False


def _style_name(document, p_el) -> str:
    style_el = p_el.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    if style_el is None:
        return "Normal"
    style_id = style_el.get(qn("w:val"))
    try:
        return document.styles.get_by_id(style_id, 1).name or style_id  # 1 = paragraph
    except Exception:
        return style_id or "Normal"


def parse_docx(path: str) -> Document:
    d = docx.Document(path)
    doc = Document(path=str(path))
    fields = _FieldTracker()
    section = "front_matter"

    for idx, (p_el, in_table) in enumerate(_iter_block_paragraphs(d.element.body)):
        out: list[str] = []
        flags: dict = {"bibliography": fields.in_bibliography}
        _walk(p_el, idx, fields, out, flags)
        raw = re.sub(r"[ \u00a0]+", " ", "".join(out))
        # _extract_superscripts already works on the stripped text, so the
        # spans it returns need no further adjustment.
        text, spans, italics = _extract_spans(raw.strip())
        spans = [(a, b) for a, b in spans if text[a:b].strip()]
        italics = [(a, b) for a, b in italics if text[a:b].strip()]
        style = _style_name(d, p_el)
        is_list_item = (p_el.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None
                        or style.lower().startswith(("list number", "list bullet")))

        is_heading = False
        if not in_table and text:
            named = _section_for_heading(text)
            styled_heading = style.lower().startswith(("heading", "title"))
            if named or (styled_heading and len(text) < 120):
                is_heading = True
                section = named or text.lower()

        doc.paragraphs.append(Paragraph(
            index=idx, text=text, style=style, section=section,
            is_heading=is_heading, in_table=in_table,
            in_bibliography_field=flags["bibliography"],
            is_list_item=is_list_item, superscript_spans=spans,
            italic_spans=italics,
            footnote_ids=flags.get("notes", [])))

    doc.citations = fields.citations
    doc.notes = _read_notes(str(path))
    return doc
