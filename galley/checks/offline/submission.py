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
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ...model.document import Document, Issue

CHECK = "submission"

PROFILE_DIR = Path(__file__).resolve().parents[2] / "profiles"


def user_profile_dir() -> Path:
    """Where profiles the user creates are kept.

    Separate from the bundled folder, which lives inside the installed app and
    is not writable once Galley is packaged.
    """
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "Galley"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", home)) / "Galley"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "galley"
    return base / "profiles"
# Sections whose words count towards a main-text limit.
MAIN_TEXT = {"introduction", "results", "discussion", "conclusions"}
COUNTED_SEPARATELY = {"abstract", "methods", "references", "figure_legends",
                      "acknowledgments", "back_matter", "supplementary"}
WORD = re.compile(r"[\w\u00c0-\u024f][\w\u00c0-\u024f'\u2019\-]*")


@dataclass
class Profile:
    """A journal's submission rules, read from a small JSON file.

    Limits change without notice, so every profile records the date it was
    checked and a link to the journal's own guidelines. Galley reports both,
    and warns when a profile is old, rather than implying its numbers are
    authoritative.
    """
    name: str = "no journal profile"
    limits: dict[str, int] = field(default_factory=dict)
    required_sections: list[str] = field(default_factory=list)
    reference_style: str | None = None      # "numbered" | "author_year"
    max_authors_listed: int | None = None   # before "et al." in the reference list
    require_doi: bool = False
    template: bool = False                  # documentation, not a real journal
    guidelines_url: str | None = None
    verified: str | None = None             # YYYY-MM-DD
    notes: str | None = None
    path: Path | None = None

    @classmethod
    def load(cls, source: str | Path) -> "Profile":
        path = Path(source)
        if not path.exists() and not path.suffix:
            path = PROFILE_DIR / f"{source}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        style = (data.get("reference_style") or "").strip().lower() or None
        if style not in (None, "numbered", "author_year"):
            raise ValueError(f'reference_style must be "numbered" or '
                             f'"author_year", not "{style}"')
        return cls(name=data.get("name", path.stem),
                   limits={k: int(v) for k, v in (data.get("limits") or {}).items()},
                   required_sections=list(data.get("required_sections") or []),
                   reference_style=style,
                   max_authors_listed=(int(data["max_authors_listed"])
                                       if data.get("max_authors_listed") else None),
                   require_doi=bool(data.get("require_doi")),
                   template=bool(data.get("template")),
                   guidelines_url=data.get("guidelines_url"),
                   verified=data.get("verified"),
                   notes=data.get("notes"),
                   path=path)

    @property
    def months_old(self) -> float | None:
        if not self.verified:
            return None
        try:
            checked = date.fromisoformat(self.verified)
        except ValueError:
            return None
        return (date.today() - checked).days / 30.44


def available_profiles(include_templates: bool = False) -> list[Profile]:
    """Profiles the user has made, plus any real ones shipped with Galley.

    The bundled example is a template with invented numbers, so it stays out of
    the list a user picks from: a fake journal in the dropdown is worse than an
    empty one.
    """
    out, seen = [], set()
    for folder in (user_profile_dir(), PROFILE_DIR):
        try:
            paths = sorted(folder.glob("*.json"))
        except OSError:
            continue
        for path in paths:
            if path.name in seen:
                continue
            try:
                profile = Profile.load(path)
                if profile.template and not include_templates:
                    continue
                out.append(profile)
                seen.add(path.name)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return sorted(out, key=lambda p: p.name.lower())


def is_user_profile(profile: "Profile") -> bool:
    """True for a profile the user made, as opposed to one shipped with Galley."""
    try:
        return (profile.path is not None
                and profile.path.parent.resolve() == user_profile_dir().resolve())
    except OSError:
        return False


def delete_profile(profile: "Profile") -> bool:
    """Remove a profile the user made. Bundled profiles are left alone."""
    if not is_user_profile(profile):
        return False
    try:
        profile.path.unlink()
    except OSError:
        return False
    return True


def save_profile(data: dict, filename: str | None = None) -> Path:
    """Write a profile the user filled in, and return where it went."""
    folder = user_profile_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stem = filename or re.sub(r"[^a-z0-9]+", "-",
                              str(data.get("name", "journal")).lower()).strip("-")
    path = folder / f"{stem or 'journal'}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


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

    # Say which profile is in use, how old it is, and where its rules came
    # from. A journal's limits change without notice, so an unverified or
    # stale profile must not read as authoritative.
    provenance = f'Checked against the "{profile.name}" profile'
    if profile.verified:
        provenance += f", last verified {profile.verified}"
    if profile.guidelines_url:
        provenance += f". Journal guidelines: {profile.guidelines_url}"
    issues.append(Issue(CHECK, "info", provenance + "."))

    age = profile.months_old
    if age is None:
        issues.append(Issue(
            CHECK, "warning",
            f'The "{profile.name}" profile has no verification date, so its '
            f"limits may be out of date.",
            None, None,
            "Check the journal's author guidelines before relying on these "
            "numbers."))
    elif age > 12:
        issues.append(Issue(
            CHECK, "warning",
            f'The "{profile.name}" profile was last verified '
            f"{int(age)} months ago and may be out of date.",
            None, None,
            "Confirm the current limits in the journal's author guidelines."))
    elif age > 6:
        issues.append(Issue(
            CHECK, "info",
            f'The "{profile.name}" profile was last verified '
            f"{int(age)} months ago; worth confirming against the journal."))
    if profile.notes:
        issues.append(Issue(CHECK, "info", profile.notes))

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
