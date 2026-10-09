"""Lab orders: what was requested, approved, ordered and received, where it
was put, and what it cost.

Each order is one small JSON file in the lab folder's orders/ folder, and the
lab's settings (members, accounts, storage locations) are lab.json beside it.
The lab folder can live on a shared drive, so a whole lab can use one
tracker: people editing different orders never write the same file, and
every save is atomic.

Which lab folder to use, and who "I" am, are personal and stay in the user's
own Galley settings folder.
"""
from __future__ import annotations

import csv
import json
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

# In the order they normally happen. Back-ordered is ordered but delayed.
STATUSES = ["requested", "approved", "ordered", "backordered", "received", "cancelled"]
OPEN_STATUSES = {"requested", "approved", "ordered", "backordered"}
STATUS_LABEL = {"requested": "Requested", "approved": "Approved", "ordered": "Ordered",
                "backordered": "Back-ordered", "received": "Received",
                "cancelled": "Cancelled"}


def _settings_root() -> Path:
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)                       # never leave a half-written file


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ---- where the lab is, and who I am -------------------------------------------

@dataclass
class Me:
    """Personal: kept in the user's own settings, never in the shared folder."""
    name: str = ""
    folder: str = ""                # the lab folder; blank = the default

    def lab_folder(self) -> Path:
        return Path(self.folder).expanduser() if self.folder else _settings_root() / "lab"


def load_me(path: Path | None = None) -> Me:
    d = _read_json(path or _settings_root() / "my-lab.json")
    return Me(str(d.get("name") or ""), str(d.get("folder") or ""))


def save_me(me: Me, path: Path | None = None) -> None:
    _write_json(path or _settings_root() / "my-lab.json", asdict(me))


# ---- the lab ---------------------------------------------------------------------

@dataclass
class Lab:
    name: str = ""
    members: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)   # grants / cost centres
    locations: list[str] = field(default_factory=list)  # benches, freezers...
    currency: str = "$"
    order_within_days: int = 7      # a request not yet ordered after this is flagged
    deliver_within_days: int = 14   # an order not yet received after this is flagged

    def money(self, amount: float | None) -> str:
        return "" if amount is None else f"{self.currency}{amount:,.2f}"


def load_lab(folder: Path) -> Lab:
    d = _read_json(Path(folder) / "lab.json")
    known = {k: v for k, v in d.items() if k in Lab.__dataclass_fields__}
    try:
        return Lab(**known)
    except TypeError:
        return Lab()


def save_lab(lab: Lab, folder: Path) -> None:
    _write_json(Path(folder) / "lab.json", asdict(lab))


# ---- orders ----------------------------------------------------------------------

@dataclass
class Order:
    id: str
    item: str
    vendor: str = ""
    catalog: str = ""
    qty: float = 1
    unit_price: float | None = None
    unit_size: str = ""             # "500/pack", "1 L"
    url: str = ""
    account: str = ""               # grant or cost centre it's charged to
    project: str = ""               # optional: what it's for
    status: str = "requested"
    requested_by: str = ""
    requested: str = ""             # dates are YYYY-MM-DD
    approved_by: str = ""
    approved: str = ""
    ordered: str = ""
    received_by: str = ""
    received: str = ""
    location: str = ""
    sublocation: str = ""
    notes: str = ""
    history: list[dict] = field(default_factory=list)   # {date, status, by}
    updated: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")

    @property
    def total(self) -> float | None:
        return None if self.unit_price is None else round(self.qty * self.unit_price, 2)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def when(self, key: str) -> date | None:
        try:
            return date.fromisoformat(getattr(self, key))
        except (TypeError, ValueError):
            return None

    def spend_date(self) -> date | None:
        """The date the money counts on: when it was ordered, or failing that
        received or requested."""
        return self.when("ordered") or self.when("received") or self.when("requested")

    @classmethod
    def from_dict(cls, d: dict) -> "Order":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def new_order(item: str, by: str = "", on: date | None = None, **details) -> Order:
    if not item.strip():
        raise ValueError("Say what to order.")
    on = on or date.today()
    o = Order(new_id(), item.strip(), requested_by=by, requested=on.isoformat(),
              **details)
    o.history.append({"date": on.isoformat(), "status": "requested", "by": by})
    return o


