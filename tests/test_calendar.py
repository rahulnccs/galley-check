"""Fellowship deadlines as calendar events and an .ics file."""
from datetime import date, datetime

from galley.fellowships import Fellowship, Researcher, match_all
from galley.fellowships.calendar import deadline_events, to_ics
from galley.fellowships.tracker import Application

TODAY = date(2026, 10, 9)


def fellowship(fid, **kw):
    return Fellowship.from_dict({"id": fid, "name": kw.pop("name", fid.title()),
                                 "funder": "Funder", "url": f"https://example.org/{fid}",
                                 "verified": "2026-10-01", **kw})


def test_my_applications_and_what_i_could_apply_for():
    mine = fellowship("mine", deadlines=[
        {"kind": "internal", "date": "2026-11-01"},
        {"kind": "final", "date": "2026-11-20", "time": "17:00",
         "timezone": "Europe/Berlin"}])
    open_to_me = fellowship("open", deadlines=[{"kind": "final", "date": "2026-12-01",
                                                "estimated": True}])
    closed = fellowship("closed", nationalities=["DE"],
                        deadlines=[{"kind": "final", "date": "2026-12-02"}])
    done = fellowship("done", deadlines=[{"kind": "final", "date": "2026-10-20"}])
    apps = {"mine": Application("mine", status="interview", interview_date="2026-12-10"),
            "done": Application("done", status="withdrawn")}
    fs = [mine, open_to_me, closed, done]
    only_mine = deadline_events(fs, apps)
    assert [(e.date.isoformat(), e.kind) for e in only_mine] == [
        ("2026-11-01", "internal"), ("2026-11-20", "final"), ("2026-12-10", "interview")]
    assert all(e.mine for e in only_mine)

    matches = match_all(fs, Researcher(nationalities=["IN"]), TODAY)
    everything = deadline_events(fs, apps, matches)
    others = [e for e in everything if not e.mine]
    assert [e.fellowship_id for e in others] == ["open"]           # not "closed"
    assert others[0].estimated and others[0].title == "Deadline: Open"


def test_ics_file():
    f = fellowship("embo", name="EMBO Postdoctoral Fellowship, 2027; long name " * 2,
                   deadlines=[{"kind": "final", "date": "2026-11-20", "time": "17:00",
                               "timezone": "Europe/Berlin"}])
    events = deadline_events([f], {"embo": Application("embo")})
    ics = to_ics(events, {"embo": f.url}, now=datetime(2026, 10, 9, 12))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261120" in ics and "DTEND;VALUE=DATE:20261121" in ics
    assert "UID:embo-final-20261120@galley" in ics
    assert "TRIGGER:-P7D" in ics                       # a reminder a week before
    assert "\\," in ics and "\\;" in ics                # escaped
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    unfolded = ics.replace("\r\n ", "")
    assert "Closes 17:00 Europe/Berlin" in unfolded
