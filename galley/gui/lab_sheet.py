"""The orders spreadsheet on the My Lab screen: one row per order, a header
that stays put while the rows scroll, edited in place like Excel.

Edits go through OrderSheet.commit, which updates the Order, saves it and
redraws the row, so what is on screen is always what is saved. The header
names can be renamed by double-clicking them; they are kept in the lab's
settings, so the whole lab sees the same names.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QDateEdit, QHeaderView,
    QInputDialog, QLineEdit, QMessageBox, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem,
)

from ..lab import STATUS_LABEL, STATUSES, Order, catalogue
from ..lab.model import new_id
from .fellowships_page import APPLE, SOFT, day

# key, default header, kind, width
COLUMNS = [
    ("status", "Status", "status", 118),
    ("requested", "Date Requested", "date", 118),
    ("approved", "Date Approved", "date", 118),
    ("approved_by", "Approved By", "person", 120),
    ("ordered", "Date Ordered", "date", 118),
    ("account", "Account", "account", 90),
    ("item", "Item Name", "item", 320),
    ("requested_by", "Requested By", "person", 130),
    ("vendor", "Vendor", "vendor", 160),
    ("catalog", "Catalog #", "text", 110),
    ("qty", "Qty", "number", 56),
    ("unit_price", "Unit Price", "money", 92),
    ("total", "Total Price", "total", 100),
    ("received_by", "Received By", "person", 120),
    ("received", "Date Received", "date", 118),
    ("location", "Location", "location", 120),
    ("sublocation", "SubLocation", "text", 170),
    ("unit_size", "Unit Size", "text", 90),
    ("url", "URL", "text", 160),
    ("notes", "Notes", "text", 220),
]
KEYS = [c[0] for c in COLUMNS]
STATUS_COLOR = {"requested": SOFT["red"], "approved": SOFT["indigo"],
                "ordered": SOFT["amber"], "backordered": SOFT["purple"],
                "received": SOFT["green"], "cancelled": SOFT["grey"]}
RAW = Qt.UserRole + 1           # the stored value behind a cell's display text


def parse_number(text: str, what: str) -> float | None:
    s = text.strip().replace(",", "")
    for sign in "$€£₹¥":
        s = s.replace(sign, "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        raise ValueError(f"{what} should be a number, not “{text.strip()}”.") from None
    if v < 0:
        raise ValueError(f"{what} can't be negative.")
    return v


class SheetDelegate(QStyledItemDelegate):
    """The editor for each kind of column: a status menu, a calendar for
    dates, and suggestions from the lab's history for names."""

    def __init__(self, sheet: "OrderSheet"):
        super().__init__(sheet)
        self.sheet = sheet

    def createEditor(self, parent, option, index):
        kind = COLUMNS[index.column()][2]
        if kind == "status":
            box = QComboBox(parent)
            for s in STATUSES:
                box.addItem(STATUS_LABEL[s], s)
            # Choosing from the menu is the edit; don't wait for Enter.
            box.activated.connect(lambda _=0, box=box: (self.commitData.emit(box),
                                                        self.closeEditor.emit(box)))
            return box
        if kind == "date":
            d = QDateEdit(parent)
            d.setCalendarPopup(True)
            d.setDisplayFormat("d MMM yyyy")
            return d
        edit = QLineEdit(parent)
        options = self.sheet.suggestions(kind)
        if options:
            c = QCompleter(options, edit)
            c.setCaseSensitivity(Qt.CaseInsensitive)
            c.setFilterMode(Qt.MatchContains)
            edit.setCompleter(c)
        return edit

    def setEditorData(self, editor, index):
        raw = index.data(RAW)
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(max(0, STATUSES.index(raw) if raw in STATUSES else 0))
            QTimer.singleShot(0, editor.showPopup)
        elif isinstance(editor, QDateEdit):
            d = QDate.fromString(raw or "", "yyyy-MM-dd")
            t = self.sheet.today
            editor.setDate(d if d.isValid() else QDate(t.year, t.month, t.day))
        else:
            editor.setText("" if raw is None else str(raw))

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            value = editor.currentData()
        elif isinstance(editor, QDateEdit):
            value = editor.date().toPython().isoformat()
        else:
            value = editor.text()
        self.sheet.commit(index.row(), index.column(), value)


