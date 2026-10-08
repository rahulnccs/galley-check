"""The Projects screen: a README, a sample tracker and a lab notebook per
project, in the same iOS-style lists and soft palette as Fellowships.

Clicking a sample opens a menu of the analyses it went through; choosing one
opens that folder in Finder or Explorer. Galley only records where the data
lives, it never copies or moves it.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..projects import (ANALYSIS_STATUSES, DEFAULT_ANALYSES, Analysis, Sample,
                        delete_project, export_sample_sheet,
                        import_sample_sheet, load_projects, new_project,
                        save_project)
from .fellowships_page import (APPLE, SOFT, Card, Picker, Row, ScrollPage,
                               Segmented, apple_font, apple_stylesheet, day,
                               dot, field_row, filled_button, label, nav_bar,
                               pill, plain_button, tile_row)

README, SAMPLES, NOTEBOOK = 0, 1, 2
STATUS_LABEL = {"planned": "Planned", "in_progress": "In progress",
                "done": "Done", "failed": "Failed"}
STATUS_COLOR = {"planned": SOFT["grey"], "in_progress": SOFT["amber"],
                "done": SOFT["green"], "failed": SOFT["red"]}
# Colours for the per-analysis tiles, in turn.
TILE_COLORS = [SOFT["blue"], SOFT["indigo"], SOFT["green"], SOFT["purple"],
               SOFT["amber"], SOFT["red"], SOFT["grey"]]


def open_folder(parent: QWidget, path: str) -> bool:
    """Open a folder in Finder / Explorer, or say clearly why not."""
    p = Path(path).expanduser()
    if not p.exists():
        QMessageBox.warning(parent, "Folder not found",
                            f"{path}\n\nThis folder doesn't exist any more; it may "
                            f"have been moved, renamed, or be on a drive that "
                            f"isn't connected. Edit the analysis to update it.")
        return False
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
    return True


def parse_date(text: str) -> QDate:
    d = QDate.fromString(text or "", "yyyy-MM-dd")
    return d if d.isValid() else QDate.currentDate()


class ActionMenu(QFrame):
    """A popup list of actions, styled like the Picker's menu: large rows,
    an optional colour dot and a grey subtitle."""

    def __init__(self, title: str, items, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 18)
        card = QFrame()
        card.setObjectName("menuCard")
        card.setStyleSheet(f"""
            #menuCard {{ background: white; border-radius: 14px;
                         border: 1px solid {APPLE['fill']}; }}
            #menuRow {{ background: transparent; border: none; border-radius: 9px;
                        text-align: left; }}
            #menuRow:hover {{ background: #E8F1FF; }}""")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 60))
        card.setGraphicsEffect(shadow)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(2)
        head = QLabel(title)
        head.setStyleSheet(f"color:{APPLE['secondary']}; font-size:12px; "
                           f"font-weight:600; padding:2px 12px 6px 12px;")
        lay.addWidget(head)
        self.rows: list[QPushButton] = []
        for text, sub, color, action, enabled in items:
            row = QPushButton()
            row.setObjectName("menuRow")
            row.setCursor(Qt.PointingHandCursor)
            row.setMinimumHeight(48 if sub else 44)
            row.setMinimumWidth(300)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 4, 14, 4)
            rl.setSpacing(10)
            if color:
                rl.addWidget(dot(color))
            text_box = QVBoxLayout()
            text_box.setSpacing(0)
            t = QLabel(text)
            t.setStyleSheet("background:transparent; font-size:16px;"
                            + ("" if enabled else f" color:{APPLE['gray']};"))
            text_box.addWidget(t)
            if sub:
                st = QLabel(sub)
                st.setStyleSheet(f"background:transparent; font-size:12px; "
                                 f"color:{SOFT['red'] if not enabled else APPLE['secondary']};")
                text_box.addWidget(st)
            rl.addLayout(text_box, 1)
            for w in row.findChildren(QLabel):
                w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            row.clicked.connect(lambda _=False, a=action: self._run(a))
            lay.addWidget(row)
            self.rows.append(row)
        outer.addWidget(card)

    def _run(self, action):
        self.close()
        action()


# ---- dialogs ----------------------------------------------------------------

