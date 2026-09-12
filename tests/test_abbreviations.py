"""Abbreviation checks."""
import pytest

from galley.checks.offline.abbreviations import check_abbreviations, derive_expansion
from galley.model.document import Document, Paragraph


def make_doc(sections):
    """sections: list of (section, text)."""
    return Document(path="t.docx", paragraphs=[
        Paragraph(index=i, text=t, style="Normal", section=s)
        for i, (s, t) in enumerate(sections)])


def messages(doc):
    return [(i.severity, i.message) for i in check_abbreviations(doc)]


def test_normal_use_is_silent():
    doc = make_doc([
        ("introduction", "We studied complex microbial extracts (CME) in worms."),
        ("results", "Each CME behaved consistently, and CME stocks were stable."),
    ])
    assert messages(doc) == []


def test_used_before_defined():
    doc = make_doc([
        ("introduction", "Worms were raised on CME throughout the experiment."),
        ("results", "We prepared complex microbial extracts (CME) from compost."),
        ("results", "CME samples were then sequenced."),
    ])
    assert any("used in the main text before it is defined" in m for _, m in messages(doc))


def test_defined_twice():
    doc = make_doc([
        ("results", "We used complex microbial extracts (CME) here."),
        ("results", "Again, complex microbial extracts (CME) were prepared."),
        ("results", "CME was stable."),
    ])
    assert any("defined 2 times" in m for _, m in messages(doc))


def test_inconsistent_expansion_is_caught():
    doc = make_doc([
        ("results", "We prepared complex microbial extracts (CME) from compost."),
        ("discussion", "Each compost microbial extract (CME) was stable over time."),
        ("discussion", "CME remains useful."),
    ])
    assert any("spelled out differently" in m for _, m in messages(doc))


def test_defined_but_never_used():
    doc = make_doc([
        ("results", "We measured the gut transit index (GTI) in each mouse."),
        ("results", "Diversity differed between groups."),
    ])
    assert any("never used again" in m for _, m in messages(doc))


def test_methods_only_definitions_are_not_nagged():
    """Methods define instrument settings used once; that isn't worth a note."""
    doc = make_doc([
        ("methods", "Spectra were acquired using a declustering potential (DP) of 80 V."),
        ("results", "Levels differed between groups."),
    ])
    assert not any("never used again" in m for _, m in messages(doc))


def test_abstract_and_main_text_are_separate_zones():
    """Redefining in the main text after the abstract is normal practice."""
    doc = make_doc([
        ("abstract", "We used complex microbial extracts (CME) in worms."),
        ("abstract", "CME was stable."),
        ("introduction", "Here we describe complex microbial extracts (CME)."),
        ("results", "CME stocks were stable."),
    ])
    assert not any("defined 2 times" in m for _, m in messages(doc))


@pytest.mark.parametrize("text", [
    "Diversity fell with age (Figure 2).",
    "The effect was significant (P < 0.05).",
    "Earlier work disagreed (Smith et al., 2019).",
    "Cells were grown in medium (see Methods).",
])
def test_ordinary_parentheses_are_not_definitions(text):
    doc = make_doc([("results", text), ("results", "A second sentence follows.")])
    assert messages(doc) == []


def test_standard_terms_are_left_alone():
    doc = make_doc([
        ("methods", "We extracted DNA and ran PCR on each sample."),
        ("results", "DNA yield was similar; PCR worked for all samples. DNA again."),
    ])
    assert messages(doc) == []


def test_strain_names_are_not_reported_as_undefined():
    doc = make_doc([
        ("methods", "We used BALB/c mice from ATCC."),
        ("methods", "BALB/c mice were housed together; ATCC strains were revived."),
        ("results", "BALB/c mice gained weight. ATCC strains grew well."),
    ])
    assert not any("never defined" in m for _, m in messages(doc))


def test_derive_expansion_matches_initials():
    assert derive_expansion("based on complex microbial extracts", "CME") == \
        "complex microbial extracts"
    assert derive_expansion("the mice were housed", "CME") is None


