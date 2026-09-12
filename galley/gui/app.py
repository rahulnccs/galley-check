"""Desktop app for Galley (Windows and Mac).

Start screen: drop a .docx, choose it with a file dialog, or paste a path.
Results screen: filter by severity, click an issue to see the exact sentence
in the manuscript with the problem highlighted, then re-check after fixing.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSplitter,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from ..checks.offline.submission import PROFILE_DIR, Profile
from ..engine import load, run_checks
from ..model.document import SEVERITY_ORDER, Document, Issue
from ..report.docx_comments import annotate, default_output_path
from ..report.text_report import render_json, render_text

# ---- Design tokens ---------------------------------------------------------
INK = "#1F2A44"         # body text
INK_SOFT = "#5B6478"    # secondary text
PAPER = "#F4F6F9"       # window background
SHEET = "#FFFFFF"       # surfaces
RULE = "#DCE1E8"        # borders
GREEN_INK = "#1E6B52"   # primary action: an editor's green pen
SEVERITY = {
    "error":   {"color": "#C0392B", "tint": "#FBE3E0", "name": "error"},
    "warning": {"color": "#A86A12", "tint": "#FBEFD9", "name": "warning"},
    "info":    {"color": "#46699C", "tint": "#E4ECF7", "name": "note"},
}
# Where the "Get in touch" link goes. Replace with your own form or contact page.
FEEDBACK_URL = "https://docs.google.com/forms/d/e/1FAIpQLSf-IEokqhT8mjond7SFDCp90sDzUDCupJPK8p26aVls46QYjg/viewform"

UI_FONTS = ["Segoe UI", "SF Pro Text", ".AppleSystemUIFont", "Helvetica Neue",
            "Cantarell", "DejaVu Sans"]
PAPER_FONTS = ["Charter", "Cambria", "Georgia", "Bitstream Charter", "DejaVu Serif"]


def pick_font(candidates: list[str]) -> str:
    available = set(QFontDatabase.families())
    return next((f for f in candidates if f in available), candidates[-1])


def stylesheet(ui: str) -> str:
    return f"""
    QWidget {{ font-family: "{ui}"; color: {INK}; font-size: 14px; }}
    QMainWindow, #page {{ background: {PAPER}; }}
    #title {{ font-size: 30px; font-weight: 600; }}
    #subtitle {{ color: {INK_SOFT}; font-size: 15px; }}
    #muted {{ color: {INK_SOFT}; }}
    #errorText {{ color: {SEVERITY['error']['color']}; }}
    #dropZone {{ background: {SHEET}; border: 2px dashed {RULE}; border-radius: 14px; }}
    #dropZone[hover="true"] {{ border-color: {GREEN_INK}; background: #EEF6F2; }}
    #dropTitle {{ font-size: 18px; font-weight: 600; }}
    QPushButton {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 8px;
                  padding: 8px 16px; }}
    QPushButton:hover {{ border-color: {INK_SOFT}; }}
    QPushButton:focus {{ border: 2px solid {GREEN_INK}; }}
    QPushButton#primary {{ background: {GREEN_INK}; color: white; border: none;
                          font-weight: 600; }}
    QPushButton#primary:hover {{ background: #175642; }}
    QPushButton#primary:disabled {{ background: #9DB9AE; }}
    QPushButton#chip {{ border-radius: 12px; padding: 4px 14px; background: {SHEET}; }}
    QPushButton#chip:checked {{ background: #E9EEF6; border: 1px solid {INK_SOFT}; }}
    QPushButton#chip:disabled {{ color: #A3AAB8; }}
    QLineEdit {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 8px;
                padding: 8px 10px; }}
    QLineEdit:focus {{ border: 2px solid {GREEN_INK}; }}
    QListWidget {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 10px;
                  padding: 4px; outline: none; }}
    QListWidget::item {{ padding: 10px 8px; border-bottom: 1px solid #EEF1F5; }}
    QListWidget::item:selected {{ background: #E9EEF6; color: {INK}; border-radius: 6px; }}
    QTextBrowser {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 10px;
                   padding: 18px; }}
    QProgressBar {{ background: {RULE}; border: none; border-radius: 3px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {GREEN_INK}; border-radius: 3px; }}
    #header {{ background: {SHEET}; border-bottom: 1px solid {RULE}; }}
    #linkButton {{ background: transparent; border: none; color: {INK_SOFT};
                  padding: 4px 2px; text-decoration: underline; }}
    #linkButton:hover {{ color: {GREEN_INK}; }}
    #fileName {{ font-size: 17px; font-weight: 600; }}
    """


def dot_icon(color: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 10, 10)
    p.end()
    icon = QIcon(pm)
    icon.addPixmap(pm, QIcon.Selected)   # keep the color when the row is selected
    return icon


# ---- Background work -------------------------------------------------------
class CheckWorker(QObject):
    finished = Signal(object, object)   # Document, list[Issue]
    failed = Signal(str)

    def __init__(self, path: str, profile=None):
        super().__init__()
        self.path = path
        self.profile = profile

    def run(self):
        try:
            doc = load(self.path)
            self.finished.emit(doc, run_checks(doc, profile=self.profile))
        except ValueError as e:
            self.failed.emit(f"{e}. Open the file in Word, save it as .docx, and try again.")
        except Exception as e:  # corrupt or locked file
            self.failed.emit(f"Couldn't read this file ({e.__class__.__name__}). "
                             "If it's open in Word with unsaved changes, save it and try again.")


# ---- Start screen ----------------------------------------------------------
class DropZone(QFrame):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(220)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        title = QLabel("Drop your manuscript here")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("Word documents (.docx)")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignCenter)
        self.button = QPushButton("Choose file…")
        self.button.setObjectName("primary")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._choose)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addSpacing(6)
        lay.addWidget(self.button, alignment=Qt.AlignCenter)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a manuscript", str(Path.home()),
                                              "Word documents (*.docx)")
        if path:
            self.fileDropped.emit(path)

    def _set_hover(self, on: bool):
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, e):
        self._set_hover(False)

    def dropEvent(self, e):
        self._set_hover(False)
        urls = e.mimeData().urls()
        if urls:
            self.fileDropped.emit(urls[0].toLocalFile())


class StartPage(QWidget):
    checkRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.profile = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        col = QWidget()
        col.setFixedWidth(600)
        lay = QVBoxLayout(col)
        lay.setSpacing(14)

        title = QLabel("Galley")
        title.setObjectName("title")
        sub = QLabel("Checks figures, tables, citations and references before "
                     "reviewers do. Your manuscript stays on this computer.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)

        self.drop = DropZone()
        self.drop.fileDropped.connect(self.checkRequested)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Or paste a file path, e.g. C:\\Papers\\draft.docx")
        self.path_edit.returnPressed.connect(self._check_path)
        go = QPushButton("Check")
        go.clicked.connect(self._check_path)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(go)

        profile_row = QHBoxLayout()
        self.profile_label = QLabel("No journal limits")
        self.profile_label.setObjectName("muted")
        choose = QPushButton("Use journal limits…")
        choose.setCursor(Qt.PointingHandCursor)
        choose.clicked.connect(self._choose_profile)
        self.clear_profile = QPushButton("Clear")
        self.clear_profile.setCursor(Qt.PointingHandCursor)
        self.clear_profile.clicked.connect(self._clear_profile)
        self.clear_profile.hide()
        profile_row.addWidget(self.profile_label, 1)
        profile_row.addWidget(choose)
        profile_row.addWidget(self.clear_profile)

        self.message = QLabel("")
        self.message.setObjectName("errorText")
        self.message.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        self.progress_label.hide()

        lay.addStretch(1)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(10)
        lay.addWidget(self.drop)
        lay.addLayout(path_row)
        lay.addLayout(profile_row)
        lay.addWidget(self.progress)
        lay.addWidget(self.progress_label)
        lay.addWidget(self.message)
        lay.addStretch(2)
        outer.addWidget(col, alignment=Qt.AlignHCenter)

    def _choose_profile(self):
        """Load a journal profile: word and item limits to check against."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a journal profile", str(PROFILE_DIR),
            "Journal profiles (*.json)")
        if not path:
            return
        try:
            self.profile = Profile.load(path)
        except (OSError, ValueError) as e:
            self.show_error(f"That profile couldn't be read: {e}")
            return
        self.profile_label.setText(f"Checking against {self.profile.name}")
        self.clear_profile.show()

    def _clear_profile(self):
        self.profile = None
        self.profile_label.setText("No journal limits")
        self.clear_profile.hide()

    def _check_path(self):
        text = self.path_edit.text().strip().strip('"').strip("'")
        if not text:
            self.show_error("Paste the full path to a .docx file, or choose one above.")
        elif not Path(text).expanduser().exists():
            self.show_error(f"No file found at {text}. Check the path and try again.")
        else:
            self.checkRequested.emit(str(Path(text).expanduser()))

    def set_busy(self, busy: bool, name: str = ""):
        self.drop.button.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress_label.setText(f"Checking {name}…" if busy else "")
        self.progress_label.setVisible(busy)
        if busy:
            self.message.setText("")

    def show_error(self, text: str):
        self.set_busy(False)
        self.message.setText(text)


