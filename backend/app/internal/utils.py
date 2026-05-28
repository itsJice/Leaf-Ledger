import os
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now() -> datetime:
    """Return current time in UTC."""
    return datetime.now(tz=timezone.utc)


def compute_signature(txt: str) -> str:
    """Compute hash of text."""
    return hashlib.sha256(txt.encode()).digest().hex()


def compute_spec_signature(obj: Dict[str, Any]) -> str:
    """Compute hash of json-serialization of object."""
    return compute_signature(json.dumps(obj, sort_keys=True))


def debug_enabled() -> bool:
    return os.environ.get("ENABLE_DEBUG_PRINTS") == "1"


def debug(*args, **kwargs):
    """Internal debugging utility, not for user apps."""
    if debug_enabled():
        print(*args, **kwargs)