def advance(o: Order, status: str, by: str = "", on: date | None = None,
            location: str | None = None, sublocation: str | None = None) -> Order:
    """Move an order on, recording who did it and when."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    on_s = (on or date.today()).isoformat()
    o.status = status
    if status == "approved":
        o.approved, o.approved_by = on_s, by
    elif status in ("ordered", "backordered") and not o.ordered:
        o.ordered = on_s
    elif status == "received":
        o.received, o.received_by = on_s, by
        if not o.ordered:
            o.ordered = on_s
        if location is not None:
            o.location = location
        if sublocation is not None:
            o.sublocation = sublocation
    o.history.append({"date": on_s, "status": status, "by": by})
    return o


def order_again(o: Order, by: str = "", on: date | None = None) -> Order:
    """A new request for the same item, from the same vendor, at the last
    price; where the last one was put is kept as a hint."""
    return new_order(o.item, by, on, vendor=o.vendor, catalog=o.catalog, qty=o.qty,
                     unit_price=o.unit_price, unit_size=o.unit_size, url=o.url,
                     account=o.account, project=o.project, location=o.location,
                     sublocation=o.sublocation)


def orders_dir(folder: Path) -> Path:
    return Path(folder) / "orders"


def save_order(o: Order, folder: Path) -> Path:
    o.updated = datetime.now().isoformat(timespec="seconds")
    path = orders_dir(folder) / f"{o.id}.json"
    _write_json(path, asdict(o))
    return path


def delete_order(order_id: str, folder: Path) -> bool:
    try:
        (orders_dir(folder) / f"{order_id}.json").unlink()
    except OSError:
        return False
    return True


def load_orders(folder: Path) -> list[Order]:
    """Every order, newest request first. A damaged file is skipped rather
    than hiding the others."""
    out = []
    try:
        paths = sorted(orders_dir(folder).glob("*.json"))
    except OSError:
        return out
    for path in paths:
        try:
            out.append(Order.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(out, key=lambda o: (o.requested, o.updated), reverse=True)


# ---- what the lab's history tells us ---------------------------------------------

def catalogue(orders: list[Order]) -> dict[str, Order]:
    """The most recent order of each item, by name: typing an item ordered
    before fills in its vendor, catalogue number and price."""
    latest: dict[str, Order] = {}
    for o in sorted(orders, key=lambda o: o.requested):
        latest[o.item.strip().lower()] = o
    return latest


def frequent_items(orders: list[Order], n: int = 8) -> list[Order]:
    """The items ordered most often, latest order of each."""
    counts = Counter(o.item.strip().lower() for o in orders if o.status != "cancelled")
    latest = catalogue(orders)
    return [latest[k] for k, c in counts.most_common(n) if c > 1]


@dataclass
class Attention:
    order: Order
    text: str
    urgent: bool = False


def attention(orders: list[Order], lab: Lab, today: date) -> list[Attention]:
    """Orders that seem stuck: requested but not ordered, ordered but not
    delivered, or back-ordered. Oldest first."""
    out = []
    for o in orders:
        if o.status in ("requested", "approved"):
            since = o.when("approved") or o.when("requested")
            if since and (days := (today - since).days) > lab.order_within_days:
                out.append(Attention(o, f"{STATUS_LABEL[o.status]} {days} days ago, "
                                        f"not ordered yet"))
        elif o.status == "ordered":
            since = o.when("ordered")
            if since and (days := (today - since).days) > lab.deliver_within_days:
                out.append(Attention(o, f"Ordered {days} days ago, not received yet",
                                     urgent=True))
        elif o.status == "backordered":
            since = o.when("ordered")
            out.append(Attention(o, "Back-ordered" + (
                f" since {since:%d %b}" if since else ""), urgent=True))
    return sorted(out, key=lambda a: (a.order.when("ordered") or a.order.when("requested")
                                      or today))


def spend(orders: list[Order], start: date, end: date, by: str = "account") -> dict[str, float]:
    """Money committed (ordered or received) between two dates, grouped by
    account, vendor or month, largest first. Requested and cancelled orders
    aren't spent yet."""
    totals: dict[str, float] = defaultdict(float)
    for o in orders:
        d = o.spend_date()
        if (o.status not in ("ordered", "backordered", "received") or o.total is None
                or d is None or not start <= d <= end):
            continue
        key = (f"{d:%Y-%m}" if by == "month" else
               (getattr(o, by) or "Not set").strip() or "Not set")
        totals[key] += o.total
    order = sorted(totals.items(), key=lambda kv: kv[0]) if by == "month" else \
        sorted(totals.items(), key=lambda kv: -kv[1])
    return {k: round(v, 2) for k, v in order}


