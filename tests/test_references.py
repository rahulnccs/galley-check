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
