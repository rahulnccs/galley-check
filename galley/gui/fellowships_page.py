"""The Fellowships screen, styled after Apple's iOS settings-style lists:
large titles, grouped rounded cards on a light grey background, the system
font, and Apple's system colours.

Three tabs: Matches (what you can apply for and why), Applications (what you
are working on, with reminders), and Profile (what Galley knows about you,
kept on this computer only).
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QObject, QRectF, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QDateEdit, QGraphicsDropShadowEffect, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..fellowships import (ELIGIBLE, NOT_ELIGIBLE, POSSIBLE, STATUSES,
                           check_application, check_document,
                           load_applications, load_fellowships, pdf_supported,
                           match, match_all, plan, reminders,
                           save_applications, start_application)
from ..fellowships.application_check import FAIL, PASS, WARN
from ..fellowships.application_check import INFO as NOTE
from ..fellowships.match import INFO, MET, NOT_MET, UNSURE
from ..fellowships.update import fetch_updates, last_updated
from ..fellowships.model import (FIELDS, Researcher, Stay,
                                 delete_custom_fellowship, load_researcher,
                                 save_custom_fellowship, save_researcher)

# Apple's iOS system colours (light appearance).
APPLE = {
    "background": "#F2F2F7",    # systemGroupedBackground
    "card": "#FFFFFF",          # secondarySystemGroupedBackground
    "label": "#000000",
    "secondary": "#6C6C70",     # secondaryLabel on white
    "tertiary": "#C7C7CC",
    "separator": "#C6C6C8",
    "fill": "#E5E5EA",          # systemGray5, segmented control track
    "blue": "#007AFF",
    "green": "#34C759",
    "orange": "#FF9500",
    "red": "#FF3B30",
    "gray": "#8E8E93",
}
APPLE_FONTS = [".AppleSystemUIFont", "SF Pro Text", "SF Pro", "Helvetica Neue",
               "Segoe UI", "Inter", "Cantarell", "DejaVu Sans"]

STATUS_COLOR = {ELIGIBLE: APPLE["green"], POSSIBLE: APPLE["orange"],
                NOT_ELIGIBLE: APPLE["gray"]}
STATUS_LABEL = {ELIGIBLE: "Eligible", POSSIBLE: "Check", NOT_ELIGIBLE: "Not eligible"}
REASON_MARK = {MET: ("✓", APPLE["green"]), NOT_MET: ("✕", APPLE["red"]),
               UNSURE: ("?", APPLE["orange"]), INFO: ("i", APPLE["blue"])}
FINDING_MARK = {PASS: MET, FAIL: NOT_MET, WARN: UNSURE, NOTE: INFO}
URGENCY_COLOR = {"overdue": APPLE["red"], "changed": APPLE["orange"],
                 "soon": APPLE["orange"], "upcoming": APPLE["blue"]}
# The three tabs, in order.
PROFILE, MATCHES, APPLICATIONS = 0, 1, 2

# A colour per application stage, from Apple's system palette.
STAGE_COLOR = {"planning": "#007AFF",      # blue: in progress
               "submitted": "#5856D6",     # indigo
               "shortlisted": "#FF9500",   # orange
               "interview": "#AF52DE",     # purple
               "awarded": "#34C759",       # green
               "not_funded": "#FF3B30",    # red
               "withdrawn": "#8E8E93"}     # grey
APP_STATUS_LABEL = {"planning": "Preparing", "submitted": "Submitted",
                    "shortlisted": "Shortlisted", "interview": "Interview",
                    "awarded": "Awarded", "not_funded": "Not funded",
                    "withdrawn": "Withdrawn"}
FIELD_LABEL = {
    "molecular_cell_biology": "Molecular & cell biology",
    "neuroscience": "Neuroscience",
    "immunology_infection": "Immunology & infection",
    "genetics_genomics": "Genetics & genomics",
    "ecology_evolution": "Ecology & evolution",
    "plant_science": "Plant science",
    "microbiology": "Microbiology",
    "structural_biology": "Structural biology",
    "bioinformatics": "Bioinformatics",
    "biomedical_clinical": "Biomedical & clinical",
}
DEADLINE_LABEL = {"final": "Deadline", "internal": "Internal deadline",
                  "pre_proposal": "Pre-proposal", "call_opens": "Call opens"}
CATEGORY_LABEL = {"postdoc": "Postdoc fellowship", "phd": "PhD fellowship",
                  "travel": "Travel grant"}
CATEGORY_FILTERS = [None, "postdoc", "phd", "travel"]
PURPOSE_LABEL = {"conference": "Conference", "lab_visit": "Lab visit",
                 "course": "Course or workshop", "fieldwork": "Fieldwork",
                 "other": "Other"}
# What each career stage means for the PhD row: 0 awarded, 1 in progress,
# 2 none. Not set (None) leaves the choice to the user.
PHD_STATE_FOR_LEVEL = {"masters_student": 2, "phd_student": 1,
                       "postdoc": 0, "faculty": 0}
LEVEL_CHOICES = [(None, "Not set"), ("masters_student", "Master's student"),
                 ("phd_student", "PhD student"), ("postdoc", "Postdoc"),
                 ("faculty", "Faculty or independent researcher")]
CV_LABEL = {"standard": "Standard CV", "narrative": "Narrative CV",
            "funder_template": "Funder's CV template"}
ROUTE_LABEL = {"portal": "Funder's online portal", "email": "By email",
               "institution": "Through your institution"}


def apple_font() -> str:
    available = set(QFontDatabase.families())
    return next((f for f in APPLE_FONTS if f in available), APPLE_FONTS[-1])


def apple_stylesheet(font: str) -> str:
    a = APPLE
    return f"""
    QWidget {{ font-family: "{font}"; font-size: 15px; color: {a['label']}; }}
    #fellowships, #fellowships QScrollArea, #scrollBody {{ background: {a['background']}; }}
    #largeTitle {{ font-size: 32px; font-weight: 700; }}
    #detailTitle {{ font-size: 24px; font-weight: 700; }}
    #secondary {{ color: {a['secondary']}; }}
    #sectionHeader {{ color: {a['secondary']}; font-size: 12px; }}
    #footnote {{ color: {a['secondary']}; font-size: 12px; }}
    #card {{ background: {a['card']}; border-radius: 10px; }}
    #separator {{ background: {a['separator']}; }}
    #rowTitle {{ font-size: 15px; font-weight: 600; }}
    #rowText {{ font-size: 15px; }}
    #rowSubtitle {{ color: {a['secondary']}; font-size: 13px; }}
    #chevron {{ color: {a['tertiary']}; font-size: 18px; }}
    #plainButton {{ color: {a['blue']}; background: transparent; border: none;
                    font-size: 15px; padding: 4px 0; text-align: left; }}
    #plainButton:hover {{ color: #0062CC; }}
    #destructive {{ color: {a['red']}; background: transparent; border: none;
                    font-size: 15px; padding: 4px 0; text-align: left; }}
    #backButton {{ color: {a['blue']}; background: transparent; border: none;
                   font-size: 15px; padding: 6px 0; }}
    #filledButton {{ background: {a['blue']}; color: white; border: none;
                     border-radius: 10px; font-size: 15px; font-weight: 600;
                     padding: 10px 18px; }}
    #filledButton:hover {{ background: #0062CC; }}
    #filledButton:disabled {{ background: {a['fill']}; color: {a['gray']}; }}
    QLineEdit, QPlainTextEdit {{ background: {a['card']}; border: none;
        padding: 4px 2px; selection-background-color: {a['blue']}; }}
    #valueEditor {{ background: transparent; border: none; color: {a['secondary']};
        padding: 4px 2px; min-width: 150px; }}
    QComboBox#valueEditor, QDateEdit#valueEditor, QSpinBox#valueEditor {{
        color: {a['blue']}; }}
    QComboBox#valueEditor::drop-down, QDateEdit#valueEditor::drop-down {{
        border: none; width: 0px; }}
    QSpinBox#valueEditor::up-button, QSpinBox#valueEditor::down-button {{
        border: none; width: 14px; }}
    QCalendarWidget {{ min-width: 340px; min-height: 300px; background: white; }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: white; }}
    QCalendarWidget QToolButton {{ color: {a['blue']}; font-size: 16px; font-weight: 600;
        background: transparent; border: none; padding: 6px 10px; }}
    QCalendarWidget QAbstractItemView {{ font-size: 15px; background: white;
        selection-background-color: {a['blue']}; selection-color: white;
        outline: none; }}
    QComboBox QAbstractItemView {{ background: {a['card']}; border: 1px solid {a['fill']};
        selection-background-color: {a['blue']}; selection-color: white; }}
    """


# ---- building blocks -------------------------------------------------------

def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextInteractionFlags(Qt.NoTextInteraction)   # let rows get clicks
    return lab


def pill(text: str, color: str) -> QLabel:
    p = QLabel(text)
    p.setStyleSheet(f"background:{color}; color:white; border-radius:9px; "
                    f"padding:2px 9px; font-size:12px; font-weight:600;")
    p.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return p


def mark(outcome: str) -> QLabel:
    symbol, color = REASON_MARK[outcome]
    m = QLabel(symbol)
    m.setFixedSize(22, 22)
    m.setAlignment(Qt.AlignCenter)
    m.setStyleSheet(f"background:{color}; color:white; border-radius:11px; "
                    f"font-size:12px; font-weight:700;")
    return m


def dot(color: str) -> QLabel:
    d = QLabel()
    d.setFixedSize(10, 10)
    d.setStyleSheet(f"background:{color}; border-radius:5px;")
    return d


class Segmented(QWidget):
    """An iOS segmented control."""
    changed = Signal(int)

    def __init__(self, titles: list[str]):
        super().__init__()
        self.setObjectName("segmented")
        self.setStyleSheet(f"""
            #segmented {{ background:{APPLE['fill']}; border-radius:9px; }}
            #segment {{ background:transparent; border:none; border-radius:7px;
                        padding:5px 16px; font-size:13px; font-weight:600; }}
            #segment:checked {{ background:white; }}""")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.buttons = []
        for i, t in enumerate(titles):
            b = QPushButton(t)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.select(i))
            lay.addWidget(b)
            self.buttons.append(b)
        self.select(0, emit=False)

    def select(self, index: int, emit: bool = True):
        for i, b in enumerate(self.buttons):
            b.setChecked(i == index)
        self.index = index
        if emit:
            self.changed.emit(index)

    def set_title(self, index: int, title: str):
        b = self.buttons[index]
        b.setText(title)
        b.ensurePolished()      # measure with the stylesheet's bold font
        b.setMinimumWidth(b.sizeHint().width())     # never clip a longer title
        self.layout().invalidate()
        self.updateGeometry()   # let the surrounding layout make room


