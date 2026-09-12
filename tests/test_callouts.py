import pytest

from galley.checks.offline.figures import CALLOUT_RE, parse_spec


def callouts(text):
    return [(m.group(0), parse_spec(m.group("spec"))) for m in CALLOUT_RE.finditer(text)]


@pytest.mark.parametrize("spec, expected", [
    ("1", {"1": set()}),
    ("2A", {"2": {"A"}}),
    ("1A\u2013C", {"1": {"A", "B", "C"}}),
    ("1a,b", {"1": {"A", "B"}}),
    ("1\u20133", {"1": set(), "2": set(), "3": set()}),
    ("1 and 2", {"1": set(), "2": set()}),
    ("2B, 3C", {"2": {"B"}, "3": {"C"}}),
    ("S1\u2013S3", {"S1": set(), "S2": set(), "S3": set()}),
    ("3A, B and D", {"3": {"A", "B", "D"}}),
])
def test_parse_spec(spec, expected):
    assert parse_spec(spec) == expected


def test_finds_supplementary_and_extended():
    found = [m.group("prefix") for m in CALLOUT_RE.finditer(
        "see Supplementary Fig. S2 and Extended Data Fig. 4")]
    assert [p.strip() for p in found] == ["Supplementary", "Extended Data"]


def test_ignores_words_containing_fig_or_table():
    assert callouts("We configured 3 comfortable tables of 4 samples.") == []


def test_stray_lowercase_letter_not_a_panel():
    [(_, spec)] = callouts("as in Fig. 2 and a second cohort")
    assert spec == {"2": set()}


@pytest.mark.parametrize("text, prefix", [
    ("Supp. Fig. 1", "Supp."),
    ("Supp Fig 2", "Supp"),
    ("Suppl. Figure S3", "Suppl."),
    ("Supplemental Fig. 4", "Supplemental"),
    ("Supplementary Table 1", "Supplementary"),
    ("Extended Data Fig. 4", "Extended Data"),
    ("Fig. 2A and B", ""),
])
def test_supplementary_abbreviations(text, prefix):
    m = CALLOUT_RE.search(text)
    assert (m.group("prefix") or "").strip() == prefix


def test_supp_figure_is_not_counted_as_main_figure():
    from galley.checks.offline.figures import check_figures
    from tests.test_repeat_citations import make_doc
    doc = make_doc(["Shown in Fig. 1 and Supp. Fig. 1.", "Figure 1. Main legend."])
    msgs = [i.message for i in check_figures(doc)]
    assert "Figure 1 is cited in the text but has no legend." not in msgs
