"""What an application needs: documents and their limits, CV format,
a host letter and how to submit. Also checks a draft document against its limits.

In a fellowship's JSON this is the "requirements" section; see
galley/fellowships/data/README.md.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field

from ..model.document import Issue

CV_FORMATS = {"standard", "narrative", "funder_template"}
SUBMISSION_ROUTES = {"portal", "email", "institution"}
CHECK = "application"
WORD = re.compile(r"[\wÀ-ɏ][\wÀ-ɏ'’\-]*")


@dataclass
class DocumentRequirement:
    name: str                               # "Research proposal"
    max_pages: int | None = None
    max_words: int | None = None
    min_font_size: float | None = None      # points
    sections: list[str] = field(default_factory=list)
    template_url: str | None = None
    notes: str | None = None


@dataclass
class Requirements:
    documents: list[DocumentRequirement] = field(default_factory=list)
    cv_format: str | None = None
    cv_notes: str | None = None
    host_letter: bool = False
    submission: str | None = None
    submission_url: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Requirements":
        docs = []
        for d in data.get("documents") or []:
            if not d.get("name"):
                raise ValueError("every required document needs a name")
            docs.append(DocumentRequirement(
                name=str(d["name"]),
                max_pages=_int(d.get("max_pages")),
                max_words=_int(d.get("max_words")),
                min_font_size=(float(d["min_font_size"])
                               if d.get("min_font_size") else None),
                sections=[str(s) for s in d.get("sections") or []],
                template_url=d.get("template_url"),
                notes=d.get("notes")))
        cv = data.get("cv_format")
        if cv is not None and cv not in CV_FORMATS:
            raise ValueError(f"cv_format must be one of {', '.join(sorted(CV_FORMATS))}")
        route = data.get("submission")
        if route is not None and route not in SUBMISSION_ROUTES:
            raise ValueError(f"submission must be one of "
                             f"{', '.join(sorted(SUBMISSION_ROUTES))}")
        return cls(documents=docs, cv_format=cv, cv_notes=data.get("cv_notes"),
                   host_letter=bool(data.get("host_letter")),
                   submission=route, submission_url=data.get("submission_url"))

    def document(self, name: str) -> DocumentRequirement | None:
        for d in self.documents:
            if d.name.lower() == name.lower():
                return d
        return None


def _int(v) -> int | None:
    return None if v in (None, "") else int(v)


def _saved_page_count(path: str) -> int | None:
    """The page count Word stored when the file was last saved. Word writes it
    to docProps/app.xml; other editors may not, and it can be stale."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("docProps/app.xml").decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
    m = re.search(r"<(?:\w+:)?Pages>(\d+)</", xml)
    return int(m.group(1)) if m else None


def _covers(candidate: str, words: list[str]) -> bool:
    at = 0
    for w in words:
        found = candidate.find(w, at)
        if found == -1:
            return False
        at = found + len(w)
    return True


def check_draft(path: str, req: DocumentRequirement) -> list[Issue]:
    """Check a .docx draft against one document's limits: words, pages and
    required sections. Font size and margins aren't checked; they're listed
    as a reminder instead, since Word's layout decides them."""
    from ..engine import load

    doc = load(path)
    issues: list[Issue] = []
    body = [p for p in doc.paragraphs if p.text and not doc.is_reference_paragraph(p)]
    words = sum(len(WORD.findall(p.text)) for p in body if not p.is_heading)

    if req.max_words is not None:
        if words > req.max_words:
            issues.append(Issue(CHECK, "warning",
                                f"The {req.name} is {words:,} words, over the "
                                f"limit of {req.max_words:,} by {words - req.max_words:,}.",
                                suggestion="Reference lists usually don't count; "
                                           "check the funder's rules."))
        else:
            issues.append(Issue(CHECK, "info",
                                f"The {req.name} is {words:,} words (limit "
                                f"{req.max_words:,})."))

    if req.max_pages is not None:
        pages = _saved_page_count(path) if str(path).lower().endswith(".docx") else None
        if pages is None:
            issues.append(Issue(CHECK, "info",
                                f"The limit is {req.max_pages} pages. Galley can't "
                                f"count pages in this file; check it in Word."))
        elif pages > req.max_pages:
            issues.append(Issue(CHECK, "warning",
                                f"The {req.name} was {pages} pages when last saved "
                                f"in Word, over the {req.max_pages}-page limit.",
                                suggestion="Re-save in Word after editing; the "
                                           "count updates on save."))
        else:
            issues.append(Issue(CHECK, "info",
                                f"The {req.name} was {pages} pages when last saved "
                                f"(limit {req.max_pages})."))

    candidates = [p.text.lower() for p in body if p.is_heading]
    candidates += [p.text[:70].lower() for p in body if not p.is_heading]
    for section in req.sections:
        wanted = [w for w in WORD.findall(section.lower())
                  if w not in {"and", "of", "the"}]
        if not any(_covers(c, wanted) for c in candidates):
            issues.append(Issue(CHECK, "error",
                                f'The {req.name} has no "{section}" section, '
                                f"which the funder asks for.",
                                suggestion="Add it, or check that its heading "
                                           "matches the funder's wording."))

    if req.min_font_size:
        issues.append(Issue(CHECK, "info",
                            f"Use at least {req.min_font_size:g} pt text; Galley "
                            f"doesn't check font size."))
    return issues
