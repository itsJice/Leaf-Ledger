"""The error log: what went wrong in the app, for whom, where and why.

Until this existed a crash left nothing behind. The crash catcher rendered a
blank screen and wrote to the person's own browser console, and server errors
scrolled out of Render's logs with no name attached. Every past incident
(stale tabs saving over newer data on 10/1, 10/8 and 11/1; "Couldn't save"
hiding a 401 or 403 in #51, #100 and #129; the 11/15 out-of-memory outage;
Nicole's blank schedule in Comment #39) was diagnosed by piecing the story
back together afterwards. This table is that story, written as it happens.

Who writes: every signed-in login, because everyone hits errors. MIN_ROLE is
crew, which the view-only iPad / TV login also meets (viewer ranks with crew),
and production is let in by name (``roles.PRODUCTION_WRITES``). The browser sends small batches; the server adds
its own 500s and slow requests through ``record_server_event`` (see
``app.libs.request_log``).

Who reads: super_admin only, like Claude's notes on the Comments tab.

Kept small on purpose, after 11/15 (docs/incidents/2026-11-15-out-of-memory-and-roles.md):

* One row per event; nothing is ever rebuilt from history.
* Reads are paged (at most 100 rows) and the summary is one GROUP BY over the
  last 7 days, capped at 50 groups.
* No request or response bodies, no whole schedule saves, nothing typed into a
  field. Text passes through ``app.libs.redact`` here as well as in the browser.
* A per-login rate limit, and rows older than ``RETENTION_DAYS`` are cleared
  at most once every few hours by whichever request happens along.

Storage follows the app's convention: an ``ll_app`` table created lazily on
first use; ``migrations/030_app_events.sql`` is the record.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth import AuthorizedUser
from app.libs import redact, roles
from app.libs.db import ensure_schema_once, get_conn

router = APIRouter(prefix="/app-events")

#: Every signed-in role may report; reading is checked per route (owner only).
MIN_ROLE = "crew"

RETENTION_DAYS = 90
MAX_BATCH = 20
MAX_MESSAGE_CHARS = 1000
MAX_DETAIL_BYTES = 8_000
MAX_TRAIL_STEPS = 20
MAX_TRAIL_BYTES = 8_000
#: Per login, per process: plenty for a bad afternoon, too few to flood.
RATE_LIMIT = 120
RATE_WINDOW_S = 600.0
CLEANUP_EVERY_S = 6 * 3600.0

#: What the browser may report. The server's own kinds come from request_log.
CLIENT_KINDS = {
    "crash",           # a page threw while drawing; the crash screen showed
    "error",           # a script error that didn't take the page down
    "request_failed",  # a call to our server failed, was refused, or timed out
    "stuck",           # a page still loading after 15 seconds
    "freeze",          # the page stopped responding for 5+ seconds
    "blank",           # loaded but showed nothing it should (the schedule's checks)
    "reload_after_deploy",  # an old tab reloaded itself to pick up a new version
    "previous_visit",  # the last visit in this tab ended badly before it could report
    # From inside the Install Schedule (scheduler/review_template.html):
    "save_blocked",    # a save refused or held back (older page, clashing client, kept changing)
    "save_conflict",   # merged with a newer save; some of this tab's changes were dropped
}
SERVER_KINDS = {"server_error", "slow_request"}
SOURCES = {"app", "schedule", "server"}

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.app_events (
    id           bigserial PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now(),
    occurred_at  timestamptz,
    kind         text NOT NULL,
    source       text NOT NULL DEFAULT 'app',
    user_sub     text,
    user_name    text,
    role         text,
    page         text,
    message      text,
    detail       jsonb,
    trail        jsonb,
    user_agent   text
);
CREATE INDEX IF NOT EXISTS app_events_created_idx ON ll_app.app_events (created_at DESC);
CREATE INDEX IF NOT EXISTS app_events_kind_idx ON ll_app.app_events (kind, created_at DESC);
"""


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("app_events", _ddl)


# ─── Rate limit and cleanup (per process; one Render instance) ──────────────

_recent: dict[str, deque] = defaultdict(deque)
_last_cleanup = 0.0


def _take(key: str, n: int, now: Optional[float] = None) -> int:
    """How many of ``n`` events ``key`` may still send in this window."""
    now = time.monotonic() if now is None else now
    q = _recent[key]
    while q and now - q[0] > RATE_WINDOW_S:
        q.popleft()
    room = max(0, RATE_LIMIT - len(q))
    take = min(n, room)
    q.extend([now] * take)
    return take


