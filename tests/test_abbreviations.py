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
        ("results", "We fitted a linear mixed-effects model (LMM) to the data."),
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
