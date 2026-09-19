"""The journal requirements form.

These need a Qt application, so they are skipped where PySide6 isn't installed.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from galley.gui.journal_dialog import JournalDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_filled_form_produces_a_profile(app):
    d = JournalDialog()
    d.name.setText("Journal of Fictional Biology")
    d.abstract_words.setValue(250)
    d.main_words.setValue(4500)
    d.references.setValue(60)
    d.style.setCurrentIndex(2)
    d.max_authors.setValue(6)
    d.require_doi.setChecked(True)
    d.sections.setText("data availability, ethics statement")
    data = d.data()
    assert data["limits"] == {"abstract_words": 250, "main_text_words": 4500,
                              "references": 60}
    assert data["reference_style"] == "author_year"
    assert data["max_authors_listed"] == 6
    assert data["required_sections"] == ["data availability", "ethics statement"]
    assert data["verified"]


def test_blank_fields_are_not_saved_as_limits(app):
    d = JournalDialog()
    d.name.setText("Sparse Journal")
    d.abstract_words.setValue(200)
    assert d.data()["limits"] == {"abstract_words": 200}
    assert "reference_style" not in d.data()
    assert "max_authors_listed" not in d.data()


def test_name_is_required(app):
    d = JournalDialog()
    d.abstract_words.setValue(200)
    d._save()
    assert "name" in d.error.text().lower()


def test_at_least_one_requirement_is_needed(app):
    d = JournalDialog()
    d.name.setText("Empty Journal")
    d._save()
    assert d.error.text().startswith("Set at least one")


def test_existing_profile_is_loaded_into_the_form(app, tmp_path, monkeypatch):
    from galley.checks.offline.submission import Profile, save_profile
    monkeypatch.setattr("galley.checks.offline.submission.user_profile_dir",
                        lambda: tmp_path)
    path = save_profile({"name": "Round Trip", "verified": "2026-01-01",
                         "limits": {"abstract_words": 150},
                         "reference_style": "numbered",
                         "max_authors_listed": 3, "require_doi": True,
                         "required_sections": ["ethics"]})
    d = JournalDialog(profile=Profile.load(path))
    assert d.name.text() == "Round Trip"
    assert d.abstract_words.value() == 150
    assert d.max_authors.value() == 3
    assert d.require_doi.isChecked()
    assert d.sections.text() == "ethics"
