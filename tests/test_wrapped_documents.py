"""Documents where every printed line is its own paragraph.

Files converted from PDF, and some journal templates, put a hard line break at
the end of each line. That splits citations, reference entries and figure
legends across paragraphs, and Galley used to report all three as errors.
"""
from galley.checks.offline.figures import find_callouts_and_legends
from galley.checks.offline.references import (
    check_references, collect_citations, collect_entries)
from galley.model.document import Document, Paragraph


def make_doc(rows):
    """rows: (section, text)."""
    return Document(path="t.docx", paragraphs=[
        Paragraph(index=i, text=t, style="Normal", section=s)
        for i, (s, t) in enumerate(rows)])


WRAPPED_REFS = [
    ("references", "Trizna, E.Y., Yarullina, M.N., Baidamshina, D.R., Mironova, A.V.,"),
    ("references", "Rozhina, E.V., Fakhrullin, R.F., Bogachev, M.I. &"),
    ("references", "Kayumov, A.R., (2020) \u201cBidirectional alterations in antibiotics"),
    ("references", "susceptibility in dual-species biofilm.\u201d Sci Rep. 10:14849"),
    ("references", "https://doi.org/10.1038/s41598-020-71834-w."),
]


def test_entry_split_over_five_lines_is_one_reference():
    doc = make_doc([("introduction", "Models differ (Trizna et al., 2020).")]
                   + WRAPPED_REFS)
    entries = collect_entries(doc)
    assert len(entries) == 1
    assert entries[0].year == "2020"
    assert "Kayumov" in entries[0].surnames


def test_citation_split_over_a_line_break_is_found():
    doc = make_doc([
        ("introduction", "Tolerance is increased ( Kulshrestha &"),
        ("introduction", "Gupta 2022 ; Filkins & O'Toole, 2015)."),
        ("references", "Kulshrestha, A. & Gupta, P. (2022) \u201cPolymicrobial "
                       "interaction.\u201d J Test 12:1-9."),
        ("references", "Filkins, L.M. & O'Toole, G.A. (2015) \u201cCystic fibrosis "
                       "lung infections.\u201d PLoS Path 11:1-5."),
    ])
    cites = collect_citations(doc)
    names = {n for c in cites.named for n in c.surnames}
    assert "Kulshrestha" in names and "Filkins" in names
    assert not [i for i in check_references(doc) if i.severity == "error"]


def test_a_line_holding_only_a_doi_continues_the_entry():
    doc = make_doc([
        ("introduction", "As reported (Doe et al., 2019)."),
        ("references", "Doe, J., Roe, S. (2019) \u201cA paper.\u201d J Test 1:1-10"),
        ("references", "https://doi.org/10.1000/test.1"),
        ("references", "Poe, A. (2021) \u201cAnother paper.\u201d J Test 3:1-9."),
    ])
    entries = collect_entries(doc)
    assert len(entries) == 2
    assert "10.1000/test.1" in entries[0].text


def test_legend_panels_split_across_lines_are_all_seen():
    doc = make_doc([
        ("results", "Survival differed (Fig. 6B) and again (Fig. 6D)."),
        ("figure_legends", "Fig.6: Cytotoxicity and in vivo efficacy."),
        ("figure_legends", "(A) Cytotoxic effects on HDFa cells by MTT assay."),
        ("figure_legends", "(B, C) Survival curves for infected worms treated "
                           "with GV-13 or VR-10."),
        ("figure_legends", "(D) Bacterial load in surviving worms after "
                           "treatment."),
    ])
    _, legends = find_callouts_and_legends(doc)
    assert legends and {"A", "B", "C", "D"} <= legends[0].panels


def test_ordinary_text_after_a_legend_is_not_absorbed():
    """Only a line opening with a panel marker counts as a continuation."""
    doc = make_doc([
        ("results", "Diversity fell (Figure 1A)."),
        ("figure_legends", "Figure 1. Study design."),
        ("figure_legends", "We thank the sequencing core for their help."),
    ])
    _, legends = find_callouts_and_legends(doc)
    assert "thank" not in legends[0].text


def test_phone_numbers_are_not_citations():
    doc = make_doc([
        ("front_matter", "Correspondence: Telephone: (415) 221-4810."),
        ("results", "As shown before [1]."),
        ("references", "1\tDoe J. A paper. J Test 2019;1:1-10."),
    ])
    messages = [i.message for i in check_references(doc)]
    assert not any("415" in m for m in messages)
