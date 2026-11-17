"""Note the server's own failures in the error log: 500s and slow requests.

A plain ASGI middleware (not ``BaseHTTPMiddleware``, which wraps every
response in a stream and has been known to misbehave with file responses).
It times each ``/api`` request and, only when something is wrong, hands a
small summary to ``app.apis.app_events.record_server_event`` as a background
task. The request itself is never slowed or changed, and if the log write
fails nobody notices.

Why slow requests too: on 11/15 the site ran out of memory because single
requests loaded the whole schedule history. Those requests never finished, so
they never showed up as errors -- only as unusually slow ones before the
crash. A slow request is the early warning.

What is recorded: method, route template (``/api/clients/{client_id}``, so no
ids or names), status, milliseconds, the exception's type and message
(scrubbed), and who -- from the role the auth check already worked out and
the verified token. Never headers, query strings or bodies.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from typing import Any, Optional

from app.libs import redact

SLOW_MS = 5_000
#: Calls that are slow by nature, or that would log about the log.
SKIP_PREFIXES = ("/api/app-events", "/api/scraper", "/api/install-calendar/feed")

_tasks: set = set()


def _who(scope) -> tuple[Optional[str], Optional[str], Optional[str]]:
    role = None
    try:
        role = (scope.get("state") or {}).get("ll_role")
    except Exception:  # noqa: BLE001
        pass
    sub = name = None
    try:
        from app.auth.supabase_auth import verify_token

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth.lower().startswith("bearer "):
            user = verify_token(auth[7:].strip())
            if user:
                sub = user.sub
                name = (user.email or "").split("@")[0] or None
    except Exception:  # noqa: BLE001
        pass
    return sub, name, role


def _route(scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None) or scope.get("path", "")
    if path and not path.startswith("/api"):
        path = "/api" + path
    return redact.path_only(path)


def _record(scope, *, kind: str, status: int, ms: int, exc: Optional[BaseException]) -> None:
    try:
        from app.apis.app_events import record_server_event

        sub, name, role = _who(scope)
        route = _route(scope)
        method = scope.get("method", "")
        detail: dict[str, Any] = {"method": method, "route": route, "status": status, "ms": ms}
        if exc is not None:
            detail["error_type"] = type(exc).__name__
            detail["stack"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:]
        if kind == "server_error":
            message = f"{method} {route} failed ({status})" + (f": {type(exc).__name__}: {exc}" if exc else "")
        else:
            message = f"{method} {route} took {ms / 1000:.1f}s"
        task = asyncio.get_running_loop().create_task(record_server_event(
            kind=kind, page=route, message=redact.scrub(message, 500), detail=detail,
            user_sub=sub, user_name=name, role=role,
        ))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    except Exception:  # noqa: BLE001
        pass


class RequestLogMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope.get("type") == "http" else ""
        if not path.startswith("/api/") or path.startswith(SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        status_holder = {"status": 0}

        async def _send(message):
            if message.get("type") == "http.response.start":
                status_holder["status"] = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except BaseException as exc:
            ms = int((time.monotonic() - started) * 1000)
            if isinstance(exc, Exception):
                _record(scope, kind="server_error", status=500, ms=ms, exc=exc)
            raise
        ms = int((time.monotonic() - started) * 1000)
        status = status_holder["status"]
        if status >= 500:
            _record(scope, kind="server_error", status=status, ms=ms, exc=None)
        elif ms >= SLOW_MS:
            _record(scope, kind="slow_request", status=status, ms=ms, exc=None)
