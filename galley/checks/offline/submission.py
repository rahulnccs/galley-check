"""Submission-readiness checks.

Counts the things journals put limits on — words, references, figures, tables —
and compares them with a journal profile when one is given.

With no profile, the counts are reported as notes, which is useful on its own
and can never be wrong. With a profile (`--profile nature.json`), anything over
a limit becomes a warning, and a missing required section becomes an error.

A profile is a small JSON file; see galley/profiles/example.json. Limits change
often, so Galley ships an example to copy rather than pretending to know any
journal's current rules.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ...model.document import Document, Issue

CHECK = "submission"

PROFILE_DIR = Path(__file__).resolve().parents[2] / "profiles"
# Sections whose words count towards a main-text limit.
MAIN_TEXT = {"introduction", "results", "discussion", "conclusions"}
COUNTED_SEPARATELY = {"abstract", "methods", "references", "figure_legends",
                      "acknowledgments", "back_matter", "supplementary"}
WORD = re.compile(r"[\w\u00c0-\u024f][\w\u00c0-\u024f'\u2019\-]*")


@dataclass
class Profile:
    name: str = "no journal profile"
    limits: dict[str, int] = field(default_factory=dict)
    required_sections: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, source: str | Path) -> "Profile":
        path = Path(source)
        if not path.exists() and not path.suffix:
            path = PROFILE_DIR / f"{source}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(name=data.get("name", path.stem),
                   limits={k: int(v) for k, v in (data.get("limits") or {}).items()},
                   required_sections=list(data.get("required_sections") or []))


LIMIT_LABELS = {
    "abstract_words": "abstract",
    "main_text_words": "main text",
    "total_words": "whole manuscript",
    "title_words": "title",
    "references": "references in the list",
    "figures": "figures",
    "tables": "tables",
    "display_items": "figures and tables together",
}


def _covers(candidate: str, words: list[str]) -> bool:
    """True if every word appears in the candidate, in order."""
    at = 0
    for w in words:
        found = candidate.find(w, at)
        if found == -1:
            return False
        at = found + len(w)
    return True


def _words(text: str) -> int:
    return len(WORD.findall(text))


@dataclass
class Counts:
    title: int = 0
    abstract: int = 0
    main_text: int = 0
    methods: int = 0
    total: int = 0
    references: int = 0
    figures: int = 0
    tables: int = 0

    @property
    def display_items(self) -> int:
        return self.figures + self.tables


def count(doc: Document) -> Counts:
    from .figures import find_callouts_and_legends
    from .references import collect_entries

    c = Counts()
    for p in doc.paragraphs:
        if not p.text:
            continue
        if not c.title and _words(p.text) >= 4 and (
                p.style.lower().startswith("title")
                or (p.section == "front_matter" and not p.in_table)):
            c.title = _words(p.text)
            continue
        if p.is_heading or p.in_bibliography_field:
            continue
        words = _words(p.text)
        if p.section == "abstract":
            c.abstract += words
        elif p.section in MAIN_TEXT:
            c.main_text += words
        elif p.section == "methods":
            c.methods += words
    c.total = c.abstract + c.main_text + c.methods
    c.references = len(collect_entries(doc))

    _, legends = find_callouts_and_legends(doc)
    main = [lg for lg in legends if lg.key.group == "main"]
    c.figures = sum(1 for lg in main if lg.key.kind == "figure")
    c.tables = sum(1 for lg in main if lg.key.kind == "table")
    return c


def _value(counts: Counts, key: str) -> int | None:
    return {"abstract_words": counts.abstract,
            "main_text_words": counts.main_text,
            "total_words": counts.total,
            "title_words": counts.title,
            "references": counts.references,
            "figures": counts.figures,
            "tables": counts.tables,
            "display_items": counts.display_items}.get(key)


def _summary(counts: Counts) -> str:
    parts = []
    if counts.abstract:
        parts.append(f"abstract {counts.abstract:,} words")
    if counts.main_text:
        parts.append(f"main text {counts.main_text:,}")
    if counts.methods:
        parts.append(f"methods {counts.methods:,}")
    if counts.references:
        parts.append(f"{counts.references} references")
    items = []
    if counts.figures:
        items.append(f"{counts.figures} figure{'s' if counts.figures != 1 else ''}")
    if counts.tables:
        items.append(f"{counts.tables} table{'s' if counts.tables != 1 else ''}")
    return "; ".join(parts + items)


def check_submission(doc: Document, profile: Profile | None = None) -> list[Issue]:
    counts = count(doc)
    summary = _summary(counts)
    issues: list[Issue] = []
    if summary:
        issues.append(Issue(CHECK, "info", f"Manuscript size: {summary}."))
    if profile is None:
        return issues

    for key, limit in sorted(profile.limits.items()):
        value = _value(counts, key)
        if value is None:
            issues.append(Issue(CHECK, "info",
                                f'The profile "{profile.name}" sets a limit for '
                                f'"{key}", which Galley doesn\'t measure.'))
            continue
        label = LIMIT_LABELS.get(key, key.replace("_", " "))
        if key.endswith("_words"):
            described = f"The {label} is {value:,} words"
            unit, cut = " words", f"Cut about {value - limit:,} words before submitting."
        else:
            described = f"There are {value:,} {label}"
            unit, cut = "", f"The limit is {limit:,}."
        if value > limit:
            issues.append(Issue(
                CHECK, "warning",
                f"{described}, over the {profile.name} limit of {limit:,}{unit} "
                f"by {value - limit:,}.",
                None, None, cut))
        elif value >= 0.95 * limit:
            issues.append(Issue(
                CHECK, "info",
                f"{described}, close to the {profile.name} limit of {limit:,}{unit}."))

    present = {p.section for p in doc.paragraphs if p.text}
    # Headings, plus the opening of each paragraph: many journals put
    # "Data availability." as a run-in heading inside a paragraph.
    candidates = [p.text.lower() for p in doc.paragraphs if p.is_heading]
    candidates += [p.text[:70].lower() for p in doc.paragraphs
                   if p.text and not p.is_heading]
    for wanted in profile.required_sections:
        phrase = wanted.strip().lower()
        key = phrase.replace(" ", "_")
        # "data availability" matches "DATA AND CODE AVAILABILITY" — every word
        # of the requirement appears, in order.
        words = [w for w in WORD.findall(phrase) if w not in {"and", "of", "the"}]
        if key in present or any(_covers(c, words) for c in candidates):
            continue
        issues.append(Issue(CHECK, "error",
                            f'{profile.name} requires a "{wanted}" section, which '
                            f"wasn't found.",
                            None, None,
                            "Add the section, or check that its heading is "
                            "formatted as a heading."))
    return issues
