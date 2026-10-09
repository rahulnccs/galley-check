"""The My Lab screen. Needs Qt; skipped where PySide6 isn't installed."""
from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from galley.lab import Lab, Me, advance, load_orders, new_order, save_lab, save_me, save_order  # noqa: E402

TODAY = date(2026, 10, 9)


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    if existing is not None:
        return existing
    try:
        return QApplication([])
    except Exception as e:
        pytest.skip(f"Qt cannot start here: {e}")


def texts(widget):
    return " | ".join(l.text() for l in widget.findChildren(QLabel))


@pytest.fixture
def lab(tmp_path):
    folder = tmp_path / "lab"
    me = tmp_path / "me.json"
    save_me(Me("Rahul", str(folder)), me)
    save_lab(Lab("Nayak Lab", ["Lea"], ["BB"], ["Bench 1"]), folder)
    tips = new_order("Filter tips", "Lea", date(2026, 9, 1), vendor="USA Scientific",
                     unit_price=63.25, qty=6, account="BB")
    advance(tips, "ordered", "Lea", date(2026, 9, 2))            # late: flagged
    plates = new_order("Plates", "Lea", date(2026, 10, 8), unit_price=10)
    tape = new_order("Lab tape", "Lea", date(2026, 8, 1), vendor="VWR", unit_price=24.75)
    advance(tape, "received", "Lea", date(2026, 8, 5), location="Bench 1",
            sublocation="tape box")
    for o in (tips, plates, tape):
        save_order(o, folder)
    return folder, me


def page(lab):
    from galley.gui.lab_page import LabPage
    return LabPage(lab[1], today=TODAY)


def sheet_items(p):
    from galley.gui.lab_sheet import KEYS
    col = KEYS.index("item")
    return [p.sheet.item(r, col).text() for r in range(p.sheet.rowCount())]


