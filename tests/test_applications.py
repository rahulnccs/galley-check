"""Application requirements, preparation plans, the tracker and reminders."""
import zipfile
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import docx
import pytest

from galley.fellowships import (Fellowship, check_draft, load_applications,
                                plan, reminders, save_applications,
                                start_application)
from galley.fellowships.requirements import Requirements, _saved_page_count

TODAY = date(2026, 10, 1)
FINAL = date(2027, 1, 15)


def fellowship(**overrides) -> Fellowship:
    data = {"id": "f", "name": "Test Fellowship", "funder": "Test Funder",
            "url": "https://example.org/f", "verified": "2026-09-01",
            "deadlines": [{"kind": "final", "date": FINAL.isoformat()}]}
    data.update(overrides)
    return Fellowship.from_dict(data)


FULL = {"documents": [{"name": "Research proposal", "max_words": 50,
                       "sections": ["Background", "Aims"]}],
        "host_letter": True}


# --- requirements ------------------------------------------------------------

@pytest.mark.parametrize("bad, complaint", [
    ({"documents": [{"max_pages": 3}]}, "needs a name"),
    ({"cv_format": "fancy"}, "cv_format must be"),
    ({"documents": [{"name": "Proposal", "max_words": "lots"}]}, "invalid literal"),
    ({"submission": "fax"}, "submission must be"),
])
def test_bad_requirements_rejected(bad, complaint):
    with pytest.raises(ValueError, match=complaint):
        fellowship(requirements=bad)


def test_requirements_parsed():
    f = fellowship(requirements=FULL)
    assert f.requirements.host_letter
    assert f.requirements.document("research proposal").max_words == 50


def make_draft(path, paragraphs, pages=None):
    d = docx.Document()
    for kind, text in paragraphs:
        (d.add_heading(text, level=1) if kind == "h" else d.add_paragraph(text))
    d.save(path)
    if pages is not None:   # what Word writes on save
        tmp = str(path) + ".tmp"
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
            for item in src.infolist():
                if item.filename != "docProps/app.xml":
                    dst.writestr(item, src.read(item.filename))
            dst.writestr("docProps/app.xml",
                         f"<Properties><Pages>{pages}</Pages></Properties>")
        import os
        os.replace(tmp, path)
    return str(path)


def messages(issues):
    return [(i.severity, i.message) for i in issues]


def test_draft_within_limits(tmp_path):
    path = make_draft(tmp_path / "p.docx", [("h", "Background"), ("p", "Short text."),
                                            ("h", "Aims"), ("p", "Two aims.")])
    req = Requirements.from_dict(FULL).documents[0]
    msgs = messages(check_draft(path, req))
    assert not [m for s, m in msgs if s != "info"]


def test_draft_over_word_limit_and_missing_section(tmp_path):
    path = make_draft(tmp_path / "p.docx",
                      [("h", "Background"), ("p", "word " * 60)])
    req = Requirements.from_dict(FULL).documents[0]
    msgs = messages(check_draft(path, req))
    assert ("warning", "The Research proposal is 60 words, over the limit of "
                       "50 by 10.") in msgs
    assert any(s == "error" and '"Aims"' in m for s, m in msgs)


def test_page_count_from_word(tmp_path):
    req = Requirements.from_dict({"documents": [{"name": "Proposal",
                                                 "max_pages": 5}]}).documents[0]
    over = make_draft(tmp_path / "over.docx", [("p", "x")], pages=7)
    assert any("7 pages" in m and s == "warning" for s, m in messages(check_draft(over, req)))
    unknown = make_draft(tmp_path / "unknown.docx", [("p", "x")])
    if _saved_page_count(unknown) is None:
        assert any("can't count pages" in m for _, m in messages(check_draft(unknown, req)))


# --- preparation plan --------------------------------------------------------

def test_plan_works_back_from_the_deadline():
    f = fellowship(requirements=FULL)
    steps = {s.key: s for s in plan(f, TODAY)}
    assert steps["submit"].date == FINAL and steps["submit"].is_deadline
    assert steps["drafts_for_feedback"].date == FINAL - timedelta(weeks=4)
    assert steps["contact_hosts"].date == FINAL - timedelta(weeks=12)
    assert steps["final_check"].date == FINAL - timedelta(weeks=1)
    assert "Research proposal" in steps["start_writing"].task
    dates = [s.date for s in plan(f, TODAY)]
    assert dates == sorted(dates)


