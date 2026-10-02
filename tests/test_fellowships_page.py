"""The Fellowships screen. Needs Qt; skipped where PySide6 isn't installed."""
from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from galley.checks.offline import submission  # noqa: E402
from galley.fellowships import load_applications  # noqa: E402
from galley.fellowships.model import (Researcher, Stay,  # noqa: E402
                                      load_researcher, save_researcher)

TODAY = date(2026, 10, 1)


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    if existing is not None:
        return existing
    try:
        return QApplication([])
    except Exception as e:
        pytest.skip(f"Qt cannot start here: {e}")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Point Galley's settings folder at a temporary one."""
    monkeypatch.setattr(submission, "user_profile_dir", lambda: tmp_path / "profiles")
    # Include the bundled example entries so there is something to match.
    import galley.fellowships.model as model
    real = model.load_fellowships

    def with_examples(*a, **k):
        k.setdefault("include_templates", True)
        return real(*a, **k)
    import galley.gui.fellowships_page as page_mod
    monkeypatch.setattr(page_mod, "load_fellowships", with_examples)
    return tmp_path


def texts(widget):
    return " | ".join(l.text() for l in widget.findChildren(QLabel))


def make_page(app):
    from galley.gui.fellowships_page import FellowshipsPage
    return FellowshipsPage(today=TODAY)


def test_empty_profile_prompts_to_fill_it_in(app, settings):
    page = make_page(app)
    assert "Fill in your profile" in texts(page.tab_stack.widget(0))


def test_matches_grouped_by_eligibility(app, settings):
    save_researcher(Researcher(phd_date=date(2025, 1, 1), nationalities=["IN"],
                               residence="IN", clinical=False,
                               target_hosts=["DE"],
                               stays=[Stay("IN", date(2015, 1, 1))]))
    page = make_page(app)
    shown = texts(page.tab_stack.widget(0))
    assert "YOU'RE ELIGIBLE" in shown
    assert "Example International Postdoctoral Fellowship" in shown
    assert "Fill in your profile" not in shown


def test_add_application_and_tick_a_step(app, settings):
    page = make_page(app)
    page.open_fellowship("example-international-postdoc")
    detail = texts(page.detail)
    assert "WHAT YOU NEED" in detail and "Research proposal" in detail
    page._add_application("example-international-postdoc")
    saved = load_applications(settings / "applications.json")
    assert "example-international-postdoc" in saved
    app_obj = page.apps["example-international-postdoc"]
    from PySide6.QtWidgets import QPushButton
    ticks = [b for b in page.detail.findChildren(QPushButton) if b.isCheckable()]
    ticks[0].setChecked(True)
    assert app_obj.done
    assert load_applications(settings / "applications.json")[
        "example-international-postdoc"].done == app_obj.done


def test_reminders_counted_for_the_banner(app, settings):
    page = make_page(app)
    page._add_application("example-international-postdoc")
    page.today = date(2026, 12, 20)      # a few weeks before the deadline
    assert page.attention_count() > 0
    page.refresh(1)
    assert "COMING UP" in texts(page.tab_stack.widget(1))


def test_profile_form_saves(app, settings):
    page = make_page(app)
    page.show_tab(2)
    page.p_phd_state.setCurrentIndex(0)
    page.p_nationality.setText("in, gb")
    page.p_residence.setText("in")
    page.p_fields["neuroscience"].setChecked(True)
    page.save_profile()
    r = load_researcher(settings / "researcher.json")
    assert r.nationalities == ["IN", "GB"] and r.residence == "IN"
    assert r.fields == ["neuroscience"] and r.phd_date is not None


def test_bad_country_code_is_not_saved(app, settings, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warned.append(a[2]))
    page = make_page(app)
    page.p_nationality.setText("India")
    page.save_profile()
    assert warned and "INDIA" in warned[0]
    assert not (settings / "researcher.json").exists()


def test_main_window_has_both_sections(app, settings):
    from galley.gui.app import MainWindow
    win = MainWindow("Georgia")
    assert win.switcher.buttons[1].text().startswith("Fellowships")
    win.switcher.select(1)
    assert win.sections.currentWidget() is win.fellowships


def test_attach_and_check_application(app, settings, tmp_path, monkeypatch):
    import docx
    proposal = tmp_path / "proposal.docx"
    d = docx.Document()
    for heading in ("Background", "Aims", "Approach", "Feasibility"):
        d.add_heading(heading, level=1)
        d.add_paragraph("Some text.")
    d.save(proposal)

    page = make_page(app)
    page._add_application("example-international-postdoc")
    assert "CHECK YOUR APPLICATION" in texts(page.detail)
    monkeypatch.setattr(page, "_choose_file", lambda title: str(proposal))
    page._attach("example-international-postdoc", "Research proposal")
    saved = load_applications(settings / "applications.json")
    assert saved["example-international-postdoc"].files == {
        "Research proposal": str(proposal)}

    page._check_application("example-international-postdoc")
    report = texts(page.detail)
    assert "to fix" in report                       # career statement missing
    assert "Not attached yet." in report
    assert 'Includes "Feasibility".' in report
