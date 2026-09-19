"""Journal profiles: the form's output, saving, and the checks they drive."""
import json

import pytest

from galley.checks.offline.references import check_references
from galley.checks.offline.submission import (
    Profile, available_profiles, save_profile, user_profile_dir)
from tests.test_references import REFS, make_doc, messages


def test_saved_profile_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr("galley.checks.offline.submission.user_profile_dir",
                        lambda: tmp_path)
    path = save_profile({"name": "Journal of Tests", "verified": "2026-09-19",
                         "limits": {"abstract_words": 200},
                         "reference_style": "numbered",
                         "max_authors_listed": 6, "require_doi": True})
    p = Profile.load(path)
    assert p.name == "Journal of Tests"
    assert p.limits["abstract_words"] == 200
    assert p.reference_style == "numbered"
    assert p.max_authors_listed == 6 and p.require_doi is True


def test_saved_profile_filename_is_derived_from_the_name(tmp_path, monkeypatch):
    monkeypatch.setattr("galley.checks.offline.submission.user_profile_dir",
                        lambda: tmp_path)
    path = save_profile({"name": "Nature Communications"})
    assert path.name == "nature-communications.json"


def test_user_profile_dir_is_outside_the_package():
    from galley.checks.offline.submission import PROFILE_DIR
    assert user_profile_dir() != PROFILE_DIR


def test_bundled_profiles_still_listed():
    assert any(p.name for p in available_profiles(include_templates=True))


class Journal:
    """A profile built the way the dialog builds one."""
    def __init__(self, **kw):
        self.name = "Test Journal"
        self.reference_style = kw.get("reference_style")
        self.max_authors_listed = kw.get("max_authors_listed")
        self.require_doi = kw.get("require_doi", False)


def test_too_many_authors_listed():
    refs = ["1\tDoe J, Roe S, Poe A, Moe B, Loe C, Coe D, Noe E. A paper. "
            "J Test 2019;1:1-10.",
            "2\tRoe S. Another paper. J Test 2020;2:1-9."]
    doc = make_doc(["Cited [1,2]."], refs)
    issues = check_references(doc, Journal(max_authors_listed=3))
    assert any("lists at most 3 authors" in i.message for i in issues)


def test_author_limit_respected_is_silent():
    refs = ["1\tDoe J, Roe S. A paper. J Test 2019;1:1-10.",
            "2\tRoe S. Another paper. J Test 2020;2:1-9."]
    doc = make_doc(["Cited [1,2]."], refs)
    issues = check_references(doc, Journal(max_authors_listed=6))
    assert not any("authors" in i.message for i in issues)


def test_et_al_entries_are_not_counted():
    """An entry already truncated with "et al." cannot be over the limit."""
    refs = ["1\tDoe J, Roe S, Poe A, et al. A paper. J Test 2019;1:1-10.",
            "2\tRoe S. Another paper. J Test 2020;2:1-9."]
    doc = make_doc(["Cited [1,2]."], refs)
    issues = check_references(doc, Journal(max_authors_listed=2))
    assert not any("lists at most" in i.message for i in issues)


def test_doi_required_by_the_journal():
    refs = ["1\tDoe J. A paper. J Test 2019;1:1-10.",
            "2\tRoe S. Another. J Test 2020;2:1-9. doi:10.1000/x"]
    doc = make_doc(["Cited [1,2]."], refs)
    issues = check_references(doc, Journal(require_doi=True))
    assert any("requires a DOI for every reference" in i.message for i in issues)


def test_doi_not_required_stays_quiet():
    refs = ["1\tDoe J. A paper. J Test 2019;1:1-10.",
            "2\tRoe S. Another. J Test 2020;2:1-9."]
    doc = make_doc(["Cited [1,2]."], refs)
    issues = check_references(doc, Journal(require_doi=False))
    assert not any("requires a DOI" in i.message for i in issues)


def test_template_is_hidden_from_the_dropdown():
    """The bundled example has invented numbers; it isn't a journal."""
    names = [p.name for p in available_profiles()]
    assert "Example Journal" not in names
    assert any(p.template for p in available_profiles(include_templates=True))


def test_user_profiles_can_be_removed(tmp_path, monkeypatch):
    from galley.checks.offline.submission import delete_profile, is_user_profile
    monkeypatch.setattr("galley.checks.offline.submission.user_profile_dir",
                        lambda: tmp_path)
    path = save_profile({"name": "Temporary", "limits": {"references": 10}})
    profile = Profile.load(path)
    assert is_user_profile(profile)
    assert delete_profile(profile) is True
    assert not path.exists()


def test_bundled_profiles_cannot_be_removed():
    from galley.checks.offline.submission import delete_profile, is_user_profile
    bundled = available_profiles(include_templates=True)
    template = next(p for p in bundled if p.template)
    assert is_user_profile(template) is False
    assert delete_profile(template) is False
    assert template.path.exists()
