"""My Lab: orders, their lifecycle, the shared folder, spreadsheets, spending."""
import csv
import json
from datetime import date, datetime

import pytest

from galley.lab import (Lab, Me, advance, attention, catalogue, delete_order,
                        export_orders, frequent_items, import_orders, load_lab,
                        load_me, load_orders, new_order, order_again,
                        request_text, save_lab, save_me, save_order, spend, total)

TODAY = date(2026, 10, 9)


def order(item="Filter tips", **kw):
    return new_order(item, kw.pop("by", "Lea"), kw.pop("on", date(2026, 9, 1)), **kw)


def test_an_order_moves_through_its_life():
    o = order(vendor="USA Scientific", catalog="1120-8710", qty=6, unit_price=63.25)
    assert o.status == "requested" and o.requested == "2026-09-01"
    assert o.total == 379.5
    advance(o, "approved", "Rahul", date(2026, 9, 2))
    advance(o, "ordered", "Rahul", date(2026, 9, 3))
    advance(o, "received", "Veronica", date(2026, 9, 10), location="Bench 1",
            sublocation="Above weigh station")
    assert (o.approved_by, o.approved, o.ordered) == ("Rahul", "2026-09-02", "2026-09-03")
    assert (o.received_by, o.received, o.location) == ("Veronica", "2026-09-10", "Bench 1")
    assert [h["status"] for h in o.history] == ["requested", "approved", "ordered",
                                                "received"]
    with pytest.raises(ValueError):
        advance(o, "lost")
    with pytest.raises(ValueError):
        new_order("  ")


def test_order_again_copies_the_details_not_the_history():
    o = order(vendor="VWR", catalog="89039-658", unit_price=94.49, location="Bench 1")
    advance(o, "received", "Lea", date(2026, 9, 14))
    again = order_again(o, "Mae", TODAY)
    assert again.id != o.id and again.status == "requested"
    assert (again.vendor, again.catalog, again.unit_price) == ("VWR", "89039-658", 94.49)
    assert again.requested_by == "Mae" and again.received == ""
    assert again.location == "Bench 1"         # where it went last time


def test_orders_are_one_file_each_in_the_lab_folder(tmp_path):
    a, b = order("Tips"), order("Plates", on=date(2026, 9, 5))
    for o in (a, b):
        save_order(o, tmp_path)
    assert sorted(p.name for p in (tmp_path / "orders").iterdir()) == \
        sorted([f"{a.id}.json", f"{b.id}.json"])
    (tmp_path / "orders" / "broken.json").write_text("{not json")
    assert [o.item for o in load_orders(tmp_path)] == ["Plates", "Tips"]   # newest first
    assert delete_order(a.id, tmp_path) and not delete_order(a.id, tmp_path)
    assert load_orders(tmp_path / "missing") == []


def test_lab_and_personal_settings_are_kept_apart(tmp_path):
    save_lab(Lab("Nayak Lab", ["Lea"], ["BB", "NCIRE"], ["Bench 1"], "$", 5, 10), tmp_path)
    lab = load_lab(tmp_path)
    assert lab.accounts == ["BB", "NCIRE"] and lab.order_within_days == 5
    assert lab.money(1165.7) == "$1,165.70"
    assert load_lab(tmp_path / "nowhere") == Lab()
    me_file = tmp_path / "me.json"
    save_me(Me("Rahul", str(tmp_path / "shared")), me_file)
    me = load_me(me_file)
    assert me.name == "Rahul" and me.lab_folder() == tmp_path / "shared"
    assert "lab.json" not in me_file.read_text()


def test_stuck_orders_need_attention():
    lab = Lab(order_within_days=7, deliver_within_days=14)
    fresh = order("Fresh", on=date(2026, 10, 5))
    waiting = order("Waiting", on=date(2026, 9, 20))
    late = order("Late")
    advance(late, "ordered", on=date(2026, 9, 1))
    delayed = order("Delayed")
    advance(delayed, "backordered", on=date(2026, 10, 1))
    done = order("Done")
    advance(done, "received", on=date(2026, 9, 2))
    found = {a.order.item: a for a in attention([fresh, waiting, late, delayed, done],
                                                lab, TODAY)}
    assert set(found) == {"Waiting", "Late", "Delayed"}
    assert "19 days ago, not ordered" in found["Waiting"].text
    assert found["Late"].urgent and "not received" in found["Late"].text


def test_spending_counts_what_was_ordered():
    a = order("A", vendor="VWR", account="BB", qty=2, unit_price=100)
    advance(a, "ordered", on=date(2026, 9, 3))
    b = order("B", vendor="Fisher", account="NCIRE", unit_price=50)
    advance(b, "received", on=date(2026, 10, 2))
    c = order("C", vendor="VWR", unit_price=999)                  # only requested
    d = order("D", vendor="VWR", unit_price=999)
    advance(d, "cancelled")
    old = order("Old", unit_price=10)
    advance(old, "ordered", on=date(2025, 12, 1))
    orders = [a, b, c, d, old]
    year = (date(2026, 1, 1), TODAY)
    assert spend(orders, *year, by="account") == {"BB": 200, "NCIRE": 50}
    assert spend(orders, *year, by="vendor") == {"VWR": 200, "Fisher": 50}
    assert spend(orders, *year, by="month") == {"2026-09": 200, "2026-10": 50}
    assert spend(orders, date(2025, 1, 1), TODAY, by="account")["Not set"] == 10
    assert total(orders, {"requested"}) == 999