def test_orders_are_a_spreadsheet_with_the_lab_sheet_columns(app, lab):
    from galley.gui.app import Tile
    p = page(lab)
    assert "Nayak Lab" in texts(p.current)
    headers = [p.sheet.horizontalHeaderItem(c).text() for c in range(p.sheet.columnCount())]
    assert headers[:8] == ["Status", "Date Requested", "Date Approved", "Approved By",
                           "Date Ordered", "Account", "Item Name", "Requested By"]
    assert sorted(sheet_items(p)) == ["Filter tips", "Lab tape", "Plates"]
    tiles = {t.key: t.text() for t in p.current.findChildren(Tile)}
    assert set(tiles) == {"requested", "approved", "ordered"}      # no Open / Received
    assert "1 order needs attention" in " ".join(
        b.text() for b in p.current.findChildren(__import__(
            "PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton))
    p._set_filter("ordered")
    assert sheet_items(p) == ["Filter tips"]
    p._set_filter("ordered")                                   # again: everything
    assert len(sheet_items(p)) == 3


def test_new_row_is_typed_into_the_sheet_and_saved(app, lab):
    from galley.gui.lab_sheet import KEYS
    p = page(lab)
    o = p.new_row()
    assert p.sheet.rows[0] is o and o.requested_by == "Rahul"
    assert len(load_orders(lab[0])) == 3                       # nothing saved yet
    p.sheet.commit(0, KEYS.index("item"), "Filter tips")      # known: filled in
    saved = {x.id: x for x in load_orders(lab[0])}[o.id]
    assert saved.vendor == "USA Scientific" and saved.unit_price == 63.25
    p.sheet.commit(0, KEYS.index("qty"), "2")
    p.sheet.commit(0, KEYS.index("received"), "2026-10-09")
    assert p.sheet.item(0, KEYS.index("total")).text() == "$126.50"
    assert p.sheet.item(0, KEYS.index("received")).text() == "9 Oct 2026"
    from PySide6.QtWidgets import QMessageBox
    warned = []
    QMessageBox.warning = staticmethod(lambda *a: warned.append(a[2]))
    assert not p.sheet.commit(0, KEYS.index("unit_price"), "lots")
    assert warned and {x.id: x for x in load_orders(lab[0])}[o.id].unit_price == 63.25


def test_status_cell_moves_the_order_on(app, lab):
    from PySide6.QtWidgets import QApplication
    from galley.gui.lab_sheet import KEYS
    p = page(lab)
    r = sheet_items(p).index("Plates")
    p.sheet.commit(r, KEYS.index("status"), "approved")
    QApplication.processEvents()                               # the deferred redraw
    saved = {o.item: o for o in load_orders(lab[0])}
    assert (saved["Plates"].status, saved["Plates"].approved_by) == ("approved", "Rahul")


def test_columns_can_be_renamed_for_the_whole_lab(app, lab):
    from galley.lab import load_lab
    p = page(lab)
    p.rename_column("account", "System")
    assert p.sheet.horizontalHeaderItem(5).text() == "System"
    assert load_lab(lab[0]).columns == {"account": "System"}
    assert page(lab).sheet.horizontalHeaderItem(5).text() == "System"
    p.rename_column("account", "")
    assert p.sheet.horizontalHeaderItem(5).text() == "Account"


def test_a_new_tracker_starts_with_example_rows_once(app, tmp_path):
    from galley.gui.lab_page import LabPage
    me = tmp_path / "me.json"
    save_me(Me("Rahul", str(tmp_path / "new-lab")), me)
    p = LabPage(me, today=TODAY)
    assert len(p.orders) == 6 and all(o.example for o in p.orders)
    assert {o.status for o in p.orders} == {"requested", "approved", "ordered", "received"}
    p.remove_examples()
    assert p.orders == []
    assert LabPage(me, today=TODAY).orders == []                # not added again


def test_menu_offers_next_steps_and_marking_received_records_where(app, lab):
    p = page(lab)
    tips = next(o for o in p.orders if o.item == "Filter tips")
    names = [i[0] for i in p.order_menu_items(tips)]
    assert names[:2] == ["Mark as Received…", "Back-ordered"]
    assert "Approve" not in names and "Order Again" in names and "Edit…" not in names
    plates = next(o for o in p.orders if o.item == "Plates")
    assert [i[0] for i in p.order_menu_items(plates)][:2] == ["Approve", "Mark as Ordered"]
    p.move(tips, "received", location="-20 °C", sublocation="box 3")
    saved = {o.item: o for o in load_orders(lab[0])}
    assert (saved["Filter tips"].status, saved["Filter tips"].location) == ("received", "-20 °C")
    assert p.attention_count() == 0
    p.reorder(saved["Filter tips"])
    assert sheet_items(p)[0] == "Filter tips" and len(load_orders(lab[0])) == 4


def test_inventory_finds_where_things_are(app, lab):
    p = page(lab)
    p.show_tab(1)                              # Inventory
    assert "BENCH 1 · 1" in texts(p.current) and "tape box" in texts(p.current)
    p._search_inventory("nothing like this")
    assert "Nothing matches" in texts(p.current)


def test_spending_tab_totals(app, lab):
    p = page(lab)
    p.show_tab(2)
    from galley.gui.app import Tile
    tiles = {t.key: t.text() for t in p.current.findChildren(Tile)}
    assert tiles["year"] == "$404.25\nThis year"           # tips + tape
    assert tiles["month"] == "$0.00\nThis month"
    shown = texts(p.current)
    assert "BY ACCOUNT" in shown and "BY VENDOR" in shown and "September 2026" in shown
    assert "$10.00" in shown                   # plates, waiting to be ordered


def test_lab_settings_save_and_import(app, lab, tmp_path):
    p = page(lab)
    p.show_tab(3)
    p.s_accounts.setText("BB, NCIRE")
    p.s_me.setText("Rahul B")
    p.save_settings()
    assert p.lab.accounts == ["BB", "NCIRE"] and p.me.name == "Rahul B"

    sheet = tmp_path / "sheet.csv"
    sheet.write_text("Status,Item Name,Vendor,Location,Qty,Unit Price\n"
                     "Received,Gavage needles,Cadence,Bench 2,1,610.06\n")
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    assert p.import_from(str(sheet))
    assert "Gavage needles" in [o.item for o in load_orders(lab[0])]
    assert "Bench 2" in p.lab.locations       # learned from the sheet


def test_main_window_has_my_lab(app, tmp_path, monkeypatch):
    from galley.checks.offline import submission
    monkeypatch.setattr(submission, "user_profile_dir", lambda: tmp_path / "profiles")
    from galley.gui.app import MainWindow
    win = MainWindow("Georgia")
    assert win.switcher.buttons[3].text() == "My Lab"
    win.switcher.select(3)
    assert win.sections.currentWidget() is win.lab
