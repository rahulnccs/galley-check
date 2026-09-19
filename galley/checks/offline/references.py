"""Citation and reference-list checks.

Handles the two styles used in most journals:

  * numeric — "[12]", "[3,5-7]", or superscript numbers, with a numbered
    reference list (typed, or a Word auto-numbered list);
  * author-year — "(Smith et al., 2020)" or "Smith et al. (2020)".

Checks:
  * every citation points at a reference that exists
  * every reference in the list is cited somewhere in the text
  * numbered references are first cited in ascending order
  * no gaps or repeats in the reference numbering
  * no duplicate reference entries
  * entries that are missing a year, and malformed DOIs
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ...model.document import REFERENCES, Document, Issue, Paragraph

CHECK = "references"

BRACKETED = re.compile(r"[\[(]\s*(\d{1,3}(?:\s*[,;\u2013\u2014-]\s*\d{1,3})*)\s*[\])]")
NUMBER_SPEC = re.compile(r"\d{1,3}")
RANGE_SPEC = re.compile(r"(\d{1,3})\s*[\u2013\u2014-]\s*(\d{1,3})")
LEADING_NUMBER = re.compile(r"^\s*[\[(]?(\d{1,3})[\])]?[.\t)]?\s+")
YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)([a-z])?\b")
DOI = re.compile(r"\b(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\S+)", re.I)
VALID_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
# "(Smith et al., 2020)" / "(Smith and Jones 2019; Doe 2021)" / "Smith et al. (2020)"
PAREN_AUTHOR_YEAR = re.compile(
    r"\(([^()]{0,200}?\b(?:1[89]\d\d|20\d\d)[a-z]?\b[^()]{0,40})\)")
NARRATIVE_AUTHOR_YEAR = re.compile(
    r"\b([A-Z][A-Za-z\u00c0-\u024f'\u2019-]{1,25})\s+"
    r"(?:et\s+al\.?|and\s+[A-Z][A-Za-z'\u2019-]{1,25}|&\s*[A-Z][A-Za-z'\u2019-]{1,25})?\s*"
    r"\(\s*(1[89]\d\d|20\d\d)[a-z]?\s*\)")
# "[Adler and Byrne 2019]" — author-year inside square brackets
BRACKET_AUTHOR_YEAR = re.compile(
    r"\[([^\[\]]{0,200}?\b(?:1[89]\d\d|20\d\d)[a-z]?\b[^\[\]]{0,40})\]")
# "[Adl19]", "[CD20]", "[ABC+21]", "[Doe2020a]" — a key must contain a digit
CITATION_KEY = re.compile(
    r"\[([A-Za-z][A-Za-z0-9+'\u2019-]{1,19}(?:\s*[,;]\s*[A-Za-z][A-Za-z0-9+'\u2019-]{1,19})*)\]")
# "Berg M," / "Doe, J. A." / "Smith et al." at the start of an entry. Case
# matters here: with IGNORECASE, "Population dynamics" would look like a name.
AUTHOR_START = re.compile(
    r"\b[A-Z\u00c0-\u024f][\w'\u2019-]+,?\s+(?:[A-Z]\.?\s?){1,4}\b|\bet al\b|\bEt al\b")
# One author at the start of an entry: "Shreiner AB", "Doe, J. A.", "Kao JY".
AUTHOR_NAME = re.compile(
    r"[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019-]{1,24}"      # surname
    r"(?:\s+[A-Z][a-z]+)?"                                        # compound surname
    r",?\s+[A-Z]\.?(?:\s*[A-Z]\.?){0,3}")                          # initials
# What separates one author from the next.
# ", " but also ", & " and " and ", which APA style puts before the last author.
SEPARATOR = re.compile(r"(?:\s*[,;&]\s*|\s+and\s+)+")
# A source: a journal with volume/pages, a DOI, a URL, or a publisher year.
HAS_SOURCE = re.compile(
    r"\b\d{1,4}\s*[:(;,]\s*\d|\bdoi\b|10\.\d{4,9}/|https?://|\bpp?\.\s*\d"
    r"|\bpress\b|\bpublish|\bbioRxiv\b|\bmedRxiv\b|\barXiv\b|\bpreprint\b", re.I)
SURNAME_IN_CITATION = re.compile(r"\b([A-Z][A-Za-z\u00c0-\u024f'\u2019-]{1,25})")
NOT_A_SURNAME = {"Fig", "Figure", "Figures", "Table", "Tables", "Supplementary", "See",
                 "Data", "Extended", "Ref", "Refs", "Eq", "Equation", "Chapter", "Section",
                 "In", "The", "And", "Panel", "Movie", "Video", "Appendix", "Note"}
BODY_SECTIONS = {"abstract", "introduction", "methods", "results", "discussion",
                 "conclusions", "supplementary", "figure_legends"}


@dataclass
class Entry:
    number: int                 # position in the list, 1-based
    stated_number: int | None   # number printed in the file, if any
    text: str
    para_index: int

    @property
    def year(self) -> str | None:
        m = YEAR.search(self.text)
        return m.group(1) if m else None

    @property
    def surnames(self) -> set[str]:
        """Surnames near the start of the entry, where the author list sits."""
        head = self.text[:180]
        return {w for w in SURNAME_IN_CITATION.findall(head) if w not in NOT_A_SURNAME}

    @property
    def author_count(self) -> int | None:
        """How many authors an entry lists, when that can be counted reliably.

        Counting by splitting on commas overcounts, because the title that
        follows the authors contains commas too. Instead the author names are
        matched one after another from the start of the entry, and counting
        stops at the first thing that isn't a name — which is the title.
        """
        text = self.text.strip()
        if not text or "et al" in text[:220].lower():
            return None            # truncated with et al., so not a full count
        count, at = 0, 0
        while at < len(text):
            m = AUTHOR_NAME.match(text, at)
            if not m:
                break
            count += 1
            at = m.end()
            sep = SEPARATOR.match(text, at)
            if not sep:
                break
            at = sep.end()
        return count or None

    @property
    def first_sentence(self) -> str:
        return re.split(r"\.\s|\?\s", self.text, 1)[0]

    @property
    def has_authors(self) -> bool:
        """False when an entry starts with its title, the author list lost."""
        head = self.first_sentence
        if head[:1].islower() or len(head.split()) < 6:
            return True          # a software name or an organization, not a title
        return bool(AUTHOR_START.search(head))

    @property
    def author_zone(self) -> str:
        """The part of the entry that holds the author list."""
        m = YEAR.search(self.text)
        if m and m.start() < 160:
            return self.text[:m.start()]
        return self.text.split(". ")[0][:160]

    @property
    def author_surnames(self) -> list[str]:
        seen, names = set(), []
        for w in SURNAME_IN_CITATION.findall(self.author_zone):
            if w not in NOT_A_SURNAME and w.lower() not in seen:
                seen.add(w.lower())
                names.append(w)
        return names

    def citation_keys(self) -> set[str]:
        """Keys a LaTeX-style citation might use for this entry."""
        year = self.year
        names = self.author_surnames
        if not year or not names:
            return set()
        short, full = year[-2:], year
        first = names[0].lower()
        initials = "".join(n[0] for n in names[:4]).lower()
        out = set()
        for y in (short, full):
            out |= {f"{first[:3]}{y}", f"{first}{y}", f"{initials}{y}",
                    f"{initials}+{y}"}
            if len(names) > 1:
                out.add(f"{first[:3]}{names[1][:3].lower()}{y}")
        return out

    @property
    def key(self) -> str:
        return re.sub(r"[^a-z0-9]", "", self.text.lower())[:90]


@dataclass
class NumericCitation:
    number: int
    para_index: int
    anchor: str


@dataclass
class NameCitation:
    surnames: set[str]
    year: str
    para_index: int
    anchor: str


@dataclass
class KeyCitation:
    key: str
    para_index: int
    anchor: str


@dataclass
class Citations:
    numeric: list[NumericCitation] = field(default_factory=list)
    named: list[NameCitation] = field(default_factory=list)
    keys: list[KeyCitation] = field(default_factory=list)
    notes: list[NameCitation] = field(default_factory=list)   # citations in footnotes

    def total(self) -> int:
        return len(self.numeric) + len(self.named) + len(self.keys) + len(self.notes)


def _expand(spec: str) -> list[int]:
    numbers, covered = [], []
    for m in RANGE_SPEC.finditer(spec):
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < b - a < 60:
            numbers.extend(range(a, b + 1))
            covered.append((m.start(), m.end()))
    for m in NUMBER_SPEC.finditer(spec):
        if not any(s <= m.start() < e for s, e in covered):
            numbers.append(int(m.group()))
    return numbers


def collect_entries(doc: Document) -> list[Entry]:
    entries: list[Entry] = []
    for p in doc.paragraphs:
        if p.section != REFERENCES or p.is_heading or len(p.text) < 25:
            continue
        m = LEADING_NUMBER.match(p.text)
        stated = int(m.group(1)) if m else None
        text = p.text[m.end():] if m else p.text
        if not (p.is_list_item or stated or YEAR.search(text) or "et al" in text.lower()):
            continue
        entries.append(Entry(len(entries) + 1, stated, text.strip(), p.index))
    return entries


def _is_body(p: Paragraph) -> bool:
    return (p.section in BODY_SECTIONS and not p.is_heading
            and not p.in_bibliography_field and p.section != REFERENCES)


def collect_citations(doc: Document) -> Citations:
    found = Citations()
    for p in doc.paragraphs:
        if not p.text or not _is_body(p):
            continue
        for m in BRACKETED.finditer(p.text):
            if m.group(0).startswith("(") and not re.fullmatch(r"[\d\s,;\u2013\u2014-]+",
                                                               m.group(1)):
                continue
            for n in _expand(m.group(1)):
                found.numeric.append(NumericCitation(n, p.index, m.group(0)))
        for a, b in p.superscript_spans:
            token = p.text[a:b]
            if re.fullmatch(r"[\d\s,;\u2013\u2014-]+", token) and any(c.isdigit() for c in token):
                for n in _expand(token):
                    found.numeric.append(NumericCitation(n, p.index, token))
        for m in CITATION_KEY.finditer(p.text):
            for part in re.split(r"[,;]", m.group(1)):
                part = part.strip()
                if part and any(c.isdigit() for c in part) and not part.isdigit():
                    found.keys.append(KeyCitation(part, p.index, m.group(0)))
        for m in list(PAREN_AUTHOR_YEAR.finditer(p.text)) + \
                list(BRACKET_AUTHOR_YEAR.finditer(p.text)):
            inside = m.group(1)
            for chunk in re.split(r";", inside):
                ym = YEAR.search(chunk)
                if not ym:
                    continue
                names = {w for w in SURNAME_IN_CITATION.findall(chunk)
                         if w not in NOT_A_SURNAME}
                if names:
                    found.named.append(NameCitation(names, ym.group(1), p.index,
                                                    m.group(0)[:60]))
        for m in NARRATIVE_AUTHOR_YEAR.finditer(p.text):
            if m.group(1) not in NOT_A_SURNAME:
                found.named.append(NameCitation({m.group(1)}, m.group(2), p.index,
                                                m.group(0)[:60]))
        for note_id in p.footnote_ids:
            note = doc.notes.get(note_id)
            if note is None:
                continue
            ym = YEAR.search(note.text)
            names = {w for w in SURNAME_IN_CITATION.findall(note.text[:160])
                     if w not in NOT_A_SURNAME}
            if ym and names:
                found.notes.append(NameCitation(names, ym.group(1), p.index,
                                                note.text[:60]))
    return found


def _dedupe_named(named: list[NameCitation]) -> list[NameCitation]:
    seen, out = set(), []
    for c in named:
        key = (frozenset(c.surnames), c.year, c.para_index)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def detect_style(entries: list[Entry], cites: Citations) -> str:
    """Return "numeric", "author_year", "key", "note", or "unknown".

    Anything that isn't clearly one of the supported styles returns "unknown",
    and the reference checks are skipped rather than guessed at: a wrong guess
    produces a page of false errors, while skipping only loses one check.
    """
    counts = {"numeric": len(cites.numeric), "author_year": len(cites.named),
              "key": len(cites.keys), "note": len(cites.notes)}
    best = max(counts, key=lambda k: counts[k])
    if counts[best] == 0:
        return "unknown"
    rest = sum(n for k, n in counts.items() if k != best)
    if counts[best] < 2 * max(1, rest) and rest > 2:
        return "unknown"          # styles are mixed; we can't tell which is real
    if best == "numeric":
        # Bracketed numbers are also used for units, p-values and equations.
        cited = {c.number for c in cites.numeric}
        limit = max([len(entries)] + [e.stated_number or 0 for e in entries])
        beyond = {n for n in cited if n > limit}
        # Brackets also hold units, p-values and equation numbers. If many
        # "citations" fall outside the list, they probably aren't citations.
        if limit and len(cited) >= 4 and len(beyond) > 0.5 * len(cited):
            return "unknown"
    if best in ("author_year", "key") and not any(e.year for e in entries):
        return "unknown"          # entries carry no years to match against
    return best


STYLE_NAMES = {"numbered": "numbered", "author_year": "author-year"}


def _check_style_matches_journal(style: str, profile) -> list[Issue]:
    """Compare the style the manuscript uses with the one the journal wants."""
    wanted = getattr(profile, "reference_style", None)
    if not wanted or style not in STYLE_NAMES:
        return []
    if style == wanted:
        return []
    return [Issue(CHECK, "warning",
                  f"{profile.name} expects {STYLE_NAMES[wanted]} citations, but "
                  f"this manuscript uses {STYLE_NAMES[style]} citations.",
                  None, None,
                  "Switch the style in your reference manager and re-check. "
                  "This changes both the in-text citations and the list.")]


def check_references(doc: Document, profile=None) -> list[Issue]:
    entries = collect_entries(doc)
    cites = collect_citations(doc)
    cites.named = _dedupe_named(cites.named)
    cites.notes = _dedupe_named(cites.notes)
    issues: list[Issue] = []

    if not entries:
        if cites.total():
            issues.append(Issue(CHECK, "info",
                                "No reference list was found, so citations couldn't be "
                                "matched to references."))
        return issues

    style = detect_style(entries, cites)
    if profile is not None:
        issues.extend(_check_style_matches_journal(
            {"numeric": "numbered", "author_year": "author_year",
             "key": "author_year", "note": "author_year"}.get(style, style),
            profile))
    if style == "numeric":
        issues.extend(_check_numeric(entries, cites.numeric))
    elif style == "author_year":
        issues.extend(_check_named(entries, cites.named))
    elif style == "note":
        issues.extend(_check_named(entries, cites.notes, source="footnotes"))
    elif style == "key":
        issues.extend(_check_keys(entries, cites.keys))
    elif cites.total() == 0:
        issues.append(Issue(CHECK, "info",
                            f"No citations were recognized in the text, so they "
                            f"weren't compared with the {len(entries)} reference "
                            f"entries. If the text does cite sources, its citation "
                            f"style may not be supported yet."))
    else:
        issues.append(Issue(CHECK, "info",
                            "Citation style wasn't recognized, so citations and "
                            "references weren't compared. Everything else was checked."))
    issues.extend(_check_entries(entries))
    if profile is not None:
        issues.extend(_check_entries_against_journal(entries, profile))
    return issues


def _check_entries_against_journal(entries: list[Entry], profile) -> list[Issue]:
    """Rules that only exist because a particular journal asks for them."""
    issues: list[Issue] = []

    limit = getattr(profile, "max_authors_listed", None)
    if limit:
        over = [e for e in entries
                if e.author_count and e.author_count > limit]
        if over:
            listed = ", ".join(str(e.number) for e in over[:12])
            more = f" and {len(over) - 12} more" if len(over) > 12 else ""
            issues.append(Issue(
                CHECK, "warning",
                f"{profile.name} lists at most {limit} authors before "
                f"\u201cet al.\u201d, but {len(over)} entries list more: "
                f"{listed}{more}.",
                over[0].para_index, over[0].text[:45],
                f"Set your reference manager to truncate after {limit} authors."))

    if getattr(profile, "require_doi", False):
        without = [e for e in entries if not DOI.search(e.text)]
        if without:
            listed = ", ".join(str(e.number) for e in without[:12])
            more = f" and {len(without) - 12} more" if len(without) > 12 else ""
            issues.append(Issue(
                CHECK, "warning",
                f"{profile.name} requires a DOI for every reference, but "
                f"{len(without)} entries have none: {listed}{more}.",
                without[0].para_index, without[0].text[:45],
                "Add the missing DOIs before submitting."))
    return issues


def _check_numeric(entries: list[Entry], cites: list[NumericCitation]) -> list[Issue]:
    issues: list[Issue] = []
    total = len(entries)
    by_number = {e.stated_number or e.number: e for e in entries}

    first: dict[int, NumericCitation] = {}
    for c in cites:
        first.setdefault(c.number, c)

    for n in sorted(first):
        if n not in by_number:
            c = first[n]
            issues.append(Issue(CHECK, "error",
                                f"Citation {n} has no matching reference "
                                f"(the list has {total} entries).",
                                c.para_index, c.anchor,
                                "Check the citation number or add the missing reference."))
    for n, entry in sorted(by_number.items()):
        if n not in first:
            issues.append(Issue(CHECK, "error",
                                f"Reference {n} is never cited in the text.",
                                entry.para_index, entry.text[:45],
                                "Cite it where it belongs, or remove it from the list."))

    # Numbered lists are normally ordered by first appearance in the text.
    ordered = sorted((c for c in first.values()), key=lambda c: (c.para_index,))
    out_of_order = []
    highest = 0
    for c in ordered:
        if c.number in by_number:
            if c.number < highest:
                out_of_order.append(c)
            highest = max(highest, c.number)
    if out_of_order and len(out_of_order) <= max(2, 0.2 * total):
        for c in out_of_order[:10]:
            issues.append(Issue(CHECK, "warning",
                                f"Reference {c.number} is first cited after a "
                                f"higher-numbered reference.",
                                c.para_index, c.anchor,
                                "Numbered reference lists usually follow the order of "
                                "first citation."))
    elif out_of_order:
        issues.append(Issue(CHECK, "info",
                            "References are not numbered in order of first citation "
                            "(normal for alphabetical reference lists)."))
    return issues


def _check_keys(entries: list[Entry], cites: list[KeyCitation]) -> list[Issue]:
    issues: list[Issue] = []
    keys_for: dict[int, set[str]] = {e.number: e.citation_keys() for e in entries}
    used: set[int] = set()
    seen_missing: set[str] = set()
    for c in cites:
        want = c.key.lower().replace("\u2019", "'")
        hits = [n for n, keys in keys_for.items() if want in keys]
        if hits:
            used.update(hits)
        elif want not in seen_missing:
            seen_missing.add(want)
            issues.append(Issue(CHECK, "error",
                                f"The citation key [{c.key}] has no matching entry in "
                                f"the reference list.",
                                c.para_index, c.anchor,
                                "Check the key, or add the missing reference."))
    for e in entries:
        if e.number not in used and keys_for[e.number]:
            issues.append(Issue(CHECK, "error",
                                f"This reference is never cited in the text: "
                                f"{e.text[:60]}\u2026",
                                e.para_index, e.text[:45],
                                "Cite it where it belongs, or remove it from the list."))
    return issues


def _check_named(entries: list[Entry], cites: list[NameCitation],
                 source: str = "text") -> list[Issue]:
    issues: list[Issue] = []
    by_year: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        if e.year:
            by_year[e.year].append(e)

    matched: set[int] = set()
    for c in cites:
        hits = [e for e in by_year.get(c.year, []) if e.surnames & c.surnames]
        if hits:
            matched.update(e.number for e in hits)
        else:
            name = sorted(c.surnames)[0]
            where = " in a footnote" if source == "footnotes" else ""
            issues.append(Issue(CHECK, "error",
                                f"The citation to {name} ({c.year}){where} has no "
                                f"matching entry in the reference list.",
                                c.para_index, c.anchor,
                                "Check the spelling and year, or add the reference."))
    for e in entries:
        if e.number not in matched:
            issues.append(Issue(CHECK, "error",
                                f"This reference is never cited in the text: "
                                f"{e.text[:60]}…",
                                e.para_index, e.text[:45],
                                "Cite it where it belongs, or remove it from the list."))
    return issues


def _check_entries(entries: list[Entry]) -> list[Issue]:
    issues: list[Issue] = []
    stated = [e for e in entries if e.stated_number is not None]
    if len(stated) > 1 and len(stated) >= 0.8 * len(entries):
        numbers = [e.stated_number for e in stated]
        for a, b in zip(numbers, numbers[1:]):
            if b == a:
                issues.append(Issue(CHECK, "warning",
                                    f"The reference list has two entries numbered {b}.",
                                    next(e.para_index for e in stated
                                         if e.stated_number == b)))
            elif b != a + 1:
                issues.append(Issue(CHECK, "warning",
                                    f"Reference numbering jumps from {a} to {b}.",
                                    next(e.para_index for e in stated
                                         if e.stated_number == b)))

    seen: dict[str, Entry] = {}
    for e in entries:
        if e.key in seen:
            issues.append(Issue(CHECK, "warning",
                                f"References {seen[e.key].number} and {e.number} look "
                                f"like the same entry.",
                                e.para_index, e.text[:45]))
        else:
            seen[e.key] = e

    incomplete = [e for e in entries if not e.has_authors]
    for e in incomplete[:8]:
        issues.append(Issue(CHECK, "warning",
                            f"Reference {e.number} has no author list: "
                            f"{e.first_sentence[:55]}\u2026",
                            e.para_index, e.text[:45],
                            "The entry starts with its title. Check that the authors "
                            "weren't lost when the reference was imported."))

    no_source = [e for e in entries
                 if e.has_authors and e.year and not HAS_SOURCE.search(e.text)]
    if no_source and len(no_source) <= max(3, 0.2 * len(entries)):
        for e in no_source[:6]:
            issues.append(Issue(CHECK, "warning",
                                f"Reference {e.number} has no journal, volume or DOI: "
                                f"{e.text[:55]}\u2026",
                                e.para_index, e.text[:45],
                                "The entry may have been truncated."))

    missing_year = [e for e in entries if not e.year]
    if missing_year and len(missing_year) <= max(3, 0.2 * len(entries)):
        for e in missing_year[:6]:
            issues.append(Issue(CHECK, "info",
                                f"Reference {e.number} has no year: {e.text[:55]}…",
                                e.para_index, e.text[:45]))

    # Missing DOIs are only worth raising when the list mostly has them: a
    # reference style that doesn't use DOIs at all is a choice, not an error.
    with_doi = [e for e in entries if DOI.search(e.text)]
    without = [e for e in entries if not DOI.search(e.text)]
    if len(with_doi) >= 0.5 * len(entries) and without:
        listed = ", ".join(str(e.number) for e in without[:12])
        more = f" and {len(without) - 12} more" if len(without) > 12 else ""
        issues.append(Issue(
            CHECK, "info",
            f"{len(with_doi)} of {len(entries)} references have a DOI, but these "
            f"don't: {listed}{more}.",
            without[0].para_index, without[0].text[:45],
            "Add the missing DOIs, or remove them all, so the list is consistent."))

    for e in entries:
        m = DOI.search(e.text)
        if m and not VALID_DOI.match(m.group(1).rstrip(".,;")):
            issues.append(Issue(CHECK, "warning",
                                f"Reference {e.number} has a DOI that looks malformed.",
                                e.para_index, m.group(1)[:45]))
    return issues