def test_internal_deadline_pulls_drafting_earlier():
    internal = FINAL - timedelta(weeks=4)
    f = fellowship(deadlines=[{"kind": "internal", "date": internal.isoformat()},
                              {"kind": "final", "date": FINAL.isoformat()}])
    steps = {s.key: s for s in plan(f, TODAY)}
    assert steps["internal"].is_deadline
    assert steps["start_writing"].date == internal - timedelta(weeks=8)


def test_no_plan_without_a_deadline():
    assert plan(fellowship(deadlines=[], rolling=True), TODAY) == []


def test_late_start_keeps_steps_as_overdue():
    late = FINAL - timedelta(weeks=2)
    steps = {s.key: s for s in plan(fellowship(requirements=FULL), late)}
    assert steps["contact_hosts"].overdue(late)
    assert not steps["submit"].overdue(late)


# --- tracker -----------------------------------------------------------------

def test_tracker_round_trip(tmp_path):
    path = tmp_path / "applications.json"
    apps = {}
    app = start_application(apps, fellowship(), TODAY)
    app.mark_done("start_writing")
    app.set_status("submitted", TODAY)
    app.notes = "Host: Dr Example"
    save_applications(apps, path)
    back = load_applications(path)["f"]
    assert back.status == "submitted" and back.done == ["start_writing"]
    assert back.status_dates["submitted"] == TODAY.isoformat()
    assert back.notes == "Host: Dr Example"


def test_starting_twice_keeps_the_original(tmp_path):
    apps = {}
    a = start_application(apps, fellowship(), TODAY)
    a.notes = "keep"
    assert start_application(apps, fellowship(), TODAY).notes == "keep"


def test_bad_status_rejected():
    app = start_application({}, fellowship(), TODAY)
    with pytest.raises(ValueError):
        app.set_status("pending", TODAY)


def test_missing_or_broken_file_gives_no_applications(tmp_path):
    assert load_applications(tmp_path / "none.json") == {}
    (tmp_path / "bad.json").write_text("{ broken")
    assert load_applications(tmp_path / "bad.json") == {}


# --- reminders ---------------------------------------------------------------

def test_reminders_when_the_app_opens():
    f = fellowship(requirements=FULL)
    apps = {}
    start_application(apps, f, TODAY)
    day = FINAL - timedelta(weeks=5)
    found = reminders(apps, [f], day)
    texts = [r.text for r in found]
    assert any("Contact potential host labs" in t for t in texts)
    assert found[0].urgency == "overdue"            # most urgent first
    assert all((r.date - day).days <= 42 for r in found)


def test_done_and_snoozed_steps_are_quiet():
    f = fellowship(requirements=FULL)
    apps = {}
    app = start_application(apps, f, TODAY)
    day = FINAL - timedelta(weeks=5)
    app.mark_done("contact_hosts")
    app.snooze("drafts_for_feedback", day + timedelta(days=7))
    keys = [r.step for r in reminders(apps, [f], day)]
    assert "contact_hosts" not in keys and "drafts_for_feedback" not in keys


def test_submitted_application_stops_preparation_reminders():
    f = fellowship(requirements=FULL)
    apps = {}
    start_application(apps, f, TODAY).set_status("submitted", TODAY)
    assert reminders(apps, [f], FINAL - timedelta(weeks=1)) == []


def test_interview_reminder():
    f = fellowship()
    apps = {}
    app = start_application(apps, f, TODAY)
    app.set_status("interview", TODAY)
    app.interview_date = (TODAY + timedelta(days=10)).isoformat()
    found = reminders(apps, [f], TODAY)
    assert [(r.text, r.urgency) for r in found] == [("Interview", "soon")]


def test_moved_deadline_reported_once():
    apps = {}
    start_application(apps, fellowship(), TODAY)
    moved = fellowship(deadlines=[{"kind": "final", "date": "2027-02-01"}])
    first = reminders(apps, [moved], TODAY)
    assert any(r.urgency == "changed" and "15 Jan 2027 to 01 Feb 2027" in r.text
               for r in first)
    assert not [r for r in reminders(apps, [moved], TODAY) if r.urgency == "changed"]


# --- reporting a problem with an entry ----------------------------------------

def test_report_link_names_the_entry_only():
    url = fellowship().report_problem_url()
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://github.com/rahulnccs/galley-check/issues/new")
    assert "Test Fellowship" in q["title"][0]
    assert "https://example.org/f" in q["body"][0]


def test_no_report_link_for_your_own_entries():
    f = Fellowship.from_dict({"id": "custom-x", "name": "X", "custom": True})
    assert f.report_problem_url() is None
