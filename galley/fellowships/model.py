"""Fellowships and researchers: the two things the matcher compares.

A fellowship is a small JSON file in galley/fellowships/data/ (see the README
there for the format). A researcher profile is what the user tells Galley
about themselves; it never leaves their computer.

Countries are ISO 3166 two-letter codes ("IN", "DE", "GB"). Dates are
YYYY-MM-DD.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .requirements import Requirements

DATA_DIR = Path(__file__).resolve().parent / "data"
CUSTOM_PREFIX = "custom-"
# Where users report an entry that is wrong or out of date.
REPORT_URL = "https://github.com/rahulnccs/galley-check/issues/new"


def user_fellowship_dir() -> Path:
    """Where the user's own entries are kept: next to their journal profiles,
    outside the bundled data, so a database refresh never touches them."""
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent / "fellowships"

# Life-science fields a fellowship can be restricted to, and a researcher can
# work in. "any" on a fellowship means any life-science field.
FIELDS = {
    "any",
    "molecular_cell_biology",
    "neuroscience",
    "immunology_infection",
    "genetics_genomics",
    "ecology_evolution",
    "plant_science",
    "microbiology",
    "structural_biology",
    "bioinformatics",
    "biomedical_clinical",
}
TRACKS = {"any", "clinical", "non_clinical"}
# What kind of funding an entry is. All are life-science only.
CATEGORIES = {"postdoc", "phd", "travel"}
# Career levels an entry can be open to, and a researcher can be at.
CAREER_LEVELS = {"masters_student", "phd_student", "postdoc", "faculty"}
# Who a category is for when an entry doesn't say. Postdoc fellowships are
# decided by the PhD rules instead, and travel grants vary too much to assume.
DEFAULT_LEVELS = {"phd": ["masters_student", "phd_student"]}
TRAVEL_PURPOSES = {"conference", "lab_visit", "course", "fieldwork", "other"}
DEADLINE_KINDS = {"final", "internal", "pre_proposal", "call_opens"}


def _date(value, what: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{what} must be a date written YYYY-MM-DD, not {value!r}")


def _countries(value, what: str) -> list[str] | None:
    """None means no restriction; otherwise a list of upper-case codes."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{what} must be a list of country codes, or left out")
    codes = [str(c).strip().upper() for c in value]
    bad = [c for c in codes if len(c) != 2 or not c.isalpha()]
    if bad:
        raise ValueError(f"{what}: {', '.join(bad)} not two-letter country codes")
    return codes


@dataclass
class Deadline:
    kind: str                   # see DEADLINE_KINDS
    date: date
    time: str | None = None     # "17:00", in the funder's time zone
    timezone: str | None = None # "Europe/Berlin"
    estimated: bool = False     # inferred from previous years, not announced
    label: str | None = None    # e.g. "Letters of reference due"


@dataclass
class Mobility:
    """'Must not have lived in the host country for more than N months in
    the Y years before the deadline' -- the most common mobility rule."""
    max_months_in_host: int
    window_years: int