class Switch(QAbstractButton):
    """An iOS toggle switch."""

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 28)

    def sizeHint(self):
        return QSize(46, 28)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(APPLE["green"] if self.isChecked() else APPLE["fill"]))
        p.drawRoundedRect(QRectF(0, 0, 46, 28), 14, 14)
        p.setBrush(QColor("white"))
        x = 20 if self.isChecked() else 2
        p.drawEllipse(QRectF(x, 2, 24, 24))


class _PickerMenu(QFrame):
    """The menu a Picker opens: a rounded card with large rows, a blue
    checkmark on the current choice and an optional colour dot per option,
    like a menu on iOS."""
    chosen = Signal(int)

    def __init__(self, items, current: int, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 18)        # room for the shadow
        card = QFrame()
        card.setObjectName("pickerCard")
        card.setStyleSheet(f"""
            #pickerCard {{ background: white; border-radius: 14px;
                           border: 1px solid {APPLE['fill']}; }}
            #pickerRow {{ background: transparent; border: none; border-radius: 9px;
                          text-align: left; padding: 0 14px; font-size: 16px;
                          color: {APPLE['label']}; }}
            #pickerRow:hover {{ background: #E8F1FF; }}""")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 60))
        card.setGraphicsEffect(shadow)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        for i, (text, _, color) in enumerate(items):
            row = QPushButton()
            row.setObjectName("pickerRow")
            row.setCursor(Qt.PointingHandCursor)
            row.setMinimumHeight(44)                    # Apple's minimum tap target
            row.setMinimumWidth(260)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 0, 14, 0)
            rl.setSpacing(10)
            check = QLabel("\u2713" if i == current else "")
            check.setFixedWidth(16)
            check.setStyleSheet(f"color:{APPLE['blue']}; font-size:16px; "
                                f"font-weight:700; background:transparent;")
            rl.addWidget(check)
            if color:
                rl.addWidget(dot(color))
            name = QLabel(text)
            name.setStyleSheet("background:transparent; font-size:16px;"
                               + (" font-weight:600;" if i == current else ""))
            rl.addWidget(name, 1)
            for w in (check, name):
                w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            row.clicked.connect(lambda _=False, i=i: self._choose(i))
            lay.addWidget(row)
        outer.addWidget(card)

    def _choose(self, i: int):
        self.chosen.emit(i)
        self.close()


