"""Submission-readiness counts and journal-profile limits."""
import json

import pytest

from galley.checks.offline.submission import Profile, check_submission, count
from galley.model.document import Document, Paragraph


def make_doc(sections, title="A study of microbial communities in model hosts"):
    paras = [Paragraph(index=0, text=title, style="Title", section="front_matter")]
    for section, text in sections:
        paras.append(Paragraph(index=len(paras), text=text, style="Normal",
                               section=section))
    return Document(path="t.docx", paragraphs=paras)


BODY = [("abstract", "one two three four five."),
        ("introduction", " ".join(["word"] * 40)),
        ("results", " ".join(["word"] * 60)),
        ("methods", " ".join(["word"] * 30))]


def test_counts():
    c = count(make_doc(BODY))
    assert c.title == 8
    assert c.abstract == 5
    assert c.main_text == 100
    assert c.methods == 30
    assert c.total == 135


def test_size_note_without_a_profile():
    issues = check_submission(make_doc(BODY))
    assert len(issues) == 1 and issues[0].severity == "info"
    assert "main text 100" in issues[0].message


def profile(**limits):
    return Profile(name="Test Journal", limits=limits)


def test_over_a_word_limit_is_a_warning():
    issues = check_submission(make_doc(BODY), profile(main_text_words=50))
    assert any(i.severity == "warning" and "over the Test Journal limit" in i.message
               for i in issues)


def test_within_a_limit_is_silent():
    issues = check_submission(make_doc(BODY), profile(main_text_words=5000))
    assert not [i for i in issues if i.severity in ("warning", "error")]


def test_close_to_a_limit_is_a_note():
    issues = check_submission(make_doc(BODY), profile(main_text_words=101))
    assert any(i.severity == "info" and "close to" in i.message for i in issues)


def test_missing_required_section_is_an_error():
    issues = check_submission(make_doc(BODY),
                              Profile(name="Test Journal",
                                      required_sections=["data availability"]))
    assert any(i.severity == "error" and "data availability" in i.message
               for i in issues)


@pytest.mark.parametrize("heading", [
    "Data availability",
    "DATA AND CODE AVAILABILITY",
    "Data and code availability statement",
])
def test_required_section_matches_real_world_headings(heading):
    doc = make_doc(BODY + [("methods", f"{heading}. Raw data are in the SRA.")])
    issues = check_submission(doc, Profile(name="Test Journal",
                                           required_sections=["data availability"]))
    assert not [i for i in issues if i.severity == "error"]


def test_unknown_limit_is_reported_not_ignored():
    issues = check_submission(make_doc(BODY), profile(colour_figures=2))
    assert any("doesn't measure" in i.message for i in issues)


def test_profile_loads_from_a_file(tmp_path):
    path = tmp_path / "journal.json"
    path.write_text(json.dumps({"name": "J. Fict", "limits": {"references": 30},
                                "required_sections": ["acknowledgments"]}))
    p = Profile.load(path)
    assert p.name == "J. Fict" and p.limits["references"] == 30


def test_shipped_example_profile_is_valid():
    p = Profile.load("example")
    assert p.limits and p.name
