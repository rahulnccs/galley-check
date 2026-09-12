from pathlib import Path

import pytest

from galley.engine import load, run_checks
from tests.fixtures.make_sample import build

FIXTURE = Path(__file__).parent / "fixtures" / "sample_manuscript.docx"


@pytest.fixture(scope="module")
def doc():
    build(FIXTURE)
    return load(FIXTURE)


@pytest.fixture(scope="module")
def messages(doc):
    return {(i.severity, i.message) for i in run_checks(doc)}


def test_reference_manager_citations_detected(doc):
    assert sorted(c.source for c in doc.citations) == ["endnote", "mendeley", "zotero"]
    assert {c.text for c in doc.citations} == {"(Doe et al., 2021)", "(Roe et al., 2019)",
                                               "(Poe, 2020)"}


def test_field_codes_hidden_from_text(doc):
    intro = next(p for p in doc.paragraphs if "immune responses" in p.text)
    assert "ZOTERO" not in intro.text and "(Doe et al., 2021)" in intro.text


def test_tracked_changes(doc):
    p = next(p for p in doc.paragraphs if p.text.startswith("Weight loss"))
    assert "Fig. 2B" in p.text          # insertion kept
    assert "Fig. 6" not in p.text       # deletion dropped


def test_sections_assigned(doc):
    sections = {p.section for p in doc.paragraphs}
    assert {"abstract", "introduction", "results", "discussion",
            "references", "figure_legends"} <= sections


@pytest.mark.parametrize("expected", [
    ("error", "Figure 5 is cited in the text but has no legend."),
    ("error", "Table 2 is cited in the text but has no caption."),
    ("error", "Figure 4 has a legend but is never cited in the text."),
    ("error", "Supplementary Figure S2 has a legend but is never cited in the text."),
    ("warning", "Figure 2 is first cited before Figure 1."),
    ("warning", "Figure 3D is cited, but the legend only describes panels A, B and C."),
])
def test_deliberate_errors_found(messages, expected):
    assert expected in messages


def test_no_false_errors(messages):
    errors = {m for s, m in messages if s == "error"}
    assert len(errors) == 4
    assert not any("Figure 6" in m for s, m in messages)