class Picker(QPushButton):
    """A value that opens an iOS-style menu when clicked. It has the parts of
    QComboBox's interface that the screens use."""
    currentIndexChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("picker")
        self.setCursor(Qt.PointingHandCursor)
        self.items: list[tuple[str, object, str | None]] = []
        self.index = -1
        self.clicked.connect(self._open)

    def addItem(self, text: str, data=None, color: str | None = None):
        self.items.append((text, data, color))
        if self.index < 0:
            self.setCurrentIndex(0)

    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def count(self) -> int:
        return len(self.items)

    def currentIndex(self) -> int:
        return self.index

    def currentData(self):
        return self.items[self.index][1] if self.index >= 0 else None

    def currentText(self) -> str:
        return self.items[self.index][0] if self.index >= 0 else ""

    def setCurrentIndex(self, i: int):
        changed = i != self.index
        self.index = i
        text, _, color = self.items[i]
        self.setText(f"{text}  \u25BE")
        tint = color or APPLE["blue"]
        self.setStyleSheet(f"#picker {{ color:{tint}; background:transparent; "
                           f"border:none; font-size:15px; font-weight:500; "
                           f"padding:6px 2px; text-align:right; }}"
                           f"#picker:hover {{ color:{APPLE['label'] if not color else tint}; }}")
        if changed:
            self.currentIndexChanged.emit(i)

    def _open(self):
        menu = _PickerMenu(self.items, self.index, self)
        menu.chosen.connect(self.setCurrentIndex)
        menu.adjustSize()
        pos = self.mapToGlobal(self.rect().bottomRight())
        menu.move(pos.x() - menu.width() + 14, pos.y() - 4)
        menu.show()
        self._menu = menu                               # keep it alive while open


class Card(QFrame):
    """A rounded white group of rows with hairline separators."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.rows = 0

    def add(self, widget: QWidget) -> QWidget:
        widget.separator = None
        if self.rows:
            line = QFrame()
            line.setObjectName("separator")
            line.setFixedHeight(1)
            holder = QWidget()
            h = QHBoxLayout(holder)
            h.setContentsMargins(16, 0, 0, 0)
            h.addWidget(line)
            self.lay.addWidget(holder)
            widget.separator = holder
        self.lay.addWidget(widget)
        self.rows += 1
        return widget

    @staticmethod
    def show_row(widget: QWidget, visible: bool):
        widget.setVisible(visible)
        if widget.separator is not None:
            widget.separator.setVisible(visible)


class Row(QFrame):
    """A list row: optional leading widget, title, subtitle, trailing widget
    and a chevron when it can be tapped."""
    clicked = Signal()

    def __init__(self, title: str, subtitle: str = "", leading: QWidget | None = None,
                 trailing: QWidget | None = None, tappable: bool = False,
                 title_color: str | None = None, plain: bool = False):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.tappable = tappable
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 14, 10)
        lay.setSpacing(12)
        if leading is not None:
            lay.addWidget(leading, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = label(title, "rowText" if plain else "rowTitle", wrap=True)
        if title_color:
            t.setStyleSheet(f"color:{title_color};")
        text.addWidget(t)
        if subtitle:
            text.addWidget(label(subtitle, "rowSubtitle", wrap=True))
        lay.addLayout(text, 1)
        if trailing is not None:
            lay.addWidget(trailing, 0, Qt.AlignVCenter)
        if tappable:
            lay.addWidget(label("›", "chevron"), 0, Qt.AlignVCenter)
            self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if self.tappable and e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        if self.tappable:
            self.setStyleSheet(f"background:{APPLE['background']};")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet("")
        super().leaveEvent(e)


def field_row(title: str, editor: QWidget) -> QWidget:
    if isinstance(editor, (QLineEdit, QComboBox, QDateEdit, QSpinBox)):
        editor.setObjectName("valueEditor")
        if isinstance(editor, QLineEdit):
            editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        else:
            editor.setLayoutDirection(Qt.LeftToRight)
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(16, 8, 14, 8)
    lay.addWidget(label(title), 1)
    lay.addWidget(editor, 0)
    return w


def plain_button(text: str, destructive: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("destructive" if destructive else "plainButton")
    b.setCursor(Qt.PointingHandCursor)
    return b


def filled_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("filledButton")
    b.setCursor(Qt.PointingHandCursor)
    return b


class ScrollPage(QScrollArea):
    """A scrolling page with a centred column, like an iOS grouped list."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("scrollBody")
        outer = QHBoxLayout(body)
        outer.setContentsMargins(20, 12, 20, 28)
        column = QWidget()
        column.setMaximumWidth(720)
        self.col = QVBoxLayout(column)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(6)
        outer.addStretch(1)
        outer.addWidget(column, 100)
        outer.addStretch(1)
        self.setWidget(body)

    def header(self, text: str, detail: str = ""):
        """An upper-case section heading; `detail` (a file name) keeps its case."""
        h = label(text.upper() + (f" · {detail}" if detail else ""),
                  "sectionHeader")
        h.setContentsMargins(16, 14, 0, 2)
        self.col.addWidget(h)

    def footnote(self, text: str):
        f = label(text, "footnote", wrap=True)
        f.setContentsMargins(16, 2, 16, 0)
        self.col.addWidget(f)

    def add(self, w: QWidget):
        self.col.addWidget(w)
        return w

    def finish(self):
        self.col.addStretch(1)


def nav_bar(back_text: str, on_back) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    b = QPushButton("‹  " + back_text)
    b.setObjectName("backButton")
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(on_back)
    lay.addWidget(b)
    lay.addStretch(1)
    return w


def day(d: date, fmt: str = "%b %Y") -> str:
    """'5 Jan 2027', without a leading zero (strftime has no portable way)."""
    return f"{d.day} {d:{fmt}}"


def countdown(d: date, today: date) -> str:
    days = (d - today).days
    if days < 0:
        return f"{-days} day{'s' if days != -1 else ''} ago"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


# ---- dialogs ---------------------------------------------------------------