@dataclass
class Fellowship:
    id: str
    name: str
    funder: str
    url: str
    verified: date | None
    fields: list[str] = field(default_factory=lambda: ["any"])
    track: str = "any"
    min_years_since_phd: float | None = None
    max_years_since_phd: float | None = None
    phd_required: bool = True
    career_breaks_extend: bool = False
    nationalities: list[str] | None = None          # allowed; None = any
    excluded_nationalities: list[str] = field(default_factory=list)
    residence: list[str] | None = None              # where applicants must live
    host_countries: list[str] | None = None         # where the work happens
    excluded_host_countries: list[str] = field(default_factory=list)
    mobility: Mobility | None = None
    deadlines: list[Deadline] = field(default_factory=list)
    rolling: bool = False
    annual: bool = True
    amount: str | None = None
    duration_months: int | None = None
    notes: str | None = None
    other_rules: list[str] = field(default_factory=list)  # checked by the user
    requirements: Requirements | None = None
    category: str = "postdoc"
    career_levels: list[str] = field(default_factory=list)  # empty = not checked
    purpose: str | None = None              # travel grants: what it pays for
    membership: str | None = None           # society membership required
    membership_min_months: int | None = None
    template: bool = False
    custom: bool = False        # added by the user, not from the database
    path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict, path: Path | None = None) -> "Fellowship":
        where = f"{path.name}: " if path else ""
        try:
            return cls._from_dict(data, path)
        except (KeyError, TypeError, ValueError) as e:
            msg = f"missing {e}" if isinstance(e, KeyError) else str(e)
            raise ValueError(f"{where}{msg}") from None

    @classmethod
    def _from_dict(cls, data: dict, path: Path | None) -> "Fellowship":
        custom = bool(data.get("custom"))
        if custom and not str(data.get("name") or "").strip():
            raise ValueError("give the entry a name")
        fields_ = list(data.get("fields") or ["any"])
        unknown = [f for f in fields_ if f not in FIELDS]
        if unknown:
            raise ValueError(f"unknown field(s) {', '.join(unknown)}; "
                             f"use {', '.join(sorted(FIELDS))}")
        category = data.get("category", "postdoc")
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(sorted(CATEGORIES))}")
        levels = data.get("career_levels")
        levels = list(DEFAULT_LEVELS.get(category, [])) if levels is None else list(levels)
        bad = [x for x in levels if x not in CAREER_LEVELS]
        if bad:
            raise ValueError(f"unknown career level(s) {', '.join(bad)}; "
                             f"use {', '.join(sorted(CAREER_LEVELS))}")
        purpose = data.get("purpose")
        if purpose is not None and purpose not in TRAVEL_PURPOSES:
            raise ValueError(f"purpose must be one of {', '.join(sorted(TRAVEL_PURPOSES))}")
        track = data.get("track", "any")
        if track not in TRACKS:
            raise ValueError(f'track must be one of {", ".join(sorted(TRACKS))}')

        stage = data.get("career_stage") or {}
        mob = data.get("mobility")
        deadlines = []
        for d in data.get("deadlines") or []:
            kind = d.get("kind", "final")
            if kind not in DEADLINE_KINDS:
                raise ValueError(f"deadline kind must be one of "
                                 f"{', '.join(sorted(DEADLINE_KINDS))}")
            deadlines.append(Deadline(
                kind=kind, date=_date(d["date"], "deadline date"),
                time=d.get("time"), timezone=d.get("timezone"),
                estimated=bool(d.get("estimated")), label=d.get("label")))

        def years(key):
            v = stage.get(key)
            return None if v is None else float(v)

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            # The user's own entries need only a name; the database's need
            # a funder and an official page.
            funder=str(data.get("funder") or "") if custom else str(data["funder"]),
            url=str(data.get("url") or "") if custom else str(data["url"]),
            verified=_date(data.get("verified"), "verified"),
            fields=fields_,
            track=track,
            min_years_since_phd=years("min_years_since_phd"),
            max_years_since_phd=years("max_years_since_phd"),
            # With no career_stage section, career stage isn't checked.
            phd_required=bool(stage.get("phd_required", bool(stage))),
            career_breaks_extend=bool(stage.get("career_breaks_extend", False)),
            nationalities=_countries(data.get("nationalities"), "nationalities"),
            excluded_nationalities=_countries(
                data.get("excluded_nationalities") or [], "excluded_nationalities"),
            residence=_countries(data.get("residence"), "residence"),
            host_countries=_countries(data.get("host_countries"), "host_countries"),
            excluded_host_countries=_countries(
                data.get("excluded_host_countries") or [], "excluded_host_countries"),
            mobility=(Mobility(int(mob["max_months_in_host"]), int(mob["window_years"]))
                      if mob else None),
            deadlines=sorted(deadlines, key=lambda d: d.date),
            rolling=bool(data.get("rolling")),
            annual=bool(data.get("annual", True)),
            amount=data.get("amount"),
            duration_months=data.get("duration_months"),
            notes=data.get("notes"),
            other_rules=[str(x) for x in data.get("other_rules") or []],
            category=category,
            career_levels=levels,
            purpose=purpose,
            membership=data.get("membership") or None,
            membership_min_months=(int(data["membership_min_months"])
                                   if data.get("membership_min_months") else None),
            requirements=(Requirements.from_dict(data["requirements"])
                          if data.get("requirements") else None),
            template=bool(data.get("template")),
            custom=custom,
            path=path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "Fellowship":
        path = Path(path)
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), path)

    def next_deadline(self, today: date, kind: str = "final") -> Deadline | None:
        """The first deadline of this kind on or after today."""
        for d in self.deadlines:
            if d.kind == kind and d.date >= today:
                return d
        return None

    def report_problem_url(self) -> str | None:
        """A link that opens a pre-filled GitHub issue about this entry. It
        names the entry only; nothing about the user is included. None for
        the user's own entries, which the maintainer can't fix."""
        if self.custom:
            return None
        from urllib.parse import urlencode
        body = (f"Fellowship: {self.name} ({self.id})\n"
                f"Official page: {self.url}\n"
                f"Last verified: {self.verified or 'never'}\n\n"
                f"What is wrong or out of date?\n\n")
        return REPORT_URL + "?" + urlencode({
            "title": f"Fellowship entry: {self.name}",
            "body": body, "labels": "fellowship-data"})

    def months_since_verified(self, today: date) -> float | None:
        if self.verified is None:
            return None
        return (today - self.verified).days / 30.44


