"""Deadlines as calendar events: for the Calendar tab, and as an .ics file
that Apple Calendar, Google Calendar and Outlook can import."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .match import NOT_ELIGIBLE, Match
from .model import Fellowship
from .tracker import FINISHED, Application

KIND_LABEL = {"final": "Deadline", "internal": "Internal deadline",
              "pre_proposal": "Pre-proposal due", "call_opens": "Call opens",
              "interview": "Interview"}


@dataclass
class Event:
    date: date
    title: str              # "Deadline: EMBO Postdoctoral Fellowship"
    fellowship_id: str
    kind: str               # a deadline kind
    mine: bool              # one of the user's applications
    estimated: bool = False
    time: str | None = None
    timezone: str | None = None


def deadline_events(fellowships: list[Fellowship], apps: dict[str, Application],
                    matches: list[Match] | None = None,
                    since: date | None = None) -> list[Event]:
    """The deadlines (and interview) of the user's applications, plus the
    final deadlines of fellowships they could apply for (when matches are
    given). Finished applications are left out. Earliest first."""
    by_id = {f.id: f for f in fellowships}
    events, seen = [], set()
    for fid, a in apps.items():
        f = by_id.get(fid)
        seen.add(fid)                       # never offered again as a match
        if f is None or a.status in FINISHED:
            continue
        for d in f.deadlines:
            events.append(Event(d.date, f"{KIND_LABEL[d.kind]}: {f.name}", f.id, d.kind,
                                True, d.estimated, d.time, d.timezone))
        if a.status == "interview" and a.interview_date:
            events.append(Event(date.fromisoformat(a.interview_date),
                                f"Interview: {f.name}", f.id, "interview", True))
    for m in matches or []:
        f = m.fellowship
        if f.id in seen or m.status == NOT_ELIGIBLE or f.template:
            continue
        for d in f.deadlines:
            if d.kind == "final":
                events.append(Event(d.date, f"{KIND_LABEL[d.kind]}: {f.name}", f.id,
                                    d.kind, False, d.estimated, d.time, d.timezone))
    if since is not None:
        events = [e for e in events if e.date >= since]
    return sorted(events, key=lambda e: (e.date, not e.mine, e.title.lower()))


def _ics_text(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """iCalendar lines are at most 75 octets; longer ones continue with a space."""
    out, b = [], line.encode("utf-8")
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:          # don't split a UTF-8 character
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def to_ics(events: list[Event], urls: dict[str, str] | None = None,
           now: datetime | None = None) -> str:
    """An iCalendar file of all-day events, each with a reminder a week
    before. Event ids are stable, so importing again updates rather than
    duplicates in most calendar apps."""
    stamp = (now or datetime.utcnow()).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Galley//Fellowships//EN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Fellowship deadlines"]
    for e in events:
        note = []
        if e.time:
            note.append(f"Closes {e.time}" + (f" {e.timezone}" if e.timezone else ""))
        if e.estimated:
            note.append("Estimated from previous years; not yet announced.")
        url = (urls or {}).get(e.fellowship_id)
        if url:
            note.append(url)
        lines += ["BEGIN:VEVENT",
                  f"UID:{e.fellowship_id}-{e.kind}-{e.date:%Y%m%d}@galley",
                  f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{e.date:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{e.date + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_ics_text(e.title)}"]
        if note:
            lines.append(f"DESCRIPTION:{_ics_text(chr(10).join(note))}")
        if url:
            lines.append(f"URL:{url}")
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(e.title)}",
                  "TRIGGER:-P7D", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
