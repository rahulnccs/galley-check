"""Projects, samples, the analyses each sample went through, and notebook
entries. One JSON file per project in the user's Galley settings folder.

Galley never copies or moves research data: an analysis only records where
the user keeps it (a raw-data folder and an analysis folder), so the files
stay where they are and Galley can open them.
"""
from __future__ import annotations

import csv
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

DEFAULT_ANALYSES = ["RNA-seq", "DNA-seq", "Metabolomics", "Proteomics",
                    "Amplicon (16S/ITS)", "Imaging"]
ANALYSIS_STATUSES = ["planned", "in_progress", "done", "failed"]


def projects_dir() -> Path:
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent / "projects"


@dataclass
class Analysis:
    kind: str                       # "RNA-seq"
    status: str = "done"
    data_path: str = ""             # raw data folder
    results_path: str = ""          # analysis / results folder
    date: str = ""                  # YYYY-MM-DD
    notes: str = ""

    def __post_init__(self):
        if self.status not in ANALYSIS_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ANALYSIS_STATUSES)}")

    def folders(self) -> list[tuple[str, str]]:
        """(label, path) for each folder the user recorded."""
        return [(lab, p) for lab, p in (("raw data", self.data_path),
                                        ("analysis", self.results_path)) if p]


BOX_COLORS = ["blue", "green", "amber", "purple", "indigo", "red"]


@dataclass
class SampleBox:
    """A coloured box of information on a sample's page: what was done or
    found, and optionally the folder holding the data that goes with it."""
    id: str
    title: str = ""
    text: str = ""
    folder: str = ""
    color: str = "blue"             # one of BOX_COLORS
    date: str = ""                  # YYYY-MM-DD, when it was added


@dataclass
class Sample:
    sample_id: str
    description: str = ""
    collected: str = ""             # YYYY-MM-DD, or free text
    notes: str = ""
    analyses: list[Analysis] = field(default_factory=list)
    boxes: list[SampleBox] = field(default_factory=list)

    def analysis(self, kind: str) -> Analysis | None:
        for a in self.analyses:
            if a.kind.lower() == kind.lower():
                return a
        return None

    def set_analysis(self, a: Analysis) -> None:
        """Add an analysis, or replace the one of the same kind."""
        self.analyses = [x for x in self.analyses if x.kind.lower() != a.kind.lower()]
        self.analyses.append(a)

    def add_box(self, title: str = "", on: date | None = None) -> SampleBox:
        """A new box, in the next colour along."""
        color = BOX_COLORS[len(self.boxes) % len(BOX_COLORS)]
        box = SampleBox(uuid.uuid4().hex[:12], title, color=color,
                        date=(on or date.today()).isoformat())
        self.boxes.append(box)
        return box

    def remove_box(self, box_id: str) -> None:
        self.boxes = [b for b in self.boxes if b.id != box_id]


@dataclass
class NoteEntry:
    id: str
    date: str                       # YYYY-MM-DD
    text: str
    samples: list[str] = field(default_factory=list)   # linked sample IDs


@dataclass
class Project:
    id: str
    name: str
    readme: str = ""
    owner: str = ""
    started: str = ""
    analysis_types: list[str] = field(default_factory=lambda: list(DEFAULT_ANALYSES[:3]))
    samples: list[Sample] = field(default_factory=list)
    notebook: list[NoteEntry] = field(default_factory=list)
    updated: str = ""

    # -- samples --------------------------------------------------------------
    def sample(self, sample_id: str) -> Sample | None:
        for s in self.samples:
            if s.sample_id == sample_id:
                return s
        return None

    def add_sample(self, s: Sample) -> Sample:
        s.sample_id = s.sample_id.strip()
        if not s.sample_id:
            raise ValueError("Give the sample an ID.")
        if self.sample(s.sample_id):
            raise ValueError(f"There is already a sample {s.sample_id}.")
        self.samples.append(s)
        return s

    def remove_sample(self, sample_id: str) -> None:
        self.samples = [s for s in self.samples if s.sample_id != sample_id]

    def count(self, kind: str, status: str | None = "done") -> int:
        """Samples with this analysis (in this status; None = any status)."""
        return sum(1 for s in self.samples
                   if (a := s.analysis(kind)) and (status is None or a.status == status))

    # -- notebook -------------------------------------------------------------
    def add_note(self, text: str, on: date | None = None,
                 samples: list[str] | None = None) -> NoteEntry:
        if not text.strip():
            raise ValueError("The entry is empty.")
        entry = NoteEntry(uuid.uuid4().hex[:12], (on or date.today()).isoformat(),
                          text.strip(), list(samples or []))
        self.notebook.append(entry)
        return entry

    def notes_for(self, sample_id: str) -> list[NoteEntry]:
        return [n for n in self.notebook if sample_id in n.samples]

    def unknown_samples(self, ids: list[str]) -> list[str]:
        return [i for i in ids if not self.sample(i)]

    # -- storage --------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        samples = [Sample(**{**s, "analyses": [Analysis(**a) for a in s.get("analyses", [])],
                             "boxes": [SampleBox(**b) for b in s.get("boxes", [])]})
                   for s in d.get("samples", [])]
        notes = [NoteEntry(**n) for n in d.get("notebook", [])]
        known = {k: v for k, v in d.items()
                 if k in cls.__dataclass_fields__ and k not in ("samples", "notebook")}
        return cls(**known, samples=samples, notebook=notes)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    return s or "project"


