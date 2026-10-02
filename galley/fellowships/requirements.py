"""What an application needs: documents and their limits, CV format,
a host letter and how to submit. application_check.py checks files against
these.

In a fellowship's JSON this is the "requirements" section; see
galley/fellowships/data/README.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CV_FORMATS = {"standard", "narrative", "funder_template"}
SUBMISSION_ROUTES = {"portal", "email", "institution"}
FILE_FORMATS = {"pdf", "docx"}


@dataclass
class DocumentRequirement:
    name: str                               # "Research proposal"
    max_pages: int | None = None
    max_words: int | None = None
    min_font_size: float | None = None      # points
    min_margin_cm: float | None = None
    file_format: str | None = None          # "pdf" | "docx"
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
                min_margin_cm=(float(d["min_margin_cm"])
                               if d.get("min_margin_cm") else None),
                file_format=_format(d.get("file_format")),
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


def _format(v) -> str | None:
    if v in (None, ""):
        return None
    v = str(v).lower().lstrip(".")
    if v not in FILE_FORMATS:
        raise ValueError("file_format must be pdf or docx")
    return v


def _int(v) -> int | None:
    return None if v in (None, "") else int(v)
