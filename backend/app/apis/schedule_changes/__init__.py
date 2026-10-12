"""Install Schedule "Changes": a readable list of what changed on the board,
with a per-user "follow" and "last seen" (Comment #19, user 2026-10-12).

The words come from app.libs.schedule_changes, which diffs consecutive saved
states. It reads the whole season: every save in
``ll_app.install_schedule_history`` across every schedule build (saves are no
longer trimmed), plus older states recovered from backups into
``ll_app.install_schedule_history_archive`` by
``scripts/backfill_schedule_history.py`` -- so the list runs from the first
plan onward. This router adds the people: who saved each change (a display
name, never an email), and for each signed-in user whether they follow the
list and when they last looked, kept server-side so the NEW markers follow
them between devices.

Who may use it:

* staff, admin, super_admin: read, follow, mark seen.
* production (view-only office login): the same. Following and "seen" are
  its own bookkeeping, like its theme preference, so the two writes are in
  roles.PRODUCTION_WRITES; nothing here changes the schedule.
* viewer (the warehouse TV): may read (VIEWER_READ), never write, so it has
  no follow state.
* lead and crew: refused. The feed covers every crew-day and client on the
  board, and a field login should only see the days it works. Filtering
  every event by the lead's days is possible but easy to get subtly wrong
  (a move OFF their day names where the client went), so the safer rule
  ships first: office roles only.

Saves made by a local dev server against the live database (writer
``local-dev-user``) are hidden unless a super admin asks for them (``tests=1``).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.apis.install_schedule import caller_role
from app.apis.user_context import get_request_user_id
from app.libs import schedule_board
from app.libs import schedule_changes as sc
from app.libs.db import ensure_schema_once, get_conn
from app.libs.jsonutil import loads_json

router = APIRouter(prefix="/schedule-changes", tags=["schedule-changes"])

MIN_ROLE = "staff"
VIEWER_READ = True

MAX_LIMIT = 200

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.schedule_change_follows (
    user_id      text PRIMARY KEY,
    following    boolean NOT NULL DEFAULT true,
    last_seen_at timestamptz,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
-- Older saved states recovered from backups (scripts/backfill_schedule_history.py),
-- kept apart from the real history table, which the backfill never writes.
-- kind 'plan' is a spreadsheet build of the schedule (placement, planClients,
-- planDays); 'save' is a saved state of the board.
CREATE TABLE IF NOT EXISTS ll_app.install_schedule_history_archive (
    id          bigserial PRIMARY KEY,
    kind        text NOT NULL DEFAULT 'save',
    version     text,
    season      text NOT NULL,
    state       jsonb NOT NULL,
    updated_by  text,
    created_at  timestamptz NOT NULL,
    source      text NOT NULL,
    source_ref  text,
    dedupe_key  text NOT NULL UNIQUE,
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS install_schedule_history_archive_season_idx
    ON ll_app.install_schedule_history_archive (season, created_at);
"""


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("schedule_change_follows", _ddl)


#: A saved state, lightened for the feed: the roster (100 KB a save) shrinks
#: to the id and name fields, the moves log to row + name (it names rows of
#: builds whose page is gone), and the tool's other bookkeeping is dropped.
LIGHT_STATE = """
       (state - 'roster' - 'comments' - 'moves' - 'notInstallingNames'
              - 'notInstallingDates' - 'holdNames' - 'dateMoves')
       || jsonb_build_object(
            'roster', COALESCE((
              SELECT jsonb_agg(jsonb_build_object(
                       'id', p->'id', 'name', p->'name', 'first', p->'first',
                       'last', p->'last', 'title', p->'title'))
                FROM jsonb_array_elements(
                       CASE WHEN jsonb_typeof(state->'roster') = 'array'
                            THEN state->'roster' ELSE '[]'::jsonb END) p
            ), '[]'::jsonb),
            'moves', COALESCE((
              SELECT jsonb_agg(jsonb_build_object('row', m->'row', 'name', m->'name'))
                FROM jsonb_array_elements(
                       CASE WHEN jsonb_typeof(state->'moves') = 'array'
                            THEN state->'moves' ELSE '[]'::jsonb END) m
            ), '[]'::jsonb),
            'newClients', COALESCE((
              SELECT jsonb_agg(jsonb_build_object('row', c->'row', 'name', c->'name'))
                FROM jsonb_array_elements(
                       CASE WHEN jsonb_typeof(state->'newClients') = 'array'
                            THEN state->'newClients' ELSE '[]'::jsonb END) c
            ), '[]'::jsonb)
          ) AS state"""

