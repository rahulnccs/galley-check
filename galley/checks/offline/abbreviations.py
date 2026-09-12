"""Abbreviation checks.

Journals ask that every abbreviation be spelled out at first use, defined only
once, and then actually used. This finds the definitions ("complex microbial
extract (CME)") and every later use, and reports:

  * an abbreviation used before it is defined
  * an abbreviation defined twice in the same part of the paper
  * an abbreviation defined but never used again, so the abbreviation is
    pointless
  * the same abbreviation defined with two different expansions
  * an abbreviation used repeatedly but never defined (reported as a note,
    since specialist terms are often left undefined on purpose)

The abstract and the main text are treated separately, because most journals
want an abbreviation defined once in each.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from ...model.document import Document, Issue, Paragraph

CHECK = "abbreviations"

# The body of the paper, where abbreviation rules apply.
ABSTRACT = {"abstract"}
NARRATIVE = {"introduction", "results", "discussion", "conclusions"}
METHODS = {"methods"}
# Methods often sit after the discussion, so an abbreviation defined there is
# not "defined late" — each zone is judged on its own.
ZONES = {"abstract": ABSTRACT, "main": NARRATIVE, "methods": METHODS}
ZONE_NAMES = {"abstract": "the abstract", "main": "the main text",
              "methods": "the methods"}

# "complex microbial extract (CME)" — up to seven words before the bracket.
# "complex microbial extracts (CME)" and also "germ-free (GF, N = 6)": authors
# often put sample sizes, units or settings in the same bracket as the
# abbreviation, and that is still a definition.
DEFINITION = re.compile(
    r"(?P<expansion>[A-Za-z][\w'\u2019/-]*(?:[ \u2010-][A-Za-z][\w'\u2019/-]*){0,6})"
    r"\s*[(\[](?P<abbr>[A-Za-z]?[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9-]{0,8})s?"
    r"(?P<extra>\s*[,;]\s*[^)\]]{0,45})?[)\]]")
# A use: at least two capitals, optionally with a leading lowercase (pMABG).
USE = re.compile(r"\b[a-z]?[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9-]{0,8}\b")

# Abbreviations journals don't require anyone to define.
STANDARD = {
    "DNA", "RNA", "cDNA", "mRNA", "rRNA", "tRNA", "PCR", "qPCR", "RTPCR", "ATP", "ADP",
    "NADH", "PBS", "EDTA", "DMSO", "BSA", "SDS", "HPLC", "LCMS", "GCMS", "NMR", "ELISA",
    "FACS", "OD", "UV", "IR", "PH", "SD", "SEM", "SE", "CI", "IQR", "ANOVA", "GLM",
    "AUC", "ROC", "PCA", "PCoA", "OTU", "ASV", "BMI", "MRI", "CT", "PET", "ECG", "ICU",
    "HIV", "AIDS", "SARS", "COVID", "TB", "US", "USA", "UK", "EU", "NIH", "NSF", "WHO",
    "FDA", "EMA", "CDC", "NCBI", "SRA", "EMBL", "NASA", "IRB", "IACUC", "PI", "CEO",
    "ID", "IT", "AI", "ML", "API", "CPU", "GPU", "RAM", "PDF", "HTML", "XML", "CSV",
    "URL", "ISBN", "DOI", "ORCID", "PMID", "PMCID", "SI", "MW", "RPM", "RCF", "CFU",
    "SPF", "WT", "KO", "IL", "TNF", "IFN", "LPS", "FBS", "PFA", "HE", "IHC", "FISH",
    # Strain, vendor and collection names — not abbreviations authors define.
    "BALB", "ATCC", "DSM", "DSMZ", "NCTC", "NCIMB", "JCM", "KCTC", "LB", "BL",
    # Statistics and buffers treated as standard by most journals.
    "FDR", "HEPES", "MOPS", "TAE", "TBE", "PBST", "TBS", "BH", "GLMM", "LMM",
}
# Words that look like abbreviations but aren't, in this context.
NOT_ABBREVIATIONS = {"FIGURE", "FIGURES", "TABLE", "TABLES", "AND", "THE", "OR", "IN",
                     "OF", "FOR", "WITH", "SUPPLEMENTARY", "EXTENDED", "DATA"}


@dataclass
class Mention:
    abbr: str
    para_index: int
    position: int
    zone: str                   # "abstract" | "main" | "methods"
    expansion: str | None = None    # only set when the initials matched
    context: str = ""               # the words before the bracket, for display


def _zone(p: Paragraph) -> str | None:
    for name, sections in ZONES.items():
        if p.section in sections:
            return name
    return None


STOPWORDS = {"of", "the", "and", "for", "in", "on", "to", "a", "an", "with", "by"}


def derive_expansion(words: str, abbr: str) -> str | None:
    """Return the phrase whose initials match the abbreviation, if there is one.

    "based on complex microbial extracts (CME)" -> "complex microbial extracts".
    Returns None when the initials don't line up, which means we can't be sure
    what the expansion is — those definitions are still counted, but their
    wording is never compared.
    """
    letters = [c.lower() for c in abbr if c.isalpha()]
    # A hyphenated term may contribute one letter ("mixed-effects" -> m) or two
    # ("CONV-D"), so both readings are tried.
    for pattern in (r"\s+", r"[\s\u2010-]+"):
        parts = [w for w in re.split(pattern, words) if w]
        for count in range(len(letters), min(len(letters) + 3, len(parts)) + 1):
            if count > len(parts):
                break
            phrase = parts[-count:]
            initials = [w[0].lower() for w in phrase if w.lower() not in STOPWORDS]
            if initials == letters:
                return " ".join(phrase)
    return None


def _normalize(abbr: str) -> str:
    return abbr.rstrip("s") if abbr.endswith("s") and abbr[:-1].isupper() else abbr


def _plausible(abbr: str, expansion: str) -> bool:
    """Keep definitions that could really be one, and drop coincidences."""
    if abbr.upper() in NOT_ABBREVIATIONS or len(abbr) < 2:
        return False
    if not expansion or expansion.split()[-1].upper() in NOT_ABBREVIATIONS:
        return False
    # An expansion should have at least as many words as the abbreviation has
    # capitals, or share its first letter — otherwise it's probably an aside.
    capitals = sum(1 for c in abbr if c.isupper())
    words = expansion.split()
    return len(words) >= min(2, capitals) or words[0][:1].lower() == abbr[:1].lower()


def collect(doc: Document) -> tuple[list[Mention], list[Mention]]:
    """Return (definitions, uses) across the body of the paper."""
    definitions: list[Mention] = []
    uses: list[Mention] = []
    for p in doc.paragraphs:
        zone = _zone(p)
        if zone is None or p.is_heading or not p.text:
            continue
        defined_spans: list[tuple[int, int]] = []
        for m in DEFINITION.finditer(p.text):
            abbr, expansion = _normalize(m.group("abbr")), m.group("expansion").strip()
            if not _plausible(abbr, expansion):
                continue
            derived = derive_expansion(expansion, abbr)
            if m.group("extra") and not derived:
                continue        # a vendor or address, not a definition
            definitions.append(Mention(abbr, p.index, m.start("abbr"), zone,
                                       derived, expansion))
            defined_spans.append(m.span("abbr"))
        for m in USE.finditer(p.text):
            abbr = _normalize(m.group())
            if abbr.upper() in NOT_ABBREVIATIONS or len(abbr) < 2:
                continue
            # Quoted names are software packages, genes or titles, not
            # abbreviations the author is expected to spell out.
            before = p.text[max(0, m.start() - 1):m.start()]
            after = p.text[m.end():m.end() + 1]
            if before in "'\u2018\u201c\"" and after in "'\u2019\u201d\"":
                continue
            if any(a <= m.start() < b for a, b in defined_spans):
                continue          # the definition itself, already recorded
            uses.append(Mention(abbr, p.index, m.start(), zone))
    return definitions, uses


def check_abbreviations(doc: Document) -> list[Issue]:
    definitions, uses = collect(doc)
    if not definitions and not uses:
        return []
    issues: list[Issue] = []

    defs_by_abbr: dict[str, list[Mention]] = defaultdict(list)
    for d in definitions:
        defs_by_abbr[d.abbr].append(d)
    uses_by_abbr: dict[str, list[Mention]] = defaultdict(list)
    for u in uses:
        uses_by_abbr[u.abbr].append(u)

    for abbr, defined in sorted(defs_by_abbr.items()):
        if abbr.upper() in STANDARD:
            continue          # nobody is required to define PBS or DNA
        defined.sort(key=lambda m: (m.para_index, m.position))
        used = sorted(uses_by_abbr.get(abbr, []), key=lambda m: (m.para_index, m.position))

        # 1. Used before it is defined anywhere in the paper.
        first_def = defined[0]
        early = [u for u in used
                 if (u.para_index, u.position) < (first_def.para_index,
                                                  first_def.position)]
        if early:
            issues.append(Issue(
                CHECK, "warning",
                f"{abbr} is used in {ZONE_NAMES[early[0].zone]} before it is "
                f"defined.",
                early[0].para_index, abbr,
                "Spell it out at the first use, then abbreviate."))

        # 2. Defined more than once in the same zone.
        for zone in ZONE_NAMES:
            # Only count definitions we are confident about, so a stray bracket
            # doesn't look like a second definition.
            repeats = [d for d in defined if d.zone == zone and d.expansion]
            if len(repeats) > 1:
                issues.append(Issue(
                    CHECK, "warning",
                    f"{abbr} is defined {len(repeats)} times in {ZONE_NAMES[zone]}.",
                    repeats[1].para_index, repeats[1].expansion,
                    "Define an abbreviation once, at its first use."))

        # 3. Defined with different expansions.
        spellings: dict[str, str] = {}
        for d in defined:
            if d.expansion:
                spellings.setdefault(d.expansion.lower().rstrip("s"), d.expansion)
        if len(spellings) > 1:
            issues.append(Issue(
                CHECK, "warning",
                f"{abbr} is spelled out differently in different places: "
                f"{'; '.join(sorted(spellings.values()))}.",
                defined[-1].para_index, defined[-1].expansion))

        # 4. Defined but never used again. Methods sections legitimately define
        # instrument settings and reagents that appear only once, so this is
        # only worth raising outside the methods, and only where the expansion
        # was confidently matched to the initials.
        confident = [d for d in defined if d.expansion and d.zone != "methods"]
        if not used and confident:
            issues.append(Issue(
                CHECK, "info",
                f"{abbr} is defined but never used again.",
                confident[0].para_index, abbr,
                "Either use the abbreviation or drop it and keep the full term."))

    # 5. Used repeatedly but never defined.
    # Only all-letter, all-capital tokens are reported as possibly undefined.
    # Strain and product names (C57BL, BALB, RefSeq, BioLabs) are not
    # abbreviations an author is expected to spell out, and flagging them
    # buries the real ones.
    undefined = [(abbr, mentions) for abbr, mentions in sorted(uses_by_abbr.items())
                 if abbr not in defs_by_abbr
                 and abbr.upper() not in STANDARD
                 and abbr.isupper() and abbr.isalpha()
                 and 3 <= len(abbr) <= 8     # initials like "RB" are usually people
                 and len(mentions) >= 3]
    for abbr, mentions in undefined[:5]:
        issues.append(Issue(
            CHECK, "info",
            f"{abbr} is used {len(mentions)} times but never defined.",
            mentions[0].para_index, abbr,
            "Spell it out at the first use, unless your journal treats it as standard."))
    return issues
