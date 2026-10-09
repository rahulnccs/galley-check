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
    QComboBox, QCompleter, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..lab import (OPEN_STATUSES, STATUS_LABEL, Lab, Order, advance, attention,
                   catalogue, delete_order, export_orders, frequent_items,
                   import_orders, load_lab, load_me, load_orders, new_order,
                   order_again, request_text, save_lab, save_me, save_order,
                   spend, total)
from ..lab.model import month_start, months_back
from .fellowships_page import (APPLE, SOFT, Card, Row, ScrollPage, Segmented,
                               apple_font, apple_stylesheet, day, dot,
                               field_row, filled_button, label, pill,
                               plain_button, tile_row)
from .projects_page import ActionMenu

ORDERS, INVENTORY, SPENDING, LAB = 0, 1, 2, 3
STATUS_COLOR = {"requested": SOFT["red"], "approved": SOFT["indigo"],
                "ordered": SOFT["amber"], "backordered": SOFT["purple"],
                "received": SOFT["green"], "cancelled": SOFT["grey"]}
# The tiles above the order list; "ordered" includes back-ordered.
ORDER_TILES = [("open", "Open", SOFT["all"]), ("requested", "Requested", SOFT["red"]),
               ("approved", "Approved", SOFT["indigo"]),
               ("ordered", "Ordered", SOFT["amber"]),
               ("received", "Received", SOFT["green"])]
PERIODS = [("month", "This month", SOFT["blue"]), ("year", "This year", SOFT["indigo"]),
           ("last12", "Last 12 months", SOFT["purple"])]
SHOW_AT_MOST = 200
SEARCH_STYLE = (f"background:white; border:1px solid {APPLE['fill']}; "
                f"border-radius:10px; padding:8px 12px; font-size:15px;")


def _split(text: str) -> list[str]:
    return list(dict.fromkeys(x.strip() for x in text.split(",") if x.strip()))


def _number(text: str, what: str, allow_blank: bool = True) -> float | None:
    s = text.strip().replace(",", "")
    for sign in "$€£₹¥":
        s = s.replace(sign, "")
    if not s:
        if allow_blank:
            return None
        raise ValueError(f"Enter the {what}.")
    try:
        v = float(s)
    except ValueError:
        raise ValueError(f"The {what} should be a number, not “{text.strip()}”.") from None
    if v < 0:
        raise ValueError(f"The {what} can't be negative.")
    return v


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