def test_items_ordered_before_are_remembered():
    first = order("Lab tape", vendor="VWR", unit_price=20, on=date(2026, 1, 1))
    second = order("Lab tape", vendor="VWR", unit_price=24.75, on=date(2026, 9, 1))
    once = order("Gavage needles")
    known = catalogue([second, first, once])
    assert known["lab tape"].unit_price == 24.75             # the latest price
    assert [o.item for o in frequent_items([first, second, once])] == ["Lab tape"]


def test_request_text_for_purchasing():
    o = order("Filter plates", vendor="Fisher", catalog="7200754", qty=2,
              unit_price=10.5, url="https://example.org/p")
    text = request_text(o, Lab())
    assert text.splitlines()[0] == "Filter plates"
    assert "Catalog #: 7200754" in text and "Total: $21.00" in text
    assert "Link: https://example.org/p" in text


# ---- spreadsheets -----------------------------------------------------------

HEADER = ["Status", "Date Requested", "Date Approved", "Approved By", "Date Ordered",
          "System", "Item Name", "Requested By", "Lab Name", "Vendor", "Catalog #", "Qty",
          "Unit Price", "Total Price", "Received By", "Date Received", "Location",
          "SubLocation", "Unit Size", "URL"]


def sheet_rows():
    return [
        ["Requested", "10/7/2026", "", "", "", "BB", "Precellys CK28 Lysing Kit",
         "Mae Miranda", "NayakLab", "VWR International", "10144-494", 8, 197.2,
         1577.6, "", "", "", "", "", ""],
        ["Received", "9/24/2026", "", "", "", "BB", "TipOne 200 ul filter tips",
         "Veronica Escalante", "NayakLab", "USA Scientific", "1120-8710", 6, 63.25,
         379.5, "Lea Twicken", "10/2/2026", "Bench 1", "3 boxes between bench 1 and 2",
         "", ""],
        ["Ordered", "9/14/2026", "", "", "", "BB", "Falcon 96-Well Microplate",
         "Veronica Escalante", "NayakLab", "Fisher Scientific", "08-772-54", 1, "",
         "142.44", "", "", "", "", "", ""],
        ["Cancelled", "9/9/2026", "", "", "", "BB", "Colored Labeling Tape, Orange",
         "Lea Twicken", "NayakLab", "Fisher Scientific", "1590120F", 1, "55.14", "55.14",
         "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]


def test_the_labs_own_excel_sheet_imports_as_it_is(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    ws = book.active
    ws.append(HEADER)
    ws.append([])                       # blank rows under the header, as in the lab's sheet
    ws.append([])
    for r in sheet_rows():
        r = list(r)
        r[1] = datetime.strptime(r[1], "%m/%d/%Y") if r[1] else None
        r[10] = int(r[10]) if r[10].isdigit() else r[10]    # catalogue no. typed as a number
        ws.append(r)
    path = tmp_path / "orders.xlsx"
    book.save(path)
    result = import_orders(path)
    assert result.problems == [] and len(result.orders) == 4
    by_item = {o.item: o for o in result.orders}
    tips = by_item["TipOne 200 ul filter tips"]
    assert (tips.status, tips.requested, tips.received) == ("received", "2026-09-24",
                                                            "2026-10-02")
    assert tips.account == "BB" and tips.sublocation.startswith("3 boxes")
    assert by_item["Falcon 96-Well Microplate"].unit_price == 142.44   # from the total
    assert by_item["Colored Labeling Tape, Orange"].status == "cancelled"
    assert by_item["Precellys CK28 Lysing Kit"].total == 1577.6

    again = import_orders(path, result.orders)       # importing twice adds nothing
    assert again.orders == [] and again.duplicates == 4


def test_csv_round_trip_and_problems(tmp_path):
    path = tmp_path / "orders.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(sheet_rows())
        w.writerow(["Lost", "", "", "", "", "", "Mystery item"] + [""] * 13)
        w.writerow(["", "31/31/2026", "", "", "", "", "Bad date"] + [""] * 13)
    result = import_orders(path)
    assert len(result.orders) == 4
    assert any("unknown status" in p for p in result.problems)
    assert any("can't read the date" in p for p in result.problems)

    out = tmp_path / "export.csv"
    export_orders(result.orders, out)
    back = import_orders(out)
    assert sorted((o.item, o.status, o.total) for o in back.orders) == \
        sorted((o.item, o.status, o.total) for o in result.orders)


def test_a_sheet_without_an_item_column_is_refused(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("Name,Price\nTips,3\n")
    with pytest.raises(ValueError, match="Item Name"):
        import_orders(path)


def test_status_is_worked_out_from_dates_when_missing(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("Item,Date Ordered,Date Received\nA,2026-09-01,\nB,2026-09-01,"
                    "2026-09-05\nC,,\n")
    status = {o.item: o.status for o in import_orders(path).orders}
    assert status == {"A": "ordered", "B": "received", "C": "requested"}
    json.dumps([o.__dict__ for o in import_orders(path).orders])   # stays serialisable


def test_example_orders_show_each_stage():
    from galley.lab import example_orders
    rows = example_orders(TODAY, "Rahul")
    assert all(o.example for o in rows)
    assert [o.status for o in rows][:4] == ["requested", "approved", "ordered", "received"]
    received = [o for o in rows if o.status == "received"]
    assert all(o.location and o.received for o in received)
    assert all(o.requested <= o.ordered <= o.received for o in received)
