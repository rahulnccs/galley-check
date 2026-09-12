"""Citation and reference-list checks, in both common styles."""
import pytest

from galley.checks.offline.references import check_references, collect_citations
from galley.model.document import Document, Paragraph


def make_doc(body, refs, superscripts=None):
    paras = [Paragraph(index=i, text=t, style="Normal", section="results")
             for i, t in enumerate(body)]
    for i, spans in (superscripts or {}).items():
        paras[i].superscript_spans = spans
    paras.append(Paragraph(index=len(paras), text="References", style="Heading 1",
                           section="references", is_heading=True))
    paras += [Paragraph(index=len(paras) + j, text=t, style="Normal", section="references")
              for j, t in enumerate(refs)]
    return Document(path="t.docx", paragraphs=paras)


REFS = ["1\tDoe J. A first paper. J Test 2019;1:1-10.",
        "2\tRoe S. A second paper. J Test 2020;2:11-20.",
        "3\tPoe A. A third paper. J Test 2021;3:21-30."]


def messages(doc):
    return [(i.severity, i.message) for i in check_references(doc)]


def test_all_cited_and_listed_is_clean():
    doc = make_doc(["First point [1]. Second point [2,3]."], REFS)
    assert messages(doc) == []


def test_citation_beyond_the_list():
    doc = make_doc(["A claim [1] and another [7]."], REFS)
    assert ("error", "Citation 7 has no matching reference (the list has 3 entries).") \
        in messages(doc)


def test_uncited_reference():
    doc = make_doc(["Only the first is used [1,2]."], REFS)
    assert ("error", "Reference 3 is never cited in the text.") in messages(doc)


def test_ranges_count_as_citations():
    doc = make_doc(["Everything at once [1-3]."], REFS)
    assert messages(doc) == []


def test_superscript_citations_are_read():
    doc = make_doc(["Prior work16,2 and more3.", ""],
                   REFS, superscripts={0: [(10, 14), (23, 24)]})
    cited = {c.number for c in collect_citations(doc).numeric}
    assert cited == {16, 2, 3}


def test_duplicate_entries_flagged():
    doc = make_doc(["Cited [1,2,3,4]."],
                   REFS + ["4\tDoe J. A first paper. J Test 2019;1:1-10."])
    assert any("look like the same entry" in m for _, m in messages(doc))


def test_numbering_gap_flagged():
    doc = make_doc(["Cited [1,2,5]."],
                   REFS[:2] + ["5\tPoe A. A third paper. J Test 2021;3:21-30."])
    assert any("numbering jumps from 2 to 5" in m for _, m in messages(doc))


def test_author_year_style():
    refs = ["Doe J. A first paper. J Test 2019;1:1-10.",
            "Roe S. A second paper. J Test 2020;2:11-20."]
    doc = make_doc(["As shown before (Doe, 2019), and later work by Roe (2020)."], refs)
    assert messages(doc) == []


def test_author_year_missing_entry():
    refs = ["Doe J. A first paper. J Test 2019;1:1-10."]
    doc = make_doc(["Earlier work (Smith et al., 2015) disagrees."], refs)
    assert any(m.startswith("The citation to Smith (2015)") for _, m in messages(doc))


@pytest.mark.parametrize("text", ["Figure 2 (2020) shows", "see Table 3 (2019)"])
def test_figure_mentions_are_not_author_year_citations(text):
    doc = make_doc([text], ["Doe J. A paper. J Test 2020;1:1."])
    assert not any("citation to Figure" in m or "citation to Table" in m
                   for _, m in messages(doc))


def test_entry_missing_its_author_list():
    """An entry that starts with its title lost the authors on import."""
    refs = ["1\tDoe J. A real paper. J Test 2019;1:1-10.",
            "2\tPopulation dynamics and habitat sharing of natural worm populations. "
            "BMC Biol 2012;10:1-19."]
    doc = make_doc(["Cited [1,2]."], refs)
    assert any(m.startswith("Reference 2 has no author list") for _, m in messages(doc))


def test_organization_and_software_entries_are_not_flagged():
    """"WHO." and "labdsv:" are legitimate entry openings, not lost authors."""
    refs = ["1\tWho. Selection and use of essential medicines. Geneva 2021;1:1-5.",
            "2\tlabdsv: Ordination and multivariate analysis for ecology, v2.1, 2025. "
            "doi:10.5281/zenodo.1",
            "3\tConsortium TC. Genome sequence of a nematode. Science 1998;282:2012-8."]
    doc = make_doc(["Cited [1,2,3]."], refs)
    assert not any("no author list" in m for _, m in messages(doc))


def test_entry_with_no_journal_or_doi():
    refs = ["1\tDoe J. A real paper. J Test 2019;1:1-10.",
            "2\tRoe S, Poe A et al. A truncated entry. Oxford Encyclopedia 2017,"]
    doc = make_doc(["Cited [1,2]."], refs)
    assert any("has no journal, volume or DOI" in m for _, m in messages(doc))


@pytest.mark.parametrize("entry", [
    "Doe J. A paper. Journal of Fictional Biology, 4, 1-12.",
    "Doe J. A paper. J Test 2019;1:1-10.",
    "Doe J. A paper. Nature 2020;580(7802):107.",
    "Doe J. A paper. bioRxiv 2024. doi:10.1101/2024.01.01.000001",
    "Doe J. A paper. J Test 2019. https://doi.org/10.1000/abc",
])
def test_complete_entries_are_not_flagged(entry):
    doc = make_doc(["Cited [1]."], [f"1\t{entry}"])
    assert not any("no journal" in m for _, m in messages(doc))


DOI_REFS = [f"{n}\tDoe J. Paper {n}. J Test 20{n:02d};1:1-10. doi:10.1000/test.{n}"
            for n in range(1, 5)]


def test_missing_dois_are_flagged_when_the_list_mostly_has_them():
    refs = DOI_REFS[:3] + ["4\tRoe S. A paper with no DOI. J Test 2021;2:5-9."]
    doc = make_doc(["Cited [1,2,3,4]."], refs)
    assert any("but these don't: 4" in m for _, m in messages(doc))


def test_no_doi_anywhere_is_a_style_choice_not_an_error():
    refs = [f"{n}\tDoe J. Paper {n}. J Test 2019;1:{n}-10." for n in range(1, 5)]
    doc = make_doc(["Cited [1,2,3,4]."], refs)
    assert not any("DOI" in m for _, m in messages(doc))


def test_complete_doi_coverage_is_silent():
    doc = make_doc(["Cited [1,2,3,4]."], DOI_REFS)
    assert not any("DOI" in m for _, m in messages(doc))
