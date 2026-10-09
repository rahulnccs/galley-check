"""Download a list (fellowships, journals) from Galley's public GitHub
repository, check every file, and keep it in the user's settings folder.

Only the list is downloaded; nothing about the user is sent. A failure
leaves any previous download untouched: the new files are written to a
fresh folder and swapped in only once all of them have been checked.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

# The public repository: releases and the lists, not the code.
REPO = "rahulnccs/galley"
TIMEOUT = 20
META = "update-info.meta"   # not *.json, so it is never read as an entry


def listing_url(remote_folder: str) -> str:
    return f"https://api.github.com/repos/{REPO}/contents/{remote_folder}?ref=main"


@dataclass
class UpdateResult:
    count: int
    updated: datetime
    skipped: list[str] = field(default_factory=list)   # files that failed checks


def _get(url: str, opener) -> bytes:
    req = Request(url, headers={"User-Agent": "Galley",
                                "Accept": "application/vnd.github+json"})
    with opener(req, timeout=TIMEOUT) as resp:
        return resp.read()


def fetch_list(url: str, folder: Path, validate: Callable[[dict], object],
               opener=urlopen) -> UpdateResult:
    """Download every .json file listed at `url` into `folder`, keeping only
    those `validate` accepts. Raises OSError when GitHub can't be reached,
    and ValueError when nothing usable came back."""
    try:
        listing = json.loads(_get(url, opener))
    except json.JSONDecodeError:
        raise ValueError("GitHub sent an unexpected reply.") from None
    if not isinstance(listing, list):
        raise ValueError("GitHub sent an unexpected reply.")

    files: dict[str, bytes] = {}
    skipped: list[str] = []
    for item in listing:
        name = str(item.get("name", ""))
        file_url = item.get("download_url")
        if item.get("type") != "file" or not name.endswith(".json") or not file_url:
            continue
        if "/" in name or "\\" in name or name.startswith("."):
            continue                             # never write outside the folder
        raw = _get(file_url, opener)
        try:
            validate(json.loads(raw))            # the same checks as the app
        except (ValueError, TypeError, AttributeError, KeyError):
            skipped.append(name)
            continue
        files[name] = raw
    if not files:
        raise ValueError("The downloaded list had no usable entries.")

    tmp = folder.with_name(folder.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name, raw in files.items():
        (tmp / name).write_bytes(raw)
    now = datetime.now(timezone.utc)
    (tmp / META).write_text(json.dumps({"updated": now.isoformat(), "source": url,
                                        "count": len(files)}), encoding="utf-8")
    shutil.rmtree(folder, ignore_errors=True)
    tmp.rename(folder)
    return UpdateResult(len(files), now, skipped)


def last_updated(folder: Path) -> datetime | None:
    """When the list in `folder` was last downloaded, or None if never."""
    try:
        meta = json.loads((folder / META).read_text(encoding="utf-8"))
        return datetime.fromisoformat(meta["updated"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