#: Every save of the season across every build, after history id $2. Rows
#: saved before the season column existed have none; they count when their
#: build has rows that do.
HISTORY_SQL = f"""
SELECT id, version, updated_by, created_at, {LIGHT_STATE}
  FROM ll_app.install_schedule_history
 WHERE id > $2
   AND (season = $1 OR (season IS NULL AND version IN (
         SELECT version FROM ll_app.install_schedule_history WHERE season = $1)))
 ORDER BY created_at ASC, id ASC
"""

ARCHIVE_SQL = f"""
SELECT id, kind, version, updated_by, created_at, source, {LIGHT_STATE}
  FROM ll_app.install_schedule_history_archive
 WHERE season = $1
 ORDER BY created_at ASC, id ASC
"""

#: Per season: the snapshots read so far, the names they carry and the events
#: computed from them. A new save only diffs itself against the one before it;
#: the archive changing (a backfill) or a new build rebuilds everything.
_cache: dict[str, dict] = {}


def clear_cache() -> None:
    _cache.clear()


async def writer_names(conn, writers: set[str], board: Optional[schedule_board.Board]) -> dict[str, str]:
    """Login ids -> display names. Emails are looked up to find the roster
    name and never leave this function."""
    ids = sorted(w for w in writers if sc.is_login_id(w))
    if not ids:
        return {}
    try:
        rows = await conn.fetch(
            "SELECT id::text AS id, email, raw_user_meta_data->>'full_name' AS full_name "
            "FROM auth.users WHERE id::text = ANY($1::text[])",
            ids,
        )
    except Exception as exc:  # noqa: BLE001 - the app's DB role may not see auth.users
        print(f"schedule-changes: auth.users not readable: {exc}")
        rows = []
    out = {}
    for r in rows:
        person = board.person_for_email(r["email"] or "") if board else None
        out[r["id"]] = sc.login_display_name(r["email"], r["full_name"], person["name"] if person else None)
    for w in ids:
        out.setdefault(w, "Office")
    return out


def context_for(board: schedule_board.Board) -> sc.Context:
    return sc.Context(
        clients={r: str(c.get("name") or "") for r, c in board.clients.items() if c.get("name")},
        base_days=board.base_days,
        people={p["id"]: p["name"] for p in board.roster},
    )


def merge_snapshots(history: list[dict], archive: list[dict]) -> list[dict]:
    """History and backfilled rows as one chronological list. A backfilled
    save duplicating a history row (same build, same moment) is dropped: the
    history row is the record."""
    seen = {(h.get("version"), h["created_at"]) for h in history}
    out = [{**h, "key": f"h{h['id']}", "kind": "save", "from_backup": False} for h in history]
    for a in archive:
        kind = a.get("kind") or "save"
        if kind != "plan" and (a.get("version"), a["created_at"]) in seen:
            continue
        out.append({**a, "kind": kind, "key": f"a{a['id']}", "from_backup": True})
    # At the same instant: plans first, then backfilled rows, then history.
    out.sort(key=lambda r: (r["created_at"], r["kind"] != "plan", r["key"][0] != "a", r["key"]))
    return out


def _row_of(r) -> dict:
    d = dict(r)
    d["state"] = loads_json(d["state"]) or {}
    return d


def _add_names(ctx: sc.Context, rows: list[dict]) -> None:
    for r in rows:
        c, p = sc.names_from_state(r["state"])
        for k, v in c.items():
            ctx.clients.setdefault(k, v)
        for k, v in p.items():
            ctx.people.setdefault(k, v)


