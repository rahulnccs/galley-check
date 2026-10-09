"""Download the latest fellowship list from Galley's public GitHub repository.

Galley ships with a copy of the list. "Check for Updates" fetches the current
files from fellowships/ in the public repository (the source code itself is
kept in a private one), checks every one, and keeps
them in the user's settings folder. Only the list is downloaded; nothing
about the user is sent.

Downloaded entries are merged over the bundled ones by id, so an older
download never hides entries added in a newer version of the app.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .model import Fellowship

# The public repository: releases and the fellowship list, not the code.
REPO = "rahulnccs/galley"
LISTING_URL = (f"https://api.github.com/repos/{REPO}/contents/"
               f"fellowships?ref=main")
TIMEOUT = 20
META = "update-info.meta"   # not *.json, so it is never read as an entry


def downloaded_dir() -> Path:
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent / "fellowship-list"


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


def fetch_updates(folder: Path | None = None, opener=urlopen) -> UpdateResult:
    """Download and check the current list. Raises OSError when GitHub can't
    be reached, and ValueError when nothing usable came back; the previous
    download, if any, is left untouched in both cases."""
    folder = folder or downloaded_dir()
    try:
        listing = json.loads(_get(LISTING_URL, opener))
    except json.JSONDecodeError:
        raise ValueError("GitHub sent an unexpected reply.") from None
    if not isinstance(listing, list):
        raise ValueError("GitHub sent an unexpected reply.")

    files: dict[str, bytes] = {}
    skipped: list[str] = []
    for item in listing:
        name = str(item.get("name", ""))
        url = item.get("download_url")
        if item.get("type") != "file" or not name.endswith(".json") or not url:
            continue
        if "/" in name or name.startswith("."):
            continue                             # never write outside the folder
        raw = _get(url, opener)
        try:
            data = json.loads(raw)
            Fellowship.from_dict(data)           # the same checks as the app
        except (ValueError, TypeError, AttributeError):
            skipped.append(name)
            continue
        files[name] = raw
    if not files:
        raise ValueError("The downloaded list had no usable entries.")

    # Write to a fresh folder, then swap it in, so a failure halfway never
    # leaves a half-updated list.
    tmp = folder.with_name(folder.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name, raw in files.items():
        (tmp / name).write_bytes(raw)
    now = datetime.now(timezone.utc)
    (tmp / META).write_text(json.dumps({"updated": now.isoformat(),
                                        "source": LISTING_URL,
                                        "count": len(files)}), encoding="utf-8")
    shutil.rmtree(folder, ignore_errors=True)
    tmp.rename(folder)
    return UpdateResult(len(files), now, skipped)


def last_updated(folder: Path | None = None) -> datetime | None:
    """When the list was last downloaded, or None if it never was."""
    try:
        meta = json.loads(((folder or downloaded_dir()) / META).read_text(encoding="utf-8"))
        return datetime.fromisoformat(meta["updated"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