class OrderSheet(QTableWidget):
    """The orders as a spreadsheet. `page` is the LabPage: it knows the lab,
    who "I" am, today, and how to save and move orders on."""
    menuRequested = Signal(object, QPoint)      # an Order, where to show its menu

    def __init__(self, page, orders: list[Order]):
        super().__init__(0, len(COLUMNS))
        self.page = page
        self.today: date = page.today
        self.rows: list[Order] = []
        self.setObjectName("orderSheet")
        self.setItemDelegate(SheetDelegate(self))
        self.setEditTriggers(QAbstractItemView.DoubleClicked |
                             QAbstractItemView.EditKeyPressed |
                             QAbstractItemView.AnyKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setWordWrap(False)
        self.setAlternatingRowColors(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        head = self.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.Interactive)
        head.setHighlightSections(False)
        head.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        head.setToolTip("Double-click a column name to rename it")
        head.sectionDoubleClicked.connect(self.rename_column)
        for i, (_, _, _, width) in enumerate(COLUMNS):
            self.setColumnWidth(i, width)
        rows = self.verticalHeader()
        rows.setDefaultSectionSize(34)
        rows.setToolTip("Click a row number for that order's actions")
        rows.sectionClicked.connect(self._row_menu)
        self.setStyleSheet(f"""
            #orderSheet {{ background:white; border:1px solid {APPLE['fill']};
                           border-radius:10px; gridline-color:{APPLE['fill']};
                           alternate-background-color:#FAFAFC; font-size:13px;
                           selection-background-color:#DCEBFF;
                           selection-color:{APPLE['label']}; }}
            QHeaderView::section {{ background:{APPLE['background']}; border:none;
                           border-right:1px solid {APPLE['fill']};
                           border-bottom:1px solid {APPLE['separator']};
                           padding:6px 8px; font-weight:600; font-size:12px;
                           color:{APPLE['secondary']}; }}
            QTableCornerButton::section {{ background:{APPLE['background']};
                           border:none; }}""")
        self.set_headers()
        self.load(orders)

    # -- contents -------------------------------------------------------------------
    def header_text(self, key: str) -> str:
        default = next(c[1] for c in COLUMNS if c[0] == key)
        return self.page.lab.columns.get(key) or default

    def set_headers(self):
        self.setHorizontalHeaderLabels([self.header_text(k) for k in KEYS])

    def load(self, orders: list[Order]):
        self.rows = list(orders)
        self.setRowCount(len(self.rows))
        for r in range(len(self.rows)):
            self.fill_row(r)

    def display(self, o: Order, key: str, kind: str) -> tuple[str, object]:
        """(text shown, raw value) for one cell."""
        if kind == "status":
            return STATUS_LABEL[o.status], o.status
        if kind == "total":
            return self.page.lab.money(o.total), o.total
        value = getattr(o, key)
        if kind == "date":
            d = o.when(key)
            return (day(d) if d else ""), value
        if kind == "money":
            return self.page.lab.money(value), "" if value is None else f"{value:g}"
        if kind == "number":
            return f"{value:g}", f"{value:g}"
        return str(value or ""), value or ""

    def fill_row(self, r: int):
        o = self.rows[r]
        for c, (key, _, kind, _) in enumerate(COLUMNS):
            text, raw = self.display(o, key, kind)
            item = QTableWidgetItem(text)
            item.setData(RAW, raw)
            flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
            if kind != "total":
                flags |= Qt.ItemIsEditable
            item.setFlags(flags)
            if kind == "status":
                item.setBackground(QBrush(QColor(STATUS_COLOR[o.status])))
                item.setForeground(QBrush(QColor("white")))
                f = QFont()
                f.setBold(True)
                item.setFont(f)
            elif kind in ("money", "total", "number"):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if o.example and kind != "status":
                item.setForeground(QBrush(QColor(APPLE["secondary"])))
                f = QFont()
                f.setItalic(True)
                item.setFont(f)
            if key == "item" and o.notes:
                item.setToolTip(o.notes)
            self.setItem(r, c, item)
        self.setVerticalHeaderItem(r, QTableWidgetItem("ex." if o.example else str(r + 1)))

    def suggestions(self, kind: str) -> list[str]:
        lab, orders = self.page.lab, self.page.orders
        if kind == "item":
            return sorted({o.item for o in orders if o.item}, key=str.lower)
        if kind == "vendor":
            return sorted({o.vendor for o in orders if o.vendor}, key=str.lower)
        if kind == "person":
            people = set(lab.members) | {self.page.me.name}
            people |= {o.requested_by for o in orders} | {o.received_by for o in orders}
            return sorted({p for p in people if p}, key=str.lower)
        if kind == "account":
            return sorted(set(lab.accounts) | {o.account for o in orders if o.account})
        if kind == "location":
            return sorted(set(lab.locations) | {o.location for o in orders if o.location})
        return []

    # -- editing --------------------------------------------------------------------
    def commit(self, r: int, c: int, value) -> bool:
        """Apply an edit to the order in row r, save it and redraw the row."""
        if not 0 <= r < len(self.rows):
            return False
        o = self.rows[r]
        key, label, kind, _ = COLUMNS[c]
        try:
            if kind == "status":
                if value != o.status:
                    # Records who and when, then redraws the page: after the
                    # editor has closed, not while it is still open.
                    QTimer.singleShot(0, lambda: self.page.move(o, value))
                return True
            if kind == "date":
                setattr(o, key, value or "")
            elif kind == "number":
                v = parse_number(str(value), self.header_text(key))
                if not v:
                    raise ValueError(f"{self.header_text(key)} should be at least 1.")
                o.qty = int(v) if float(v).is_integer() else v
            elif kind == "money":
                o.unit_price = parse_number(str(value), self.header_text(key))
            elif kind == "item":
                o.item = str(value).strip()
                known = catalogue([x for x in self.page.orders if x is not o]).get(
                    o.item.lower())
                if known and not o.vendor:          # fill in what the lab knows
                    for k in ("vendor", "catalog", "unit_price", "unit_size", "url",
                              "account"):
                        if not getattr(o, k):
                            setattr(o, k, getattr(known, k))
            else:
                setattr(o, key, str(value).strip())
        except ValueError as e:
            QMessageBox.warning(self, "Not saved", str(e))
            self.fill_row(r)
            return False
        if o.item:
            if not self.page.save_edit(o):
                return False
        self.fill_row(r)
        return True

    def new_row(self) -> Order:
        """A blank order at the top, ready to type its item into."""
        on = self.today.isoformat()
        me = self.page.me.name
        o = Order(new_id(), "", requested=on, requested_by=me,
                  history=[{"date": on, "status": "requested", "by": me}])
        self.rows.insert(0, o)
        self.insertRow(0)
        self.fill_row(0)
        for r in range(1, len(self.rows)):
            self.setVerticalHeaderItem(r, QTableWidgetItem(
                "ex." if self.rows[r].example else str(r + 1)))
        self.scrollToTop()
        col = KEYS.index("item")
        self.setCurrentCell(0, col)
        self.editItem(self.item(0, col))
        return o

    def rename_column(self, c: int):
        key = KEYS[c]
        default = COLUMNS[c][1]
        text, ok = QInputDialog.getText(self, "Rename column",
                                        f"New name for “{self.header_text(key)}” "
                                        f"(leave empty for “{default}”):",
                                        text=self.header_text(key))
        if not ok:
            return
        self.page.rename_column(key, text.strip())

    # -- menus ----------------------------------------------------------------------
    def _row_menu(self, r: int):
        if 0 <= r < len(self.rows) and self.rows[r].item:
            pos = self.verticalHeader().mapToGlobal(
                QPoint(self.verticalHeader().width(), self.rowViewportPosition(r)))
            self.menuRequested.emit(self.rows[r], pos)

    def contextMenuEvent(self, e):
        r = self.rowAt(e.pos().y())
        if 0 <= r < len(self.rows) and self.rows[r].item:
            self.menuRequested.emit(self.rows[r], e.globalPos())
