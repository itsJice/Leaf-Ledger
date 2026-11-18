"""Strip secrets and customer details out of text before it is logged.

Used by the error log (`app.apis.app_events`) and the "last minute" trail
attached to comments (`app.apis.feedback`). The browser already strips what it
can; this is the server's second pass, so a slip on one side is caught on the
other.

What goes:

* Everything after ``?`` or ``#`` in a page address or URL. The calendar feed
  (``feed.ics?token=``), the password-reset link (``#access_token=``) and
  client pages (``/clients?client=Allums,...``, Comment #23) all carry a
  secret or a client's name there.
* Sign-in tokens (JWTs: ``eyJ...``), ``Bearer ...`` values, and
  ``token=`` / ``password=`` / ``secret=`` / ``api_key=`` style pairs.
* Share-link tokens in a path (``/api/share/<token>/...``).
* Any other long unbroken run of letters and digits (40+), the shape of a key.

Nothing here raises: logging must never break the thing it is logging.
"""
from __future__ import annotations

import json
import re
from typing import Any

MASK = "[hidden]"

_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_PAIR = re.compile(
    r"(?i)\b(access_token|refresh_token|token_hash|token|password|passwd|secret|api[_-]?key|apikey)"
    r"(\s*[=:]\s*)(\"?)[^\s\"&,;]+"
)
_SHARE_PATH = re.compile(r"(/(?:api/)?share/)[^/\s?#]+")
_LONG = re.compile(r"\b[A-Za-z0-9_-]{40,}\b")
_URL = re.compile(r"(https?://[^\s?#\"']+|(?<![\w/])/[\w\-./{}%]*)[?#][^\s\"']*")


def path_only(value: Any, limit: int = 300) -> str:
    """A page address with no query string or hash, capped at ``limit``."""
    try:
        text = str(value or "")
        for sep in ("?", "#"):
            text = text.split(sep, 1)[0]
        return scrub(text)[:limit]
    except Exception:  # noqa: BLE001
        return ""


def scrub(value: Any, limit: int | None = None) -> str:
    """Text with secrets masked (see the module docstring)."""
    try:
        text = str(value if value is not None else "")
        text = _URL.sub(lambda m: m.group(1), text)
        text = _JWT.sub(MASK, text)
        text = _BEARER.sub("Bearer " + MASK, text)
        text = _PAIR.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{MASK}", text)
        text = _SHARE_PATH.sub(lambda m: m.group(1) + MASK, text)
        text = _LONG.sub(MASK, text)
        return text[:limit] if limit else text
    except Exception:  # noqa: BLE001
        return ""


#: Keys whose values are dropped outright, whatever they hold.
_SECRET_KEYS = re.compile(
    r"(?i)^(authorization|cookie|set-cookie|token|access_token|refresh_token|password|secret|"
    r"api_?key|apikey|body|payload|value|headers)$"
)


def scrub_tree(value: Any, depth: int = 0) -> Any:
    """``scrub`` applied to every string in a JSON-like value. Keys that name a
    secret or a request body lose their value entirely."""
    try:
        if depth > 6:
            return None
        if isinstance(value, dict):
            out = {}
            for k, v in list(value.items())[:60]:
                key = str(k)[:60]
                out[key] = MASK if _SECRET_KEYS.match(key) else scrub_tree(v, depth + 1)
            return out
        if isinstance(value, (list, tuple)):
            return [scrub_tree(v, depth + 1) for v in list(value)[:60]]
        if isinstance(value, str):
            return scrub(value, 4000)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return scrub(value, 500)
    except Exception:  # noqa: BLE001
        return None


def json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, default=str))
    except Exception:  # noqa: BLE001
        return 10**9
