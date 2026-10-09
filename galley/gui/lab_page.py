"""The My Lab screen: the lab's orders from request to the shelf they end up
on, an inventory of what was received and where it is, and what it all cost.

Status colours follow the usual lab order sheet: requested red, ordered
amber, received green.
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..lab import (STATUS_LABEL, Lab, Order, advance, attention, delete_order,
                   example_orders, export_orders, import_orders, load_lab,
                   load_me, load_orders, order_again, request_text, save_lab,
                   save_me, save_order, spend, total)
from ..lab.model import month_start, months_back
from .fellowships_page import (APPLE, SOFT, Card, Row, ScrollPage, Segmented,
                               apple_font, apple_stylesheet, day, dot,
                               field_row, filled_button, label, pill,
                               plain_button, tile_row)
from .lab_sheet import OrderSheet
from .projects_page import ActionMenu

ORDERS, INVENTORY, SPENDING, LAB = 0, 1, 2, 3
STATUS_COLOR = {"requested": SOFT["red"], "approved": SOFT["indigo"],
                "ordered": SOFT["amber"], "backordered": SOFT["purple"],
                "received": SOFT["green"], "cancelled": SOFT["grey"]}
# The tiles above the spreadsheet; "ordered" includes back-ordered. Clicking
# a tile shows only those orders; clicking it again shows them all.
ORDER_TILES = [("requested", "Requested", SOFT["red"]),
               ("approved", "Approved", SOFT["indigo"]),
               ("ordered", "Ordered", SOFT["amber"])]
PERIODS = [("month", "This month", SOFT["blue"]), ("year", "This year", SOFT["indigo"]),
           ("last12", "Last 12 months", SOFT["purple"])]
SHOW_AT_MOST = 200
SEARCH_STYLE = (f"background:white; border:1px solid {APPLE['fill']}; "
                f"border-radius:10px; padding:8px 12px; font-size:15px;")


def _split(text: str) -> list[str]:
    return list(dict.fromkeys(x.strip() for x in text.split(",") if x.strip()))


def _combo(values: list[str], current: str = "", placeholder: str = "") -> QComboBox:
    c = QComboBox()
    c.setEditable(True)
    c.addItems([v for v in values if v])
    c.setCurrentText(current)
    if placeholder:
        c.lineEdit().setPlaceholderText(placeholder)
    c.setMinimumWidth(240)
    return c


def bar(fraction: float, color: str, width: int = 150) -> QWidget:
    """A horizontal bar for the spending lists."""
    holder = QWidget()
    holder.setFixedSize(width, 10)
    track = QFrame(holder)
    track.setGeometry(0, 1, width, 8)
    track.setStyleSheet(f"background:{APPLE['fill']}; border-radius:4px;")
    fill = QFrame(holder)
    fill.setGeometry(0, 1, max(4, round(width * max(0.0, min(1.0, fraction)))), 8)
    fill.setStyleSheet(f"background:{color}; border-radius:4px;")
    return holder


# ---- dialogs ----------------------------------------------------------------

class ReceiveDialog(QDialog):
    """Who took the delivery, when, and where it was put."""

    def __init__(self, lab: Lab, me: str, o: Order, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mark as Received")
        self.setMinimumWidth(460)
        form = QFormLayout()
        head = QLabel(o.item)
        head.setWordWrap(True)
        head.setStyleSheet("font-weight:600;")
        self.by = _combo(sorted(set(lab.members) | ({me} if me else set())), me,
                         "Who received it")
        self.when = QDateEdit(QDate.currentDate())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("d MMM yyyy")
        self.location = _combo(lab.locations, o.location, "e.g. Bench 1, -20 °C freezer")
        self.sublocation = QLineEdit(o.sublocation)
        self.sublocation.setPlaceholderText("e.g. top shelf, box 3")
        form.addRow(head)
        form.addRow("Received by", self.by)
        form.addRow("Date", self.when)
        form.addRow("Put in", self.location)
        form.addRow("Where exactly", self.sublocation)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)


# ---- the page ----------------------------------------------------------------

class LabPage(QWidget):
    attentionChanged = Signal(int)

    def __init__(self, me_path: Path | None = None, today: date | None = None):
        super().__init__()
        self.setObjectName("fellowships")       # shares the Fellowships styling
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(apple_stylesheet(apple_font()))
        self.me_path = me_path
        self.today = today or date.today()
        self.tab = ORDERS
        self.filter = "all"
        self.search = ""
        self.inv_search = ""
        self.period = "year"
        self.stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)
        self.reload()
        self.render()

    # -- data -----------------------------------------------------------------------
    def reload(self):
        self.me = load_me(self.me_path)
        self.folder = self.me.lab_folder()
        self.lab = load_lab(self.folder)
        self.orders = load_orders(self.folder)
        if not self.orders and not self.lab.examples_added:
            self.add_examples()

    def add_examples(self):
        """Fill a new tracker with example reagent orders, once."""
        try:
            for o in example_orders(self.today, self.me.name):
                save_order(o, self.folder)
            self.lab.examples_added = True
            save_lab(self.lab, self.folder)
        except OSError:
            return                      # a read-only folder: start empty
        self.orders = load_orders(self.folder)

    def remove_examples(self):
        for o in [o for o in self.orders if o.example]:
            delete_order(o.id, self.folder)
        self.refresh()

    def _save(self, o: Order):
        try:
            save_order(o, self.folder)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't save",
                                f"{e}\n\nIs the lab folder ({self.folder}) still "
                                f"available? A shared drive may have disconnected.")
            return False
        return True

    def attention_count(self) -> int:
        return len(attention(self.orders, self.lab, self.today))

    def refresh(self):
        """Reload from the lab folder (others may have changed it) and redraw."""
        self.reload()
        self.render()

    # -- layout ---------------------------------------------------------------------
    def _show(self, w: QWidget):
        old = self.stack.currentWidget()
        self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        self.current = w

    def show_tab(self, i: int):
        self.tab = i
        self.render()

    def _title_bar(self) -> QWidget:
        title = QWidget()
        tl = QHBoxLayout(title)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(label(self.lab.name or "My Lab", "largeTitle"), 1)
        refresh = plain_button("Refresh")
        refresh.setToolTip("Load changes others made in the shared lab folder")
        refresh.clicked.connect(self.refresh)
        tl.addWidget(refresh, 0, Qt.AlignBottom)
        return title

    def _tab_bar(self) -> QWidget:
        tabs = Segmented(["Orders", "Inventory", "Spending", "Lab"])
        tabs.select(self.tab, emit=False)
        tabs.changed.connect(self.show_tab)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 6, 0, 2)
        hl.addWidget(tabs)
        hl.addStretch(1)
        return holder

    def render(self):
        self.sheet = None
        if self.tab == ORDERS:
            page = self._orders_page()      # full width, the sheet scrolls itself
        else:
            page = ScrollPage()
            page.add(self._title_bar())
            page.add(self._tab_bar())
            {INVENTORY: self._inventory_tab, SPENDING: self._spending_tab,
             LAB: self._lab_tab}[self.tab](page)
            page.finish()
        self._show(page)
        self.attentionChanged.emit(self.attention_count())

    def _search_box(self, text: str, placeholder: str, on_change) -> QLineEdit:
        box = QLineEdit(text)
        box.setPlaceholderText(placeholder)
        box.setClearButtonEnabled(True)
        box.setStyleSheet(SEARCH_STYLE)
        box.textChanged.connect(on_change)
        return box

    def _order_row(self, o: Order, subtitle: str | None = None) -> Row:
        right = QWidget()
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        if o.total is not None:
            rl.addWidget(label(self.lab.money(o.total), "rowSubtitle"))
        rl.addWidget(pill(STATUS_LABEL[o.status], STATUS_COLOR[o.status]))
        if subtitle is None:
            bits = [o.vendor, o.catalog and f"#{o.catalog}"]
            if o.unit_price is not None:
                bits.append(f"{o.qty:g} × {self.lab.money(o.unit_price)}")
            elif o.qty != 1:
                bits.append(f"{o.qty:g}")
            who = o.requested_by or "someone"
            when = o.when("requested")
            bits.append(f"{who}, {day(when)}" if when else who)
            subtitle = " · ".join(b for b in bits if b)
        row = Row(o.item, subtitle, trailing=right, tappable=True)
        row.clicked.connect(lambda o=o, row=row: self.order_menu(o, row))
        return row

    # -- orders ---------------------------------------------------------------------
    def _matches(self, o: Order, stuck: set[str]) -> bool:
        f = self.filter
        in_tile = (True if f == "all" else o.id in stuck if f == "attention" else
                   o.status in ("ordered", "backordered") if f == "ordered" else
                   o.status == f)
        q = self.search.lower()
        return in_tile and (not q or q in " ".join(
            (o.item, o.vendor, o.catalog, o.requested_by, o.account, o.project,
             o.location, o.notes)).lower())

    def _orders_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 12, 24, 12)
        lay.setSpacing(8)
        lay.addWidget(self._title_bar())
        lay.addWidget(self._tab_bar())

        stuck = attention(self.orders, self.lab, self.today)
        if stuck:
            first = stuck[0]
            n = len(stuck)
            more = f" and {n - 1} more" if n > 1 else ""
            action = "Show all orders" if self.filter == "attention" else "Show them"
            banner = QPushButton(
                f"\u26A0  {n} order{'s need' if n != 1 else ' needs'} attention: "
                f"{first.order.item[:50]} ({first.text.lower()}){more}.   {action}")
            banner.setObjectName("labBanner")
            banner.setCursor(Qt.PointingHandCursor)
            banner.setStyleSheet("#labBanner { background:#FFF4E5; color:#7A4B00; "
                                 "border:none; border-radius:10px; padding:9px 14px; "
                                 "text-align:left; font-size:14px; }")
            banner.clicked.connect(lambda: self._set_filter("attention"))
            lay.addWidget(banner)

        counts = {"requested": sum(o.status == "requested" for o in self.orders),
                  "approved": sum(o.status == "approved" for o in self.orders),
                  "ordered": sum(o.status in ("ordered", "backordered")
                                 for o in self.orders)}
        lay.addWidget(tile_row(ORDER_TILES, counts, self.filter, self._set_filter))

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search_input = self._search_box(
            self.search, "Search items, vendors, catalogue numbers, people, places",
            self._search_orders)
        bar.addWidget(self.search_input, 1)
        new = filled_button("+  New Row")
        new.clicked.connect(self.new_row)
        bar.addWidget(new)
        for text, handler in (("Import Spreadsheet…", self.import_sheet),
                              ("Export CSV…", self.export_sheet)):
            b = plain_button(text)
            b.clicked.connect(handler)
            bar.addWidget(b)
        if any(o.example for o in self.orders):
            b = plain_button("Remove Example Rows", destructive=True)
            b.clicked.connect(self.remove_examples)
            bar.addWidget(b)
        lay.addLayout(bar)

        ids = {a.order.id for a in stuck}
        shown = [o for o in self.orders if self._matches(o, ids)]
        if self.filter != "all" or self.search:
            what = dict((k, t) for k, t, _ in ORDER_TILES).get(
                self.filter, "Needing attention" if self.filter == "attention" else "All")
            lay.addWidget(label(f"{what.upper()} · {len(shown)} of {len(self.orders)}",
                                "sectionHeader"))
        self.sheet = OrderSheet(self, shown)
        self.sheet.menuRequested.connect(self.order_menu_at)
        lay.addWidget(self.sheet, 1)
        lay.addWidget(label("Double-click a cell to edit it; Status offers a menu and "
                            "dates a calendar. Click a row number (or right-click a "
                            "row) to mark it received, order it again or copy its "
                            "details. Double-click a column name to rename it.",
                            "footnote", wrap=True))
        return page

    def _set_filter(self, key: str):
        self.filter = "all" if key == self.filter else key    # a second click clears
        self.render()

    def _search_orders(self, text: str):
        self.search = text
        self.render()
        self.search_input.setFocus()
        self.search_input.setCursorPosition(len(text))

    def order_menu_items(self, o: Order):
        """What clicking an order offers: its next steps first."""
        me = self.me.name
        step = lambda status: (lambda: self.move(o, status))     # noqa: E731
        items = []
        if o.status == "requested":
            items.append(("Approve", f"as {me}" if me else "", STATUS_COLOR["approved"],
                          step("approved"), True))
        if o.status in ("requested", "approved"):
            items.append(("Mark as Ordered", "", STATUS_COLOR["ordered"],
                          step("ordered"), True))
        if o.status in ("ordered", "backordered"):
            items.append(("Mark as Received…", "Say who took it and where it went",
                          STATUS_COLOR["received"], lambda: self.receive(o), True))
        if o.status == "ordered":
            items.append(("Back-ordered", "The vendor says it's delayed",
                          STATUS_COLOR["backordered"], step("backordered"), True))
        items.append(("Order Again", "A new request with the same details",
                      SOFT["blue"], lambda: self.reorder(o), True))
        items.append(("Copy Order Details", "To paste into an email or purchasing form",
                      None, lambda: self.copy_details(o), True))
        if o.url:
            items.append(("Open Product Page", o.url[:60], None,
                          lambda: QDesktopServices.openUrl(QUrl(o.url)), True))
        if o.is_open:
            items.append(("Cancel Order", "", STATUS_COLOR["cancelled"],
                          step("cancelled"), True))
        items.append(("Delete…", "Remove it from the tracker", None,
                      lambda: self.delete(o), True))
        return items

    def order_menu_at(self, o: Order, pos):
        menu = ActionMenu(STATUS_LABEL[o.status] + " · " + o.item[:50],
                          self.order_menu_items(o), self)
        menu.adjustSize()
        menu.move(pos.x() + 8, pos.y())
        menu.show()
        self._menu = menu

    def order_menu(self, o: Order, anchor: QWidget):
        menu = ActionMenu(STATUS_LABEL[o.status] + " · " + o.item[:50],
                          self.order_menu_items(o), self)
        menu.adjustSize()
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        menu.move(pos.x() + 40, pos.y() - 8)
        menu.show()
        self._menu = menu

    # -- actions --------------------------------------------------------------------
    def move(self, o: Order, status: str, **where):
        advance(o, status, self.me.name, self.today, **where)
        if self._save(o):
            self.render()

    def receive(self, o: Order):
        dlg = ReceiveDialog(self.lab, self.me.name, o, self)
        if dlg.exec() != QDialog.Accepted:
            return
        advance(o, "received", dlg.by.currentText().strip(),
                dlg.when.date().toPython(), location=dlg.location.currentText().strip(),
                sublocation=dlg.sublocation.text().strip())
        loc = dlg.location.currentText().strip()
        if loc and loc not in self.lab.locations:
            self.lab.locations.append(loc)      # offer it next time
            save_lab(self.lab, self.folder)
        if self._save(o):
            self.render()

    def new_row(self):
        """Add a blank row at the top of the sheet to type the order into."""
        if self.filter not in ("all", "requested") or self.search or self.sheet is None:
            self.filter, self.search, self.tab = "all", "", ORDERS
            self.render()
        return self.sheet.new_row()

    def save_edit(self, o: Order) -> bool:
        """Save an order edited in the sheet, without redrawing the page."""
        if not self._save(o):
            return False
        if all(x is not o for x in self.orders):
            self.orders.insert(0, o)            # a new row, now it has an item
        self.attentionChanged.emit(self.attention_count())
        return True

    def reorder(self, o: Order):
        again = order_again(o, self.me.name, self.today)
        if self._save(again):
            self.orders.insert(0, again)
            self.filter, self.search, self.tab = "all", "", ORDERS
            self.render()
            self.sheet.setCurrentCell(0, 0)

    def rename_column(self, key: str, text: str):
        if text:
            self.lab.columns[key] = text
        else:
            self.lab.columns.pop(key, None)
        try:
            save_lab(self.lab, self.folder)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't save", str(e))
        if self.sheet is not None:
            self.sheet.set_headers()

    def delete(self, o: Order):
        if QMessageBox.question(self, "Delete order",
                                f"Delete “{o.item}” from the tracker? To keep a "
                                f"record, cancel it instead.") != QMessageBox.Yes:
            return
        delete_order(o.id, self.folder)
        self.orders = [x for x in self.orders if x.id != o.id]
        self.render()

    def copy_details(self, o: Order):
        QGuiApplication.clipboard().setText(request_text(o, self.lab))

    def import_sheet(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import the lab's order spreadsheet", "",
            "Spreadsheets (*.xlsx *.xlsm *.csv)")
        if path:
            self.import_from(path)

    def import_from(self, path: str) -> bool:
        try:
            result = import_orders(path, self.orders)
        except ImportError:
            QMessageBox.warning(self, "Couldn't import",
                                "Reading Excel files needs the openpyxl package. "
                                "Save the sheet as CSV and import that instead.")
            return False
        except (OSError, ValueError, UnicodeDecodeError) as e:
            QMessageBox.warning(self, "Couldn't import", str(e))
            return False
        for o in result.orders:
            if not self._save(o):
                return False
        lab_changed = False
        for o in result.orders:      # learn the lab's people, accounts, places
            for value, known in ((o.account, self.lab.accounts),
                                 (o.location, self.lab.locations),
                                 (o.requested_by, self.lab.members)):
                if value and value not in known:
                    known.append(value)
                    lab_changed = True
        if lab_changed:
            save_lab(self.lab, self.folder)
        lines = [f"{len(result.orders)} orders imported."]
        if result.duplicates:
            lines.append(f"{result.duplicates} were already in the tracker and "
                         f"were skipped.")
        if result.problems:
            lines.append("Not imported:\n" + "\n".join(result.problems[:10]))
        QMessageBox.information(self, "Orders imported", "\n\n".join(lines))
        self.filter = "all"
        self.refresh()
        return True

    def export_sheet(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export the orders",
                                              "lab-orders.csv", "CSV files (*.csv)")
        if path:
            export_orders(self.orders, path)

    # -- inventory ------------------------------------------------------------------
    def _inventory_tab(self, page: ScrollPage):
        self.inv_input = page.add(self._search_box(
            self.inv_search, "Where is it? Search items, catalogue numbers, places",
            self._search_inventory))
        q = self.inv_search.lower()
        received = [o for o in self.orders if o.status == "received" and
                    (not q or q in " ".join((o.item, o.vendor, o.catalog, o.location,
                                             o.sublocation, o.notes)).lower())]
        by_place: dict[str, list[Order]] = defaultdict(list)
        for o in received:
            by_place[o.location or "No location recorded"].append(o)
        if not received:
            page.header("Inventory")
            card = page.add(Card())
            card.add(Row("Nothing matches" if q else "Nothing received yet",
                         "Items appear here once an order is marked as received, "
                         "with where it was put."))
        places = sorted(by_place, key=lambda p: (p == "No location recorded", p.lower()))
        for place in places:
            items = sorted(by_place[place], key=lambda o: o.received, reverse=True)
            page.header(f"{place} · {len(items)}")
            card = page.add(Card())
            for o in items[:SHOW_AT_MOST]:
                bits = [o.sublocation]
                when = o.when("received")
                if when:
                    bits.append(f"received {day(when)}"
                                + (f" by {o.received_by}" if o.received_by else ""))
                bits += [o.vendor, o.catalog and f"#{o.catalog}"]
                card.add(self._order_row(o, " · ".join(b for b in bits if b)))
        page.footnote("Click an item to order it again or open its product page.")

    def _search_inventory(self, text: str):
        self.inv_search = text
        self.render()
        self.inv_input.setFocus()
        self.inv_input.setCursorPosition(len(text))

    # -- spending -------------------------------------------------------------------
    def period_range(self) -> tuple[date, date]:
        t = self.today
        if self.period == "month":
            return month_start(t), t
        if self.period == "year":
            return date(t.year, 1, 1), t
        return months_back(t, 11), t

    def _spending_tab(self, page: ScrollPage):
        lab, t = self.lab, self.today
        amounts = {"month": sum(spend(self.orders, month_start(t), t, "month").values()),
                   "year": sum(spend(self.orders, date(t.year, 1, 1), t, "month").values()),
                   "last12": sum(spend(self.orders, months_back(t, 11), t,
                                       "month").values())}
        page.add(tile_row(PERIODS, {k: lab.money(v) for k, v in amounts.items()},
                          self.period, self._set_period))
        card = page.add(Card())
        card.add(Row("On order", "Ordered, not received yet",
                     trailing=label(lab.money(total(self.orders,
                                                    {"ordered", "backordered"})),
                                    "rowSubtitle")))
        card.add(Row("Waiting to be ordered", "Requested or approved",
                     trailing=label(lab.money(total(self.orders,
                                                    {"requested", "approved"})),
                                    "rowSubtitle")))

        start, end = self.period_range()
        period = dict((k, t) for k, t, _ in PERIODS)[self.period]
        for by, title, color, n in (("account", "By account", SOFT["indigo"], 12),
                                    ("vendor", "By vendor", SOFT["blue"], 10),
                                    ("month", "By month", SOFT["purple"], 12)):
            if by == "month" and self.period == "month":
                continue
            totals = spend(self.orders, start, end, by)
            page.header(f"{title} · {period}")
            card = page.add(Card())
            if not totals:
                card.add(Row("Nothing spent in this period",
                             "Orders count once they are ordered."))
                continue
            top = max(totals.values()) or 1
            for key, amount in list(totals.items())[:n]:
                name = f"{date.fromisoformat(key + '-01'):%B %Y}" if by == "month" else key
                right = QWidget()
                rl = QHBoxLayout(right)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(10)
                rl.addWidget(bar(amount / top, color))
                amt = label(lab.money(amount), "rowSubtitle")
                amt.setMinimumWidth(90)
                amt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rl.addWidget(amt)
                card.add(Row(name, trailing=right))
        page.footnote("Spending counts an order on the date it was ordered, at "
                      "quantity × unit price. Cancelled orders and requests "
                      "not yet ordered aren't included.")

    def _set_period(self, key: str):
        self.period = key
        self.render()

    # -- lab settings ---------------------------------------------------------------
    def _lab_tab(self, page: ScrollPage):
        lab = self.lab
        page.header("You")
        card = page.add(Card())
        self.s_me = QLineEdit(self.me.name)
        self.s_me.setPlaceholderText("Your name, as on orders")
        card.add(field_row("Your name", self.s_me))
        page.footnote("Used for “Requested by”, “Approved by” and "
                      "“Received by”. Kept on this computer only.")

        page.header("The lab")
        card = page.add(Card())
        self.s_name = QLineEdit(lab.name)
        self.s_name.setPlaceholderText("e.g. Nayak Lab")
        card.add(field_row("Lab name", self.s_name))
        self.s_currency = QLineEdit(lab.currency)
        self.s_currency.setMaximumWidth(80)
        card.add(field_row("Currency symbol", self.s_currency))
        self.s_members = QLineEdit(", ".join(lab.members))
        card.add(field_row("Members", self.s_members))
        self.s_accounts = QLineEdit(", ".join(lab.accounts))
        self.s_accounts.setPlaceholderText("e.g. BB, NCIRE")
        card.add(field_row("Accounts", self.s_accounts))
        self.s_locations = QLineEdit(", ".join(lab.locations))
        self.s_locations.setPlaceholderText("e.g. Bench 1, -20 °C, Cold room")
        card.add(field_row("Storage places", self.s_locations))
        page.footnote("Separated by commas. These are offered when ordering and "
                      "receiving; importing a spreadsheet adds the ones it uses.")

        page.header("Reminders")
        card = page.add(Card())
        self.s_order_days = QSpinBox()
        self.s_order_days.setRange(1, 365)
        self.s_order_days.setValue(lab.order_within_days)
        self.s_order_days.setSuffix(" days")
        card.add(field_row("Flag requests not ordered after", self.s_order_days))
        self.s_deliver_days = QSpinBox()
        self.s_deliver_days.setRange(1, 365)
        self.s_deliver_days.setValue(lab.deliver_within_days)
        self.s_deliver_days.setSuffix(" days")
        card.add(field_row("Flag orders not received after", self.s_deliver_days))

        page.header("")
        card = page.add(Card())
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(16, 12, 16, 12)
        save = filled_button("Save")
        save.clicked.connect(self.save_settings)
        al.addWidget(save)
        al.addStretch(1)
        card.add(actions)

        if lab.columns:
            page.header("Spreadsheet")
            card = page.add(Card())
            r = Row("Restore Original Column Names",
                    ", ".join(f"{v}" for v in lab.columns.values()),
                    title_color=APPLE["blue"], tappable=True)
            r.clicked.connect(self.reset_columns)
            card.add(r)

        page.header("Lab folder")
        card = page.add(Card())
        card.add(Row(str(self.folder), f"{len(self.orders)} orders"))
        r = Row("Choose a Shared Folder…", title_color=APPLE["blue"], tappable=True)
        r.clicked.connect(self.choose_folder)
        card.add(r)
        if self.me.folder:
            r = Row("Use This Computer Only", title_color=APPLE["blue"], tappable=True)
            r.clicked.connect(lambda: self.use_folder(""))
            card.add(r)
        page.footnote("To share the tracker with your lab, choose a folder on a "
                      "shared drive (OneDrive, Google Drive, Dropbox, a network "
                      "drive) and ask everyone to choose the same one. Each "
                      "order is its own small file, so people working at the "
                      "same time don't overwrite each other. Press Refresh to "
                      "see their changes.")

    def save_settings(self):
        lab = self.lab
        lab.name = self.s_name.text().strip()
        lab.currency = self.s_currency.text().strip() or "$"
        lab.members = _split(self.s_members.text())
        lab.accounts = _split(self.s_accounts.text())
        lab.locations = _split(self.s_locations.text())
        lab.order_within_days = self.s_order_days.value()
        lab.deliver_within_days = self.s_deliver_days.value()
        self.me.name = self.s_me.text().strip()
        try:
            save_lab(lab, self.folder)
            save_me(self.me, self.me_path)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't save", str(e))
            return
        self.render()

    def reset_columns(self):
        self.lab.columns = {}
        save_lab(self.lab, self.folder)
        self.render()

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose the lab's shared folder",
                                                str(self.folder))
        if path:
            self.use_folder(path)

    def use_folder(self, path: str):
        """Switch to another lab folder, offering to bring this one's orders."""
        old = self.folder
        self.me.folder = path
        new = self.me.lab_folder()
        if new.resolve() == Path(old).resolve():
            return
        if self.orders and not load_orders(new):
            answer = QMessageBox.question(
                self, "Bring your orders?",
                f"The new folder has no orders yet. Copy your {len(self.orders)} "
                f"orders and lab settings there?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                self.me.folder = load_me(self.me_path).folder
                return
            if answer == QMessageBox.Yes:
                try:
                    (new / "orders").mkdir(parents=True, exist_ok=True)
                    for f in (Path(old) / "orders").glob("*.json"):
                        shutil.copy2(f, new / "orders" / f.name)
                    if (Path(old) / "lab.json").exists() and not (new / "lab.json").exists():
                        shutil.copy2(Path(old) / "lab.json", new / "lab.json")
                except OSError as e:
                    QMessageBox.warning(self, "Couldn't copy", str(e))
                    self.me.folder = load_me(self.me_path).folder
                    return
        save_me(self.me, self.me_path)
        self.refresh()
