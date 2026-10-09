"""Download the latest fellowship list from Galley's public GitHub repository.

Galley ships with a copy of the list. "Check for Updates" fetches the current
files from fellowships/ in the public repository (the source code itself is
kept in a private one), checks every one, and keeps them in the user's
settings folder. Only the list is downloaded; nothing about the user is sent.

Downloaded entries are merged over the bundled ones by id, so an older
download never hides entries added in a newer version of the app.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

from .. import updates
from ..updates import META, REPO, UpdateResult  # noqa: F401  (re-exported)
from .model import Fellowship

LISTING_URL = updates.listing_url("fellowships")


def downloaded_dir() -> Path:
    from ..checks.offline.submission import user_profile_dir
    return user_profile_dir().parent / "fellowship-list"


def fetch_updates(folder: Path | None = None, opener=urlopen) -> UpdateResult:
    """Download and check the current list. Raises OSError when GitHub can't
    be reached, and ValueError when nothing usable came back; the previous
    download, if any, is left untouched in both cases."""
    return updates.fetch_list(LISTING_URL, folder or downloaded_dir(),
                              Fellowship.from_dict, opener)


def last_updated(folder: Path | None = None) -> datetime | None:
    """When the list was last downloaded, or None if it never was."""
    return updates.last_updated(folder or downloaded_dir())
