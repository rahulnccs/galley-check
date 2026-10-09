"""Choose the journal to check a manuscript against.

A searchable list: the journals the user entered or corrected first, then
Galley's journal list, each saying whether its requirements have been
checked against the journal's guidelines. From here the user can also enter
a journal Galley doesn't list, and download the latest list.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from ..checks.offline.submission import (Profile, available_profiles,
                                         fetch_journal_updates, is_user_profile,
                                         journals_last_updated)

NONE = "none"           # the "No journal limits" row
CHECKED = "#2E7D4F"
UNCHECKED = "#9A6200"


def describe(p: Profile) -> str:
    """The grey line under a journal's name."""
    bits = [p.publisher] if p.publisher else []
    if is_user_profile(p):
        bits.append("your entry")
    if p.verified:
        bits.append(f"✓ checked {p.verified}")
    else:
        bits.append("requirements not yet confirmed")
    return " · ".join(bits)


class JournalPicker(QDialog):
    def __init__(self, parent=None, current: Profile | None = None):
        super().__init__(parent)
        self.setWindowTitle("Choose a Journal")
        self.setMinimumSize(560, 600)
        self.chosen: Profile | None = current
        self.wants_new = False
        self.current = current

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(10)
        head = QLabel("Which journal is this for?")
        head.setObjectName("dialogTitle")
        lay.addWidget(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a journal or publisher, e.g. eLife, Cell Press")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.fill)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setSpacing(1)
        self.list.setStyleSheet("QListWidget { border:1px solid #E5E5EA; border-radius:10px; "
                                "background:white; padding:4px; font-size:14px; }"
                                "QListWidget::item { padding:6px 8px; border-radius:6px; }"
                                "QListWidget::item:selected { background:#DCEBFF; "
                                "color:black; }")
        self.list.itemDoubleClicked.connect(lambda _: self.accept_choice())
        lay.addWidget(self.list, 1)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        row = QHBoxLayout()
        new = QPushButton("Another Journal…")
        new.setToolTip("Enter the requirements of a journal that isn't listed")
        new.clicked.connect(self._new)
        row.addWidget(new)
        update = QPushButton("Check for Updates")
        update.setToolTip("Download the latest journal list")
        update.clicked.connect(self.update_list)
        row.addWidget(update)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        choose = QPushButton("Choose")
        choose.setObjectName("primary")
        choose.setDefault(True)
        choose.clicked.connect(self.accept_choice)
        row.addWidget(choose)
        lay.addLayout(row)

        self.profiles = available_profiles()
        self.fill()
        self._show_status()
        self.search.setFocus()

    # -- the list -------------------------------------------------------------------
    def _header(self, text: str):
        item = QListWidgetItem(text.upper())
        item.setFlags(Qt.NoItemFlags)
        f = QFont()
        f.setBold(True)
        f.setPointSize(max(8, f.pointSize() - 2))
        item.setFont(f)
        item.setForeground(QBrush(QColor("#6C6C70")))
        self.list.addItem(item)

    def _row(self, profile: Profile | None):
        if profile is None:
            item = QListWidgetItem("No journal limits\nCounts only, nothing compared")
            item.setData(Qt.UserRole, NONE)
        else:
            item = QListWidgetItem(f"{profile.label}\n{describe(profile)}")
            item.setData(Qt.UserRole, profile)
            item.setForeground(QBrush(QColor("black")))
            item.setToolTip(profile.guidelines_url or "")
        self.list.addItem(item)
        if (profile is None and self.current is None) or (
                profile is not None and self.current is not None
                and profile.path == self.current.path):
            self.list.setCurrentItem(item)
        return item

    def fill(self, *_):
        q = self.search.text().strip().lower()
        self.list.clear()
        match = [p for p in self.profiles
                 if not q or q in f"{p.name} {p.publisher or ''} {p.article_type or ''}".lower()]
        if not q:
            self._row(None)
        mine = [p for p in match if is_user_profile(p)]
        listed = [p for p in match if not is_user_profile(p)]
        if mine:
            self._header(f"Your journals · {len(mine)}")
            for p in mine:
                self._row(p)
        if listed:
            self._header(f"Journal list · {len(listed)}")
            for p in listed:
                self._row(p)
        if not match:
            item = QListWidgetItem(f"No journal matches “{self.search.text().strip()}”.\n"
                                   f"Choose Another Journal… to enter its requirements.")
            item.setFlags(Qt.NoItemFlags)
            self.list.addItem(item)
        elif q and self.list.currentItem() is None:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) is not None:
                    self.list.setCurrentRow(i)
                    break

    def _show_status(self):
        when = journals_last_updated()
        checked = sum(1 for p in self.profiles if p.verified)
        text = (f"{len(self.profiles)} journals, {checked} with requirements checked "
                f"against the journal's guidelines. Unchecked ones are marked "
                f"“not yet confirmed” in the results.")
        if when:
            text += f" List downloaded {when:%d %b %Y}."
        self.status.setText(text)

    # -- actions --------------------------------------------------------------------
    def accept_choice(self):
        item = self.list.currentItem()
        value = item.data(Qt.UserRole) if item else None
        if value is None:
            return
        self.chosen = None if value == NONE else value
        self.accept()

    def _new(self):
        self.wants_new = True
        self.accept()

    def update_list(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = fetch_journal_updates()
        except OSError:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Couldn't update",
                                "Galley couldn't reach GitHub. Check your internet "
                                "connection and try again; the current list is kept.")
            return
        except ValueError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Couldn't update", str(e))
            return
        QApplication.restoreOverrideCursor()
        self.profiles = available_profiles()
        self.fill()
        self._show_status()
        note = f"The journal list now has {result.count} journals."
        if result.skipped:
            note += f" {len(result.skipped)} files couldn't be read and were skipped."
        QMessageBox.information(self, "Journal list updated", note)
