"""Re-citing an earlier figure later in the text is normal and must not be flagged."""
from galley.checks.offline.figures import check_figures
from galley.model.document import Document, Paragraph


def make_doc(texts):
    return Document(path="t.docx", paragraphs=[
        Paragraph(index=i, text=t, style="Normal",
                  section="figure_legends" if t.startswith("Figure ") and "." in t[:10]
                  else "results")
        for i, t in enumerate(texts)])


def test_recalling_earlier_figure_is_not_an_order_error():
    body = [f"Result {n} is shown in Fig. {n}." for n in range(1, 8)]
    body.append("Fig. 8 extends the design shown in Fig. 1 (see also Fig. 1B).")
    legends = [f"Figure {n}. Legend. (A) One. (B) Two." for n in range(1, 9)]
    issues = check_figures(make_doc(body + legends))
    assert not [i for i in issues if i.severity in ("error", "warning")]


def test_real_out_of_order_first_citation_still_caught():
    body = ["See Fig. 1.", "See Fig. 3.", "See Fig. 2."]
    legends = [f"Figure {n}. Legend." for n in range(1, 4)]
    msgs = [i.message for i in check_figures(make_doc(body + legends))]
    assert "Figure 3 is first cited before Figure 2." in msgs
