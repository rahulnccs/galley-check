"""Consistency checks: units, micro signs, spelling, numerals at sentence start."""
import pytest

from galley.checks.offline.consistency import check_consistency
from galley.model.document import Document, Paragraph


def make_doc(rows):
    """rows: (section, text) pairs."""
    paras = [Paragraph(index=i, text=text, style="Normal", section=section)
             for i, (section, text) in enumerate(rows)]
    return Document(path="t.docx", paragraphs=paras)


def messages(rows):
    return [(i.severity, i.message) for i in check_consistency(make_doc(rows))]


def test_consistent_manuscript_is_silent():
    assert messages([
        ("methods", "Cells were treated with 5 mg of drug for 24 h at 37 °C."),
        ("methods", "Then 10 mL of buffer and 2 µL of dye were added."),
        ("results", "The tumor shrank and the color changed."),
    ]) == []


def test_unit_spacing_mixed():
    msgs = messages([
        ("methods", "Add 5 mg of drug, then 10 mg more, then 2 mg."),
        ("methods", "Finally add 3mg."),
    ])
    assert any('"mg" is written with a space' in m and '"3mg"' in m
               for _, m in msgs)


def test_each_unit_judged_on_its_own():
    # A journal may write "37°C" but "5 mg"; that's a style, not a mix.
    assert messages([
        ("methods", "Incubate at 37°C with 5 mg of drug, then at 4°C with 2 mg."),
    ]) == []


def test_litre_capitalization_mixed():
    msgs = messages([
        ("methods", "Add 10 mL of medium and 5 mL of serum."),
        ("methods", "Wash with 2 ml of PBS."),
    ])
    assert any('written "ml" once but "mL" 2 times' in m for _, m in msgs)


def test_millimolar_and_millimetre_are_different_units():
    assert messages([
        ("methods", "Use 5 mM Tris on a 10 mm dish with 2 mM EDTA."),
    ]) == []


def test_figure_panels_are_not_grams_or_hours():
    assert messages([
        ("results", "Growth stopped after 24 h (Fig. 2h) and mass fell to 5 g (Fig. 3g)."),
    ]) == []


def test_u_used_for_micro():
    msgs = messages([("methods", "Add 5 uL of enzyme.")])
    assert any('"u" is used in place of the micro sign' in m for _, m in msgs)


def test_two_micro_signs():
    msgs = messages([("methods", "Add 5 µL of enzyme and 2 μL of dye.")])
    assert any("Two different micro signs" in m for _, m in msgs)


def test_mixed_spelling_flags_the_minority():
    msgs = messages([
        ("introduction", "The tumour grew and the colour changed."),
        ("results", "Tumour size and behaviour were recorded."),
        ("discussion", "The tumor was smaller."),
    ])
    loud = [m for s, m in msgs if s == "warning"]
    assert len(loud) == 1
    assert '"tumor" is American spelling' in loud[0]
    assert "mostly uses British spelling" in loud[0]


def test_consistent_british_is_silent():
    assert messages([
        ("results", "The tumour was labelled and analysed; its colour was grey."),
    ]) == []


def test_names_keep_their_own_spelling():
    # A British manuscript thanking an American institute is not mixed spelling.
    assert messages([
        ("results", "The tumour was labelled and analysed."),
        ("acknowledgments", "We thank the Cancer Center and Gray et al. for advice."),
    ]) == []


def test_reference_list_is_ignored():
    assert messages([
        ("results", "The tumour was analysed."),
        ("references", "1. Smith J. Tumor color in mice. J Biol. 2020;1:1-2."),
    ]) == []


@pytest.mark.parametrize("text", [
    "Mice were weighed. 15 mice were then housed in pairs.",
    "15 mice were housed in pairs for the whole study.",
])
def test_sentence_starting_with_numeral(text):
    msgs = messages([("methods", text)])
    assert any('starts with a numeral: "15 mice"' in m for _, m in msgs)


@pytest.mark.parametrize("text", [
    "As shown in Fig. 3 mice lost weight.",
    "Doses differed (e.g. 5 mg versus 10 mg).",
    "This was first described by Smith et al. 2020 and later confirmed.",
    "The policy changed. 2019 saw the first trial.",
])
def test_abbreviations_and_years_are_not_sentence_starts(text):
    assert not [m for _, m in messages([("results", text)]) if "numeral" in m]
