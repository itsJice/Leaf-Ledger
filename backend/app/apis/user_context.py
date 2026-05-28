import base64
import json
from typing import Optional

from fastapi import Request


LOCAL_USER_ID = "local-dev-user"


def extract_user_id(request: Request) -> Optional[str]:
    """Read the user id from a Bearer JWT if the browser supplied one."""
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        parts = auth[7:].split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub") or payload.get("user_id")
    except Exception:
        return None


def get_request_user_id(request: Request) -> str:
    return extract_user_id(request) or LOCAL_USER_ID
