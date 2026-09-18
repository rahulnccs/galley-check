"""Species name formatting checks."""
import pytest

from galley.checks.offline.species import check_species, collect
from galley.model.document import Document, Paragraph


def make_doc(rows):
    """rows: (section, text, [italic spans]) — spans are (start, end) pairs."""
    paras = []
    for i, row in enumerate(rows):
        section, text = row[0], row[1]
        spans = row[2] if len(row) > 2 else []
        p = Paragraph(index=i, text=text, style="Normal", section=section)
        p.italic_spans = spans
        paras.append(p)
    return Document(path="t.docx", paragraphs=paras)


def messages(doc):
    return [(i.severity, i.message) for i in check_species(doc)]


def span(text, phrase):
    at = text.index(phrase)
    return (at, at + len(phrase))


def test_consistently_italicized_is_silent():
    t1 = "We studied Caenorhabditis elegans in compost."
    t2 = "Each C. elegans population was scored weekly."
    doc = make_doc([("results", t1, [span(t1, "Caenorhabditis elegans")]),
                    ("results", t2, [span(t2, "C. elegans")])])
    assert messages(doc) == []


def test_mixed_italics_flagged():
    t1 = "We studied Caenorhabditis elegans in compost."
    t2 = "Each C. elegans population was scored weekly."
    doc = make_doc([("results", t1, [span(t1, "Caenorhabditis elegans")]),
                    ("results", t2, [])])
    assert any("italicized in 1 place and not in 1" in m for _, m in messages(doc))


def test_abbreviated_before_spelled_out():
    t1 = "Worms of C. elegans were raised on compost extracts."
    t2 = "Caenorhabditis elegans is a standard model organism."
    doc = make_doc([("results", t1, [span(t1, "C. elegans")]),
                    ("results", t2, [span(t2, "Caenorhabditis elegans")])])
    assert any("abbreviated before Caenorhabditis is spelled out" in m
               for _, m in messages(doc))


@pytest.mark.parametrize("phrase", [
    "Alpha diversity was similar between groups.",
    "Taken together, these data suggest a role for diet.",
    "Beta diversity differed between sites.",
    "Stacked bar plots show genus composition.",
    "Differential abundance was computed per sample.",
])
def test_ordinary_prose_is_not_a_species(phrase):
    doc = make_doc([("results", phrase), ("results", phrase)])
    assert collect(doc) == {}


@pytest.mark.parametrize("phrase", [
    "Enterobacteriaceae bloom followed the disturbance.",
    "The Clostridiaceae family dominated late samples.",
    "Pseudomonadaceae bacteria were enriched in worms.",
])
def test_higher_taxa_are_not_binomials(phrase):
    doc = make_doc([("results", phrase, [(0, 20)])])
    assert collect(doc) == {}


def test_sp_and_spp_mixed():
    t = "We isolated Pseudomonas sp. from soil and Pseudomonas spp. from worms."
    doc = make_doc([("results", t, [span(t, "Pseudomonas sp.")])])
    assert any("both" in m and "spp." in m for _, m in messages(doc))


def test_lower_case_genus():
    t1 = "Cultures of Clostridium sporogenes were grown anaerobically."
    t2 = "Colonies of clostridium sporogenes appeared after two days."
    doc = make_doc([("results", t1, [span(t1, "Clostridium sporogenes")]),
                    ("results", t2, [])])
    assert any("lower case" in m for _, m in messages(doc))


def test_italic_detection_uses_recorded_spans():
    t = "The strain Bacteroides ovatus was used throughout the study."
    doc = make_doc([("results", t, [span(t, "Bacteroides ovatus")])])
    found = collect(doc)
    assert found["Bacteroides ovatus"].mentions[0].italic is True