def total(orders: list[Order], statuses: set[str]) -> float:
    return round(sum(o.total or 0 for o in orders if o.status in statuses), 2)


def month_start(d: date) -> date:
    return d.replace(day=1)


def months_back(d: date, n: int) -> date:
    """The first day of the month n months before d's month."""
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    return date(y, m + 1, 1)


# ---- spreadsheets ----------------------------------------------------------------
# Columns are found by header, in any order, so a lab's existing order sheet
# imports as it is. Unknown columns are ignored.

ALIASES = {
    "status": ["status", "state"],
    "requested": ["daterequested", "requested", "requestedon", "requestdate"],
    "approved": ["dateapproved", "approvedon", "approvaldate"],
    "approved_by": ["approvedby", "approver"],
    "ordered": ["dateordered", "orderedon", "orderdate"],
    "account": ["system", "account", "grant", "fund", "costcenter", "costcentre",
                "speedtype", "budget"],
    "item": ["itemname", "item", "description", "product", "productname"],
    "requested_by": ["requestedby", "requester", "orderedby"],
    "vendor": ["vendor", "supplier", "company", "manufacturer"],
    "catalog": ["catalog", "catalogno", "catalognumber", "cat", "catno", "catalogue",
                "cataloguenumber", "partnumber", "sku"],
    "qty": ["qty", "quantity"],
    "unit_price": ["unitprice", "price", "priceeach", "unitcost"],
    "total": ["totalprice", "total", "totalcost", "cost"],
    "received_by": ["receivedby"],
    "received": ["datereceived", "receivedon", "received"],
    "location": ["location", "storage", "storedin"],
    "sublocation": ["sublocation", "shelf", "position"],
    "unit_size": ["unitsize", "size", "packsize"],
    "url": ["url", "link", "website"],
    "project": ["project"],
    "notes": ["notes", "comments", "comment"],
}
STATUS_WORDS = {"requested": "requested", "request": "requested", "pending": "requested",
                "new": "requested", "approved": "approved", "ordered": "ordered",
                "placed": "ordered", "backordered": "backordered",
                "backorder": "backordered", "received": "received",
                "delivered": "received", "cancelled": "cancelled",
                "canceled": "cancelled", "rejected": "cancelled"}
EXPORT_COLUMNS = [("Status", "status"), ("Date Requested", "requested"),
                  ("Date Approved", "approved"), ("Approved By", "approved_by"),
                  ("Date Ordered", "ordered"), ("Account", "account"),
                  ("Item Name", "item"), ("Requested By", "requested_by"),
                  ("Vendor", "vendor"), ("Catalog #", "catalog"), ("Qty", "qty"),
                  ("Unit Price", "unit_price"), ("Total Price", "total"),
                  ("Received By", "received_by"), ("Date Received", "received"),
                  ("Location", "location"), ("SubLocation", "sublocation"),
                  ("Unit Size", "unit_size"), ("URL", "url"), ("Project", "project"),
                  ("Notes", "notes")]


def _key(header) -> str:
    return re.sub(r"[^a-z]", "", str(header or "").lower())


def _match_columns(headers: list) -> dict[str, int]:
    found: dict[str, int] = {}
    keys = [_key(h) for h in headers]
    for name, aliases in ALIASES.items():     # exact matches first
        for i, k in enumerate(keys):
            if k in aliases and i not in found.values():
                found.setdefault(name, i)
    return found


def _date_text(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"can't read the date {s!r}; use YYYY-MM-DD or MM/DD/YYYY")


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v))
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"can't read the number {v!r}") from None


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))              # catalogue numbers typed as numbers
    return str(v).strip()