# ---- Results screen --------------------------------------------------------
class ResultsPage(QWidget):
    recheck = Signal()
    newFile = Signal()

    def __init__(self, paper_font: str):
        super().__init__()
        self.setObjectName("page")
        self.paper_font = paper_font
        self.doc: Document | None = None
        self.issues: list[Issue] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 14, 24, 14)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.file_label = QLabel()
        self.file_label.setObjectName("fileName")
        self.file_label.setMinimumWidth(80)
        self.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._file_name = ""
        self.summary_label = QLabel()
        self.summary_label.setObjectName("muted")
        self.summary_label.setMinimumWidth(80)
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._summary_text = ""
        names.addWidget(self.file_label)
        names.addWidget(self.summary_label)
        names_box = QWidget()
        names_box.setLayout(names)
        names_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        names_box.setMinimumWidth(160)     # the file name keeps a readable share
        h.addWidget(names_box, 1)
        for text, slot, primary in [("Open in Word", self._open_doc, False),
                                    ("Save with comments…", self._save_comments, False),
                                    ("Save report…", self._save_report, False),
                                    ("Check another", self.newFile.emit, False),
                                    ("Re-check", self.recheck.emit, True)]:
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(slot)
            h.addWidget(b)
        root.addWidget(header)

        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(24, 16, 24, 20)
        b.setSpacing(12)

        self.filters: dict[str, QPushButton] = {}
        frow = QHBoxLayout()
        frow.setSpacing(8)
        for sev in ("error", "warning", "info"):
            btn = QPushButton()
            btn.setObjectName("chip")
            btn.setToolTip("Show or hide these issues")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setIcon(dot_icon(SEVERITY[sev]["color"]))
            btn.setCursor(Qt.PointingHandCursor)
            btn.toggled.connect(self._refresh_list)
            self.filters[sev] = btn
            frow.addWidget(btn)
        frow.addStretch(1)
        b.addLayout(frow)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(12)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setIconSize(QSize(14, 14))
        self.list.currentItemChanged.connect(self._show_detail)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        split.addWidget(self.list)
        split.addWidget(self.detail)
        split.setSizes([420, 560])
        b.addWidget(split, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        prompt = QLabel("Something wrong here, or a check you'd like added?")
        prompt.setObjectName("muted")
        contact = QPushButton("Get in touch")
        contact.setObjectName("linkButton")
        contact.setCursor(Qt.PointingHandCursor)
        contact.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
        footer.addWidget(prompt)
        footer.addWidget(contact)
        footer.addStretch(1)
        b.addLayout(footer)
        root.addWidget(body, 1)

    # -- data
    def show_results(self, doc: Document, issues: list[Issue]):
        self.doc = doc
        self.issues = sorted(issues, key=lambda i: (
            SEVERITY_ORDER[i.severity], i.para_index if i.para_index is not None else -1))
        self._file_name = Path(doc.path).name
        self._elide_file_name()
        # The label's real width is only known once the layout has run.
        QTimer.singleShot(0, self._elide_file_name)
        n_cites = len(doc.citations)
        self._summary_text = (
            f"{sum(1 for p in doc.paragraphs if p.text)} paragraphs read, "
            f"{n_cites} reference-manager citation{'s' if n_cites != 1 else ''} found")
        self.summary_label.setText(self._summary_text)
        for sev, btn in self.filters.items():
            n = sum(1 for i in self.issues if i.severity == sev)
            name = SEVERITY[sev]["name"]
            btn.setText(f"{n} {name}{'s' if n != 1 else ''}")
            btn.setEnabled(n > 0)
        self._refresh_list()

    def _refresh_list(self):
        self.list.clear()
        shown = [i for i in self.issues if self.filters[i.severity].isChecked()]
        for issue in shown:
            item = QListWidgetItem(dot_icon(SEVERITY[issue.severity]["color"]), issue.message)
            item.setData(Qt.UserRole, issue)
            self.list.addItem(item)
        if shown:
            self.list.setCurrentRow(0)
        else:
            self.detail.setHtml(self._empty_html())

    def _empty_html(self) -> str:
        if not self.issues:
            return (f"<h2 style='color:{GREEN_INK}'>No problems found</h2>"
                    "<p>Every figure and table is cited, has a legend, and appears in order.</p>")
        return "<p>All issues are hidden. Turn a filter back on to see them.</p>"

    def _show_detail(self, item: QListWidgetItem | None):
        if item is None or self.doc is None:
            return
        issue: Issue = item.data(Qt.UserRole)
        sev = SEVERITY[issue.severity]
        parts = [f"<p style='color:{sev['color']}; font-weight:600; margin:0'>"
                 f"{sev['name'].capitalize()}</p>",
                 f"<h3 style='margin-top:4px'>{html.escape(issue.message)}</h3>"]
        if issue.suggestion:
            parts.append(f"<p style='color:{INK_SOFT}'>{html.escape(issue.suggestion)}</p>")
        if issue.para_index is not None:
            p = self.doc.paragraph(issue.para_index)
            where = p.section.replace("_", " ").capitalize()
            parts.append(f"<p style='color:{INK_SOFT}; margin-top:18px'>"
                         f"{where}, paragraph {p.index + 1}</p>")
            parts.append(self._paragraph_html(p.text, issue.anchor, sev))
        self.detail.setHtml("".join(parts))

    def _paragraph_html(self, text: str, anchor: str | None, sev: dict) -> str:
        style = (f"font-family:'{self.paper_font}'; font-size:16px; line-height:150%; "
                 f"border-left:3px solid {RULE}; padding-left:14px")
        if anchor and anchor in text:
            before, after = text.split(anchor, 1)
            body = (html.escape(before)
                    + f"<span style='background:{sev['tint']}; color:{sev['color']}; "
                      f"font-weight:600; text-decoration:underline'>{html.escape(anchor)}</span>"
                    + html.escape(after))
        else:
            body = html.escape(text)
        return f"<table width='100%'><tr><td style=\"{style}\">{body}</td></tr></table>"

    def _elide_file_name(self):
        metrics = self.file_label.fontMetrics()
        width = max(80, self.file_label.width())
        self.file_label.setText(
            metrics.elidedText(self._file_name, Qt.ElideMiddle, width))
        self.file_label.setToolTip(self._file_name)
        if self._summary_text:
            self.summary_label.setText(
                self.summary_label.fontMetrics().elidedText(
                    self._summary_text, Qt.ElideRight,
                    max(80, self.summary_label.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._file_name:
            self._elide_file_name()

    # -- actions
    def _open_doc(self):
        if self.doc:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.doc.path))

    def _save_comments(self):
        """Save a copy of the manuscript with a Word comment at each issue."""
        if not self.doc:
            return
        shown = {sev for sev, btn in self.filters.items() if btn.isChecked()}
        if not shown:
            QMessageBox.information(self, "Nothing to comment on",
                                    "Turn on at least one filter to choose which "
                                    "issues to add as comments.")
            return
        default = str(default_output_path(self.doc.path))
        path, _ = QFileDialog.getSaveFileName(self, "Save commented copy", default,
                                              "Word documents (*.docx)")
        if not path:
            return
        try:
            written = annotate(self.doc, self.issues, path, severities=tuple(shown))
        except Exception as e:
            QMessageBox.warning(self, "Copy not saved",
                                f"Couldn't write the commented copy: {e}")
            return
        count = sum(1 for i in self.issues if i.severity in shown)
        answer = QMessageBox.question(
            self, "Commented copy saved",
            f"Added {count} comment{'s' if count != 1 else ''} to a copy of your "
            f"manuscript.\n\nYour original file is unchanged.\n\nOpen the copy now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(written)))

    def _save_report(self):
        if not self.doc:
            return
        default = str(Path(self.doc.path).with_name(Path(self.doc.path).stem + "_report.txt"))
        path, _ = QFileDialog.getSaveFileName(self, "Save report", default,
                                              "Text report (*.txt);;JSON (*.json)")
        if not path:
            return
        out = (render_json if path.lower().endswith(".json") else render_text)(
            self.doc, self.issues)
        try:
            Path(path).write_text(out, encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Report not saved", f"Couldn't save the report: {e}")


# ---- Main window -----------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, paper_font: str):
        super().__init__()
        self.setWindowTitle("Galley")
        self.resize(1080, 720)
        self.setMinimumSize(940, 560)
        self.current_path: str | None = None
        self._thread: QThread | None = None

        self.stack = QStackedWidget()
        self.start = StartPage()
        self.results = ResultsPage(paper_font)
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.results)
        self.setCentralWidget(self.stack)

        self.start.checkRequested.connect(self.check)
        self.results.recheck.connect(lambda: self.current_path and self.check(self.current_path))
        self.results.newFile.connect(lambda: self.stack.setCurrentWidget(self.start))

    def check(self, path: str):
        if self._thread is not None:
            return
        if not path.lower().endswith(".docx"):
            self.stack.setCurrentWidget(self.start)
            self.start.show_error(f"{Path(path).name} isn't a Word document (.docx). "
                                  "Save it as .docx in Word and try again.")
            return
        self.current_path = path
        self.stack.setCurrentWidget(self.start)
        self.start.set_busy(True, Path(path).name)

        self._thread = QThread()
        self._worker = CheckWorker(path, self.start.profile)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _done(self, doc, issues):
        self.start.set_busy(False)
        self.results.show_results(doc, issues)
        self.stack.setCurrentWidget(self.results)
        self.results.list.setFocus()

    def _failed(self, message: str):
        self.start.show_error(message)

    def _cleanup(self):
        self._thread.deleteLater()
        self._thread = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Galley")
    ui_font = pick_font(UI_FONTS)
    app.setFont(QFont(ui_font, 10))
    app.setStyleSheet(stylesheet(ui_font))
    win = MainWindow(pick_font(PAPER_FONTS))
    win.show()
    if len(sys.argv) > 1:          # allow "open with" / drag onto the app icon
        win.check(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