class CustomEntryDialog(QDialog):
    """Add a fellowship that isn't in the database."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Your Own Fellowship")
        self.setMinimumWidth(420)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Institute Internal Fellowship")
        self.funder = QLineEdit()
        self.link = QLineEdit()
        self.link.setPlaceholderText("https://")
        self.has_deadline = Switch(True)
        self.deadline = QDateEdit(QDate.currentDate().addMonths(2))
        self.deadline.setCalendarPopup(True)
        self.deadline.setDisplayFormat("d MMM yyyy")
        self.has_deadline.toggled.connect(self.deadline.setEnabled)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(70)
        form.addRow("Name", self.name)
        form.addRow("Funder", self.funder)
        form.addRow("Link", self.link)
        form.addRow("Has a deadline", self.has_deadline)
        form.addRow("Deadline", self.deadline)
        form.addRow("Notes", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def data(self) -> dict:
        d = {"name": self.name.text().strip(), "funder": self.funder.text().strip(),
             "url": self.link.text().strip(), "notes": self.notes.toPlainText().strip()}
        if self.has_deadline.isChecked():
            d["deadlines"] = [{"kind": "final",
                               "date": self.deadline.date().toPython().isoformat()}]
        return d

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Name needed", "Give the fellowship a name.")
            return
        self.accept()


class StayDialog(QDialog):
    """A place the researcher has lived, for mobility rules."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a Place You've Lived")
        form = QFormLayout()
        self.country = QLineEdit()
        self.country.setPlaceholderText("Two-letter code, e.g. IN")
        self.country.setMaxLength(2)
        self.start = QDateEdit(QDate.currentDate().addYears(-3))
        self.end = QDateEdit(QDate.currentDate())
        for d in (self.start, self.end):
            d.setCalendarPopup(True)
            d.setDisplayFormat("MMM yyyy")
        self.current = Switch(True)
        self.end.setEnabled(False)
        self.current.toggled.connect(lambda on: self.end.setEnabled(not on))
        form.addRow("Country", self.country)
        form.addRow("From", self.start)
        form.addRow("I still live here", self.current)
        form.addRow("Until", self.end)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def stay(self) -> Stay:
        return Stay(self.country.text().strip().upper(),
                    self.start.date().toPython(),
                    None if self.current.isChecked() else self.end.date().toPython())

    def _accept(self):
        code = self.country.text().strip()
        if len(code) != 2 or not code.isalpha():
            QMessageBox.warning(self, "Country code", "Use a two-letter country "
                                                      "code, like IN, DE or GB.")
            return
        self.accept()


def parse_codes(text: str) -> list[str]:
    """'in, gb' -> ['IN', 'GB']; raises ValueError naming any bad code."""
    codes = [c.strip().upper() for c in text.replace(";", ",").split(",") if c.strip()]
    bad = [c for c in codes if len(c) != 2 or not c.isalpha()]
    if bad:
        raise ValueError(", ".join(bad))
    return codes


class UpdateWorker(QObject):
    """Downloads the fellowship list off the main thread."""
    finished = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.finished.emit(fetch_updates())
        except OSError:
            self.failed.emit("Galley couldn't reach GitHub. Check your internet "
                             "connection and try again.")
        except ValueError as e:
            self.failed.emit(str(e))


# ---- the page --------------------------------------------------------------

