"""Desktop app for Galley (Windows and Mac).

Start screen: drop a .docx, choose it with a file dialog, or paste a path.
Results screen: filter by severity, click an issue to see the exact sentence
in the manuscript with the problem highlighted, then re-check after fixing.
"""
from __future__ import annotations

import html
import sys
from collections import Counter
from pathlib import Path

from PySide6.QtCore import (
    QObject, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal)
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListView, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QMenu, QSizePolicy, QSplitter, QToolButton,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from ..checks.offline.submission import (
    PROFILE_DIR, Profile, available_profiles, delete_profile, is_user_profile)
from ..report.compare_versions import compare, highlight, summarize
from ..report.compare_versions import default_output_path as changes_path
from .journal_dialog import JournalDialog
from ..engine import load, run_checks
from ..model.document import SEVERITY_ORDER, Document, Issue
from ..report.docx_comments import annotate, default_output_path
from ..report.text_report import render_json, render_text

# ---- Design tokens ---------------------------------------------------------
# The tile palette: soft, saturated cards on a light background.
INK = "#2B2F36"          # body text
INK_SOFT = "#6B7480"     # secondary text
PAPER = "#F2F3F5"        # window background
SHEET = "#FFFFFF"        # surfaces
RULE = "#DEE1E6"         # borders
# Tints for the journal list, so each kind of row reads differently.
ROW_NONE = "#EDEFF2"     # "No journal limits"
ROW_JOURNAL = "#E7EFFA"  # a saved journal
ROW_ACTION = "#FBEEF2"   # "Enter journal requirements…"
GREEN_INK = "#3E7BC4"    # primary action