class OrderDialog(QDialog):
    """A new order or an edit. Typing an item the lab has ordered before
    offers it, and choosing it fills in the vendor, catalogue number and
    last price."""

    def __init__(self, lab: Lab, known: dict[str, Order], me: str,
                 current: Order | None = None, parent=None):
        super().__init__(parent)
        self.known = known
        self.setWindowTitle("Edit Order" if current else "New Order")
        self.setMinimumWidth(540)
        c = current
        form = QFormLayout()
        self.item = QLineEdit(c.item if c else "")
        self.item.setPlaceholderText("e.g. TipOne 200 µl filter tips, sterile")
        names = sorted({o.item for o in known.values()}, key=str.lower)
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(self.fill_from)
        self.item.setCompleter(completer)
        self.vendor = _combo(sorted({o.vendor for o in known.values()}, key=str.lower),
                             c.vendor if c else "", "e.g. Fisher Scientific")
        self.catalog = QLineEdit(c.catalog if c else "")
        self.qty = QLineEdit(f"{c.qty:g}" if c else "1")
        self.price = QLineEdit("" if not c or c.unit_price is None else f"{c.unit_price:g}")
        self.price.setPlaceholderText(f"in {lab.currency}, optional")
        self.size = QLineEdit(c.unit_size if c else "")
        self.size.setPlaceholderText("e.g. 500/pack, 1 L")
        self.url = QLineEdit(c.url if c else "")
        self.url.setPlaceholderText("Product page, optional")
        self.account = _combo(lab.accounts, c.account if c else
                              (lab.accounts[0] if len(lab.accounts) == 1 else ""),
                              "Grant or cost centre")
        self.by = _combo(sorted(set(lab.members) | ({me} if me else set())),
                         c.requested_by if c else me, "Who needs it")
        self.project = QLineEdit(c.project if c else "")
        self.project.setPlaceholderText("What it's for, optional")
        self.notes = QPlainTextEdit(c.notes if c else "")
        self.notes.setFixedHeight(60)
        for title, w in (("Item", self.item), ("Vendor", self.vendor),
                         ("Catalog #", self.catalog), ("Quantity", self.qty),
                         ("Unit price", self.price), ("Unit size", self.size),
                         ("Link", self.url), ("Account", self.account),
                         ("Requested by", self.by), ("Project", self.project),
                         ("Notes", self.notes)):
            form.addRow(title, w)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def fill_from(self, name: str):
        """Fill in what the lab knows about an item it ordered before."""
        o = self.known.get(name.strip().lower())
        if o is None:
            return
        self.vendor.setCurrentText(o.vendor)
        self.catalog.setText(o.catalog)
        self.price.setText("" if o.unit_price is None else f"{o.unit_price:g}")
        self.size.setText(o.unit_size)
        self.url.setText(o.url)
        if o.account and not self.account.currentText():
            self.account.setCurrentText(o.account)

    def details(self) -> dict:
        """The fields as Order keyword arguments; raises ValueError."""
        if not self.item.text().strip():
            raise ValueError("Say what to order.")
        qty = _number(self.qty.text(), "quantity", allow_blank=False)
        if qty == 0:
            raise ValueError("The quantity should be at least 1.")
        return dict(item=self.item.text().strip(),
                    vendor=self.vendor.currentText().strip(),
                    catalog=self.catalog.text().strip(),
                    qty=int(qty) if qty.is_integer() else qty,
                    unit_price=_number(self.price.text(), "unit price"),
                    unit_size=self.size.text().strip(), url=self.url.text().strip(),
                    account=self.account.currentText().strip(),
                    requested_by=self.by.currentText().strip(),
                    project=self.project.text().strip(),
                    notes=self.notes.toPlainText().strip())

    def _accept(self):
        try:
            self.details()
        except ValueError as e:
            QMessageBox.warning(self, "Order", str(e))
            return
        self.accept()


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
        self.filter = "open"
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

    def render(self):
        page = ScrollPage()
        title = QWidget()
        tl = QHBoxLayout(title)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(label(self.lab.name or "My Lab", "largeTitle"), 1)
        refresh = plain_button("Refresh")
        refresh.setToolTip("Load changes others made in the shared lab folder")
        refresh.clicked.connect(self.refresh)
        tl.addWidget(refresh, 0, Qt.AlignBottom)
        page.add(title)
        tabs = Segmented(["Orders", "Inventory", "Spending", "Lab"])
        tabs.select(self.tab, emit=False)
        tabs.changed.connect(self.show_tab)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 6, 0, 2)
        hl.addWidget(tabs)
        hl.addStretch(1)
        page.add(holder)
        {ORDERS: self._orders_tab, INVENTORY: self._inventory_tab,
         SPENDING: self._spending_tab, LAB: self._lab_tab}[self.tab](page)
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
    def _matches(self, o: Order) -> bool:
        f = self.filter
        in_tile = (o.is_open if f == "open" else
                   o.status in ("ordered", "backordered") if f == "ordered" else
                   True if f == "all" else o.status == f)
        q = self.search.lower()
        return in_tile and (not q or q in " ".join(
            (o.item, o.vendor, o.catalog, o.requested_by, o.account, o.project,
             o.notes)).lower())

    def _orders_tab(self, page: ScrollPage):
        stuck = attention(self.orders, self.lab, self.today)
        if stuck:
            page.header("Needs attention")
            card = page.add(Card())
            for a in stuck[:8]:
                row = Row(a.order.item, a.text + (f" · {a.order.vendor}" if a.order.vendor
                                                  else ""),
                          leading=dot(SOFT["red"] if a.urgent else SOFT["amber"]),
                          tappable=True)
                row.clicked.connect(lambda o=a.order, row=row: self.order_menu(o, row))
                card.add(row)
            if len(stuck) > 8:
                card.add(Row(f"{len(stuck) - 8} more", "Choose Open to see them all."))

        counts = {"open": sum(o.is_open for o in self.orders),
                  "requested": sum(o.status == "requested" for o in self.orders),
                  "approved": sum(o.status == "approved" for o in self.orders),
                  "ordered": sum(o.status in ("ordered", "backordered")
                                 for o in self.orders),
                  "received": sum(o.status == "received" for o in self.orders)}
        page.add(tile_row(ORDER_TILES, counts, self.filter, self._set_filter))
        self.search_input = page.add(self._search_box(
            self.search, "Search items, vendors, catalogue numbers, people",
            self._search_orders))

        shown = [o for o in self.orders if self._matches(o)]
        title = dict((k, t) for k, t, _ in ORDER_TILES).get(self.filter, "All")
        page.header(f"{title} orders · {len(shown)}")
        card = page.add(Card())
        if not self.orders:
            card.add(Row("No orders yet", "Add one, or import the lab's order "
                                          "spreadsheet (Excel or CSV) as it is."))
        elif not shown:
            card.add(Row("No orders match", "Clear the search, or choose another tile."))
        for o in shown[:SHOW_AT_MOST]:
            card.add(self._order_row(o))
        if len(shown) > SHOW_AT_MOST:
            card.add(Row(f"{len(shown) - SHOW_AT_MOST} older orders not shown",
                         "Search to find them."))
        if self.filter != "all":
            r = Row("Show All Orders, Including Cancelled", title_color=APPLE["blue"],
                    tappable=True)
            r.clicked.connect(lambda: self._set_filter("all"))
            card.add(r)

        again = frequent_items(self.orders)
        if again:
            page.header("Order again")
            card = page.add(Card())
            for o in again:
                sub = " · ".join(b for b in (o.vendor, o.catalog and f"#{o.catalog}",
                                             self.lab.money(o.unit_price)) if b)
                r = Row(o.item, sub, leading=dot(SOFT["blue"]), tappable=True)
                r.clicked.connect(lambda o=o: self.reorder(o))
                card.add(r)

        page.header("")
        card = page.add(Card())
        for text, handler in (("New Order…", self.new_order),
                              ("Import Order Spreadsheet (Excel or CSV)…",
                               self.import_sheet),
                              ("Export Orders (CSV)…", self.export_sheet)):
            r = Row(text, title_color=APPLE["blue"], tappable=True)
            r.clicked.connect(handler)
            card.add(r)
        page.footnote("Click an order to move it on: approve, order, mark as "
                      "received and say where it went, order it again, or copy "
                      "its details for purchasing. Red: requested · indigo: "
                      "approved · amber: ordered · purple: back-ordered · green: "
                      "received.")

    def _set_filter(self, key: str):
        self.filter = key
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
        items.append(("Edit…", "", None, lambda: self.edit(o), True))
        if o.is_open:
            items.append(("Cancel Order", "", STATUS_COLOR["cancelled"],
                          step("cancelled"), True))
        items.append(("Delete…", "Remove it from the tracker", None,
                      lambda: self.delete(o), True))
        return items

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

    def new_order(self):
        dlg = OrderDialog(self.lab, catalogue(self.orders), self.me.name, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.details()
        o = new_order(d.pop("item"), d.pop("requested_by"), self.today, **d)
        if self._save(o):
            self.orders.insert(0, o)
            self.filter = "open" if self.filter not in ("open", "requested", "all") \
                else self.filter
            self.render()

    def reorder(self, o: Order):
        again = order_again(o, self.me.name, self.today)
        dlg = OrderDialog(self.lab, catalogue(self.orders), self.me.name, again, self)
        dlg.setWindowTitle("Order Again")
        if dlg.exec() != QDialog.Accepted:
            return
        for k, v in dlg.details().items():
            setattr(again, k, v)
        if self._save(again):
            self.orders.insert(0, again)
            self.render()

    def edit(self, o: Order):
        dlg = OrderDialog(self.lab, catalogue(self.orders), self.me.name, o, self)
        if dlg.exec() != QDialog.Accepted:
            return
        for k, v in dlg.details().items():
            setattr(o, k, v)
        if self._save(o):
            self.render()

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