async def load_events(conn, board: schedule_board.Board) -> list[dict]:
    """Every change of the board's season, newest first (see sc.build_feed)."""
    season = board.season
    hist_max = await conn.fetchval("SELECT max(id) FROM ll_app.install_schedule_history") or 0
    try:
        arch_max = await conn.fetchval("SELECT max(id) FROM ll_app.install_schedule_history_archive") or 0
    except Exception:  # noqa: BLE001 - not created yet
        arch_max = 0
    hit = _cache.get(season)
    if hit and hit["arch_max"] == arch_max and hit["version"] == board.version:
        if hit["hist_max"] == hist_max:
            return hit["events"]
        new = merge_snapshots([_row_of(r) for r in await conn.fetch(HISTORY_SQL, season, hit["hist_max"])], [])
        last = hit["rows"][-1] if hit["rows"] else None
        if not new:
            hit["hist_max"] = hist_max
            return hit["events"]
        if last and new[0]["created_at"] >= last["created_at"]:
            hit["names"].update(await writer_names(
                conn, {r["updated_by"] or "" for r in new} - set(hit["names"]), board))
            _add_names(hit["ctx"], new)
            fresh = sc.build_feed([last, *new], hit["ctx"], hit["names"], current_version=board.version)
            hit.update(rows=hit["rows"] + new, events=fresh + hit["events"], hist_max=hist_max)
            return hit["events"]
    history = [_row_of(r) for r in await conn.fetch(HISTORY_SQL, season, 0)]
    try:
        archive = [_row_of(r) for r in await conn.fetch(ARCHIVE_SQL, season)]
    except Exception as exc:  # noqa: BLE001 - archive not created yet
        print(f"schedule-changes: archive not readable: {exc}")
        archive = []
    rows = merge_snapshots(history, archive)
    names = await writer_names(conn, {r["updated_by"] or "" for r in rows}, board)
    ctx = context_for(board)
    _add_names(ctx, rows)
    events = sc.build_feed(rows, ctx, names, current_version=board.version)
    _cache[season] = {"rows": rows, "events": events, "names": names, "ctx": ctx,
                      "hist_max": hist_max, "arch_max": arch_max, "version": board.version}
    return events


async def follow_row(conn, user_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT following, last_seen_at FROM ll_app.schedule_change_follows WHERE user_id = $1",
        user_id,
    )
    return {
        "following": bool(row and row["following"]),
        "lastSeenAt": row["last_seen_at"] if row else None,
    }


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat() if isinstance(d, datetime) else None


def _clean_day(v: Optional[str], label: str) -> Optional[str]:
    if not v:
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Bad {label} date") from exc


def _clean_types(raw: Optional[str]) -> Optional[set[str]]:
    if not raw:
        return None
    want = {t.strip() for t in raw.split(",") if t.strip()}
    bad = want - set(sc.TYPES)
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown change type: {', '.join(sorted(bad))}")
    return want


def public(ev: dict) -> dict:
    """What the page gets: no raw writer ids."""
    return {k: v for k, v in ev.items() if k != "writer"}


def visible(events: list[dict], show_tests: bool) -> list[dict]:
    """Local-dev test saves are hidden unless asked for (super admin only)."""
    return events if show_tests else [e for e in events if not e.get("test")]


async def _board() -> Optional[schedule_board.Board]:
    try:
        return await schedule_board.load_board()
    except Exception as exc:  # noqa: BLE001
        print(f"schedule-changes: board not readable: {exc}")
        return None