def test_definition_with_extra_content_in_the_bracket():
    """Authors often put a sample size or unit in the same bracket."""
    doc = make_doc([
        ("results", "We compared germ-free (GF, N = 6) and conventional mice."),
        ("results", "GF mice gained less weight than controls."),
    ])
    assert messages(doc) == []


def test_vendor_parenthetical_is_not_a_definition():
    """"(SCIEX, Framingham, MA)" is an address, not an abbreviation definition."""
    doc = make_doc([
        ("methods", "Samples were run on a Triple Quad (SCIEX, Framingham, MA)."),
        ("methods", "Peaks were integrated manually."),
    ])
    assert not any("SCIEX" in m for _, m in messages(doc))


def test_defined_early_and_reused_later_is_not_used_before_defined():
    """Defined in the results, used again in the methods: that is normal."""
    doc = make_doc([
        ("results", "Mice received vehicle control (VEH) by gavage."),
        ("methods", "VEH was prepared fresh each week."),
        ("methods", "Mice in the vehicle control (VEH) arm were housed together."),
    ])
    assert not any("before it is defined" in m for _, m in messages(doc))


def test_quoted_package_names_are_not_undefined_abbreviations():
    doc = make_doc([
        ("methods", "Areas were computed with the 'MESS' package in R."),
        ("methods", "The 'MESS' package was used again for AUC."),
        ("results", "Values from 'MESS' agreed with manual integration."),
    ])
    assert not any("MESS" in m for _, m in messages(doc))


def test_chemical_name_definition_with_a_numeric_prefix():
    """"6-methylpteridine-2,4-diamine (6-MPDA)" is a definition of MPDA."""
    doc = make_doc([
        ("abstract", "We found 6-methylpteridine-2,4-diamine (6-MPDA) in stool."),
        ("results", "Levels of 6-MPDA rose over time, and 6-MPDA tracked dose."),
    ])
    assert messages(doc) == []


def test_organization_abbreviations_are_left_alone():
    doc = make_doc([
        ("methods", "Mice were housed at UCSF before the study began."),
        ("methods", "Work was done at the University of California, San Francisco "
                    "(UCSF) barrier facility."),
    ])
    assert not any("UCSF" in m for _, m in messages(doc))


def test_instrument_terms_are_standard():
    doc = make_doc([
        ("methods", "Data were acquired by MRM on a QTRAP instrument."),
        ("methods", "MRM transitions were optimized; the QTRAP was calibrated."),
        ("results", "MRM signals were stable and the QTRAP performed well."),
    ])
    assert messages(doc) == []


def test_undefined_terms_are_one_note_not_many():
    doc = make_doc([
        ("methods", "Cells grew in BHI with CPG added; SKG mice were used."),
        ("methods", "BHI and CPG were prepared weekly for SKG mice."),
        ("results", "BHI cultures, CPG levels and SKG arthritis were measured."),
    ])
    notes = [m for sev, m in messages(doc) if sev == "info"]
    assert len(notes) == 1 and "never spelled out" in notes[0]


def test_duplicate_definition_names_both_places():
    doc = make_doc([
        ("results", "We used the gut transit index (GTI) throughout."),
        ("results", "Again, the gut transit index (GTI) was measured."),
        ("results", "GTI rose over time."),
    ])
    assert any("paragraph 1, paragraph 2" in m for _, m in messages(doc))


def test_definition_written_inside_the_bracket():
    """"(Analysis of similarities; ANOSIM)" defines ANOSIM."""
    doc = make_doc([
        ("results", "Groups differed (Analysis of similarities; ANOSIM, p = 0.001)."),
        ("results", "ANOSIM also separated the duodenal samples."),
    ])
    assert not any("ANOSIM" in m for _, m in messages(doc))


def test_supplier_names_are_not_undefined_abbreviations():
    doc = make_doc([
        ("methods", "DNA was extracted with the QIAGEN DNeasy kit (QIAGEN, Germany)."),
        ("methods", "QIAGEN buffers were used throughout."),
        ("results", "QIAGEN extractions gave consistent yields."),
    ])
    assert not any("QIAGEN" in m for _, m in messages(doc))
