"""Downloading the latest fellowship list."""
import json
from io import BytesIO

import pytest

from galley.fellowships import update
from galley.fellowships.model import DATA_DIR, load_fellowships

GOOD = {"id": "new-fellowship", "name": "New Fellowship", "funder": "F",
        "url": "https://example.org/new", "verified": "2026-10-01"}
CHANGED = {"id": "example-clinical-rolling", "name": "Renamed Clinical Fellowship",
           "funder": "F", "url": "https://example.org/c", "verified": "2026-10-01"}


def fake_github(files: dict, listing_status: Exception | None = None):
    listing = [{"name": n, "type": "file", "download_url": f"https://raw.example/{n}"}
               for n in files]
    listing.append({"name": "README.md", "type": "file",
                    "download_url": "https://raw.example/README.md"})

    class Resp(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout):
        url = req.full_url
        if url == update.LISTING_URL:
            if listing_status:
                raise listing_status
            return Resp(json.dumps(listing).encode())
        name = url.rsplit("/", 1)[1]
        body = files[name]
        return Resp(body if isinstance(body, bytes) else json.dumps(body).encode())
    return opener


def test_download_checks_and_saves(tmp_path):
    folder = tmp_path / "list"
    result = update.fetch_updates(folder, fake_github({
        "new-fellowship.json": GOOD, "broken.json": b"{ not json",
        "bad-date.json": dict(GOOD, id="bad", verified="soon")}))
    assert result.count == 1
    assert sorted(result.skipped) == ["bad-date.json", "broken.json"]
    assert sorted(p.name for p in folder.glob("*.json")) == ["new-fellowship.json"]
    assert update.last_updated(folder) == result.updated


def test_downloaded_entries_merge_over_bundled(tmp_path):
    folder = tmp_path / "list"
    update.fetch_updates(folder, fake_github({"new.json": GOOD, "c.json": CHANGED}))
    entries = {f.id: f for f in load_fellowships(include_templates=True,
                                                 include_custom=False,
                                                 downloaded_folder=folder)}
    assert entries["new-fellowship"].name == "New Fellowship"
    assert entries["example-clinical-rolling"].name == "Renamed Clinical Fellowship"
    assert "example-international-postdoc" in entries       # bundled, kept
    bundled = load_fellowships(DATA_DIR, include_templates=True, include_custom=False)
    assert len(entries) == len(bundled) + 1


def test_offline_leaves_previous_download(tmp_path):
    folder = tmp_path / "list"
    update.fetch_updates(folder, fake_github({"new.json": GOOD}))
    with pytest.raises(OSError):
        update.fetch_updates(folder, fake_github({}, listing_status=OSError("offline")))
    assert (folder / "new.json").exists()


def test_nothing_usable_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no usable entries"):
        update.fetch_updates(tmp_path / "list", fake_github({"b.json": b"[]"}))
    assert not (tmp_path / "list").exists()


def test_never_downloaded():
    assert update.last_updated(DATA_DIR / "does-not-exist") is None