@router.get("")
async def list_changes(
    request: Request,
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    before: Optional[str] = None,
    q: str = "",
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    type: Optional[str] = None,  # noqa: A002 - the query parameter's name
    tests: bool = False,
    role: str = Depends(caller_role),
) -> dict:
    """One page of changes, newest first, plus this user's follow state.

    ``from``/``to`` are Central-time days (inclusive) the change was MADE;
    ``type`` is a comma list of TYPES; ``q`` searches client names and the
    line itself; ``before`` is the last event id of the previous page;
    ``tests`` shows local-dev test saves (super admin only, else ignored).
    """
    s, e = _clean_day(start, "from"), _clean_day(end, "to")
    types = _clean_types(type)
    show_tests = bool(tests) and role == "super_admin"
    me = get_request_user_id(request)
    board = await _board()
    if not board:
        return {"events": [], "next": None, "total": 0, "following": False,
                "lastSeenAt": None, "unseen": 0, "season": None, "canShowTests": role == "super_admin"}
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        events = await load_events(conn, board)
        follow = await follow_row(conn, me)
    finally:
        await conn.close()
    real = visible(events, False)
    shown = [ev for ev in visible(events, show_tests) if sc.matches(ev, q, s, e, types)]
    chunk, nxt = sc.page(shown, limit=limit, before=before)
    seen = follow["lastSeenAt"] if follow["following"] else None
    cut = seen if seen is None or seen.tzinfo else seen.replace(tzinfo=timezone.utc)
    return {
        "events": [
            {**public(ev),
             "isNew": bool(cut and not ev.get("test") and datetime.fromisoformat(ev["at"]) > cut
                           and ev["writer"] != me),
             "mine": ev["writer"] == me}
            for ev in chunk
        ],
        "next": nxt,
        "total": len(shown),
        "following": follow["following"],
        "lastSeenAt": _iso(follow["lastSeenAt"]),
        "unseen": sc.unseen_count(real, seen, me),
        "newest": real[0]["at"] if real else None,
        "season": board.season,
        "types": list(sc.TYPES),
        "canShowTests": role == "super_admin",
        "showingTests": show_tests,
    }


@router.get("/status")
async def change_status(request: Request) -> dict:
    """For the menu badge: is this user following, and how many are new."""
    me = get_request_user_id(request)
    board = await _board()
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        follow = await follow_row(conn, me)
        if not follow["following"] or not board:
            return {"following": follow["following"], "unseen": 0, "lastSeenAt": _iso(follow["lastSeenAt"])}
        events = await load_events(conn, board)
    finally:
        await conn.close()
    return {
        "following": True,
        "unseen": sc.unseen_count(visible(events, False), follow["lastSeenAt"], me),
        "lastSeenAt": _iso(follow["lastSeenAt"]),
    }


class FollowIn(BaseModel):
    following: bool


@router.put("/follow")
async def set_follow(body: FollowIn, request: Request) -> dict:
    """Start or stop following. Starting fresh counts everything up to now
    as seen, so a new follower isn't handed the whole season as NEW."""
    me = get_request_user_id(request)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "INSERT INTO ll_app.schedule_change_follows (user_id, following, last_seen_at) "
            "VALUES ($1, $2, CASE WHEN $2 THEN now() END) "
            "ON CONFLICT (user_id) DO UPDATE SET following = EXCLUDED.following, "
            "  last_seen_at = COALESCE(ll_app.schedule_change_follows.last_seen_at, EXCLUDED.last_seen_at), "
            "  updated_at = now() "
            "RETURNING following, last_seen_at",
            me, body.following,
        )
    finally:
        await conn.close()
    return {"following": row["following"], "lastSeenAt": _iso(row["last_seen_at"]), "unseen": 0}


class SeenIn(BaseModel):
    #: Mark changes up to this moment as seen (the newest the page showed),
    #: so a change saved while the page was open stays NEW. Default: now.
    upTo: Optional[datetime] = None


@router.post("/seen")
async def mark_seen(body: SeenIn, request: Request) -> dict:
    me = get_request_user_id(request)
    up_to = body.upTo
    if up_to is not None and up_to.tzinfo is None:
        up_to = up_to.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if up_to is None or up_to > now:
        up_to = now
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        # Never moves backwards: an older tab closing late can't bring back
        # NEW markers someone already cleared.
        row = await conn.fetchrow(
            "INSERT INTO ll_app.schedule_change_follows (user_id, following, last_seen_at) "
            "VALUES ($1, false, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "  last_seen_at = GREATEST(ll_app.schedule_change_follows.last_seen_at, EXCLUDED.last_seen_at), "
            "  updated_at = now() "
            "RETURNING following, last_seen_at",
            me, up_to,
        )
    finally:
        await conn.close()
    return {"following": row["following"], "lastSeenAt": _iso(row["last_seen_at"])}