def reset_limits() -> None:
    """Tests: forget the rate limit and cleanup clock."""
    global _last_cleanup
    _recent.clear()
    _last_cleanup = 0.0


async def _maybe_cleanup(conn) -> None:
    global _last_cleanup
    now = time.monotonic()
    if _last_cleanup and now - _last_cleanup < CLEANUP_EVERY_S:
        return
    _last_cleanup = now
    try:
        await conn.execute(
            f"DELETE FROM ll_app.app_events WHERE created_at < now() - interval '{RETENTION_DAYS} days'"
        )
    except Exception:  # noqa: BLE001 - housekeeping never fails a report
        pass


# ─── Shaping what gets stored ───────────────────────────────────────────────

def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def clean_detail(detail: Any) -> Optional[dict]:
    if not isinstance(detail, dict) or not detail:
        return None
    cleaned = redact.scrub_tree(detail)
    if redact.json_size(cleaned) > MAX_DETAIL_BYTES:
        # Keep the small facts; the stack is what grows.
        stack = str(cleaned.pop("stack", "") or "")
        cleaned = {k: v for k, v in cleaned.items() if redact.json_size(v) < 1000}
        cleaned["stack"] = stack[:3000]
        cleaned["trimmed"] = True
    return cleaned


def clean_trail(trail: Any, max_steps: int = MAX_TRAIL_STEPS, max_bytes: int = MAX_TRAIL_BYTES) -> Optional[list]:
    """The newest ``max_steps`` steps that fit in ``max_bytes``, scrubbed."""
    if not isinstance(trail, list) or not trail:
        return None
    steps = [redact.scrub_tree(s) for s in trail[-max_steps:] if isinstance(s, dict)]
    while steps and redact.json_size(steps) > max_bytes:
        steps.pop(0)
    return steps or None


class EventIn(BaseModel):
    kind: str
    source: str = "app"
    page: Optional[str] = None
    message: Optional[str] = None
    detail: Optional[dict] = None
    trail: Optional[list] = None
    occurred_at: Optional[str] = None


class EventsIn(BaseModel):
    events: list[EventIn] = Field(default_factory=list)


class EventsOut(BaseModel):
    saved: int
    dropped: int = 0
    #: The new rows, so a comment sent soon after can point at them.
    ids: list[int] = Field(default_factory=list)


def _row_args(ev: EventIn, *, user_sub, user_name, role, user_agent) -> tuple:
    detail = clean_detail(ev.detail)
    trail = clean_trail(ev.trail)
    return (
        _parse_time(ev.occurred_at),
        ev.kind,
        ev.source if ev.source in SOURCES else "app",
        user_sub,
        user_name,
        role,
        redact.path_only(ev.page),
        redact.scrub(ev.message, MAX_MESSAGE_CHARS),
        json.dumps(detail) if detail else None,
        json.dumps(trail) if trail else None,
        (user_agent or "")[:400],
    )


INSERT_SQL = (
    "INSERT INTO ll_app.app_events "
    "(occurred_at, kind, source, user_sub, user_name, role, page, message, detail, trail, user_agent) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11) RETURNING id"
)


@router.post("", response_model=EventsOut)
async def report_events(body: EventsIn, request: Request, user: AuthorizedUser) -> EventsOut:
    """Save a small batch of browser-side events. Unknown kinds and anything
    past the batch size or rate limit are dropped, not refused, so a noisy
    tab never sees an error of its own from here."""
    wanted = [e for e in body.events[:MAX_BATCH] if e.kind in CLIENT_KINDS]
    take = _take(user.sub, len(wanted))
    keep = wanted[:take]
    dropped = len(body.events) - len(keep)
    if not keep:
        return EventsOut(saved=0, dropped=dropped)
    role = await roles.role_of(user)
    user_agent = request.headers.get("user-agent", "")
    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error log unavailable") from exc
    ids: list[int] = []
    try:
        await ensure_schema(conn)
        for ev in keep:
            new_id = await conn.fetchval(INSERT_SQL, *_row_args(
                ev, user_sub=user.sub, user_name=user.display_name, role=role, user_agent=user_agent,
            ))
            if isinstance(new_id, int):
                ids.append(new_id)
        await _maybe_cleanup(conn)
    finally:
        await conn.close()
    return EventsOut(saved=len(keep), dropped=dropped, ids=ids)


