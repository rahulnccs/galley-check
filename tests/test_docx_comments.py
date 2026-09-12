"""The commented copy: correct anchoring, correct counts, original untouched."""
from __future__ import annotations

import zipfile

import docx
import pytest
from lxml import etree

from galley.engine import load, run_checks
from galley.model.document import Issue
from galley.report.docx_comments import annotate, default_output_path
from tests.fixtures.make_corpus import CORPUS_DIR, build
from tests.fixtures.make_corpus import CORPUS

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SPEC = next(s for s in CORPUS if s.name == "vancouver_uncited")


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    build(SPEC, CORPUS_DIR)
    return CORPUS_DIR / f"{SPEC.name}.docx"


def anchored_text(path) -> dict[str, str]:
    """Map each comment id to the manuscript text it points at."""
    xml = etree.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    found: dict[str, str] = {}
    for p in xml.iter(f"{W}p"):
        for start in p.findall(f"{W}commentRangeStart"):
            ident = start.get(f"{W}id")
            collecting, chunk = False, []
            for el in p.iter():
                tag = el.tag.split("}")[-1]
                if tag == "commentRangeStart" and el.get(f"{W}id") == ident:
                    collecting = True
                    continue
                if tag == "commentRangeEnd" and el.get(f"{W}id") == ident:
                    collecting = False
                if collecting and tag == "t":
                    chunk.append(el.text or "")
            found[ident] = "".join(chunk)
    return found


def test_comments_are_written(source, tmp_path):
    doc = load(source)
    issues = run_checks(doc)
    out = annotate(doc, issues, tmp_path / "out.docx")
    assert len(docx.Document(str(out)).comments) == len(issues)


def test_original_file_is_untouched(source, tmp_path):
    before = source.read_bytes()
    doc = load(source)
    annotate(doc, run_checks(doc), tmp_path / "out.docx")
    assert source.read_bytes() == before


def test_refuses_to_overwrite_the_original(source):
    doc = load(source)
    with pytest.raises(ValueError):
        annotate(doc, run_checks(doc), source)


def test_comment_text_carries_severity_and_suggestion(source, tmp_path):
    doc = load(source)
    out = annotate(doc, run_checks(doc), tmp_path / "out.docx")
    texts = [c.text for c in docx.Document(str(out)).comments]
    assert any(t.startswith("Error: Reference 3 is never cited") for t in texts)
    assert any("remove it from the list" in t for t in texts)


def test_severity_filter(source, tmp_path):
    doc = load(source)
    issues = run_checks(doc)
    out = annotate(doc, issues, tmp_path / "errors.docx", severities=("error",))
    assert len(docx.Document(str(out)).comments) == \
        sum(1 for i in issues if i.severity == "error")


def test_anchor_points_at_the_exact_phrase(tmp_path):
    """A comment on a figure callout highlights the callout, not the paragraph."""
    spec = next(s for s in CORPUS if s.name == "vancouver_overrun")
    path = build(spec, CORPUS_DIR)
    doc = load(path)
    issues = [i for i in run_checks(doc) if i.anchor and "[9]" in (i.anchor or "")]
    assert issues, "expected an issue anchored on the [9] citation"
    out = annotate(doc, issues, tmp_path / "out.docx")
    assert "[9]" in "".join(anchored_text(out).values())


def test_issue_without_a_location_still_lands(tmp_path):
    spec = next(s for s in CORPUS if s.name == "vancouver_brackets")
    path = build(spec, CORPUS_DIR)
    doc = load(path)
    floating = Issue("figures", "info", "A note with no paragraph attached.")
    out = annotate(doc, [floating], tmp_path / "out.docx")
    assert len(docx.Document(str(out)).comments) == 1


def test_default_output_path_is_beside_the_original():
    assert default_output_path("/tmp/paper.docx").name == "paper_commented.docx"
