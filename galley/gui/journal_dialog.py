"""A form for entering a journal's submission rules.

Used for a journal Galley doesn't list, and to correct one it does: the
corrected copy is saved in the user's own folder under the listed journal's
file name, so it takes the listed one's place for them. The user fills this in
while reading the journal's author guidelines, so it is saved as checked today.

Every field except the journal name is optional. A blank field is not checked,
so nobody is nagged about a limit they never set.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from ..checks.offline.submission import save_profile

STYLE_CHOICES = [("Not specified", None),
                 ("Numbered  —  [1], [2,3], or superscript", "numbered"),
                 ("Author\u2013year  —  (Smith et al., 2020)", "author_year")]


def _spin(maximum: int, suffix: str = "", step: int = 1) -> QSpinBox:
    """A spin box where zero means "no limit set"."""
    box = QSpinBox()
    box.setRange(0, maximum)
    box.setSingleStep(step)
    box.setSpecialValueText("not set")
    box.setSuffix(suffix)
    box.setValue(0)
    return box


class JournalDialog(QDialog):
    """Collects the limits Galley can check, and saves them as a profile."""

    def __init__(self, parent=None, profile=None, filename: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Journal requirements")
        self.setMinimumWidth(560)
        self.saved_path = None
        self.filename = filename        # save under this name (a listed journal's)
        self.kept = {}                  # fields the form doesn't show, kept as they are

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 20)
        root.setSpacing(14)

        banner = QLabel("Journal requirements")
        banner.setObjectName("dialogBanner")
        root.addWidget(banner)

        title = QLabel("What does the journal ask for?")
        title.setObjectName("dialogTitle")
        blurb = QLabel(
            "Fill this in from the journal's author guidelines. Anything you "
            "leave blank simply isn't checked.")
        blurb.setObjectName("muted")
        blurb.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(blurb)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Microbiome, or Nature Communications")
        form.addRow("Journal name", self.name)

        self.abstract_words = _spin(5000, " words", 50)
        self.main_words = _spin(50000, " words", 100)
        self.total_words = _spin(100000, " words", 100)
        self.title_words = _spin(100, " words")
        self.title_chars = _spin(1000, " characters", 5)
        form.addRow("Abstract limit", self.abstract_words)
        form.addRow("Main text limit", self.main_words)
        form.addRow("Whole manuscript limit", self.total_words)
        form.addRow("Title limit", self.title_words)
        form.addRow("Title limit (characters)", self.title_chars)
        self.headings = QLineEdit()
        self.headings.setPlaceholderText("e.g. Background, Methods, Results, Conclusions")
        self.headings.setToolTip("For a structured abstract: its headings, in order")
        form.addRow("Abstract headings", self.headings)
        self.keywords = _spin(30)
        form.addRow("Maximum keywords", self.keywords)

        self.references = _spin(1000)
        self.display_items = _spin(50)
        form.addRow("Maximum references", self.references)
        form.addRow("Maximum figures + tables", self.display_items)

        root.addLayout(form)
        root.addWidget(self._rule())

        cite = QFormLayout()
        cite.setSpacing(10)
        cite.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.style = QComboBox()
        for label, _ in STYLE_CHOICES:
            self.style.addItem(label)
        cite.addRow("Citation style", self.style)

        self.max_authors = _spin(100)
        self.max_authors.setToolTip(
            "How many authors an entry lists before \u201cet al.\u201d")
        cite.addRow("Authors before \u201cet al.\u201d", self.max_authors)

        self.require_doi = QCheckBox("Every reference must include a DOI")
        cite.addRow("", self.require_doi)

        self.sections = QLineEdit()
        self.sections.setPlaceholderText(
            "e.g. data availability, ethics statement  (comma separated)")
        cite.addRow("Required sections", self.sections)

        self.url = QLineEdit()
        self.url.setPlaceholderText("https://  (the guidelines page, for reference)")
        cite.addRow("Guidelines link", self.url)
        root.addLayout(cite)

        note = QLabel(
            f"Saved with today's date ({date.today().isoformat()}). Galley will "
            f"remind you to re-check these once they're a year old.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

        self.error = QLabel("")
        self.error.setObjectName("errorText")
        root.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if profile is not None:
            self._fill_from(profile)

    def _rule(self) -> QWidget:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("rule")
        return line

    def _limit_widgets(self):
        return [("abstract_words", self.abstract_words),
                ("main_text_words", self.main_words),
                ("total_words", self.total_words),
                ("title_words", self.title_words),
                ("title_chars", self.title_chars),
                ("keywords", self.keywords),
                ("references", self.references),
                ("display_items", self.display_items)]

    def _fill_from(self, profile):
        self.name.setText(profile.name)
        limits = profile.limits or {}
        for key, widget in self._limit_widgets():
            widget.setValue(int(limits.get(key, 0) or 0))
        # Limits and details the form has no field for are kept as they were.
        shown = {k for k, _ in self._limit_widgets()}
        self.kept = {"limits": {k: v for k, v in limits.items() if k not in shown},
                     "publisher": profile.publisher,
                     "article_type": profile.article_type,
                     # The pre-filled note says "not yet checked"; a copy the
                     # user corrected from the guidelines is checked.
                     "notes": (None if (profile.notes or "").startswith("Pre-filled")
                               else profile.notes)}
        self.headings.setText(", ".join(profile.abstract_headings or []))
        for index, (_, value) in enumerate(STYLE_CHOICES):
            if value == profile.reference_style:
                self.style.setCurrentIndex(index)
        self.max_authors.setValue(profile.max_authors_listed or 0)
        self.require_doi.setChecked(bool(profile.require_doi))
        self.sections.setText(", ".join(profile.required_sections or []))
        self.url.setText(profile.guidelines_url or "")

    def data(self) -> dict:
        limits = dict(self.kept.get("limits") or {})
        limits.update({key: widget.value() for key, widget in self._limit_widgets()
                       if widget.value() > 0})
        sections = [s.strip() for s in self.sections.text().split(",") if s.strip()]
        headings = [s.strip() for s in self.headings.text().split(",") if s.strip()]
        payload = {
            "name": self.name.text().strip(),
            "verified": date.today().isoformat(),
            "limits": limits,
            "required_sections": sections,
            "require_doi": self.require_doi.isChecked(),
        }
        if headings:
            payload["abstract_headings"] = headings
        for key in ("publisher", "article_type", "notes"):
            if self.kept.get(key):
                payload[key] = self.kept[key]
        style = STYLE_CHOICES[self.style.currentIndex()][1]
        if style:
            payload["reference_style"] = style
        if self.max_authors.value() > 0:
            payload["max_authors_listed"] = self.max_authors.value()
        if self.url.text().strip():
            payload["guidelines_url"] = self.url.text().strip()
        return payload

    def _save(self):
        payload = self.data()
        if not payload["name"]:
            self.error.setText("Give the journal a name so you can find it again.")
            return
        if not (payload["limits"] or payload["required_sections"]
                or payload.get("abstract_headings")
                or payload.get("reference_style") or payload.get("max_authors_listed")
                or payload["require_doi"]):
            self.error.setText("Set at least one requirement, or press Cancel.")
            return
        try:
            self.saved_path = save_profile(payload, self.filename)
        except OSError as e:
            self.error.setText(f"Couldn't save the profile: {e}")
            return
        self.accept()
