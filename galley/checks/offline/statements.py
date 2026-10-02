"""Ethics and declaration statements.

Almost every journal now asks for the same short statements at the end of a
paper: data availability, competing interests, funding and author
contributions. They are easy to forget in a draft and are a common reason for
a manuscript to be sent back before review.

Ethics approval and informed consent are only needed for some studies, so
they are asked for only when the manuscript describes research with human
participants or with animals, and then the finding is a warning: a missing
ethics statement holds up a paper far longer than a missing funding line.

A statement counts as present if its wording appears anywhere outside the
reference list, whether as a heading ("Competing interests"), a run-in
heading, or a sentence ("The authors declare no competing interests.").

When a journal profile lists a statement as a required section, the
submission check already reports it as missing, so it is not repeated here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ...model.document import Document, Issue, Paragraph

CHECK = "statements"


@dataclass(frozen=True)
class Statement:
    key: str
    name: str                   # how the finding refers to it
    present: re.Pattern
    suggestion: str


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


STANDARD = [
    Statement(
        "data_availability", "data availability",
        _rx(r"\bdata (and (code|materials|software) )?(availability|accessibility|access)"
            r"|\bavailability of (data|materials)|\bdata sharing\b"
            r"|\bdata (are|is) (publicly |freely |openly )?available"
            r"|\bdata (that support|supporting) [^.]{0,80} (are|is) available"),
        "Add a short statement saying where the data can be found (a "
        "repository and accession number), or how to request it."),
    Statement(
        "competing_interests", "competing interests",
        _rx(r"\b(competing|conflicting) (financial )?interests?"
            r"|\bconflicts? of interests?|\bdeclarations? of interests?"
            r"|\bduality of interest|\bnothing to disclose|\bdisclosures?\b"),
        'Add a statement, even if it is only "The authors declare no '
        'competing interests."'),
    Statement(
        "funding", "funding",
        _rx(r"\bfunding\b|\bfunded by\b|\bfinancial support\b|\bfinancially supported\b"
            r"|\bsupported by\b[^.]{0,160}\b(grants?|foundation|council|fellowship"
            r"|award|programme|program)\b|\bgrant (no\.?|number|agreement)"),
        "Name the funders and grant numbers, or state that the work received "
        "no specific funding."),
    Statement(
        "author_contributions", "author contributions",
        _rx(r"\bauthors?'?s?’?s? contributions?|\bcontributions of (the )?authors"
            r"|\bCRediT\b|\bconceptuali[sz]ation\s*[:,]"
            r"|\b[A-Z]\.\s?[A-Z]\.?\s+(designed|performed|wrote|conceived)"),
        "Add a sentence or two on who did what, e.g. in CRediT roles."),
]

ETHICS = _rx(
    r"\bethic(s|al)\b[^.]{0,40}\b(committee|board|approval|review|clearance|permit"
    r"|statement|guidelines)|\bethics approval|\binstitutional review board"
    r"|\bIRB\b|\bIACUC\b|\banimal (care and use|ethics|welfare)"
    r"|\bdeclaration of helsinki|\bresearch ethics\b|\bhome office\b"
    r"|\bARRIVE\b|\bapproved by (the |an? )?[^.]{0,100}\b(committee|board)"
    r"|\bexempt(ed)? from (ethic|review|IRB)")
CONSENT = _rx(
    r"\b(informed|written|verbal|oral|parental) (informed )?consent"
    r"|\bconsent (was|were|had been) (obtained|given|waived|provided)"
    r"|\bwaiver of (informed )?consent|\bconsent to (participate|publication)"
    r"|\bconsented\b")
CODE_MENTIONED = _rx(
    r"\b(custom|in-house|bespoke)\s+(python |r |matlab )?(code|scripts?|software"
    r"|pipelines?|programs?)\b")
CODE_AVAILABILITY = _rx(
    r"\bcode (and data )?(availability|is available|are available|has been deposited)"
    r"|\b(code|scripts?|software)\b[^.]{0,120}\b(github|gitlab|zenodo|bitbucket"
    r"|figshare|available)|github\.com|gitlab\.com|zenodo")

# Research with people. "Donors" and "subjects" are left out: chemistry has
# electron donors, and "subjects" is too often ordinary prose.
HUMANS = _rx(r"\b(patients|participants|volunteers|respondents|interviewees"
             r"|human subjects|healthy controls)\b")
# Research with animals. Plural nouns only: antibodies are described with the
# singular ("mouse anti-GFP", "rabbit polyclonal").
ANIMALS = _rx(r"\b(mice|rats|zebrafish|macaques|primates|piglets|hamsters"
              r"|ferrets|rabbits|guinea pigs|animals)\b")
# Phrases where an animal word does not mean animal work.
ANIMAL_NOT_STUDIED = _rx(
    r"\b(raised|produced|generated) in (mice|rats|rabbits)|\banimals? models? "
    r"(of|for) [^.]*\b(have|has) been\b|\bin (previous|earlier|other) "
    r"(studies|work)")
MIN_MENTIONS = 2
STUDY_SECTIONS = {"abstract", "methods", "results"}


def _searchable(doc: Document) -> list[Paragraph]:
    return [p for p in doc.paragraphs
            if p.text and not doc.is_reference_paragraph(p)]


def _mentions(paras: list[Paragraph], rx: re.Pattern,
              exclude: re.Pattern | None = None) -> list[tuple[int, str]]:
    sections = {p.section for p in paras}
    if sections & STUDY_SECTIONS:
        paras = [p for p in paras if p.section in STUDY_SECTIONS]
    hits = []
    for p in paras:
        if exclude is not None and exclude.search(p.text):
            text = exclude.sub(" ", p.text)
        else:
            text = p.text
        hits += [(p.index, m.group(0)) for m in rx.finditer(text)]
    return hits


def _required_by_profile(profile, statement: Statement) -> bool:
    """True when the profile lists this statement as a required section, so
    the submission check already reports it."""
    if profile is None:
        return False
    for wanted in getattr(profile, "required_sections", []) or []:
        if statement.present.search(wanted):
            return True
    return False


def check_statements(doc: Document, profile=None) -> list[Issue]:
    paras = _searchable(doc)
    text = "\n".join(p.text for p in paras)
    issues: list[Issue] = []

    humans = _mentions(paras, HUMANS)
    animals = _mentions(paras, ANIMALS, ANIMAL_NOT_STUDIED)
    has_ethics = bool(ETHICS.search(text))

    def first(hits):
        return hits[0] if hits else (None, None)

    if len(humans) >= MIN_MENTIONS:
        para, word = first(humans)
        if not has_ethics:
            issues.append(Issue(
                CHECK, "warning",
                f'The manuscript describes research with people ("{word}" '
                f"appears {len(humans)} times), but no ethics approval "
                f"statement was found.",
                para, word,
                "Name the committee or review board that approved the study, "
                "with the approval number."))
        if not CONSENT.search(text):
            issues.append(Issue(
                CHECK, "warning",
                f'The manuscript describes research with people ("{word}" '
                f"appears {len(humans)} times), but doesn't say whether "
                f"informed consent was obtained.",
                para, word,
                "State that written informed consent was obtained, or that "
                "the committee waived it and why."))

    if len(animals) >= MIN_MENTIONS and not has_ethics:
        para, word = first(animals)
        issues.append(Issue(
            CHECK, "warning",
            f'The manuscript describes work with animals ("{word}" appears '
            f"{len(animals)} times), but no animal ethics approval statement "
            f"was found.",
            para, word,
            "Name the committee that approved the procedures (e.g. an IACUC, "
            "or the national licence), with the protocol number."))

    missing = [st for st in STANDARD
               if not st.present.search(text)
               and not _required_by_profile(profile, st)]
    if missing:
        names = [st.name for st in missing]
        listed = (names[0] if len(names) == 1
                  else ", ".join(names[:-1]) + " or " + names[-1])
        plural = "statement was" if len(names) == 1 else "statements were"
        issues.append(Issue(
            CHECK, "info",
            f"No {listed} {plural} found. Most journals ask for "
            f"{'one' if len(names) == 1 else 'these'}.",
            None, None, " ".join(st.suggestion for st in missing)))

    code = [(p.index, m.group(0)) for p in paras for m in CODE_MENTIONED.finditer(p.text)]
    if code and not CODE_AVAILABILITY.search(text):
        para, phrase = code[0]
        issues.append(Issue(
            CHECK, "info",
            f'The manuscript mentions "{phrase}" but doesn\'t say where the '
            f"code can be found.",
            para, phrase,
            "Add a code availability statement with a repository link "
            "(GitHub, plus an archived copy on Zenodo for a DOI)."))
    return issues
