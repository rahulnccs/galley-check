"""Fellowships and researchers: the two things the matcher compares.

A fellowship is a small JSON file in galley/fellowships/data/ (see the README
there for the format). A researcher profile is what the user tells Galley
about themselves; it never leaves their computer.

Countries are ISO 3166 two-letter codes ("IN", "DE", "GB"). Dates are
YYYY-MM-DD.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

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
DEADLINE_KINDS = {"final", "internal", "pre_proposal", "call_opens", "referees"}


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
    template: bool = False
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
        fields_ = list(data.get("fields") or ["any"])
        unknown = [f for f in fields_ if f not in FIELDS]
        if unknown:
            raise ValueError(f"unknown field(s) {', '.join(unknown)}; "
                             f"use {', '.join(sorted(FIELDS))}")
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
            funder=str(data["funder"]),
            url=str(data["url"]),
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
            template=bool(data.get("template")),
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


def load_fellowships(folder: Path | None = None,
                     include_templates: bool = False) -> list[Fellowship]:
    """Every fellowship in the folder. A file that doesn't parse raises, with
    the file name in the message, so a broken entry is fixed rather than
    silently skipped."""
    folder = folder or DATA_DIR
    out = []
    for path in sorted(folder.glob("*.json")):
        f = Fellowship.load(path)
        if f.template and not include_templates:
            continue
        out.append(f)
    ids = [f.id for f in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate fellowship id(s): {', '.join(sorted(dupes))}")
    return out