@dataclass
class Stay:
    """A period the researcher lived in a country. `end` None means now."""
    country: str
    start: date
    end: date | None = None


@dataclass
class Researcher:
    """What the user tells Galley about themselves. Anything left as None is
    unknown, and the matcher says "possibly eligible" rather than guessing."""
    phd_date: date | None = None        # date the PhD was awarded
    phd_expected: date | None = None    # for those still finishing
    career_break_months: float = 0      # parental leave, illness, caring
    nationalities: list[str] = field(default_factory=list)
    residence: str | None = None        # country they live in now
    stays: list[Stay] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    clinical: bool | None = None
    target_hosts: list[str] = field(default_factory=list)  # where they'd go
    career_level: str | None = None     # see CAREER_LEVELS


def _load_folder(folder: Path, include_templates: bool) -> list[Fellowship]:
    out = []
    try:
        paths = sorted(folder.glob("*.json"))
    except OSError:
        return out
    for path in paths:
        f = Fellowship.load(path)
        if f.template and not include_templates:
            continue
        out.append(f)
    return out


def load_fellowships(folder: Path | None = None,
                     include_templates: bool = False,
                     custom_folder: Path | None = None,
                     include_custom: bool = True,
                     downloaded_folder: Path | None = None) -> list[Fellowship]:
    """The database's fellowships plus the user's own entries.

    The database is the copy bundled with Galley, updated by any list the
    user downloaded with "Check for Updates".

    A database file that doesn't parse raises, with the file name in the
    message, so a broken entry is fixed rather than silently skipped. A
    broken custom entry is skipped instead: the user may have edited it by
    hand, and one bad file shouldn't hide the whole list.
    """
    out = _load_folder(folder or DATA_DIR, include_templates)
    if folder is None:
        # Entries from "Check for Updates" replace bundled ones with the same
        # id and add new ones. A damaged download is skipped, not fatal.
        from .update import downloaded_dir
        newer: dict[str, Fellowship] = {}
        try:
            paths = sorted((downloaded_folder or downloaded_dir()).glob("*.json"))
        except OSError:
            paths = []
        for path in paths:
            try:
                f = Fellowship.load(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if f.template and not include_templates:
                continue
            newer[f.id] = f
        out = [newer.pop(f.id, f) for f in out] + list(newer.values())
    if include_custom:
        custom_folder = custom_folder or user_fellowship_dir()
        try:
            paths = sorted(custom_folder.glob("*.json"))
        except OSError:
            paths = []
        for path in paths:
            try:
                f = Fellowship.load(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            f.custom = True
            out.append(f)
    ids = [f.id for f in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate fellowship id(s): {', '.join(sorted(dupes))}")
    return out


def save_custom_fellowship(data: dict, folder: Path | None = None) -> Fellowship:
    """Save one of the user's own entries and return it.

    Only a name is needed; everything else (deadlines, rules, a link) is
    optional and uses the same keys as the database. A new entry gets an id
    starting "custom-", so it can never clash with a database entry. Saving
    with an existing custom id replaces that entry.
    """
    folder = folder or user_fellowship_dir()
    data = dict(data, custom=True)
    data.pop("template", None)
    if not data.get("id"):
        stem = re.sub(r"[^a-z0-9]+", "-",
                      str(data.get("name", "")).lower()).strip("-") or "entry"
        base, n = CUSTOM_PREFIX + stem, 2
        data["id"] = base
        while (folder / f"{data['id']}.json").exists():
            data["id"], n = f"{base}-{n}", n + 1
    elif not str(data["id"]).startswith(CUSTOM_PREFIX):
        raise ValueError(f'custom entry ids start with "{CUSTOM_PREFIX}"')
    fellowship = Fellowship.from_dict(data)     # validate before writing
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{data['id']}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    fellowship.path = path
    return fellowship


def delete_custom_fellowship(fellowship_id: str, folder: Path | None = None) -> bool:
    """Remove one of the user's own entries. Database entries are left alone."""
    if not fellowship_id.startswith(CUSTOM_PREFIX):
        return False
    path = (folder or user_fellowship_dir()) / f"{fellowship_id}.json"
    try:
        path.unlink()
    except OSError:
        return False
    return True


def researcher_path() -> Path:
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent / "researcher.json"


def researcher_to_dict(r: Researcher) -> dict:
    iso = lambda d: d.isoformat() if d else None    # noqa: E731
    return {"phd_date": iso(r.phd_date), "phd_expected": iso(r.phd_expected),
            "career_break_months": r.career_break_months,
            "nationalities": r.nationalities, "residence": r.residence,
            "stays": [{"country": s.country, "start": iso(s.start), "end": iso(s.end)}
                      for s in r.stays],
            "fields": r.fields, "clinical": r.clinical,
            "target_hosts": r.target_hosts, "career_level": r.career_level}


def researcher_from_dict(data: dict) -> Researcher:
    return Researcher(
        phd_date=_date(data.get("phd_date"), "phd_date"),
        phd_expected=_date(data.get("phd_expected"), "phd_expected"),
        career_break_months=float(data.get("career_break_months") or 0),
        nationalities=_countries(data.get("nationalities") or [], "nationalities"),
        residence=(data.get("residence") or "").upper() or None,
        stays=[Stay(s["country"].upper(), _date(s["start"], "start"),
                    _date(s.get("end"), "end"))
               for s in data.get("stays") or []],
        fields=[f for f in data.get("fields") or [] if f in FIELDS],
        clinical=data.get("clinical"),
        target_hosts=_countries(data.get("target_hosts") or [], "target_hosts"),
        career_level=(data.get("career_level")
                      if data.get("career_level") in CAREER_LEVELS else None))


def load_researcher(path: Path | None = None) -> Researcher:
    """The saved profile, or an empty one. Never raises: a damaged file just
    means starting the profile again."""
    try:
        data = json.loads((path or researcher_path()).read_text(encoding="utf-8"))
        return researcher_from_dict(data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Researcher()


def save_researcher(r: Researcher, path: Path | None = None) -> None:
    path = path or researcher_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(researcher_to_dict(r), indent=2), encoding="utf-8")
