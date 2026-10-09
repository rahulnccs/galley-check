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


def test_orders_tab_shows_open_orders_and_what_is_stuck(app, lab):
    p = page(lab)
    shown = texts(p.current)
    assert "Nayak Lab" in shown and "NEEDS ATTENTION" in shown
    assert "Ordered 37 days ago, not received yet" in shown
    assert "Filter tips" in shown and "Plates" in shown
    assert "OPEN ORDERS · 2" in shown and "$379.50" in shown
    assert p.attention_count() == 1
    p._set_filter("received")
    assert "Lab tape" in texts(p.current) and "Plates" not in texts(p.current)


def test_menu_offers_next_steps_and_marking_received_records_where(app, lab):
    p = page(lab)
    tips = next(o for o in p.orders if o.item == "Filter tips")
    names = [i[0] for i in p.order_menu_items(tips)]
    assert names[:2] == ["Mark as Received…", "Back-ordered"]
    assert "Approve" not in names and "Order Again" in names
    plates = next(o for o in p.orders if o.item == "Plates")
    assert [i[0] for i in p.order_menu_items(plates)][:2] == ["Approve", "Mark as Ordered"]

    p.move(plates, "approved")
    saved = {o.item: o for o in load_orders(lab[0])}
    assert saved["Plates"].approved_by == "Rahul"
    p.move(tips, "received", location="-20 °C", sublocation="box 3")
    saved = {o.item: o for o in load_orders(lab[0])}
    assert (saved["Filter tips"].status, saved["Filter tips"].location) == ("received", "-20 °C")
    assert p.attention_count() == 0


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
