"""Submission-readiness checks.

Counts the things journals put limits on — words, references, figures, tables —
and compares them with a journal profile when one is given.

With no profile, the counts are reported as notes, which is useful on its own
and can never be wrong. With a profile (`--profile nature.json`), anything over
a limit becomes a warning, and a missing required section becomes an error.

A profile is a small JSON file; see galley/profiles/example.json. Galley
ships a list of journals in galley/profiles/journals/, each recording the
date its rules were last checked against the journal's own guidelines (or
none, when nobody has yet). Limits change often, so an unchecked or old
profile is always reported as such, and every limit it sets says so.
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
JOURNAL_DIR = PROFILE_DIR / "journals"      # the journal list shipped with Galley
LIMIT_KEYS = {"abstract_words", "main_text_words", "total_words", "title_words",
              "title_chars", "keywords", "references", "figures", "tables",
              "display_items"}


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


def downloaded_journals_dir() -> Path:
    """Where Check for Updates keeps the latest journal list."""
    return user_profile_dir().parent / "journal-list"
# Sections whose words count towards a main-text limit.
MAIN_TEXT = {"introduction", "results", "discussion", "conclusions"}
COUNTED_SEPARATELY = {"abstract", "methods", "references", "figure_legends",
                      "acknowledgments", "back_matter", "supplementary"}
WORD = re.compile(r"[\w\u00c0-\u024f][\w\u00c0-\u024f'\u2019\-]*")
KEYWORDS = re.compile(r"^\s*key\s*-?\s*words?\s*[:.\-–—]\s*", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
# Which paragraphs each word limit counts, as in count().
LIMIT_SECTIONS = {"abstract_words": {"abstract"},
                  "main_text_words": MAIN_TEXT,
                  "total_words": {"abstract", "methods"} | MAIN_TEXT}


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
    abstract_headings: list[str] = field(default_factory=list)  # structured abstract
    reference_style: str | None = None      # "numbered" | "author_year"
    max_authors_listed: int | None = None   # before "et al." in the reference list
    require_doi: bool = False
    template: bool = False                  # documentation, not a real journal
    publisher: str | None = None
    article_type: str | None = None         # "Research Article"
    guidelines_url: str | None = None
    verified: str | None = None             # YYYY-MM-DD, or None: not yet checked
    notes: str | None = None
    path: Path | None = None

    @classmethod
    def load(cls, source: str | Path) -> "Profile":
        path = Path(source)
        if not path.exists() and not path.suffix:
            for folder in (PROFILE_DIR, JOURNAL_DIR):
                if (folder / f"{source}.json").exists():
                    path = folder / f"{source}.json"
                    break
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), path)

    @classmethod
    def from_dict(cls, data: dict, path: Path | None = None) -> "Profile":
        """Read and check a profile; raises ValueError on anything malformed."""
        if not isinstance(data, dict):
            raise ValueError("a profile must be a JSON object")
        style = (data.get("reference_style") or "").strip().lower() or None
        if style not in (None, "numbered", "author_year"):
            raise ValueError(f'reference_style must be "numbered" or '
                             f'"author_year", not "{style}"')
        verified = data.get("verified") or None
        if verified is not None:
            date.fromisoformat(str(verified))       # ValueError if malformed
        try:
            limits = {k: int(v) for k, v in (data.get("limits") or {}).items()}
        except (TypeError, ValueError):
            raise ValueError("limits must be whole numbers") from None
        return cls(name=data.get("name") or (path.stem if path else "journal"),
                   limits=limits,
                   required_sections=list(data.get("required_sections") or []),
                   abstract_headings=list(data.get("abstract_headings") or []),
                   reference_style=style,
                   max_authors_listed=(int(data["max_authors_listed"])
                                       if data.get("max_authors_listed") else None),
                   require_doi=bool(data.get("require_doi")),
                   template=bool(data.get("template")),
                   publisher=data.get("publisher"),
                   article_type=data.get("article_type"),
                   guidelines_url=data.get("guidelines_url"),
                   verified=verified,
                   notes=data.get("notes"),
                   path=path)

    @property
    def label(self) -> str:
        """The name shown in lists: "eLife · Research Article"."""
        return f"{self.name} · {self.article_type}" if self.article_type else self.name

    @property
    def checked(self) -> bool:
        return bool(self.verified)

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
    """Profiles the user has made, then the journal list (the latest download
    if there is one, then the copy shipped with Galley). A user's own profile
    with the same file name as a listed journal takes its place.

    The bundled example is a template with invented numbers, so it stays out of
    the list a user picks from: a fake journal in the dropdown is worse than an
    empty one.
    """
    out, seen = [], set()
    for folder in (user_profile_dir(), downloaded_journals_dir(), JOURNAL_DIR,
                   PROFILE_DIR):
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
    "title_chars": "title",
    "keywords": "keywords",
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
    title_chars: int = 0
    title_index: int | None = None
    keywords: int = 0
    keywords_index: int | None = None
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
            c.title_chars = len(p.text.strip())
            c.title_index = p.index
            continue
        if c.keywords_index is None and KEYWORDS.match(p.text):
            rest = KEYWORDS.sub("", p.text, count=1)
            c.keywords = len([k for k in re.split(r"[;,•·|]", rest) if k.strip()])
            c.keywords_index = p.index
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
            "title_chars": counts.title_chars,
            "keywords": counts.keywords if counts.keywords_index is not None else None,
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


def _sentence_at(text: str, offset: int) -> str:
    """The sentence of `text` containing the character at `offset`."""
    start = 0
    for m in SENTENCE_END.finditer(text):
        if m.start() >= offset:
            break
        start = m.end()
    end = SENTENCE_END.search(text, offset)
    return text[start:end.start() if end else len(text)].strip()


def where_limit_is_crossed(doc: Document, key: str,
                           limit: int) -> tuple[int, str] | None:
    """For a word limit, the paragraph and sentence holding word number
    limit + 1: everything from there on is over the limit."""
    sections = LIMIT_SECTIONS.get(key)
    if not sections:
        return None
    seen = 0
    title_done = False
    for p in doc.paragraphs:
        if not p.text:
            continue
        if not title_done and _words(p.text) >= 4 and (
                p.style.lower().startswith("title")
                or (p.section == "front_matter" and not p.in_table)):
            title_done = True                   # count() skips the title too
            continue
        if p.is_heading or p.in_bibliography_field or p.section not in sections:
            continue
        words = list(WORD.finditer(p.text))
        if seen + len(words) > limit:
            first_over = words[limit - seen]
            return p.index, _sentence_at(p.text, first_over.start())
        seen += len(words)
    return None


def _first_over(doc: Document, key: str, limit: int) -> tuple[int | None, str | None]:
    """The first reference, figure or table past a limit."""
    if key == "references":
        from .references import collect_entries
        entries = collect_entries(doc)
        if len(entries) > limit:
            e = entries[limit]
            return e.para_index, e.text.strip()[:80] or None
        return None, None
    if key in ("figures", "tables", "display_items"):
        from .figures import find_callouts_and_legends
        _, legends = find_callouts_and_legends(doc)
        kinds = {"figures": {"figure"}, "tables": {"table"},
                 "display_items": {"figure", "table"}}[key]
        main = sorted((lg for lg in legends
                       if lg.key.group == "main" and lg.key.kind in kinds),
                      key=lambda lg: lg.para_index)
        if len(main) > limit:
            return main[limit].para_index, None
    return None, None


def _abstract_headings(doc: Document, profile: "Profile") -> list[Issue]:
    """A structured abstract needs each of its headings, e.g. Background."""
    paras = [p for p in doc.paragraphs if p.section == "abstract" and p.text]
    if not paras:
        return []
    text = "\n".join(p.text for p in paras)
    missing = [h for h in profile.abstract_headings
               if not re.search(rf"(^|\n|\.\s)\s*{re.escape(h)}\s*[:.\-–—\n]", text, re.I)]
    if not missing:
        return []
    unconfirmed = "" if profile.checked else " (requirement not yet confirmed)"
    return [Issue(CHECK, "error" if profile.checked else "warning",
                  f"{profile.name} asks for a structured abstract with the headings "
                  f"{', '.join(profile.abstract_headings)}; "
                  f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                  f"missing{unconfirmed}.",
                  paras[0].index, None,
                  "Start each part of the abstract with its heading, e.g. "
                  f"“{profile.abstract_headings[0]}: …”.")]


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
    provenance = f'Checked against the "{profile.label}" requirements'
    if profile.verified:
        provenance += f", last verified {profile.verified}"
    if profile.guidelines_url:
        provenance += f". Journal guidelines: {profile.guidelines_url}"
    issues.append(Issue(CHECK, "info", provenance + "."))

    age = profile.months_old
    if age is None:
        issues.append(Issue(
            CHECK, "warning",
            f"The {profile.name} requirements haven't been checked against the "
            f"journal's author guidelines yet, so they may be out of date.",
            None, None,
            "Confirm each limit against the journal's guidelines before relying "
            "on it" + (f": {profile.guidelines_url}" if profile.guidelines_url
                       else ".")))
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
    # The pre-filled note repeats the "not yet checked" warning above.
    if profile.notes and not (age is None and profile.notes.startswith("Pre-filled")):
        issues.append(Issue(CHECK, "info", profile.notes))

    unconfirmed = "" if profile.checked else " (not yet confirmed)"
    for key, limit in sorted(profile.limits.items()):
        value = _value(counts, key)
        if value is None:
            if key == "keywords":
                issues.append(Issue(
                    CHECK, "warning",
                    f"{profile.name} asks for keywords (up to {limit}), and no "
                    f"“Keywords:” line was found.", None, None,
                    "Add a line starting “Keywords:” after the abstract."))
            else:
                issues.append(Issue(CHECK, "info",
                                    f'The profile "{profile.name}" sets a limit for '
                                    f'"{key}", which Galley doesn\'t measure.'))
            continue
        label = LIMIT_LABELS.get(key, key.replace("_", " "))
        para, anchor = None, None
        if key.endswith("_words"):
            described = f"The {label} is {value:,} words"
            unit = " words"
            cut = f"Cut about {value - limit:,} words before submitting."
            found = where_limit_is_crossed(doc, key, limit) if value > limit else None
            if found:
                para, anchor = found
                cut += " The highlighted sentence is where the limit is reached."
        elif key == "title_chars":
            described = f"The title is {value:,} characters long"
            unit, cut = " characters", f"Shorten it by {value - limit:,} characters."
            para = counts.title_index
        elif key == "keywords":
            described = f"There are {value} keywords"
            unit, cut = "", f"Keep the {limit} that best describe the work."
            para = counts.keywords_index
        else:
            described = f"There are {value:,} {label}"
            unit, cut = "", f"The limit is {limit:,}."
            para, anchor = _first_over(doc, key, limit) if value > limit else (None, None)
        if key == "title_words":
            para = counts.title_index
        if value > limit:
            issues.append(Issue(
                CHECK, "warning",
                f"{described}, over the {profile.name} limit of {limit:,}{unit} "
                f"by {value - limit:,}{unconfirmed}.",
                para, anchor, cut))
        elif value >= 0.95 * limit:
            issues.append(Issue(
                CHECK, "info",
                f"{described}, close to the {profile.name} limit of {limit:,}{unit}"
                f"{unconfirmed}.", para))

    if profile.abstract_headings:
        issues.extend(_abstract_headings(doc, profile))

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
        issues.append(Issue(CHECK, "error" if profile.checked else "warning",
                            f'{profile.name} requires a "{wanted}" section, which '
                            f"wasn't found{unconfirmed}.",
                            None, None,
                            "Add the section, or check that its heading is "
                            "formatted as a heading."))
    return issues


# ---- the journal list, kept up to date -------------------------------------

def fetch_journal_updates(folder: Path | None = None, opener=None):
    """Download the current journal list from Galley's public repository into
    the user's settings folder; see galley.updates.fetch_list."""
    from urllib.request import urlopen

    from ... import updates
    return updates.fetch_list(updates.listing_url("journals"),
                              folder or downloaded_journals_dir(),
                              Profile.from_dict, opener or urlopen)


def journals_last_updated(folder: Path | None = None):
    from ... import updates
    return updates.last_updated(folder or downloaded_journals_dir())
