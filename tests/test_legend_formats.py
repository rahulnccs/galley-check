"""Legend styles differ by journal; all of these must be recognized."""
import pytest

from galley.checks.offline.figures import LEGEND_RE, check_figures
from tests.test_repeat_citations import make_doc


@pytest.mark.parametrize("text", [
    "Figure 1. Study design.",
    "Figure 1: Study design.",
    "Figure 1 | Study design.",
    "Figure 1 - Study design.",
    "Figure 1 Study design and outcomes",
    "Fig. 1. Study design.",
    "Table 1: Baseline characteristics",
    "Supplementary Figure 3. Extra data.",
    "Supplementary Figure S3. Extra data.",
    "Supplementary Figure 1, related to Figure 1. Metabolic fate of MTX.",
    "Supplementary Figure 10, related to Figure 5. pMABG stool level varies.",
])
def test_recognized_legend_formats(text):
    assert LEGEND_RE.match(text)


@pytest.mark.parametrize("text", [
    "Fig. 8 extends the design shown in Fig. 1.",
    "Figure 2 shows the results clearly.",
    "Figure 3, however, was omitted from the analysis.",
    "Figures 1 and 2 together show the effect.",
])
def test_ordinary_sentences_are_not_legends(text):
    assert not LEGEND_RE.match(text)


def test_related_to_clause_is_not_a_callout():
    """'related to Figure 1' inside a legend must not count as citing Figure 1."""
    doc = make_doc([
        "Colonization altered PK (Supplementary Figure 2).",
        "Supplementary Figure 2, related to Figure 1. Liver enzyme expression.",
    ])
    msgs = [i.message for i in check_figures(doc)]
    assert not any("Figure 1" in m and "legend" in m for m in msgs)