def _sheet_rows(path: Path) -> list[list]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=True)
        sheet = book.worksheets[0]
        return [list(r) for r in sheet.iter_rows(values_only=True)]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.reader(fh)]


@dataclass
class ImportResult:
    orders: list[Order] = field(default_factory=list)
    duplicates: int = 0
    problems: list[str] = field(default_factory=list)


def _fingerprint(o: Order) -> tuple:
    return (o.item.lower(), o.catalog.lower(), o.requested, o.qty, o.requested_by.lower())


def import_orders(path: str | Path, existing: list[Order] = ()) -> ImportResult:
    """Read a lab's order sheet (Excel or CSV). The header row is found
    automatically; orders already in the tracker are skipped, so importing
    the same sheet twice adds nothing."""
    path = Path(path)
    rows = _sheet_rows(path)
    header_at = next((i for i, r in enumerate(rows[:20])
                      if "item" in _match_columns(r)), None)
    if header_at is None:
        raise ValueError("Couldn't find the header row: the sheet needs a column "
                         "called “Item Name” (or Item, Description, Product).")
    cols = _match_columns(rows[header_at])
    seen = {_fingerprint(o) for o in existing}
    result = ImportResult()

    def get(row, name):
        i = cols.get(name)
        return row[i] if i is not None and i < len(row) else None

    for n, row in enumerate(rows[header_at + 1:], start=header_at + 2):
        item = _text(get(row, "item"))
        if not item:
            continue
        try:
            word = _key(get(row, "status"))
            status = STATUS_WORDS.get(word)
            if word and status is None:
                raise ValueError(f"unknown status {get(row, 'status')!r}")
            qty = _num(get(row, "qty")) or 1
            unit, tot = _num(get(row, "unit_price")), _num(get(row, "total"))
            if unit is None and tot is not None:
                unit = round(tot / qty, 4)
            o = Order(
                new_id(), item, vendor=_text(get(row, "vendor")),
                catalog=_text(get(row, "catalog")),
                qty=int(qty) if float(qty).is_integer() else qty, unit_price=unit,
                unit_size=_text(get(row, "unit_size")), url=_text(get(row, "url")),
                account=_text(get(row, "account")), project=_text(get(row, "project")),
                requested_by=_text(get(row, "requested_by")),
                requested=_date_text(get(row, "requested")),
                approved_by=_text(get(row, "approved_by")),
                approved=_date_text(get(row, "approved")),
                ordered=_date_text(get(row, "ordered")),
                received_by=_text(get(row, "received_by")),
                received=_date_text(get(row, "received")),
                location=_text(get(row, "location")),
                sublocation=_text(get(row, "sublocation")),
                notes=_text(get(row, "notes")))
            # No status column: work it out from the dates filled in.
            o.status = status or ("received" if o.received else "ordered" if o.ordered
                                  else "approved" if o.approved else "requested")
            o.history.append({"date": date.today().isoformat(), "status": o.status,
                              "by": "imported from " + path.name})
        except ValueError as e:
            result.problems.append(f"Row {n} ({item[:40]}): {e}")
            continue
        fp = _fingerprint(o)
        if fp in seen:
            result.duplicates += 1
            continue
        seen.add(fp)
        result.orders.append(o)
    return result


def export_orders(orders: list[Order], path: str | Path) -> None:
    """A CSV with the usual order-sheet columns; import_orders reads it back."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([h for h, _ in EXPORT_COLUMNS])
        for o in orders:
            row = []
            for _, key in EXPORT_COLUMNS:
                v = getattr(o, key)
                row.append(STATUS_LABEL[v] if key == "status" else "" if v is None else v)
            w.writerow(row)


def request_text(o: Order, lab: Lab) -> str:
    """The order as plain text, to paste into an email or purchasing form."""
    lines = [o.item]
    for label, value in (("Vendor", o.vendor), ("Catalog #", o.catalog),
                         ("Unit size", o.unit_size), ("Quantity", f"{o.qty:g}"),
                         ("Unit price", lab.money(o.unit_price)),
                         ("Total", lab.money(o.total)), ("Account", o.account),
                         ("Requested by", o.requested_by), ("Link", o.url)):
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)
