"""A client's Google Drive links (migrations/026): the client's folder, and
optionally the photos folder inside it.

They live on the client record, not on a season: the folder is the same
year after year. Only https://drive.google.com/ links are accepted, so the
card's button can never open something else, and a blank value clears the
link (the card then offers "Add folder" instead of a broken link).

Shared by PUT /api/clients/{id}/drive-links and
scripts/import_drive_folders.py, so both accept exactly the same values.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

#: (column, label) for each link, in the order the card shows them.
DRIVE_LINK_COLUMNS = ("drive_folder_url", "drive_photos_url")
LABELS = {"drive_folder_url": "Drive folder", "drive_photos_url": "Photos folder"}

DRIVE_HOST = "drive.google.com"
MAX_URL_CHARS = 2000


class DriveLinkError(ValueError):
    """A value that isn't a Google Drive link. The message says why."""


def clean_drive_url(value: Optional[str], label: str = "Drive link") -> Optional[str]:
    """The trimmed link, None for a blank one (clears it).

    Raises DriveLinkError unless it is an https://drive.google.com/ URL with
    a path -- a pasted link with stray spaces or a trailing newline is fine,
    a docs.google.com, http:// or look-alike host is not.
    """
    text = (value or "").strip()
    if not text:
        return None
    if len(text) > MAX_URL_CHARS:
        raise DriveLinkError(f"{label} is too long to be a Drive link")
    if any(c.isspace() for c in text):
        raise DriveLinkError(f"{label} has spaces in it -- paste just the link")
    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise DriveLinkError(f"{label} isn't a link") from exc
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or host != DRIVE_HOST or parts.username or parts.password or parts.port:
        raise DriveLinkError(f"{label} must start with https://drive.google.com/")
    if parts.path in ("", "/"):
        raise DriveLinkError(f"{label} needs the folder's own link, not just drive.google.com")
    return text