class FellowshipsPage(QWidget):
    attentionChanged = Signal(int)      # reminders needing action now

    def __init__(self, today: date | None = None):
        super().__init__()
        self.setObjectName("fellowships")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(apple_stylesheet(apple_font()))
        self.today = today or date.today()
        self.load_error: str | None = None
        self.category_filter: str | None = None     # None = all categories
        self.show_examples = False      # the invented entries, for trying Galley
        self._update_thread: QThread | None = None
        self.update_note = ""           # result of the last "Check for Updates"
        self.reload_data()

        self.stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)

        self.home = QWidget()
        home = QVBoxLayout(self.home)
        home.setContentsMargins(0, 16, 0, 0)
        home.setSpacing(8)
        # Same centred column as the lists below, so everything lines up.
        header = QHBoxLayout()
        header.setContentsMargins(20, 0, 20, 0)
        column = QWidget()
        column.setMaximumWidth(720)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        self.title = label("Fellowships", "largeTitle")
        col.addWidget(self.title)
        seg_row = QHBoxLayout()
        self.tabs = Segmented(["Profile", "Matches", "Applications"])
        self.tabs.changed.connect(self._tab_changed)
        seg_row.addWidget(self.tabs)
        seg_row.addStretch(1)
        col.addLayout(seg_row)
        header.addStretch(1)
        header.addWidget(column, 100)
        header.addStretch(1)
        home.addLayout(header)
        self.tab_stack = QStackedWidget()
        home.addWidget(self.tab_stack, 1)
        self.stack.addWidget(self.home)
        self.detail: QWidget | None = None
        # New users start by telling Galley about themselves.
        self.tabs.select(PROFILE if self.profile_is_empty() else MATCHES, emit=False)
        self.refresh()

    # -- data ----------------------------------------------------------------
    def reload_data(self):
        try:
            self.fellowships = load_fellowships(include_templates=self.show_examples)
            self.load_error = None
        except ValueError as e:
            self.fellowships, self.load_error = [], str(e)
        self.researcher = load_researcher()
        self.apps = load_applications()
        self.by_id = {f.id: f for f in self.fellowships}

    def save_apps(self):
        save_applications(self.apps)
        self.attentionChanged.emit(self.attention_count())

    def current_reminders(self):
        return reminders(self.apps, self.fellowships, self.today, update_seen=False)

    def attention_count(self) -> int:
        return sum(1 for r in self.current_reminders()
                   if r.urgency in ("overdue", "soon", "changed"))

    def profile_is_empty(self) -> bool:
        r = self.researcher
        return not (r.career_level or r.phd_date or r.phd_expected
                    or r.nationalities or r.fields)

    # -- navigation ----------------------------------------------------------
    def refresh(self, tab: int | None = None):
        tab = self.tabs.index if tab is None else tab
        while self.tab_stack.count():
            w = self.tab_stack.widget(0)
            self.tab_stack.removeWidget(w)
            w.deleteLater()
        self.tab_stack.addWidget(self._profile_tab())       # PROFILE
        self.tab_stack.addWidget(self._matches_tab())       # MATCHES
        self.tab_stack.addWidget(self._applications_tab())  # APPLICATIONS
        self.tabs.select(tab, emit=False)
        self.tab_stack.setCurrentIndex(tab)
        n = self.attention_count()
        self.tabs.set_title(APPLICATIONS, f"Applications ({n})" if n else "Applications")
        self.attentionChanged.emit(n)

    def _tab_changed(self, index: int):
        self.tab_stack.setCurrentIndex(index)

    def show_tab(self, index: int):
        self._close_detail()
        self.tabs.select(index)

    def _push(self, page: QWidget):
        self._close_detail()
        self.detail = page
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def _close_detail(self):
        if self.detail is not None:
            self.stack.removeWidget(self.detail)
            self.detail.deleteLater()
            self.detail = None
        self.stack.setCurrentWidget(self.home)

    def _back(self, tab: int):
        self.refresh(tab)
        self._close_detail()

    # -- Matches -------------------------------------------------------------
    def _matches_tab(self) -> QWidget:
        page = ScrollPage()
        if self.load_error:
            page.header("Fellowship list")
            card = page.add(Card())
            card.add(Row("The fellowship list couldn't be read",
                         self.load_error, leading=mark(NOT_MET)))
        if self.profile_is_empty():
            page.header("Get started")
            card = page.add(Card())
            row = card.add(Row("Fill in your profile",
                               "Add your career stage, PhD date, nationality and "
                               "field to see what you can apply for.",
                               leading=mark(INFO), tappable=True))
            row.clicked.connect(lambda: self.show_tab(PROFILE))

        page.header("Fellowship list")
        card = page.add(Card())
        when = last_updated()
        sub = (f"Updated {day(when.astimezone().date())}" if when
               else "The list included with Galley")
        if self.update_note:
            sub += f" \u00b7 {self.update_note}"
        self.update_button = plain_button("Check for Updates")
        self.update_button.clicked.connect(self.check_for_updates)
        if self._update_thread is not None:
            self.update_button.setText("Checking\u2026")
            self.update_button.setEnabled(False)
        count = sum(1 for f in self.fellowships if not f.template)
        title = f"{count} fellowship{'s' if count != 1 else ''}"
        examples = sum(1 for f in self.fellowships if f.template)
        if examples:
            title += f" (+{examples} examples shown)"
        card.add(Row(title, sub, trailing=self.update_button))

        filt = Segmented(["All", "Postdoc", "PhD", "Travel"])
        filt.select(CATEGORY_FILTERS.index(self.category_filter), emit=False)
        filt.changed.connect(self._filter_category)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 4, 0, 0)
        hl.addWidget(filt)
        hl.addStretch(1)
        page.add(holder)

        shown = [f for f in self.fellowships
                 if self.category_filter in (None, f.category)]
        matches = match_all(shown, self.researcher, self.today)
        groups = [(ELIGIBLE, "You're eligible"), (POSSIBLE, "Worth checking"),
                  (NOT_ELIGIBLE, "Not eligible")]
        for status, title in groups:
            items = [m for m in matches if m.status == status]
            if not items:
                continue
            page.header(f"{title} · {len(items)}")
            card = page.add(Card())
            for m in items:
                f = m.fellowship
                if m.deadline:
                    when = (f"Closes {day(m.deadline.date)} · "
                            f"{countdown(m.deadline.date, self.today)}")
                elif f.rolling:
                    when = "Open all year"
                else:
                    when = "No deadline announced"
                kind = CATEGORY_LABEL[f.category] + (" (example)" if f.template else "")
                sub = " · ".join(x for x in (kind, f.funder, when) if x)
                trailing = QWidget()
                tl = QHBoxLayout(trailing)
                tl.setContentsMargins(0, 0, 0, 0)
                if f.id in self.apps:
                    tl.addWidget(label("Added", "rowSubtitle"))
                tl.addWidget(pill(STATUS_LABEL[status], STATUS_COLOR[status]))
                row = card.add(Row(f.name, sub, trailing=trailing, tappable=True))
                row.clicked.connect(lambda f=f: self.open_fellowship(f.id))
        real = [f for f in self.fellowships if not f.template]
        if not matches and not self.load_error:
            page.header("Fellowships")
            card = page.add(Card())
            card.add(Row("No fellowships yet",
                         "Add your own from the Applications tab."))
        if not real or self.show_examples:
            page.header("Try Galley")
            card = page.add(Card())
            sw = Switch(self.show_examples)
            sw.toggled.connect(self._toggle_examples)
            card.add(field_row("Show invented example entries", sw))
            page.footnote("The examples aren't real fellowships; they show how "
                          "matching, plans and the application check work.")
        page.footnote("Results are guidance. The funder's official rules decide "
                      "eligibility; each entry links to them.")
        page.finish()
        return page

    def check_for_updates(self):
        """Download the latest list from GitHub in the background."""
        if self._update_thread is not None:
            return
        self.update_button.setText("Checking\u2026")
        self.update_button.setEnabled(False)
        self._update_thread = QThread()
        self._update_worker = UpdateWorker()
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._update_done)
        self._update_worker.failed.connect(self._update_failed)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.failed.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_cleanup)
        self._update_thread.start()

    def _update_done(self, result):
        skipped = (f", {len(result.skipped)} skipped" if result.skipped else "")
        self.update_note = f"{result.count} entries downloaded{skipped}"
        self.reload_data()

    def _update_failed(self, message: str):
        self.update_note = ""
        QMessageBox.warning(self, "Couldn't update the list", message)

    def _update_cleanup(self):
        self._update_thread.deleteLater()
        self._update_thread = None
        self.refresh(MATCHES)

    def _toggle_examples(self, on: bool):
        self.show_examples = on
        self.reload_data()
        self.refresh(MATCHES)

    def _filter_category(self, index: int):
        self.category_filter = CATEGORY_FILTERS[index]
        self.refresh(MATCHES)

    def open_fellowship(self, fid: str):
        f = self.by_id[fid]
        m = match(f, self.researcher, self.today)
        page = ScrollPage()
        page.add(nav_bar("Matches", lambda: self._back(MATCHES)))
        page.add(label(f.name, "detailTitle", wrap=True))
        if f.funder:
            page.add(label(f.funder, "secondary", wrap=True))
        status_row = QWidget()
        sl = QHBoxLayout(status_row)
        sl.setContentsMargins(0, 6, 0, 0)
        sl.addWidget(pill(STATUS_LABEL[m.status], STATUS_COLOR[m.status]))
        sl.addStretch(1)
        page.add(status_row)

        page.header("Eligibility")
        card = page.add(Card())
        for r in m.reasons or []:
            card.add(Row(r.text, leading=mark(r.outcome), plain=True))
        if not m.reasons:
            card.add(Row("No eligibility rules are listed.", leading=mark(INFO),
                         plain=True))

        if f.deadlines or f.rolling:
            page.header("Dates")
            card = page.add(Card())
            if f.rolling:
                card.add(Row("Open all year"))
            for d in f.deadlines:
                if d.date < self.today:
                    continue
                name = d.label or DEADLINE_LABEL.get(d.kind, d.kind)
                extra = " (estimated)" if d.estimated else ""
                tz = f" {d.time} {d.timezone or ''}".rstrip() if d.time else ""
                card.add(Row(name, f"{day(d.date, '%B %Y')}{tz}{extra} · "
                                   f"{countdown(d.date, self.today)}"))

        req = f.requirements
        if req:
            page.header("What you need")
            card = page.add(Card())
            for doc in req.documents:
                limits = []
                if doc.max_pages:
                    limits.append(f"{doc.max_pages} pages max")
                if doc.max_words:
                    limits.append(f"{doc.max_words:,} words max")
                if doc.min_font_size:
                    limits.append(f"{doc.min_font_size:g} pt text or larger")
                if doc.sections:
                    limits.append("sections: " + ", ".join(doc.sections))
                check = plain_button("Check Draft…")
                check.clicked.connect(lambda _=False, doc=doc:
                                      self._check_draft(doc, f.id))
                card.add(Row(doc.name, "; ".join(limits) or (doc.notes or ""),
                             trailing=check))
            if req.cv_format:
                card.add(Row(CV_LABEL[req.cv_format], req.cv_notes or ""))
            if req.host_letter:
                card.add(Row("Letter of support from your host"))
            if req.submission:
                card.add(Row("How to submit", ROUTE_LABEL[req.submission]))

        details = [(k, v) for k, v in (
            ("Type", CATEGORY_LABEL[f.category]),
            ("Pays for", PURPOSE_LABEL.get(f.purpose) if f.purpose else None),
            ("Funding", f.amount),
            ("Length", f"{f.duration_months} months" if f.duration_months else None),
            ("Notes", f.notes)) if v]
        if details:
            page.header("Details")
            card = page.add(Card())
            for k, v in details:
                card.add(Row(k, v))

        page.header("")
        card = page.add(Card())
        actions = QWidget()
        al = QVBoxLayout(actions)
        al.setContentsMargins(16, 12, 16, 12)
        al.setSpacing(6)
        if f.id in self.apps:
            go = filled_button("Open in My Applications")
            go.clicked.connect(lambda: self.open_application(f.id))
        else:
            go = filled_button("Add to My Applications")
            go.clicked.connect(lambda: self._add_application(f.id))
        al.addWidget(go)
        if f.url:
            official = plain_button("Official Page")
            official.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f.url)))
            al.addWidget(official)
        report = f.report_problem_url()
        if report:
            rep = plain_button("Report Outdated Information")
            rep.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(report)))
            al.addWidget(rep)
        if f.custom:
            delete = plain_button("Delete This Entry", destructive=True)
            delete.clicked.connect(lambda: self._delete_custom(f.id))
            al.addWidget(delete)
        card.add(actions)
        page.footnote(f"Eligibility is guidance only; confirm on the funder's page."
                      if not f.custom else "You added this entry yourself.")
        page.finish()
        self._push(page)

    def _choose_file(self, title: str) -> str | None:
        kinds = "*.docx *.pdf" if pdf_supported() else "*.docx"
        path, _ = QFileDialog.getOpenFileName(self, title, "",
                                              f"Documents ({kinds})")
        return path or None

    def _check_draft(self, doc, fid: str):
        path = self._choose_file(f"Check your {doc.name}")
        if not path:
            return
        try:
            findings = check_document(path, doc)
        except Exception as e:      # an unreadable file shouldn't crash the app
            QMessageBox.warning(self, "Couldn't read the file", str(e))
            return
        from pathlib import Path
        self._show_report(doc.name, "Back", lambda: self.open_fellowship(fid),
                          [(doc.name, Path(path).name, findings)], [])

    def _show_report(self, title: str, back_text: str, on_back,
                     sections: list, general: list):
        """A results page: a summary, then each document's findings."""
        page = ScrollPage()
        page.add(nav_bar(back_text, on_back))
        problems = sum(1 for *_, fs in sections for f in fs if f.outcome == FAIL)
        warnings = sum(1 for *_, fs in sections for f in fs if f.outcome == WARN)
        if problems:
            head, color = (f"{problems} thing{'s' if problems != 1 else ''} to fix",
                           APPLE["red"])
        elif warnings:
            head, color = (f"Ready, with {warnings} thing{'s' if warnings != 1 else ''}"
                           f" to check", APPLE["orange"])
        else:
            head, color = "Ready to submit", APPLE["green"]
        page.add(label(title, "detailTitle", wrap=True))
        summary = label(head, wrap=True)
        summary.setStyleSheet(f"color:{color}; font-size:17px; font-weight:600;")
        page.add(summary)
        order = {FAIL: 0, WARN: 1, PASS: 2, NOTE: 3}
        for heading, detail, findings in sections:
            page.header(heading, detail)
            card = page.add(Card())
            for f in sorted(findings, key=lambda f: order[f.outcome]):
                card.add(Row(f.text, f.suggestion or "",
                             leading=mark(FINDING_MARK[f.outcome]), plain=True))
            if not findings:
                card.add(Row("Nothing in the requirements to check.",
                             leading=mark(INFO), plain=True))
        if general:
            page.header("Also remember")
            card = page.add(Card())
            for f in general:
                card.add(Row(f.text, leading=mark(FINDING_MARK[f.outcome]), plain=True))
        page.footnote("Galley checks the format the funder sets out. Read the "
                      "official guidance too; it has the final word.")
        page.finish()
        self._push(page)

    def _add_application(self, fid: str):
        start_application(self.apps, self.by_id[fid], self.today)
        self.save_apps()
        self.open_application(fid)

    def _delete_custom(self, fid: str):
        if QMessageBox.question(self, "Delete entry",
                                "Delete this fellowship and its application?") \
                != QMessageBox.Yes:
            return
        delete_custom_fellowship(fid)
        self.apps.pop(fid, None)
        save_applications(self.apps)
        self.reload_data()
        self._back(MATCHES)

    # -- Applications --------------------------------------------------------
    def _applications_tab(self) -> QWidget:
        page = ScrollPage()
        found = self.current_reminders()
        if found:
            page.header("Coming up")
            card = page.add(Card())
            for r in found:
                if r.urgency == "changed":
                    sub = f"{r.fellowship} · tap to acknowledge"
                else:
                    sub = f"{r.fellowship} · {day(r.date, '%b')} · " \
                          f"{countdown(r.date, self.today)}"
                row = card.add(Row(r.text, sub, leading=dot(URGENCY_COLOR[r.urgency]),
                                   tappable=True))
                if r.urgency == "changed":
                    row.clicked.connect(lambda r=r: self._acknowledge(r.fellowship_id))
                else:
                    row.clicked.connect(lambda r=r: self.open_application(r.fellowship_id))

        page.header("My applications")
        card = page.add(Card())
        apps = [a for a in self.apps.values() if a.fellowship_id in self.by_id]
        if not apps:
            card.add(Row("No applications yet",
                         "Open a fellowship in Matches and choose Add to My "
                         "Applications."))
        order = {s: i for i, s in enumerate(STATUSES)}
        for a in sorted(apps, key=lambda a: (order[a.status],
                                             self.by_id[a.fellowship_id].name)):
            f = self.by_id[a.fellowship_id]
            nxt = f.next_deadline(self.today)
            sub = (f"Deadline {day(nxt.date)} · {countdown(nxt.date, self.today)}"
                   if nxt else "No upcoming deadline")
            color = STAGE_COLOR[a.status]
            row = card.add(Row(f.name, sub,
                               trailing=pill(APP_STATUS_LABEL[a.status], color),
                               tappable=True))
            row.clicked.connect(lambda a=a: self.open_application(a.fellowship_id))

        page.header("")
        card = page.add(Card())
        add = Row("Add Your Own Fellowship…", title_color=APPLE["blue"],
                  tappable=True)
        add.clicked.connect(self._add_custom)
        card.add(add)
        page.footnote("For schemes Galley doesn't list, like your institute's "
                      "internal fellowship. Saved on this computer only.")
        page.finish()
        return page

    def _acknowledge(self, fid: str):
        app, f = self.apps[fid], self.by_id[fid]
        nxt = f.next_deadline(self.today)
        app.deadline_seen = nxt.date.isoformat() if nxt else None
        self.save_apps()
        self.refresh(APPLICATIONS)

    def _add_custom(self):
        dlg = CustomEntryDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            f = save_custom_fellowship(dlg.data())
        except ValueError as e:
            QMessageBox.warning(self, "Couldn't save", str(e))
            return
        self.reload_data()
        start_application(self.apps, self.by_id[f.id], self.today)
        self.save_apps()
        self.refresh(APPLICATIONS)

    def open_application(self, fid: str):
        f, app = self.by_id[fid], self.apps[fid]
        page = ScrollPage()
        page.add(nav_bar("Applications", lambda: self._back(APPLICATIONS)))
        page.add(label(f.name, "detailTitle", wrap=True))
        if f.funder:
            page.add(label(f.funder, "secondary", wrap=True))

        page.header("Status")
        card = page.add(Card())
        status = Picker()
        for s in STATUSES:
            status.addItem(APP_STATUS_LABEL[s], s, STAGE_COLOR[s])
        status.setCurrentIndex(STATUSES.index(app.status))
        card.add(field_row("Stage", status))
        interview = QDateEdit()
        interview.setCalendarPopup(True)
        interview.setDisplayFormat("d MMM yyyy")
        interview.setDate(QDate.fromString(app.interview_date, "yyyy-MM-dd")
                          if app.interview_date else QDate.currentDate())
        interview_row = card.add(field_row("Interview date", interview))
        Card.show_row(interview_row, app.status == "interview")

        def status_changed(_):
            app.set_status(status.currentData(), self.today)
            Card.show_row(interview_row, app.status == "interview")
            if app.status == "interview" and not app.interview_date:
                app.interview_date = interview.date().toPython().isoformat()
            self.save_apps()
        status.currentIndexChanged.connect(status_changed)

        def interview_changed(d: QDate):
            app.interview_date = d.toPython().isoformat()
            self.save_apps()
        interview.dateChanged.connect(interview_changed)

        req = f.requirements
        if req and req.documents:
            page.header("Check your application")
            card = page.add(Card())
            from pathlib import Path
            for doc in req.documents:
                path = app.files.get(doc.name)
                sub = Path(path).name if path else "Not attached"
                attach = plain_button("Change…" if path else "Attach…")
                attach.clicked.connect(lambda _=False, doc=doc:
                                       self._attach(fid, doc.name))
                card.add(Row(doc.name, sub, trailing=attach))
            run = QWidget()
            rl = QHBoxLayout(run)
            rl.setContentsMargins(16, 12, 16, 12)
            check = filled_button("Check Application")
            check.setEnabled(bool(app.files))
            check.clicked.connect(lambda: self._check_application(fid))
            rl.addWidget(check)
            rl.addStretch(1)
            card.add(run)
            page.footnote("Attach each document to check it against this "
                          "fellowship's format: pages, words, sections, text "
                          "size and margins. Files stay where they are.")

        steps = plan(f, self.today)
        if steps:
            page.header("Plan")
            card = page.add(Card())
            for s in steps:
                when = f"{day(s.date)} · {countdown(s.date, self.today)}"
                if s.is_deadline:
                    card.add(Row(s.task, when, leading=dot(APPLE["red"])))
                    continue
                done = s.key in app.done
                tick = QPushButton("✓" if done else "")
                tick.setCheckable(True)
                tick.setChecked(done)
                tick.setFixedSize(24, 24)
                tick.setCursor(Qt.PointingHandCursor)
                tick.setStyleSheet(self._tick_style(done))
                overdue = s.overdue(self.today) and not done
                row = Row(s.task, when, leading=tick,
                          title_color=APPLE["red"] if overdue else None)
                tick.toggled.connect(lambda on, key=s.key, t=tick:
                                     self._toggle_step(app, key, on, t))
                card.add(row)
            page.footnote("Suggested dates, worked back from the deadline.")

        page.header("Notes")
        card = page.add(Card())
        notes = QPlainTextEdit(app.notes)
        notes.setPlaceholderText("Host lab contacts, ideas, anything to remember")
        notes.setFixedHeight(110)
        notes.setStyleSheet("border:none;")

        def notes_changed():
            app.notes = notes.toPlainText()
            save_applications(self.apps)
        notes.textChanged.connect(notes_changed)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(12, 6, 12, 6)
        hl.addWidget(notes)
        card.add(holder)

        page.header("")
        card = page.add(Card())
        actions = QWidget()
        al = QVBoxLayout(actions)
        al.setContentsMargins(16, 10, 16, 10)
        view = plain_button("View Fellowship Details")
        view.clicked.connect(lambda: self.open_fellowship(fid))
        remove = plain_button("Remove from My Applications", destructive=True)
        remove.clicked.connect(lambda: self._remove_application(fid))
        al.addWidget(view)
        al.addWidget(remove)
        card.add(actions)
        page.finish()
        self._push(page)

    def _attach(self, fid: str, document: str):
        path = self._choose_file(f"Attach your {document}")
        if not path:
            return
        self.apps[fid].files[document] = path
        save_applications(self.apps)
        self.open_application(fid)

    def _check_application(self, fid: str):
        f, app = self.by_id[fid], self.apps[fid]
        report = check_application(f, app.files)
        if report.ready and all(d.path for d in report.documents):
            app.mark_done("final_check")    # the plan's "check every document"
            self.save_apps()
        from pathlib import Path
        sections = [(d.name, Path(d.path).name if d.path else "", d.findings)
                    for d in report.documents]
        self._show_report(f.name, "Application", lambda: self.open_application(fid),
                          sections, report.general)

    @staticmethod
    def _tick_style(done: bool) -> str:
        if done:
            return (f"background:{APPLE['blue']}; color:white; border:none; "
                    f"border-radius:12px; font-weight:700;")
        return (f"background:white; border:1.5px solid {APPLE['tertiary']}; "
                f"border-radius:12px;")

    def _toggle_step(self, app, key: str, on: bool, tick: QPushButton):
        app.mark_done(key, on)
        tick.setText("✓" if on else "")
        tick.setStyleSheet(self._tick_style(on))
        self.save_apps()

    def _remove_application(self, fid: str):
        if QMessageBox.question(self, "Remove application",
                                "Remove this from My Applications? Your notes "
                                "and progress for it will be deleted.") \
                != QMessageBox.Yes:
            return
        self.apps.pop(fid, None)
        self.save_apps()
        self._back(APPLICATIONS)

    # -- Profile -------------------------------------------------------------
    def _profile_tab(self) -> QWidget:
        r = self.researcher
        page = ScrollPage()

        page.header("Career stage")
        card = page.add(Card())
        self.p_level = Picker()
        for key, text in LEVEL_CHOICES:
            self.p_level.addItem(text, key)
        self.p_level.setCurrentIndex([k for k, _ in LEVEL_CHOICES].index(r.career_level))
        card.add(field_row("I am a", self.p_level))
        self.p_phd_state = Picker()
        self.p_phd_state.addItems(["Awarded", "In progress", "Not set"])
        self.p_phd_state.setCurrentIndex(0 if r.phd_date else 1 if r.phd_expected else 2)
        phd_row = card.add(field_row("PhD", self.p_phd_state))
        self.p_phd_date = QDateEdit()
        self.p_phd_date.setCalendarPopup(True)
        self.p_phd_date.setDisplayFormat("d MMM yyyy")
        when = r.phd_date or r.phd_expected
        self.p_phd_date.setDate(QDate(when.year, when.month, when.day) if when
                                else QDate.currentDate())
        self.p_phd_date.setObjectName("valueEditor")
        self.p_phd_label = QLabel()
        date_row = QWidget()
        dl = QHBoxLayout(date_row)
        dl.setContentsMargins(16, 8, 14, 8)
        dl.addWidget(self.p_phd_label, 1)
        dl.addWidget(self.p_phd_date)
        card.add(date_row)

        def phd_state(i):
            Card.show_row(date_row, i != 2)
            self.p_phd_label.setText("PhD awarded" if i == 0 else "PhD expected")
        self.p_phd_state.currentIndexChanged.connect(phd_state)

        def level_changed(_=None):
            # The career stage answers the PhD question: a postdoc's PhD is
            # awarded, a PhD student's is in progress, a Master's student
            # has none yet. Only ask when the stage isn't set.
            state = PHD_STATE_FOR_LEVEL.get(self.p_level.currentData())
            if state is not None:
                self.p_phd_state.setCurrentIndex(state)
            Card.show_row(phd_row, state is None)
            phd_state(self.p_phd_state.currentIndex())
        self.p_level.currentIndexChanged.connect(level_changed)
        level_changed()

        self.p_breaks = QSpinBox()
        self.p_breaks.setRange(0, 240)
        self.p_breaks.setSuffix(" months")
        self.p_breaks.setValue(int(r.career_break_months))
        card.add(field_row("Career breaks", self.p_breaks))
        page.footnote("Parental leave, illness or caring. Many funders extend "
                      "their eligibility window for these.")

        page.header("Where you're from and where you'd go")
        card = page.add(Card())
        self.p_nationality = QLineEdit(", ".join(r.nationalities))
        self.p_nationality.setPlaceholderText("e.g. IN or IN, GB")
        card.add(field_row("Nationality", self.p_nationality))
        self.p_residence = QLineEdit(r.residence or "")
        self.p_residence.setPlaceholderText("e.g. IN")
        card.add(field_row("Country you live in", self.p_residence))
        self.p_hosts = QLineEdit(", ".join(r.target_hosts))
        self.p_hosts.setPlaceholderText("Optional, e.g. DE, GB")
        card.add(field_row("Where you'd like to go", self.p_hosts))
        page.footnote("Two-letter country codes, separated by commas.")

        page.header("Places you've lived")
        card = page.add(Card())
        self.p_stays = list(r.stays)
        for i, s in enumerate(self.p_stays):
            until = f"{s.end:%b %Y}" if s.end else "now"
            rm = plain_button("Remove", destructive=True)
            rm.clicked.connect(lambda _=False, i=i: self._remove_stay(i))
            card.add(Row(s.country, f"{s.start:%b %Y} – {until}", trailing=rm))
        add = Row("Add a Place…", title_color=APPLE["blue"], tappable=True)
        add.clicked.connect(self._add_stay)
        card.add(add)
        page.footnote("Used for mobility rules, such as “no more than 12 "
                      "months in the host country in the last 3 years”.")

        page.header("Research field")
        card = page.add(Card())
        self.p_fields: dict[str, Switch] = {}
        for key in sorted(FIELDS - {"any"}, key=lambda k: FIELD_LABEL[k]):
            sw = Switch(key in r.fields)
            self.p_fields[key] = sw
            card.add(field_row(FIELD_LABEL[key], sw))

        page.header("Clinical")
        card = page.add(Card())
        self.p_clinical = Switch(bool(r.clinical))
        card.add(field_row("I'm clinically qualified", self.p_clinical))

        page.header("")
        card = page.add(Card())
        save_row = QWidget()
        sl = QHBoxLayout(save_row)
        sl.setContentsMargins(16, 12, 16, 12)
        save = filled_button("Save Profile")
        save.clicked.connect(self.save_profile)
        sl.addWidget(save)
        self.p_saved = label("", "secondary")
        sl.addWidget(self.p_saved)
        sl.addStretch(1)
        card.add(save_row)
        page.footnote("Your profile is saved on this computer and never sent "
                      "anywhere.")
        page.finish()
        return page

    def _profile_from_form(self) -> Researcher:
        state = self.p_phd_state.currentIndex()
        when = self.p_phd_date.date().toPython()
        try:
            nationalities = parse_codes(self.p_nationality.text())
            hosts = parse_codes(self.p_hosts.text())
            residence = parse_codes(self.p_residence.text())
        except ValueError as e:
            raise ValueError(f"{e} isn't a two-letter country code.") from None
        if len(residence) > 1:
            raise ValueError("Give one country you live in.")
        return Researcher(
            phd_date=when if state == 0 else None,
            phd_expected=when if state == 1 else None,
            career_break_months=self.p_breaks.value(),
            nationalities=nationalities,
            residence=residence[0] if residence else None,
            stays=self.p_stays,
            fields=[k for k, sw in self.p_fields.items() if sw.isChecked()],
            clinical=self.p_clinical.isChecked(),
            target_hosts=hosts,
            career_level=self.p_level.currentData())

    def save_profile(self):
        try:
            r = self._profile_from_form()
        except ValueError as e:
            QMessageBox.warning(self, "Check your profile", str(e))
            return
        save_researcher(r)
        self.researcher = r
        self.refresh(PROFILE)
        self.p_saved.setText("Saved")

    def _save_stays(self, stays: list[Stay]):
        # Keep whatever else is typed in the form, if it's valid.
        try:
            r = self._profile_from_form()
        except ValueError:
            r = self.researcher
        r.stays = stays
        save_researcher(r)
        self.researcher = r
        self.refresh(PROFILE)

    def _add_stay(self):
        dlg = StayDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._save_stays(self.p_stays + [dlg.stay()])

    def _remove_stay(self, i: int):
        self._save_stays([s for j, s in enumerate(self.p_stays) if j != i])