TILE = {
    "all":      "#4A4E54",   # dark slate
    "error":    "#DE837C",   # red
    "warning":  "#E7B279",   # amber
    "info":     "#7BA7E0",   # blue
    "clean":    "#93A0A8",   # grey
    "accent":   "#E48AA6",   # pink
}
CHECK_LABELS = {
    "figures": "Figures and tables",
    "references": "Citations and references",
    "abbreviations": "Abbreviations",
    "species": "Species names",
    "submission": "Journal requirements",
}
CHECK_ORDER = ["figures", "references", "abbreviations", "species", "submission"]
SEVERITY = {
    "error":   {"color": "#B4463D", "tint": "#F8DFDC", "name": "error"},
    "warning": {"color": "#9A6416", "tint": "#FAEBD6", "name": "warning"},
    "info":    {"color": "#3E6DA8", "tint": "#E3ECF9", "name": "note"},
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
    QPushButton#primary:hover {{ background: #33669F; }}
    QPushButton#primary:disabled {{ background: #A9C2DF; }}
    QToolButton#menuButton {{ background: {SHEET}; border: 1px solid {RULE};
                             border-radius: 8px; padding: 8px 14px; }}
    QToolButton#menuButton:hover {{ border-color: {INK_SOFT}; }}
    /* macOS draws its own menu arrow outside the padding, on top of ours. */
    QToolButton#menuButton::menu-indicator {{ image: none; width: 0; }}
    QToolButton#menuButton::menu-button {{ border: none; width: 0; }}
    QMenu {{ background: {SHEET}; border: 1px solid {RULE}; padding: 4px; }}
    QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: #E9EEF6; }}
    QPushButton#chip {{ border-radius: 12px; padding: 4px 14px; background: {SHEET}; }}
    QPushButton#chip:checked {{ background: #E9EEF6; border: 1px solid {INK_SOFT}; }}
    QPushButton#chip:disabled {{ color: #A3AAB8; }}
    QLineEdit {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 8px;
                padding: 8px 10px; }}
    QComboBox {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 8px;
                padding: 7px 10px; }}
    QComboBox:focus {{ border: 2px solid {GREEN_INK}; }}
    QComboBox QAbstractItemView {{ background: {SHEET}; border: 1px solid {RULE};
                                  selection-background-color: #E9EEF6;
                                  selection-color: {INK}; outline: none;
                                  padding: 4px; }}
    QComboBox QAbstractItemView::item {{ padding: 11px 12px; min-height: 26px;
                                        border-radius: 8px; margin: 2px; }}
    QComboBox QAbstractItemView::separator {{ height: 1px; background: {RULE};
                                             margin: 5px 8px; }}
    QDialog {{ background: {PAPER}; }}
    QSpinBox {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 8px;
               padding: 7px 10px; }}
    QSpinBox:focus {{ border: 2px solid {GREEN_INK}; }}
    QCheckBox {{ spacing: 8px; }}
    QDialogButtonBox QPushButton {{ min-width: 92px; }}
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
    #stats {{ background: {SHEET}; border: 1px solid {RULE}; border-radius: 10px;
             padding: 10px 14px; color: {INK_SOFT}; }}
    #paneTitle {{ font-weight: 600; color: {INK_SOFT}; }}
    #manuscript, #detail {{ background: {SHEET}; border: 1px solid {RULE};
                           border-radius: 12px; padding: 16px; }}
    #dialogTitle {{ font-size: 17px; font-weight: 600; }}
    #dialogBanner {{ background: {TILE["info"]}; color: white; font-size: 19px;
                    font-weight: 600; border-radius: 12px; padding: 16px 18px; }}
    #rule {{ color: {RULE}; }}
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
        sub = QLabel("Checks figures, tables, citations, references, "
                     "abbreviations and species names before reviewers do. "
                     "Your manuscript stays on this computer.")
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
        self.journal_box = QComboBox()
        self.journal_box.setMinimumWidth(190)
        self.journal_box.addItem("No journal limits", None)
        self.journal_box.currentIndexChanged.connect(self._journal_chosen)
        self.edit_profile = QPushButton("Edit")
        self.edit_profile.setCursor(Qt.PointingHandCursor)
        self.edit_profile.clicked.connect(self._edit_profile)
        self.edit_profile.hide()
        self.remove_profile = QPushButton("Remove")
        self.remove_profile.setCursor(Qt.PointingHandCursor)
        self.remove_profile.clicked.connect(self._remove_profile)
        self.remove_profile.hide()
        profile_row.setSpacing(8)
        profile_row.addWidget(QLabel("Journal:"))
        profile_row.addWidget(self.journal_box, 1)
        profile_row.addWidget(self.edit_profile)
        profile_row.addWidget(self.remove_profile)

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
        lay.addWidget(self.profile_label)
        lay.addWidget(self.progress)
        lay.addWidget(self.progress_label)
        lay.addWidget(self.message)
        lay.addStretch(2)
        outer.addWidget(col, alignment=Qt.AlignHCenter)
        self._rebuild_journal_box()
        self._restore_last_profile()

    def _journal_chosen(self, index: int):
        value = self.journal_box.itemData(index)
        if value == "new":
            self._new_profile()
            return
        self.profile = value
        self._describe_profile()

    def _new_profile(self):
        """Fill in a journal's requirements by hand, and keep them."""
        dialog = JournalDialog(self)
        if dialog.exec() != JournalDialog.Accepted or not dialog.saved_path:
            self.journal_box.setCurrentIndex(0)
            return
        try:
            self.profile = Profile.load(dialog.saved_path)
        except (OSError, ValueError) as e:
            self.show_error(f"The profile was saved but couldn't be read: {e}")
            self.journal_box.setCurrentIndex(0)
            return
        self._rebuild_journal_box(select=self.profile)

    def _describe_profile(self):
        """Say how old the profile is; a stale limit is worse than none."""
        mine = self.profile is not None and is_user_profile(self.profile)
        self.edit_profile.setVisible(mine)
        self.remove_profile.setVisible(mine)
        if self.profile is None:
            self.profile_label.setText("")
            self._remember(None)
            return
        self._remember(self.profile)
        age = self.profile.months_old
        if age is None:
            note = "no verification date"
        elif age > 12:
            note = f"verified {self.profile.verified} — may be out of date"
        else:
            note = f"verified {self.profile.verified}"
        self.profile_label.setText(note)

    def _edit_profile(self):
        """Change a journal's requirements; limits move, and typos happen."""
        if self.profile is None:
            return
        dialog = JournalDialog(self, profile=self.profile)
        if dialog.exec() != JournalDialog.Accepted or not dialog.saved_path:
            return
        try:
            updated = Profile.load(dialog.saved_path)
        except (OSError, ValueError) as e:
            self.show_error(f"The profile was saved but couldn't be read: {e}")
            return
        # A rename writes a new file; drop the old one so it isn't listed twice.
        if (self.profile.path and dialog.saved_path != self.profile.path
                and is_user_profile(self.profile)):
            delete_profile(self.profile)
        self.profile = updated
        self._rebuild_journal_box(select=updated)

    def _remove_profile(self):
        if self.profile is None:
            return
        name = self.profile.name
        answer = QMessageBox.question(
            self, "Remove journal",
            f"Remove the requirements you saved for {name}?\n\n"
            f"This deletes the profile file. Your manuscript is not affected.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        if not delete_profile(self.profile):
            self.show_error(f"{name} couldn't be removed.")
            return
        self.profile = None
        self._rebuild_journal_box()

    def _rebuild_journal_box(self, select: Profile | None = None):
        """Refresh the dropdown after a profile is added, edited or removed."""
        self.journal_box.blockSignals(True)
        self.journal_box.clear()
        self.journal_box.addItem("No journal limits", None)
        self.journal_box.setItemData(0, QBrush(QColor(ROW_NONE)), Qt.BackgroundRole)
        chosen = 0
        for profile in available_profiles():
            self.journal_box.addItem(profile.name, profile)
            row = self.journal_box.count() - 1
            self.journal_box.setItemData(row, QBrush(QColor(ROW_JOURNAL)),
                                         Qt.BackgroundRole)
            if select is not None and profile.path == select.path:
                chosen = row
        self.journal_box.insertSeparator(self.journal_box.count())
        self.journal_box.addItem("Enter journal requirements\u2026", "new")
        self.journal_box.setItemData(self.journal_box.count() - 1,
                                     QBrush(QColor(ROW_ACTION)), Qt.BackgroundRole)
        self.journal_box.setCurrentIndex(chosen)
        self.journal_box.blockSignals(False)
        self.profile = self.journal_box.itemData(chosen) if chosen else None
        self._describe_profile()

    def _remember(self, profile: Profile | None):
        """Keep the last journal, so a second manuscript doesn't need re-picking."""
        settings = QSettings("Galley", "Galley")
        if profile is None or profile.path is None:
            settings.remove("last_profile")
        else:
            settings.setValue("last_profile", str(profile.path))

    def _restore_last_profile(self):
        path = QSettings("Galley", "Galley").value("last_profile")
        if not path or not Path(str(path)).exists():
            return
        try:
            profile = Profile.load(Path(str(path)))
        except (OSError, ValueError):
            return
        self.profile = profile
        self._rebuild_journal_box(select=profile)

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



class Tile(QPushButton):
    """A coloured count card. Clicking one filters the issue list."""

    def __init__(self, key: str, label: str, color: str):
        super().__init__()
        self.key = key
        self.label = label
        self.color = color
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{ background: {color}; border: none; border-radius: 12px;
                          color: white; text-align: left; padding: 12px 14px; }}
            QPushButton:hover {{ background: {color}; border: 2px solid white; }}
            QPushButton:checked {{ border: 3px solid {INK}; }}
        """)
        self.set_count(0)

    def set_count(self, count: int):
        self.setText(f"{count}\n{self.label}")
        self.setEnabled(True)


# ---- Results screen --------------------------------------------------------
class ResultsPage(QWidget):
    """Three panes: what was checked, the manuscript, and what was found.

    The manuscript is shown as text with every problem highlighted where it
    occurs. Clicking a finding scrolls the manuscript to that spot. Galley
    cannot reproduce a Word file's page layout — that needs a Word renderer —
    so this is the document's text, not its pages.
    """
    recheck = Signal()
    newFile = Signal()

    def __init__(self, paper_font: str):
        super().__init__()
        self.setObjectName("page")
        self.paper_font = paper_font
        self.doc: Document | None = None
        self.issues: list[Issue] = []
        self._file_name = ""
        self._summary_text = ""
        self._severity_filter = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(20, 14, 20, 16)
        b.setSpacing(12)

        self.tiles: dict[str, Tile] = {}
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        for key, label, color in [("all", "All findings", TILE["all"]),
                                  ("error", "Errors", TILE["error"]),
                                  ("warning", "Warnings", TILE["warning"]),
                                  ("info", "Notes", TILE["info"])]:
            tile = Tile(key, label, color)
            tile.clicked.connect(lambda _=False, k=key: self._filter(k))
            self.tiles[key] = tile
            tiles.addWidget(tile)
        self.tiles["all"].setChecked(True)
        b.addLayout(tiles)

        self.stats = QLabel("")
        self.stats.setObjectName("stats")
        self.stats.setWordWrap(True)
        self.stats.hide()
        b.addWidget(self.stats)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(12)

        self.manuscript = QTextBrowser()
        self.manuscript.setObjectName("manuscript")
        self.manuscript.setOpenLinks(False)
        self.manuscript.anchorClicked.connect(self._anchor_clicked)
        split.addWidget(self.manuscript)

        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(8)
        self.found_label = QLabel("Findings")
        self.found_label.setObjectName("paneTitle")
        r.addWidget(self.found_label)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setIconSize(QSize(14, 14))
        self.list.currentItemChanged.connect(self._issue_selected)
        r.addWidget(self.list, 1)
        self.detail = QTextBrowser()
        self.detail.setObjectName("detail")
        self.detail.setMaximumHeight(210)
        r.addWidget(self.detail)
        split.addWidget(right)

        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([620, 460])
        b.addWidget(split, 1)

        footer = QHBoxLayout()
        prompt = QLabel("Something wrong here, or a check you'd like added?")
        prompt.setObjectName("muted")
        contact = QPushButton("Get in touch")
        contact.setObjectName("linkButton")
        contact.setCursor(Qt.PointingHandCursor)
        contact.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
        footer.addWidget(prompt)
        footer.addWidget(contact)
        footer.addStretch(1)
        b.addLayout(footer)
        root.addWidget(body, 1)

    # -- header
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 12, 20, 12)

        names = QVBoxLayout()
        names.setSpacing(2)
        self.file_label = QLabel()
        self.file_label.setObjectName("fileName")
        self.file_label.setMinimumWidth(80)
        self.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("muted")
        self.summary_label.setMinimumWidth(80)
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        names.addWidget(self.file_label)
        names.addWidget(self.summary_label)
        box = QWidget()
        box.setLayout(names)
        box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        box.setMinimumWidth(160)
        h.addWidget(box, 1)

        actions = QToolButton()
        actions.setText("Document  \u2304")
        actions.setPopupMode(QToolButton.InstantPopup)
        actions.setCursor(Qt.PointingHandCursor)
        actions.setObjectName("menuButton")
        menu = QMenu(actions)
        for text, slot in [("Open in Word", self._open_doc),
                           ("Compare with an earlier version\u2026",
                            self._compare_versions),
                           ("Save with comments\u2026", self._save_comments),
                           ("Save report\u2026", self._save_report)]:
            menu.addAction(text, slot)
        actions.setMenu(menu)
        actions.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        h.addWidget(actions)
        for text, slot, primary in [("Check another", self.newFile.emit, False),
                                    ("Re-check", self.recheck.emit, True)]:
            button = QPushButton(text)
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if primary:
                button.setObjectName("primary")
            button.clicked.connect(slot)
            h.addWidget(button)
        return header

    # -- data
    def show_results(self, doc: Document, issues: list[Issue]):
        self.doc = doc
        self.issues = sorted(issues, key=lambda i: (
            SEVERITY_ORDER[i.severity], i.para_index if i.para_index is not None else -1))
        self._file_name = Path(doc.path).name
        self._elide_file_name()
        QTimer.singleShot(0, self._elide_file_name)

        n_cites = len(doc.citations)
        self._summary_text = (
            f"{sum(1 for p in doc.paragraphs if p.text)} paragraphs read, "
            f"{n_cites} reference-manager citation{'s' if n_cites != 1 else ''} found")
        self.summary_label.setText(self._summary_text)

        size = next((i.message for i in self.issues
                     if i.check == "submission"
                     and i.message.startswith("Manuscript size:")), "")
        if size:
            self.issues = [i for i in self.issues if i.message != size]
            self.stats.setText(size.replace("Manuscript size: ", "").rstrip("."))
        self.stats.setVisible(bool(size))

        counts = Counter(i.severity for i in self.issues)
        self.tiles["all"].set_count(len(self.issues))
        for key in ("error", "warning", "info"):
            self.tiles[key].set_count(counts[key])
        self._filter("all")
        self._render_manuscript()

    def _filter(self, key: str):
        self._severity_filter = key
        for name, tile in self.tiles.items():
            tile.setChecked(name == key)
        self._refresh_list()

    def _shown(self) -> list[Issue]:
        if self._severity_filter == "all":
            return self.issues
        return [i for i in self.issues if i.severity == self._severity_filter]

    def _refresh_list(self):
        """Rebuild the findings list, grouped by the check that produced each."""
        self.list.clear()
        shown = self._shown()
        self.found_label.setText(
            f"Findings ({len(shown)})" if shown else "Findings")

        first_row = None
        for check in CHECK_ORDER:
            group = [i for i in shown if i.check == check]
            if not group:
                continue
            heading = QListWidgetItem(
                f"{CHECK_LABELS.get(check, check.title())}   {len(group)}")
            heading.setFlags(Qt.NoItemFlags)
            font = heading.font()
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() * 0.92)
            heading.setFont(font)
            heading.setForeground(QColor(INK_SOFT))
            self.list.addItem(heading)
            for issue in group:
                item = QListWidgetItem(
                    dot_icon(SEVERITY[issue.severity]["color"]), issue.message)
                item.setData(Qt.UserRole, issue)
                self.list.addItem(item)
                if first_row is None:
                    first_row = self.list.row(item)

        if first_row is not None:
            self.list.setCurrentRow(first_row)
        else:
            self.list.setCurrentItem(None)
            self.detail.setHtml(self._empty_html())

    # -- the manuscript pane
    def _render_manuscript(self):
        """The document's text, with every finding highlighted in place."""
        if self.doc is None:
            return
        marks: dict[int, list[Issue]] = {}
        for issue in self.issues:
            if issue.para_index is not None:
                marks.setdefault(issue.para_index, []).append(issue)

        parts = [f"<style>body {{ font-family:'{self.paper_font}'; "
                 f"font-size:15px; line-height:155%; color:{INK}; }}"
                 f"h3 {{ font-family:'{self.paper_font}'; font-size:16px; "
                 f"margin:18px 0 6px 0; }}</style>"]
        for p in self.doc.paragraphs:
            if not p.text.strip():
                continue
            body = html.escape(p.text)
            for issue in marks.get(p.index, []):
                sev = SEVERITY[issue.severity]
                if issue.anchor and issue.anchor in p.text:
                    marked = html.escape(issue.anchor)
                    body = body.replace(
                        marked,
                        f"<span style='background:{sev['tint']}; "
                        f"color:{sev['color']}'>{marked}</span>", 1)
            tag = "h3" if p.is_heading else "p"
            parts.append(f'<a name="p{p.index}"></a><{tag}>{body}</{tag}>')
        self.manuscript.setHtml("".join(parts))

    def _anchor_clicked(self, url: QUrl):
        self.manuscript.scrollToAnchor(url.toString().lstrip("#"))

    def _issue_selected(self, item: QListWidgetItem | None):
        self._show_detail(item)
        if item is None:
            return
        issue: Issue = item.data(Qt.UserRole)
        if issue is not None and issue.para_index is not None:
            self.manuscript.scrollToAnchor(f"p{issue.para_index}")
            bar = self.manuscript.verticalScrollBar()
            bar.setValue(max(0, bar.value() - 40))

    def _empty_html(self) -> str:
        if not self.issues:
            return (
                f"<div style='margin-top:10px'>"
                f"<p style='font-size:30px; margin:0; color:{TILE['clean']}'>"
                f"\u2713</p>"
                f"<h3 style='margin:4px 0 2px 0'>Nothing to fix</h3>"
                f"<p style='color:{INK_SOFT}'>Figures, tables, citations, "
                f"references, abbreviations and species names all check "
                f"out.</p></div>")
        return (f"<p style='color:{INK_SOFT}'>No findings at this filter. "
                f"Choose another tile.</p>")

    def _show_detail(self, item: QListWidgetItem | None):
        if item is None or self.doc is None:
            return
        issue: Issue = item.data(Qt.UserRole)
        if issue is None:
            return
        sev = SEVERITY[issue.severity]
        parts = [f"<p style='color:{sev['color']}; font-weight:600; margin:0'>"
                 f"{sev['name'].capitalize()}</p>",
                 f"<h3 style='margin:4px 0 6px 0'>{html.escape(issue.message)}</h3>"]
        if issue.suggestion:
            parts.append(f"<p style='color:{INK_SOFT}'>"
                         f"{html.escape(issue.suggestion)}</p>")
        if issue.para_index is not None:
            p = self.doc.paragraph(issue.para_index)
            where = p.section.replace("_", " ").capitalize()
            parts.append(f"<p style='color:{INK_SOFT}; margin-top:10px'>"
                         f"{where}, paragraph {p.index + 1}</p>")
        self.detail.setHtml("".join(parts))

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

    def _compare_versions(self):
        """Highlight what changed since an earlier version of this manuscript."""
        if not self.doc:
            return
        old_path, _ = QFileDialog.getOpenFileName(
            self, "Choose the earlier version", str(Path(self.doc.path).parent),
            "Word documents (*.docx)")
        if not old_path:
            return
        if Path(old_path).resolve() == Path(self.doc.path).resolve():
            QMessageBox.information(self, "Same file",
                                    "That is the file you just checked. Choose "
                                    "the earlier version to compare against.")
            return
        default = str(changes_path(self.doc.path))
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save highlighted copy", default, "Word documents (*.docx)")
        if not out_path:
            return
        try:
            old = load(old_path)
            changes = compare(old, self.doc)
            written = highlight(self.doc, changes, out_path)
        except Exception as e:
            QMessageBox.warning(self, "Couldn't compare",
                                f"The two versions couldn't be compared: {e}")
            return
        answer = QMessageBox.question(
            self, "Comparison saved",
            f"{summarize(old, self.doc, changes)}\n\nThe changed sentences are "
            f"highlighted in a copy of your manuscript. Your original file is "
            f"unchanged.\n\nOpen the copy now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(written)))

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
        self.setMinimumSize(860, 560)
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