def new_project(name: str, folder: Path | None = None) -> Project:
    if not name.strip():
        raise ValueError("Give the project a name.")
    folder = folder or projects_dir()
    base, n, pid = _slug(name), 2, _slug(name)
    while (folder / f"{pid}.json").exists():
        pid, n = f"{base}-{n}", n + 1
    p = Project(pid, name.strip(), started=date.today().isoformat())
    save_project(p, folder)
    return p


def save_project(p: Project, folder: Path | None = None) -> Path:
    folder = folder or projects_dir()
    folder.mkdir(parents=True, exist_ok=True)
    p.updated = datetime.now().isoformat(timespec="seconds")
    path = folder / f"{p.id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(p.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)                       # never leave a half-written file
    return path


def load_projects(folder: Path | None = None) -> list[Project]:
    """Every saved project, most recently updated first. A damaged file is
    skipped rather than hiding the others."""
    out = []
    try:
        paths = sorted((folder or projects_dir()).glob("*.json"))
    except OSError:
        return out
    for path in paths:
        try:
            out.append(Project.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(out, key=lambda p: p.updated, reverse=True)


def delete_project(project_id: str, folder: Path | None = None) -> bool:
    try:
        ((folder or projects_dir()) / f"{project_id}.json").unlink()
    except OSError:
        return False
    return True


# ---- sample sheets ------------------------------------------------------------
# A sample sheet is a CSV with one row per sample:
#   sample_id, description, collected, then for each analysis two optional
#   columns "<Analysis> data" and "<Analysis> analysis" holding folder paths,
#   e.g. "RNA-seq data", "RNA-seq analysis".

ID_COLUMNS = ("sample_id", "sample id", "sample", "id")
FOLDER_COLUMN = re.compile(r"^(?P<kind>.+?)\s+(?P<which>data|analysis|results|status)$",
                           re.I)


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)    # reasons, one per row


def import_sample_sheet(p: Project, path: str | Path) -> ImportResult:
    """Add the samples in a CSV sheet to a project. Existing samples get their
    folders updated; new analysis types are added to the project."""
    result = ImportResult()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError("The sheet has no rows.")
    headers = {h.strip().lower(): h for h in rows[0].keys() if h}
    id_col = next((headers[c] for c in ID_COLUMNS if c in headers), None)
    if id_col is None:
        raise ValueError('The sheet needs a "sample_id" column.')
    folder_cols = []
    for h in rows[0].keys():
        m = FOLDER_COLUMN.match((h or "").strip())
        if m:
            kind = next((t for t in p.analysis_types
                         if t.lower() == m.group("kind").strip().lower()),
                        m.group("kind").strip())
            which = m.group("which").lower()
            folder_cols.append((h, kind, {"data": "data", "status": "status"}
                                .get(which, "results")))

    def col(row, name):
        h = headers.get(name)
        return (row.get(h) or "").strip() if h else ""

    for n, row in enumerate(rows, start=2):
        sid = (row.get(id_col) or "").strip()
        if not sid:
            result.skipped.append(f"Row {n}: no sample ID")
            continue
        s = p.sample(sid)
        if s is None:
            s = p.add_sample(Sample(sid, col(row, "description"), col(row, "collected")))
            result.added += 1
        else:
            result.updated += 1
            s.description = col(row, "description") or s.description
            s.collected = col(row, "collected") or s.collected
        for h, kind, which in folder_cols:
            value = (row.get(h) or "").strip()
            if not value:
                continue
            a = s.analysis(kind) or Analysis(kind)
            if which == "status":
                status = value.lower().replace(" ", "_")
                if status in ANALYSIS_STATUSES:
                    a.status = status
            elif which == "data":
                a.data_path = value
            else:
                a.results_path = value
            s.set_analysis(a)
            if kind not in p.analysis_types:
                p.analysis_types.append(kind)
    return result


def export_sample_sheet(p: Project, path: str | Path) -> None:
    """Write the project's samples as a CSV sheet that import_sample_sheet reads."""
    kinds = list(p.analysis_types)
    for s in p.samples:
        for a in s.analyses:
            if a.kind not in kinds:
                kinds.append(a.kind)
    header = ["sample_id", "description", "collected"]
    for k in kinds:
        header += [f"{k} status", f"{k} data", f"{k} analysis"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for s in p.samples:
            row = [s.sample_id, s.description, s.collected]
            for k in kinds:
                a = s.analysis(k)
                row += [a.status, a.data_path, a.results_path] if a else ["", "", ""]
            w.writerow(row)