def folder_field(parent: QWidget, value: str) -> tuple[QWidget, QLineEdit]:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    edit = QLineEdit(value)
    edit.setPlaceholderText("Choose a folder, or paste its path")
    browse = QPushButton("Choose…")

    def choose():
        path = QFileDialog.getExistingDirectory(parent, "Choose a folder", edit.text())
        if path:
            edit.setText(path)
    browse.clicked.connect(choose)
    lay.addWidget(edit, 1)
    lay.addWidget(browse)
    return w, edit


class SampleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a Sample")
        self.setMinimumWidth(420)
        form = QFormLayout()
        self.sample_id = QLineEdit()
        self.sample_id.setPlaceholderText("e.g. M01")
        self.description = QLineEdit()
        self.description.setPlaceholderText("e.g. Caecum, day 7, high-fat diet")
        self.collected = QLineEdit()
        self.collected.setPlaceholderText("YYYY-MM-DD, optional")
        form.addRow("Sample ID", self.sample_id)
        form.addRow("Description", self.description)
        form.addRow("Collected", self.collected)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def sample(self) -> Sample:
        return Sample(self.sample_id.text().strip(), self.description.text().strip(),
                      self.collected.text().strip())


class AnalysisDialog(QDialog):
    """Record that a sample went through an analysis, and where the data is."""

    def __init__(self, kinds: list[str], current: Analysis | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Analysis" if current else "Add an Analysis")
        self.setMinimumWidth(520)
        form = QFormLayout()
        self.kind = Picker()
        for k in kinds:
            self.kind.addItem(k, k)
        if current and current.kind not in kinds:
            self.kind.addItem(current.kind, current.kind)
        if current:
            self.kind.setCurrentIndex([d for _, d, _ in self.kind.items].index(current.kind))
            self.kind.setEnabled(False)
        self.status = Picker()
        for s in ANALYSIS_STATUSES:
            self.status.addItem(STATUS_LABEL[s], s, STATUS_COLOR[s])
        self.status.setCurrentIndex(ANALYSIS_STATUSES.index(current.status if current
                                                            else "done"))
        data_w, self.data = folder_field(self, current.data_path if current else "")
        res_w, self.results = folder_field(self, current.results_path if current else "")
        self.when = QDateEdit(parse_date(current.date if current else ""))
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("d MMM yyyy")
        self.notes = QPlainTextEdit(current.notes if current else "")
        self.notes.setFixedHeight(70)
        self.notes.setPlaceholderText("e.g. NovaSeq run 2026-14, lane 3")
        form.addRow("Analysis", self.kind)
        form.addRow("Status", self.status)
        form.addRow("Raw data folder", data_w)
        form.addRow("Analysis folder", res_w)
        form.addRow("Date", self.when)
        form.addRow("Notes", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def analysis(self) -> Analysis:
        return Analysis(self.kind.currentData(), self.status.currentData(),
                        self.data.text().strip(), self.results.text().strip(),
                        self.when.date().toPython().isoformat(),
                        self.notes.toPlainText().strip())


class NoteDialog(QDialog):
    def __init__(self, sample_ids: list[str], preset: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Notebook Entry")
        self.setMinimumWidth(520)
        form = QFormLayout()
        self.when = QDateEdit(QDate.currentDate())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("d MMM yyyy")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("What you did, what you saw, what's next")
        self.text.setMinimumHeight(140)
        self.samples = QLineEdit(", ".join(preset or []))
        self.samples.setPlaceholderText("Sample IDs, separated by commas (optional)")
        form.addRow("Date", self.when)
        form.addRow("Entry", self.text)
        form.addRow("Samples", self.samples)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def sample_ids(self) -> list[str]:
        return [s.strip() for s in self.samples.text().split(",") if s.strip()]


# ---- the page ----------------------------------------------------------------

class ProjectsPage(QWidget):
    def __init__(self, folder: Path | None = None):
        super().__init__()
        self.setObjectName("fellowships")       # shares the Fellowships styling
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(apple_stylesheet(apple_font()))
        self.folder = folder
        self.project = None
        self.tab = SAMPLES
        self.analysis_filter = "all"
        self.search = ""
        self.note_search = ""
        self.stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)
        self.show_home()

    # -- navigation ---------------------------------------------------------------
    def _show(self, w: QWidget):
        old = self.stack.currentWidget()
        self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        self.current = w

    def _save(self):
        save_project(self.project, self.folder)

    # -- home: the list of projects ---------------------------------------------
    def show_home(self):
        self.project = None
        page = ScrollPage()
        page.add(label("Projects", "largeTitle"))
        page.footnote("A short README, a sample tracker that opens each sample's "
                      "data folders, and a lab notebook. Saved on this computer only.")
        projects = load_projects(self.folder)
        page.header("Your projects")
        card = page.add(Card())
        for p in projects:
            done = sum(1 for s in p.samples for a in s.analyses if a.status == "done")
            sub = (f"{len(p.samples)} sample{'s' if len(p.samples) != 1 else ''} "
                   f"· {done} analyses done")
            if p.updated:
                sub += f" · updated {day(date.fromisoformat(p.updated[:10]))}"
            row = card.add(Row(p.name, sub, tappable=True))
            row.clicked.connect(lambda p=p: self.open_project(p.id))
        new = Row("New Project…", title_color=APPLE["blue"], tappable=True)
        new.clicked.connect(self._new_project)
        card.add(new)
        page.finish()
        self._show(page)

    def _new_project(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("New Project")
        dlg.setMinimumWidth(380)
        name = QLineEdit()
        name.setPlaceholderText("e.g. Gut microbiome in mice")
        form = QFormLayout()
        form.addRow("Name", name)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addLayout(form)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            p = new_project(name.text(), self.folder)
        except ValueError as e:
            QMessageBox.warning(self, "New project", str(e))
            return
        self.open_project(p.id, tab=README)

    # -- a project ------------------------------------------------------------------
    def open_project(self, project_id: str, tab: int | None = None):
        found = [p for p in load_projects(self.folder) if p.id == project_id]
        if not found:
            self.show_home()
            return
        self.project = found[0]
        if tab is not None:
            self.tab = tab
        self.render_project()

    def render_project(self):
        p = self.project
        page = ScrollPage()
        page.add(nav_bar("Projects", self.show_home))
        page.add(label(p.name, "detailTitle", wrap=True))
        tabs = Segmented(["README", "Samples", "Notebook"])
        tabs.select(self.tab, emit=False)
        tabs.changed.connect(self._switch_tab)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 6, 0, 2)
        hl.addWidget(tabs)
        hl.addStretch(1)
        page.add(holder)
        {README: self._readme, SAMPLES: self._samples,
         NOTEBOOK: self._notebook}[self.tab](page)
        page.finish()
        self._show(page)

    def _switch_tab(self, i: int):
        self.tab = i
        self.render_project()

    # -- README ---------------------------------------------------------------------
    def _readme(self, page: ScrollPage):
        p = self.project
        page.header("About")
        card = page.add(Card())
        self.r_name = QLineEdit(p.name)
        card.add(field_row("Name", self.r_name))
        self.r_owner = QLineEdit(p.owner)
        self.r_owner.setPlaceholderText("e.g. your name or lab")
        card.add(field_row("Owner", self.r_owner))
        self.r_started = QLineEdit(p.started)
        self.r_started.setPlaceholderText("YYYY-MM-DD")
        card.add(field_row("Started", self.r_started))

        page.header("Summary")
        card = page.add(Card())
        self.r_text = QPlainTextEdit(p.readme)
        self.r_text.setPlaceholderText("A few lines: the question, the system or "
                                       "organism, the design, where things stand.")
        self.r_text.setFixedHeight(150)
        self.r_text.setStyleSheet("border:none;")
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 6, 12, 6)
        bl.addWidget(self.r_text)
        card.add(box)

        page.header("Analyses in this project")
        card = page.add(Card())
        self.r_kinds = QLineEdit(", ".join(p.analysis_types))
        card.add(field_row("Types", self.r_kinds))
        page.footnote("Separated by commas. These are offered when you record an "
                      "analysis for a sample, e.g. " + ", ".join(DEFAULT_ANALYSES[:4]) + ".")

        page.header("")
        card = page.add(Card())
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(16, 12, 16, 12)
        save = filled_button("Save")
        save.clicked.connect(self.save_readme)
        al.addWidget(save)
        al.addStretch(1)
        delete = plain_button("Delete Project", destructive=True)
        delete.clicked.connect(self._delete_project)
        al.addWidget(delete)
        card.add(actions)

    def save_readme(self):
        p = self.project
        if not self.r_name.text().strip():
            QMessageBox.warning(self, "Name needed", "Give the project a name.")
            return
        p.name = self.r_name.text().strip()
        p.owner = self.r_owner.text().strip()
        p.started = self.r_started.text().strip()
        p.readme = self.r_text.toPlainText().strip()
        kinds = [k.strip() for k in self.r_kinds.text().split(",") if k.strip()]
        p.analysis_types = list(dict.fromkeys(kinds)) or list(DEFAULT_ANALYSES[:3])
        self._save()
        self.render_project()

    def _delete_project(self):
        if QMessageBox.question(self, "Delete project",
                                f"Delete “{self.project.name}” and its "
                                f"samples and notebook? Your data folders are not "
                                f"touched.") != QMessageBox.Yes:
            return
        delete_project(self.project.id, self.folder)
        self.show_home()

    # -- samples ------------------------------------------------------------------
    def _kinds(self) -> list[str]:
        kinds = list(self.project.analysis_types)
        for s in self.project.samples:
            for a in s.analyses:
                if a.kind not in kinds:
                    kinds.append(a.kind)
        return kinds

    def _samples(self, page: ScrollPage):
        p = self.project
        kinds = self._kinds()
        tiles = [("all", "Samples", SOFT["all"])] + [
            (k, k, TILE_COLORS[i % len(TILE_COLORS)]) for i, k in enumerate(kinds[:6])]
        counts = {"all": len(p.samples)} | {k: p.count(k, None) for k in kinds}
        if self.analysis_filter not in counts:
            self.analysis_filter = "all"
        page.add(tile_row(tiles, counts, self.analysis_filter, self._filter_analysis))

        search = QLineEdit(self.search)
        search.setPlaceholderText("Search sample IDs and descriptions")
        search.setClearButtonEnabled(True)
        search.setStyleSheet(f"background:white; border:1px solid {APPLE['fill']}; "
                             f"border-radius:10px; padding:8px 12px; font-size:15px;")
        search.textChanged.connect(self._search_samples)
        page.add(search)
        self.search_box = search

        shown = [s for s in p.samples
                 if (self.analysis_filter == "all" or s.analysis(self.analysis_filter))
                 and (not self.search or self.search.lower() in
                      f"{s.sample_id} {s.description}".lower())]
        page.header(f"Samples · {len(shown)}")
        card = page.add(Card())
        if not p.samples:
            card.add(Row("No samples yet", "Add them one by one, or import a sample "
                                           "sheet (CSV) with a sample_id column."))
        elif not shown:
            card.add(Row("No samples match", "Clear the search or choose Samples."))
        for s in shown:
            chips = QWidget()
            cl = QHBoxLayout(chips)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(4)
            for a in s.analyses:
                cl.addWidget(pill(a.kind, STATUS_COLOR[a.status]))
            row = Row(s.sample_id, s.description, trailing=chips, tappable=True)
            row.clicked.connect(lambda s=s, row=row: self.sample_menu(s, row))
            card.add(row)

        page.header("")
        card = page.add(Card())
        for text, handler in (("Add Sample…", self._add_sample),
                              ("Import Sample Sheet (CSV)…", self._import_sheet),
                              ("Export Sample Sheet (CSV)…", self._export_sheet)):
            r = Row(text, title_color=APPLE["blue"], tappable=True)
            r.clicked.connect(handler)
            card.add(r)
        page.footnote("Green: done \u00b7 amber: in progress \u00b7 grey: planned "
                      "\u00b7 red: failed. Click a sample to open its data folders. "
                      "A sample sheet has "
                      "a sample_id column and, for each analysis, columns such as "
                      "“RNA-seq data” and “RNA-seq analysis” "
                      "holding folder paths.")

    def _filter_analysis(self, key: str):
        self.analysis_filter = key
        self.render_project()

    def _search_samples(self, text: str):
        self.search = text
        self.render_project()
        self.search_box.setFocus()
        self.search_box.setCursorPosition(len(text))

    def sample_menu_items(self, s: Sample):
        """What clicking a sample offers: each analysis folder, then details."""
        items = []
        for a in s.analyses:
            for which, path in a.folders():
                exists = Path(path).expanduser().exists()
                items.append((f"{a.kind} · {which}",
                              path if exists else "Folder not found: " + path,
                              STATUS_COLOR[a.status],
                              lambda path=path: open_folder(self, path), exists))
            if not a.folders():
                items.append((a.kind, f"{STATUS_LABEL[a.status]} · no folder recorded",
                              STATUS_COLOR[a.status],
                              lambda s=s: self.open_sample(s.sample_id), True))
        items.append(("Sample details and analyses…", "", None,
                      lambda s=s: self.open_sample(s.sample_id), True))
        return items

    def sample_menu(self, s: Sample, anchor: QWidget):
        menu = ActionMenu(f"{s.sample_id} — open data", self.sample_menu_items(s), self)
        menu.adjustSize()
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        menu.move(pos.x() + 40, pos.y() - 8)
        menu.show()
        self._menu = menu

    def _add_sample(self):
        dlg = SampleDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            s = self.project.add_sample(dlg.sample())
        except ValueError as e:
            QMessageBox.warning(self, "Add sample", str(e))
            return
        self._save()
        self.open_sample(s.sample_id)

    def _import_sheet(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import a sample sheet", "",
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            result = import_sample_sheet(self.project, path)
        except (OSError, ValueError, UnicodeDecodeError) as e:
            QMessageBox.warning(self, "Couldn't import", str(e))
            return
        self._save()
        lines = [f"{result.added} samples added, {result.updated} updated."]
        if result.skipped:
            lines.append("Skipped:\n" + "\n".join(result.skipped[:10]))
        QMessageBox.information(self, "Sample sheet imported", "\n\n".join(lines))
        self.render_project()

    def _export_sheet(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export the sample sheet",
                                              f"{self.project.id}-samples.csv",
                                              "CSV files (*.csv)")
        if path:
            export_sample_sheet(self.project, path)

    # -- one sample -----------------------------------------------------------------
    def open_sample(self, sample_id: str):
        s = self.project.sample(sample_id)
        if s is None:
            self.render_project()
            return
        page = ScrollPage()
        page.add(nav_bar(self.project.name, self.render_project))
        page.add(label(s.sample_id, "detailTitle", wrap=True))
        if s.description:
            page.add(label(s.description, "secondary", wrap=True))

        page.header("Analyses")
        card = page.add(Card())
        for a in sorted(s.analyses, key=lambda a: a.kind.lower()):
            buttons = QWidget()
            bl = QHBoxLayout(buttons)
            bl.setContentsMargins(0, 0, 0, 0)
            for which, path in a.folders():
                b = plain_button("Raw data" if which == "raw data" else "Analysis")
                if not Path(path).expanduser().exists():
                    b.setText(b.text() + " (missing)")
                    b.setStyleSheet(f"color:{SOFT['red']}; background:transparent; "
                                    f"border:none; font-size:15px;")
                b.clicked.connect(lambda _=False, path=path: open_folder(self, path))
                bl.addWidget(b)
            sub = STATUS_LABEL[a.status]
            if a.date:
                sub += f" · {day(date.fromisoformat(a.date))}"
            if a.notes:
                sub += f" · {a.notes}"
            row = Row(a.kind, sub, leading=dot(STATUS_COLOR[a.status]),
                      trailing=buttons, tappable=True)
            row.clicked.connect(lambda a=a: self._edit_analysis(s, a))
            card.add(row)
        add = Row("Add Analysis…", title_color=APPLE["blue"], tappable=True)
        add.clicked.connect(lambda: self._edit_analysis(s, None))
        card.add(add)

        page.header("Details")
        card = page.add(Card())
        desc = QLineEdit(s.description)
        card.add(field_row("Description", desc))
        collected = QLineEdit(s.collected)
        collected.setPlaceholderText("YYYY-MM-DD")
        card.add(field_row("Collected", collected))
        notes = QPlainTextEdit(s.notes)
        notes.setPlaceholderText("Storage location, treatment, anything to remember")
        notes.setFixedHeight(80)
        notes.setStyleSheet("border:none;")
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 6, 12, 6)
        bl.addWidget(notes)
        card.add(box)

        def save_details():
            s.description = desc.text().strip()
            s.collected = collected.text().strip()
            s.notes = notes.toPlainText().strip()
            self._save()
        for w in (desc, collected):
            w.editingFinished.connect(save_details)
        notes.textChanged.connect(save_details)

        entries = sorted(self.project.notes_for(s.sample_id), key=lambda n: n.date,
                         reverse=True)
        page.header(f"Notebook · {len(entries)}")
        card = page.add(Card())
        for n in entries:
            card.add(Row(day(date.fromisoformat(n.date)), n.text))
        new = Row("New Entry for This Sample…", title_color=APPLE["blue"],
                  tappable=True)
        new.clicked.connect(lambda: self._new_note([s.sample_id], back=s.sample_id))
        card.add(new)

        page.header("")
        card = page.add(Card())
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(16, 10, 16, 10)
        remove = plain_button("Delete Sample", destructive=True)
        remove.clicked.connect(lambda: self._delete_sample(s))
        al.addWidget(remove)
        al.addStretch(1)
        card.add(actions)
        page.footnote("Galley only records where your data is; deleting a sample "
                      "here never touches its folders.")
        page.finish()
        self._show(page)

    def _edit_analysis(self, s: Sample, current: Analysis | None):
        dlg = AnalysisDialog(self._kinds(), current, self)
        if dlg.exec() != QDialog.Accepted:
            return
        s.set_analysis(dlg.analysis())
        self._save()
        self.open_sample(s.sample_id)

    def _delete_sample(self, s: Sample):
        if QMessageBox.question(self, "Delete sample",
                                f"Delete {s.sample_id} from this project? Its data "
                                f"folders are not touched.") != QMessageBox.Yes:
            return
        self.project.remove_sample(s.sample_id)
        self._save()
        self.render_project()

    # -- notebook ---------------------------------------------------------------
    def _notebook(self, page: ScrollPage):
        p = self.project
        search = QLineEdit(self.note_search)
        search.setPlaceholderText("Search the notebook")
        search.setClearButtonEnabled(True)
        search.setStyleSheet(f"background:white; border:1px solid {APPLE['fill']}; "
                             f"border-radius:10px; padding:8px 12px; font-size:15px;")
        search.textChanged.connect(self._search_notes)
        page.add(search)
        self.note_box = search

        page.header("")
        card = page.add(Card())
        new = Row("New Entry…", title_color=APPLE["blue"], tappable=True)
        new.clicked.connect(lambda: self._new_note([]))
        card.add(new)

        q = self.note_search.lower()
        entries = [n for n in sorted(p.notebook, key=lambda n: n.date, reverse=True)
                   if not q or q in f"{n.text} {' '.join(n.samples)}".lower()]
        current_month = None
        card = None
        for n in entries:
            d = date.fromisoformat(n.date)
            month = f"{d:%B %Y}"
            if month != current_month:
                page.header(month)
                card = page.add(Card())
                current_month = month
            chips = QWidget()
            cl = QHBoxLayout(chips)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(4)
            for sid in n.samples[:4]:
                chip = pill(sid, SOFT["blue"])
                chip.setCursor(Qt.PointingHandCursor)
                chip.mousePressEvent = lambda e, sid=sid: self.open_sample(sid)
                cl.addWidget(chip)
            card.add(Row(day(d), n.text, trailing=chips))
        if not entries:
            page.header("Entries")
            c = page.add(Card())
            c.add(Row("No entries match" if q else "No entries yet",
                      "Write what you did and link the samples involved."))

    def _search_notes(self, text: str):
        self.note_search = text
        self.render_project()
        self.note_box.setFocus()
        self.note_box.setCursorPosition(len(text))

    def _new_note(self, preset: list[str], back: str | None = None):
        dlg = NoteDialog([s.sample_id for s in self.project.samples], preset, self)
        if dlg.exec() != QDialog.Accepted:
            return
        ids = dlg.sample_ids()
        unknown = self.project.unknown_samples(ids)
        if unknown and QMessageBox.question(
                self, "Unknown samples",
                f"These aren't samples in this project: {', '.join(unknown)}. "
                f"Save the entry anyway?") != QMessageBox.Yes:
            return
        try:
            self.project.add_note(dlg.text.toPlainText(), dlg.when.date().toPython(), ids)
        except ValueError as e:
            QMessageBox.warning(self, "Notebook", str(e))
            return
        self._save()
        if back:
            self.open_sample(back)
        else:
            self.render_project()
