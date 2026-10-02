"""The user's applications: status, which steps are done, and the reminders
shown when Galley opens.

Everything is kept in one small JSON file in the user's Galley settings
folder. Nothing is sent anywhere.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .model import Fellowship
from .timeline import plan

STATUSES = ["planning", "submitted", "shortlisted", "interview",
            "awarded", "not_funded", "withdrawn"]
ACTIVE = {"planning"}
FINISHED = {"awarded", "not_funded", "withdrawn"}
REMIND_WITHIN_DAYS = 42


def applications_path() -> Path:
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent / "applications.json"


@dataclass
class Application:
    fellowship_id: str
    status: str = "planning"
    started: str = ""                                   # YYYY-MM-DD
    status_dates: dict[str, str] = field(default_factory=dict)
    done: list[str] = field(default_factory=list)       # timeline step keys
    deadline_seen: str | None = None    # the deadline when last opened
    interview_date: str | None = None
    notes: str = ""
    snoozed_until: dict[str, str] = field(default_factory=dict)  # step -> date

    def set_status(self, status: str, today: date) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        self.status = status
        self.status_dates[status] = today.isoformat()

    def mark_done(self, key: str, done: bool = True) -> None:
        if done and key not in self.done:
            self.done.append(key)
        elif not done and key in self.done:
            self.done.remove(key)

    def snooze(self, key: str, until: date) -> None:
        self.snoozed_until[key] = until.isoformat()


def load_applications(path: Path | None = None) -> dict[str, Application]:
    path = path or applications_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    known = Application.__dataclass_fields__
    out = {}
    for item in raw if isinstance(raw, list) else []:
        try:
            app = Application(**{k: v for k, v in item.items() if k in known})
        except TypeError:
            continue
        out[app.fellowship_id] = app
    return out


def save_applications(apps: dict[str, Application], path: Path | None = None) -> None:
    path = path or applications_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(a) for a in apps.values()], indent=2),
                   encoding="utf-8")
    tmp.replace(path)       # never leave a half-written file behind


def start_application(apps: dict[str, Application], f: Fellowship,
                      today: date) -> Application:
    """Add a fellowship to the user's applications, or return it if there."""
    if f.id in apps:
        return apps[f.id]
    nxt = f.next_deadline(today)
    app = Application(f.id, started=today.isoformat(),
                      status_dates={"planning": today.isoformat()},
                      deadline_seen=nxt.date.isoformat() if nxt else None)
    apps[f.id] = app
    return app


@dataclass
class Reminder:
    fellowship_id: str
    fellowship: str
    date: date
    text: str
    urgency: str            # "overdue" | "soon" | "upcoming" | "changed"
    step: str | None = None


def _urgency(when: date, today: date) -> str:
    days = (when - today).days
    return "overdue" if days < 0 else "soon" if days <= 14 else "upcoming"


def reminders(apps: dict[str, Application], fellowships: list[Fellowship],
              today: date, within_days: int = REMIND_WITHIN_DAYS,
              update_seen: bool = True) -> list[Reminder]:
    """What to show when Galley opens: steps due soon or overdue, interviews,
    and deadlines that moved since the user last looked. Most urgent first.

    With update_seen, a moved deadline is reported once and then remembered;
    save the applications afterwards.
    """
    by_id = {f.id: f for f in fellowships}
    out: list[Reminder] = []
    for app in apps.values():
        f = by_id.get(app.fellowship_id)
        if f is None or app.status in FINISHED:
            continue

        nxt = f.next_deadline(today)
        seen = app.deadline_seen
        now = nxt.date.isoformat() if nxt else None
        if seen and now and seen != now:
            out.append(Reminder(f.id, f.name, nxt.date,
                                f"The deadline moved from "
                                f"{date.fromisoformat(seen):%d %b %Y} to "
                                f"{nxt.date:%d %b %Y}.", "changed"))
        if update_seen and now:
            app.deadline_seen = now

        if app.status == "interview" and app.interview_date:
            when = date.fromisoformat(app.interview_date)
            if today <= when <= date.fromordinal(today.toordinal() + within_days):
                out.append(Reminder(f.id, f.name, when, "Interview",
                                    _urgency(when, today)))

        if app.status not in ACTIVE:
            continue
        for step in plan(f, today):
            if step.key in app.done:
                continue
            snoozed = app.snoozed_until.get(step.key)
            if snoozed and date.fromisoformat(snoozed) > today:
                continue
            if (step.date - today).days > within_days:
                continue
            out.append(Reminder(f.id, f.name, step.date, step.task,
                                _urgency(step.date, today), step.key))

    order = {"overdue": 0, "changed": 1, "soon": 2, "upcoming": 3}
    return sorted(out, key=lambda r: (order[r.urgency], r.date, r.fellowship))
