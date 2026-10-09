"""Match a researcher to fellowships, and say why.

Every rule gives one of three answers: met, not met, or can't tell (because
the profile leaves something out, or the rules leave room for judgement).
A fellowship is

  * eligible when every rule Galley can check is met,
  * not eligible when any rule is clearly not met,
  * possibly eligible otherwise.

Rules written in words (an age limit, "a lead-author paper") can't be
checked from a profile. They don't change the verdict; they are listed for
the user to confirm, as CHECK reasons, so they are never silently met.

Wrongly telling someone they can't apply costs them a real opportunity, so
when in doubt the answer is "possibly", with the reason spelled out and the
funder's own page as the final word.

Years since PhD are counted to the next deadline, which is how funders count.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .model import Deadline, Fellowship, Researcher

ELIGIBLE, POSSIBLE, NOT_ELIGIBLE = "eligible", "possibly eligible", "not eligible"
MET, NOT_MET, UNSURE, INFO, CHECK = "met", "not met", "unsure", "info", "check"
STATUS_ORDER = {ELIGIBLE: 0, POSSIBLE: 1, NOT_ELIGIBLE: 2}
STALE_AFTER_MONTHS = 12


@dataclass
class Reason:
    outcome: str                # MET | NOT_MET | UNSURE | INFO | CHECK
    text: str


@dataclass
class Match:
    fellowship: Fellowship
    reasons: list[Reason] = field(default_factory=list)
    deadline: Deadline | None = None    # next final deadline, if announced
    field_fit: int = 0                  # 2 named field, 1 any field, 0 none

    @property
    def status(self) -> str:
        outcomes = {r.outcome for r in self.reasons}
        if NOT_MET in outcomes:
            return NOT_ELIGIBLE
        if UNSURE in outcomes:
            return POSSIBLE
        return ELIGIBLE

    @property
    def to_confirm(self) -> list[Reason]:
        """Rules the user has to confirm themselves."""
        return [r for r in self.reasons if r.outcome == CHECK]

    @property
    def is_open(self) -> bool:
        return self.deadline is not None or self.fellowship.rolling

    def days_left(self, today: date) -> int | None:
        return (self.deadline.date - today).days if self.deadline else None


def _years(a: date, b: date) -> float:
    return (b - a).days / 365.25


def _fmt_years(y: float) -> str:
    y = round(y, 1)
    return f"{y:g} year" + ("" if y == 1 else "s")


def _names(codes: list[str]) -> str:
    return ", ".join(codes)


def _career_stage(f: Fellowship, r: Researcher, on: date) -> list[Reason]:
    if not f.phd_required:
        return []
    lo, hi = f.min_years_since_phd, f.max_years_since_phd
    window = ("" if lo is None and hi is None
              else f"up to {_fmt_years(hi)}" if lo is None
              else f"{_fmt_years(lo)} to {_fmt_years(hi)}" if hi is not None
              else f"at least {_fmt_years(lo)}")
    if r.phd_date is None:
        if r.phd_expected is not None:
            if lo and _years(r.phd_expected, on) < lo:
                return [Reason(NOT_MET,
                               f"Needs at least {_fmt_years(lo)} since the PhD; "
                               f"yours is expected {r.phd_expected:%b %Y}.")]
            return [Reason(UNSURE,
                           f"Your PhD is expected {r.phd_expected:%b %Y}. Check "
                           f"whether {f.funder} accepts applicants before the "
                           f"PhD is awarded.")]
        return [Reason(UNSURE, "Add the date your PhD was awarded to check the "
                               "career-stage rule" + (f" ({window} since the "
                                                      f"PhD)." if window else "."))]

    years = _years(r.phd_date, on)
    if years < 0:
        return [Reason(UNSURE, "Your PhD date is after the deadline; check it.")]
    effective = years
    breaks = r.career_break_months / 12
    if f.career_breaks_extend and breaks:
        effective = max(0.0, years - breaks)
    at = f"at the {on:%d %b %Y} deadline"
    counted = (f"{_fmt_years(effective)} counting your career break"
               if effective != years else _fmt_years(years))

    if lo is not None and effective < lo:
        return [Reason(NOT_MET, f"Needs at least {_fmt_years(lo)} since the "
                                f"PhD; you will have {counted} {at}.")]
    if hi is not None and effective > hi:
        if not f.career_breaks_extend and breaks and years - breaks <= hi:
            return [Reason(UNSURE,
                           f"Allows up to {_fmt_years(hi)} since the PhD; you "
                           f"will have {_fmt_years(years)} {at}, or "
                           f"{_fmt_years(years - breaks)} without your career "
                           f"break. Check whether {f.funder} allows for breaks.")]
        return [Reason(NOT_MET, f"Allows up to {_fmt_years(hi)} since the PhD; "
                                f"you will have {counted} {at}.")]
    if lo is None and hi is None:
        return [Reason(MET, "Requires a PhD, which you have.")]
    return [Reason(MET, f"Within the career-stage window ({window} since the "
                        f"PhD): you will have {counted} {at}.")]


def _nationality(f: Fellowship, r: Researcher) -> list[Reason]:
    if f.nationalities is None and not f.excluded_nationalities:
        return []
    if not r.nationalities:
        return [Reason(UNSURE, "Add your nationality to check this fellowship's "
                               "nationality rule.")]
    ok = [n for n in r.nationalities
          if (f.nationalities is None or n in f.nationalities)
          and n not in f.excluded_nationalities]
    if ok:
        return [Reason(MET, f"Your nationality ({_names(ok)}) is accepted.")]
    if f.nationalities is not None:
        return [Reason(NOT_MET, f"Open to nationals of {_names(f.nationalities)} "
                                f"only.")]
    return [Reason(NOT_MET, f"Not open to nationals of "
                            f"{_names(f.excluded_nationalities)}.")]


def _residence(f: Fellowship, r: Researcher) -> list[Reason]:
    if f.residence is None:
        return []
    if r.residence is None:
        return [Reason(UNSURE, "Add the country you live in to check the "
                               "residence rule.")]
    if r.residence in f.residence:
        return [Reason(MET, f"You live in {r.residence}, as required.")]
    return [Reason(NOT_MET, f"Applicants must live in {_names(f.residence)}.")]


def _hosts(f: Fellowship, r: Researcher) -> tuple[list[Reason], list[str] | None]:
    """The reasons, and the host countries still possible (None = any)."""
    allowed = f.host_countries
    if r.target_hosts:
        possible = [c for c in r.target_hosts
                    if (allowed is None or c in allowed)
                    and c not in f.excluded_host_countries]
        if not possible:
            where = (f"in {_names(allowed)}" if allowed is not None
                     else f"outside {_names(f.excluded_host_countries)}")
            return [Reason(NOT_MET, f"The work must be {where}; you chose "
                                    f"{_names(r.target_hosts)}.")], []
        return [Reason(MET, f"Can be held in {_names(possible)}.")], possible
    if allowed is not None:
        return [Reason(INFO, f"The work must be in {_names(allowed)}.")], allowed
    return [], None


def _months_in(r: Researcher, country: str, start: date, end: date) -> float:
    days = 0
    for s in r.stays:
        if s.country != country:
            continue
        a, b = max(s.start, start), min(s.end or end, end)
        if b > a:
            days += (b - a).days
    return days / 30.44


def _mobility(f: Fellowship, r: Researcher, hosts: list[str] | None,
              on: date) -> list[Reason]:
    m = f.mobility
    if m is None:
        return []
    rule = (f"no more than {m.max_months_in_host} months in the host country "
            f"in the {m.window_years} years before the deadline")
    if not r.stays:
        return [Reason(UNSURE, f"Mobility rule: {rule}. Add where you have "
                               f"lived to check it.")]
    if hosts is None:
        return [Reason(UNSURE, f"Mobility rule: {rule}. Choose where you'd go "
                               f"to check it.")]
    start = on - timedelta(days=round(m.window_years * 365.25))
    fine = [h for h in hosts if _months_in(r, h, start, on) <= m.max_months_in_host]
    if fine:
        return [Reason(MET, f"Meets the mobility rule for {_names(fine)} "
                            f"({rule}).")]
    return [Reason(NOT_MET, f"Mobility rule: {rule}. You have lived in "
                            f"{_names(hosts)} for longer than that.")]


def _track(f: Fellowship, r: Researcher) -> list[Reason]:
    if f.track == "any":
        return []
    wanted = f.track == "clinical"
    label = "clinicians" if wanted else "non-clinical researchers"
    if r.clinical is None:
        return [Reason(UNSURE, f"For {label}; say whether you are clinically "
                               f"qualified to check this.")]
    if r.clinical == wanted:
        return [Reason(MET, f"For {label}, which matches you.")]
    return [Reason(NOT_MET, f"For {label} only.")]


LEVEL_LABEL = {"masters_student": "Master's students", "phd_student": "PhD students",
               "postdoc": "postdocs", "faculty": "faculty"}


def _career_level(f: Fellowship, r: Researcher) -> list[Reason]:
    if not f.career_levels:
        return []
    who = ", ".join(LEVEL_LABEL[x] for x in f.career_levels)
    if r.career_level is None:
        return [Reason(UNSURE, f"For {who}; add your career stage to check this.")]
    if r.career_level in f.career_levels:
        return [Reason(MET, f"Open to {who}, which includes you.")]
    return [Reason(NOT_MET, f"Only for {who}.")]


def _membership(f: Fellowship) -> list[Reason]:
    if not f.membership:
        return []
    time = (f" for at least {f.membership_min_months} months"
            if f.membership_min_months else "")
    return [Reason(CHECK, f"Requires membership of {f.membership}{time}.")]


def _field_fit(f: Fellowship, r: Researcher) -> int:
    if r.fields and set(r.fields) & set(f.fields):
        return 2
    return 1 if "any" in f.fields else 0


def match(f: Fellowship, r: Researcher, today: date) -> Match:
    deadline = f.next_deadline(today)
    on = deadline.date if deadline else today
    result = Match(f, deadline=deadline, field_fit=_field_fit(f, r))

    host_reasons, hosts = _hosts(f, r)
    result.reasons += _career_stage(f, r, on)
    result.reasons += _nationality(f, r)
    result.reasons += _residence(f, r)
    result.reasons += host_reasons
    result.reasons += _mobility(f, r, hosts, on)
    result.reasons += _track(f, r)
    result.reasons += _career_level(f, r)
    result.reasons += _membership(f)
    result.reasons += [Reason(CHECK, rule[:1].upper() + rule[1:])
                       for rule in f.other_rules]

    if deadline is None and not f.rolling:
        last = f.deadlines[-1].date if f.deadlines else None
        if f.annual and last:
            # Only the month is shown, so 29 Feb can stand in for 28 Feb.
            expected = date(last.year + 1, last.month, 1)
            result.reasons.append(Reason(
                INFO, f"The last deadline was {last:%d %b %Y}; the next call "
                      f"is expected around {expected:%b %Y}."))
        else:
            result.reasons.append(Reason(INFO, "No upcoming deadline is listed."))
    elif deadline is not None and deadline.estimated:
        result.reasons.append(Reason(
            INFO, f"The {deadline.date:%d %b %Y} deadline is estimated from "
                  f"previous years and not yet announced."))

    age = f.months_since_verified(today)
    if f.custom:
        result.reasons.append(Reason(INFO, "You added this entry yourself."))
    elif age is None:
        # Nobody has confirmed these details against the funder's page, so
        # Galley can't say "eligible" on the strength of them.
        result.reasons.append(Reason(
            UNSURE, f"These details haven't been checked against the funder's "
                    f"page yet; confirm them at {f.url}."))
    elif age > STALE_AFTER_MONTHS:
        result.reasons.append(Reason(
            INFO, f"These rules were last checked {f.verified:%b %Y}; confirm "
                  f"them at {f.url}."))
    return result


def match_all(fellowships: list[Fellowship], r: Researcher,
              today: date) -> list[Match]:
    """All fellowships, best first: eligible before possibly before not, the
    researcher's own field first, then the nearest open deadline."""
    matches = [match(f, r, today) for f in fellowships]

    def key(m: Match):
        days = m.days_left(today)
        return (STATUS_ORDER[m.status], -m.field_fit,
                0 if m.is_open else 1,
                days if days is not None else 10**6,
                m.fellowship.name.lower())

    return sorted(matches, key=key)
