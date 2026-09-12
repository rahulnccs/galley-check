"""Run every check against a corpus of manuscripts in different citation styles.

This is the guard against overfitting to the handful of real papers used
during development: each fixture declares the problems it contains, and the
tool must find those and raise nothing else.
"""
from __future__ import annotations

import pytest

from galley.engine import load, run_checks
from tests.fixtures.make_corpus import CORPUS, CORPUS_DIR, build

IDS = [spec.name for spec in CORPUS]


@pytest.fixture(scope="module", params=CORPUS, ids=IDS)
def checked(request):
    spec = request.param
    path = build(spec, CORPUS_DIR)
    doc = load(path)
    return spec, doc, run_checks(doc)


def test_expected_problems_are_found(checked):
    spec, _, issues = checked
    messages = [i.message for i in issues]
    for wanted in spec.expected:
        assert any(wanted in m for m in messages), (
            f"{spec.name} ({spec.style}): expected a message containing {wanted!r}, "
            f"got {messages}")


def test_no_unexpected_problems(checked):
    spec, _, issues = checked
    loud = [i.message for i in issues if i.severity in ("error", "warning")]
    extra = [m for m in loud
             if not any(wanted in m for wanted in spec.expected)]
    assert not extra, f"{spec.name} ({spec.style}): unexpected findings {extra}"


def test_clean_manuscripts_are_silent(checked):
    spec, _, issues = checked
    if not spec.expect_clean:
        pytest.skip("this manuscript has planted errors")
    loud = [f"{i.severity}: {i.message}" for i in issues
            if i.severity in ("error", "warning")]
    assert not loud, f"{spec.name} ({spec.style}) should be clean, got {loud}"


def test_every_manuscript_parses(checked):
    spec, doc, _ = checked
    assert len(doc.paragraphs) > 3
    assert any(p.section == "results" for p in doc.paragraphs)
