"""Legends often sit after the reference list, under a plain 'Figures' heading."""
from galley.checks.offline.figures import check_figures
from galley.model.document import Document, Paragraph


def test_legends_found_after_reference_list():
    texts = [("Results", "results"),
             ("Diversity declined with age (Fig. 1B).", "results"),
             ("References", "references"),
             ("Smith J, et al. A paper about figure skating. J Test 2020;3:1-9.", "references"),
             ("Figures", "figure_legends"),
             ("Figure 1. Study overview. (A) Design. (B) Diversity.", "figure_legends")]
    doc = Document(path="t.docx", paragraphs=[
        Paragraph(index=i, text=t, style="Normal", section=s)
        for i, (t, s) in enumerate(texts)])
    msgs = [i.message for i in check_figures(doc)]
    assert not any("no legend" in m for m in msgs)
    assert not any("Figure 1 has a legend but is never cited" in m for m in msgs)


def test_legends_directly_after_references_with_no_heading():
    """Legends can follow the reference list with nothing announcing them."""
    texts = [("Cell counts rose over time (Figure 1A) and diversity fell (Fig. 2).", "results"),
             ("References", "references"),
             ("Doe J, Roe S. Figures of merit in ecology. Ecol Lett 2018;21(4):100-9.",
              "references"),
             ("Poe A, et al. Table-driven analysis of soil. Soil Biol 2020;55:12.", "references"),
             ("Figure 1. Growth over time. (A) Counts. (B) Rates.", "references"),
             ("Figure 2. Diversity across samples.", "references")]
    doc = Document(path="t.docx", paragraphs=[
        Paragraph(index=i, text=t, style="Normal", section=s)
        for i, (t, s) in enumerate(texts)])
    issues = check_figures(doc)
    serious = [i.message for i in issues if i.severity in ("error", "warning")]
    assert serious == []


def test_reference_entries_are_not_mistaken_for_callouts():
    """A reference titled 'Figures of merit...' must not create a Figure callout."""
    texts = [("Nothing is cited here.", "introduction"),
             ("References", "references"),
             ("Doe J. Figures 9 of merit. J Test 2018;21:100-9.", "references")]
    doc = Document(path="t.docx", paragraphs=[
        Paragraph(index=i, text=t, style="Normal", section=s)
        for i, (t, s) in enumerate(texts)])
    assert not [i for i in check_figures(doc) if "Figure 9" in i.message]