async def record_server_event(*, kind: str, page: str, message: str, detail: dict,
                              user_sub: Optional[str] = None, user_name: Optional[str] = None,
                              role: Optional[str] = None) -> None:
    """The server's own entry (a 500 or a slow request). Fire and forget:
    any failure here is swallowed, so logging can never break a request."""
    if kind not in SERVER_KINDS:
        return
    if not _take("server", 1):
        return
    try:
        conn = await get_conn()
    except Exception:  # noqa: BLE001
        return
    try:
        await ensure_schema(conn)
        ev = EventIn(kind=kind, source="server", page=page, message=message, detail=detail)
        await conn.fetchval(INSERT_SQL, *_row_args(
            ev, user_sub=user_sub, user_name=user_name, role=role, user_agent=None,
        ))
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            await conn.close()
        except Exception:  # noqa: BLE001
            pass


# ─── Reading (owner only) ───────────────────────────────────────────────────

async def _require_owner(user) -> None:
    if await roles.role_of(user) != "super_admin":
        raise HTTPException(status_code=403, detail="Only the owner can read the error log")


class EventRow(BaseModel):
    id: int
    created_at: str
    occurred_at: Optional[str] = None
    kind: str
    source: str
    user_name: Optional[str] = None
    role: Optional[str] = None
    page: Optional[str] = None
    message: Optional[str] = None
    detail: Optional[dict] = None
    trail: Optional[list] = None
    user_agent: Optional[str] = None


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def _json(v) -> Any:
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:  # noqa: BLE001
        return None


def to_row(r) -> EventRow:
    return EventRow(
        id=r["id"], created_at=_iso(r["created_at"]), occurred_at=_iso(r.get("occurred_at")),
        kind=r["kind"], source=r["source"], user_name=r.get("user_name"), role=r.get("role"),
        page=r.get("page"), message=r.get("message"), detail=_json(r.get("detail")),
        trail=_json(r.get("trail")), user_agent=r.get("user_agent"),
    )


ROW_COLUMNS = ("id, created_at, occurred_at, kind, source, user_name, role, page, message, "
               "detail, trail, user_agent")


@router.get("", response_model=list[EventRow])
async def list_events(
    user: AuthorizedUser,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[int] = None,
    kind: Optional[str] = None,
    person: Optional[str] = None,
    message: Optional[str] = None,
    ids: Optional[str] = None,
) -> Any:
    """Newest first, one page at a time (``before_id`` = the last id shown).
    ``ids`` (comma-separated) fetches specific events, e.g. the ones a
    comment's trail points at."""
    await _require_owner(user)
    where, args = [], []
    if ids:
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()][:50]
        if not wanted:
            return []
        args.append(wanted)
        where.append(f"id = ANY(${len(args)}::bigint[])")
    if before_id:
        args.append(before_id)
        where.append(f"id < ${len(args)}")
    if kind:
        args.append(kind)
        where.append(f"kind = ${len(args)}")
    if person:
        args.append(person)
        where.append(f"user_name = ${len(args)}")
    if message:
        args.append(message)
        where.append(f"message = ${len(args)}")
    args.append(limit)
    sql = (f"SELECT {ROW_COLUMNS} FROM ll_app.app_events "
           + (("WHERE " + " AND ".join(where) + " ") if where else "")
           + f"ORDER BY id DESC LIMIT ${len(args)}")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(sql, *args)
    finally:
        await conn.close()
    return [to_row(r) for r in rows]


class EventGroup(BaseModel):
    kind: str
    message: Optional[str] = None
    count: int
    people: list[str] = Field(default_factory=list)
    pages: list[str] = Field(default_factory=list)
    first_at: str
    last_at: str


@router.get("/summary", response_model=list[EventGroup])
async def summarize_events(user: AuthorizedUser, days: int = Query(7, ge=1, le=90)) -> Any:
    """The same error from many people or many times, as one line each."""
    await _require_owner(user)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(
            "SELECT kind, message, count(*) AS count, "
            "array_agg(DISTINCT user_name) FILTER (WHERE user_name IS NOT NULL) AS people, "
            "array_agg(DISTINCT page) FILTER (WHERE page IS NOT NULL AND page <> '') AS pages, "
            "min(created_at) AS first_at, max(created_at) AS last_at "
            "FROM ll_app.app_events WHERE created_at > now() - make_interval(days => $1) "
            "GROUP BY kind, message ORDER BY max(created_at) DESC LIMIT 50",
            days,
        )
    finally:
        await conn.close()
    return [
        EventGroup(kind=r["kind"], message=r["message"], count=r["count"],
                   people=list(r["people"] or [])[:10], pages=list(r["pages"] or [])[:10],
                   first_at=_iso(r["first_at"]), last_at=_iso(r["last_at"]))
        for r in rows
    ]
