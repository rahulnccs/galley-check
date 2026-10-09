"""scripts/import_fellowships.py: spreadsheet rows become database entries."""
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "import_fellowships", ROOT / "scripts" / "import_fellowships.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

TEMPLATE = ROOT / "templates" / "fellowship-database-template.xlsx"


def fill(tmp_path, rows, docs=()):
    """The real template with these rows added below its example row."""
    book = openpyxl.load_workbook(TEMPLATE)
    for name, data in (("Fellowships", rows), ("Documents", docs)):
        sheet = book[name]
        headers = [str(c.value).replace("*", "").strip() for c in sheet[1]]
        for i, row in enumerate(data, start=3):
            for j, h in enumerate(headers, start=1):
                sheet.cell(i, j).value = row.get(h)
    path = tmp_path / "filled.xlsx"
    book.save(path)
    return path


BASE = {"id": "test-fellowship", "name": "Test Fellowship", "funder": "Funder",
        "official_url": "https://example.org", "verified": datetime(2026, 10, 8)}


def test_a_row_becomes_an_entry(tmp_path):
    path = fill(tmp_path, [dict(BASE, category="phd", fields="neuroscience, genetics_genomics",
                                phd_required="No", nationalities="in, de",
                                final_deadline=datetime(2027, 1, 15), deadline_time="17:00",
                                timezone="Asia/Kolkata", deadline_estimated="Yes",
                                rolling="No", annual="Yes", duration_months=24.0,
                                other_rules="Age under 30; Indian residents",
                                host_letter="Yes", submission="portal")],
                [{"fellowship_id": "test-fellowship", "document_name": "Proposal",
                  "max_pages": 5, "required_sections": "Aims; Methods"}])
    [e] = importer.convert(path)
    assert e["category"] == "phd" and e["verified"] == "2026-10-08"
    assert e["fields"] == ["neuroscience", "genetics_genomics"]
    assert e["career_stage"] == {"phd_required": False}
    assert e["nationalities"] == ["IN", "DE"]
    assert e["deadlines"] == [{"kind": "final", "date": "2027-01-15", "time": "17:00",
                               "timezone": "Asia/Kolkata", "estimated": True}]
    assert "rolling" not in e and "annual" not in e       # defaults left out
    assert e["duration_months"] == 24
    assert e["other_rules"] == ["Age under 30", "Indian residents"]
    assert e["requirements"]["documents"] == [
        {"name": "Proposal", "max_pages": 5, "sections": ["Aims", "Methods"]}]


def test_problems_are_listed_and_nothing_is_written(tmp_path):
    path = fill(tmp_path, [dict(BASE, mobility_max_months_in_host=12),
                           dict(BASE, id="no-url", official_url=None),
                           dict(BASE, id="bad-field", fields="astronomy")],
                [{"fellowship_id": "missing", "document_name": "CV"}])
    out = tmp_path / "out"
    assert importer.main([str(path), "--out", str(out)]) == 1
    assert not out.exists()
    with pytest.raises(ValueError) as err:
        importer.convert(path)
    msg = str(err.value)
    assert "both mobility columns" in msg and "official_url is required" in msg
    assert "unknown field" in msg and "no fellowship with id 'missing'" in msg


def test_examples_are_skipped_and_files_written(tmp_path):
    out = tmp_path / "out"
    assert importer.main([str(fill(tmp_path, [BASE])), "--out", str(out)]) == 0
    assert [p.name for p in out.iterdir()] == ["test-fellowship.json"]
