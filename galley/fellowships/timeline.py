"""A preparation plan worked back from a fellowship's deadline.

The lead times are rules of thumb from how long each step usually takes:
referees need about six weeks, a host letter needs the host found first, and
an internal deadline pulls everything earlier. Each step has a stable key so
the tracker can record which ones are done.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .model import Fellowship

WEEK = timedelta(weeks=1)


@dataclass
class Step:
    key: str            # stable, e.g. "ask_referees"
    date: date
    task: str
    is_deadline: bool = False   # set by the funder, not a suggestion

    def overdue(self, today: date) -> bool:
        return self.date < today


def plan(f: Fellowship, today: date) -> list[Step]:
    """Steps from now to the next final deadline (and reference letters due
    shortly after it), in date order. Empty when
    no deadline is announced (rolling calls have nothing to work back from)."""
    final = f.next_deadline(today)
    if final is None:
        return []
    # Reference letters are often due a little after the applicant's own
    # deadline; everything else belongs before it.
    by_kind = {d.kind: d for d in f.deadlines
               if d.date >= today
               and (d.date <= final.date
                    or (d.kind == "referees" and (d.date - final.date).days <= 60))}
    req = f.requirements
    steps: list[Step] = []

    opens = by_kind.get("call_opens")
    if opens:
        steps.append(Step("call_opens", opens.date, "Call opens", True))

    # Anything internal or preliminary needs a near-final draft before it.
    gates = [by_kind[k] for k in ("internal", "pre_proposal") if k in by_kind]
    first_gate = min((g.date for g in gates), default=final.date)

    if req and req.host_letter:
        steps.append(Step("contact_hosts", first_gate - 12 * WEEK,
                          "Contact potential host labs"))
        steps.append(Step("host_letter", first_gate - 3 * WEEK,
                          "Ask your host for their letter of support"))

    if req and req.referees:
        refs_due = by_kind.get("referees")
        due = refs_due.date if refs_due else final.date
        n = req.referees.count
        steps.append(Step("ask_referees", due - 6 * WEEK,
                          f"Ask {n} referee{'s' if n != 1 else ''} and send them "
                          f"your CV and project summary"))
        if refs_due:
            steps.append(Step("referees_due", refs_due.date,
                              refs_due.label or "Reference letters due", True))

    documents = [d.name for d in req.documents] if req else []
    what = ", ".join(documents) if documents else "the application"
    steps.append(Step("start_writing", first_gate - 8 * WEEK, f"Start drafting {what}"))
    steps.append(Step("drafts_for_feedback", first_gate - 4 * WEEK,
                      "Send drafts to a mentor or colleague for feedback"))

    for g in gates:
        label = g.label or ("Internal deadline" if g.kind == "internal"
                            else "Pre-proposal deadline")
        steps.append(Step(g.kind, g.date, label, True))

    steps.append(Step("final_check", final.date - WEEK,
                      "Check every document against the funder's requirements"))
    steps.append(Step("submit", final.date, "Final deadline: submit", True))

    # A step whose suggested date is already past still has to happen; keep
    # it, and the tracker shows it as overdue.
    return sorted(steps, key=lambda s: (s.date, not s.is_deadline))
