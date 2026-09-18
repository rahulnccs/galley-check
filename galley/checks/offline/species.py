"""Species name formatting checks.

Journals are strict about binomial names, and authors are inconsistent about
them, especially after a manuscript has been through several rounds of edits.
This looks for:

  * a species name italicized in some places and not others
  * a genus abbreviated ("C. elegans") before it has been spelled out in full
  * the same genus abbreviated to different letters, or spelled out repeatedly
    after the first mention
  * "sp." and "spp." used inconsistently, or italicized (they should not be)
  * a genus name written in lower case

Only names that look like binomials are considered: a capitalized genus of at
least four letters followed by a lower-case species epithet. Common phrases
that share that shape ("Data availability", "Table legends") are excluded by
requiring the epithet to be a plausible Latin word and by a stop list.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ...model.document import REFERENCES, Document, Issue, Paragraph

CHECK = "species"

# "Escherichia coli", "C. elegans", "E. coli str. K-12"
BINOMIAL = re.compile(
    r"(?<![\w.])(?P<genus>[A-Z][a-z]{3,})\s+(?P<epithet>[a-z]{3,})(?![\w-])")
ABBREVIATED = re.compile(
    r"(?<![\w.])(?P<initial>[A-Z])\.\s*(?P<epithet>[a-z]{3,})(?![\w-])")
SP_FORM = re.compile(r"(?<![\w.])(?P<genus>[A-Z][a-z]{3,})\s+(?P<form>spp?\.)")
LOWER_GENUS_TEMPLATE = r"(?<![\w.])({genus})\s+({epithet})(?![\w-])"

# Word pairs that look like a binomial but are not.
NOT_SPECIES_GENUS = {
    "Table", "Figure", "Data", "Supplementary", "Extended", "Materials",
    "Methods", "Results", "Discussion", "Introduction", "Abstract", "Author",
    "Authors", "Competing", "Funding", "Ethics", "Statistical", "Sample",
    "Samples", "Total", "Mean", "Median", "These", "Those", "There", "Their",
    "This", "That", "While", "Where", "When", "Which", "After", "Before",
    "Both", "Each", "Here", "However", "Together", "Overall", "Although",
    "Because", "Since", "Thus", "Therefore", "Finally", "Briefly", "First",
    "Second", "Third", "Next", "Then", "Using", "Given", "Based", "Among",
    "Between", "During", "Following", "Fisher", "Wilcoxon", "Kruskal",
    "Benjamini", "Shannon", "Bray", "Student", "Type", "Cell", "Cells",
    "Mouse", "Mice", "Human", "Gene", "Genes", "Protein", "Proteins",
    "Standard", "Principal", "Linear", "Relative", "All", "Some", "Most",
}
# Epithets that are ordinary English words; a pair is only a binomial if the
# genus is not in the stop list above, so this is a second safety net.
NOT_EPITHET = {
    "and", "the", "for", "with", "from", "were", "was", "are", "has", "had",
    "not", "but", "all", "may", "can", "did", "does", "into", "than", "that",
    "this", "these", "those", "which", "who", "how", "why", "when", "where",
    "used", "using", "shown", "showed", "found", "data", "levels", "samples",
    # Ordinary English words that follow a capitalized word in prose and in
    # taxonomic writing: "Enterobacteriaceae bloom", "Beta diversity".
    "family", "families", "genus", "genera", "species", "strain", "strains",
    "isolate", "isolates", "culture", "cultures", "abundance", "abundances",
    "bloom", "blooms", "load", "loads", "level", "counts", "count", "over",
    "bacteria", "bacterium", "bacterial", "diversity", "richness", "evenness",
    "group", "groups", "type", "types", "soil", "gut", "plate", "plates",
    "bar", "bars", "plot", "plots", "sample", "analysis", "analyses", "index",
    "indices", "distance", "distances", "sequences", "sequencing", "reads",
    "relative", "total", "mean", "median", "average", "control", "controls",
    "treatment", "media", "medium", "broth", "agar", "stock", "stocks",
}
# Higher taxa are not binomials: "Enterobacteriaceae", "Clostridiales".
HIGHER_TAXON = re.compile(r"(aceae|ales|idae|inae|ineae|mycota|phyta)$")
BODY_SECTIONS = {"abstract", "introduction", "methods", "results", "discussion",
                 "conclusions", "supplementary", "figure_legends"}
MIN_MENTIONS_FOR_ITALIC_CHECK = 2


@dataclass
class Mention:
    name: str                   # "Escherichia coli"
    genus: str
    epithet: str
    para_index: int
    position: int
    text: str                   # as written, e.g. "E. coli"
    italic: bool | None         # None when the run's formatting is unknown
    abbreviated: bool


@dataclass
class Species:
    genus: str
    epithet: str
    mentions: list[Mention] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.genus} {self.epithet}"


def _body(doc: Document) -> list[Paragraph]:
    return [p for p in doc.paragraphs
            if p.text and not p.is_heading and p.section in BODY_SECTIONS
            and p.section != REFERENCES and not p.in_bibliography_field]


def _is_italic(p: Paragraph, start: int, end: int) -> bool:
    """Whether the span is italic, using the spans the parser recorded."""
    covered = 0
    for a, b in p.italic_spans:
        covered += max(0, min(b, end) - max(a, start))
    length = max(1, end - start)
    return covered / length > 0.6


def collect(doc: Document) -> dict[str, Species]:
    """Every binomial mention, keyed by "Genus epithet".

    A capitalized word followed by a lower-case word is far too common in
    ordinary prose ("Alpha diversity", "Taken together") to treat as a species
    on shape alone. A candidate is only kept when the manuscript itself gives
    evidence that it is a binomial: it is italicized somewhere, or it is
    written in abbreviated form ("C. elegans") somewhere, or its genus appears
    with "sp." or "spp.".
    """
    candidates: dict[str, Species] = {}
    full: dict[str, str] = {}           # initial -> genus, from full mentions

    paragraphs = _body(doc)
    for p in paragraphs:
        for m in BINOMIAL.finditer(p.text):
            genus, epithet = m.group("genus"), m.group("epithet")
            if (genus in NOT_SPECIES_GENUS or epithet in NOT_EPITHET
                    or HIGHER_TAXON.search(genus)):
                continue
            key = f"{genus} {epithet}"
            candidates.setdefault(key, Species(genus, epithet)).mentions.append(
                Mention(key, genus, epithet, p.index, m.start(), m.group(0),
                        _is_italic(p, m.start(), m.end()), abbreviated=False))
            full.setdefault(genus[0], genus)

    # Evidence 1: an abbreviated form appears somewhere.
    abbreviated_keys: set[str] = set()
    for p in paragraphs:
        for m in ABBREVIATED.finditer(p.text):
            genus = full.get(m.group("initial"))
            if genus:
                abbreviated_keys.add(f"{genus} {m.group('epithet')}")
    # Evidence 2: the genus is used with sp./spp. somewhere.
    sp_genera = {m.group("genus") for p in paragraphs
                 for m in SP_FORM.finditer(p.text)}

    found = {}
    for key, species in candidates.items():
        italic_somewhere = any(m.italic for m in species.mentions)
        if (italic_somewhere or key in abbreviated_keys
                or species.genus in sp_genera):
            found[key] = species

    # Abbreviated mentions are matched to a full genus seen anywhere in the text.
    # (Only for names that passed the evidence test above.)
    for p in paragraphs:
        for m in ABBREVIATED.finditer(p.text):
            genus = full.get(m.group("initial"))
            if genus is None:
                continue
            epithet = m.group("epithet")
            key = f"{genus} {epithet}"
            if key not in found:
                continue                # "E. coli" with no "Escherichia coli" anywhere
            found[key].mentions.append(
                Mention(key, genus, epithet, p.index, m.start(), m.group(0),
                        _is_italic(p, m.start(), m.end()), abbreviated=True))

    for s in found.values():
        s.mentions.sort(key=lambda m: (m.para_index, m.position))
    return found


def check_species(doc: Document) -> list[Issue]:
    found = collect(doc)
    issues: list[Issue] = []
    paragraphs = _body(doc)

    for key, species in sorted(found.items()):
        mentions = species.mentions
        first = mentions[0]

        # 1. Italicized in some places but not others.
        known = [m for m in mentions if m.italic is not None]
        if len(known) >= MIN_MENTIONS_FOR_ITALIC_CHECK:
            plain = [m for m in known if not m.italic]
            italic = [m for m in known if m.italic]
            if plain and italic:
                issues.append(Issue(
                    CHECK, "warning",
                    f"{key} is italicized in {len(italic)} place"
                    f"{'s' if len(italic) != 1 else ''} and not in "
                    f"{len(plain)}.",
                    plain[0].para_index, plain[0].text,
                    "Species names should be italicized throughout."))
            elif plain and not italic:
                issues.append(Issue(
                    CHECK, "warning",
                    f"{key} is never italicized.",
                    plain[0].para_index, plain[0].text,
                    "Most journals require binomial names in italics."))

        # 2. Abbreviated before the genus is spelled out.
        if first.abbreviated:
            spelled = next((m for m in mentions if not m.abbreviated), None)
            where = (f" It is spelled out later, in paragraph "
                     f"{spelled.para_index + 1}." if spelled else "")
            issues.append(Issue(
                CHECK, "warning",
                f"{first.text} is abbreviated before {species.genus} is spelled "
                f"out in full.{where}",
                first.para_index, first.text,
                f"Give the full name at first use, then abbreviate."))

        # 3. Spelled out again after the first mention.
        elif len(mentions) > 1:
            later_full = [m for m in mentions[1:] if not m.abbreviated]
            if later_full and len(later_full) < len(mentions) - 1:
                issues.append(Issue(
                    CHECK, "info",
                    f"{key} is written out in full again after the first "
                    f"mention, in {len(later_full)} place"
                    f"{'s' if len(later_full) != 1 else ''}, while elsewhere it "
                    f"is abbreviated.",
                    later_full[0].para_index, later_full[0].text,
                    f"Journals usually expect {species.genus[0]}. "
                    f"{species.epithet} after the first use."))

    # 4. sp. / spp. usage.
    forms: dict[str, set[str]] = defaultdict(set)
    first_form: dict[str, tuple[int, str]] = {}
    for p in paragraphs:
        for m in SP_FORM.finditer(p.text):
            genus = m.group("genus")
            if genus in NOT_SPECIES_GENUS:
                continue
            forms[genus].add(m.group("form"))
            first_form.setdefault(genus, (p.index, m.group(0)))
    for genus, used in sorted(forms.items()):
        if len(used) > 1:
            para, text = first_form[genus]
            issues.append(Issue(
                CHECK, "info",
                f"{genus} is followed by both \u201csp.\u201d and \u201cspp.\u201d "
                f"in different places.",
                para, text,
                "\u201csp.\u201d is one unnamed species, \u201cspp.\u201d is "
                "several. Neither is italicized."))

    # 5. A known genus written in lower case.
    for key, species in sorted(found.items()):
        pattern = re.compile(LOWER_GENUS_TEMPLATE.format(
            genus=species.genus.lower(), epithet=species.epithet))
        for p in paragraphs:
            m = pattern.search(p.text)
            if m and not p.text[:m.start()].rstrip().endswith((".", "!", "?")):
                issues.append(Issue(
                    CHECK, "warning",
                    f"{key} appears in lower case as \u201c{m.group(0)}\u201d.",
                    p.index, m.group(0),
                    "The genus takes a capital letter; the epithet does not."))
                break
    return issues
