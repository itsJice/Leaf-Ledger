"""Shared JSON helpers.

``loads_json`` is ``app.apis.preferences._loads`` copied verbatim. The copy in
``install_schedule`` behaves identically (only its docstring differs). The copy
in ``designs`` catches ``Exception`` rather than ``ValueError``, so it returns
``None`` where this one raises -- e.g. ``RecursionError`` on a pathologically
deeply nested JSON string. Do not switch ``designs`` to this without deciding
that difference is acceptable.
"""

from __future__ import annotations

import json
from typing import Any


def loads_json(raw: Any) -> Any:
    """json.loads that returns None instead of raising. asyncpg may hand back
    either a decoded object or the raw jsonb text depending on codecs."""
    if raw is None or isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
