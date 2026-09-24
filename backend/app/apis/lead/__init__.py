"""Lead pages: a crew lead's own shifts, time tracking, and property notes.

A lead signs in and sees only the crew-days they are staffed on as Lead in the
install schedule tool (roster + staffing, resolved by app.libs.schedule_board)
-- never another crew's day, and never the full client list. Office staff and
admins see every crew-day, so they can check what leads recorded.

Two app-owned tables, created on first use like every other ll_app table:

* ``shift_time_entries`` -- one row per person per stop: when they started and
  stopped working that property. A person can only be on the clock at one
  stop at a time; starting them somewhere new closes the old entry.
* ``shift_notes`` -- what happened at a property, or something new the client
  asked for. Each note is also written to the client's activity feed
  (client_activity, kind='comment') when the stop matches a saved client by
  name, so it shows on the Clients tab and carries into next season. The
  note row here is kept either way, so nothing a lead types is lost to a
  name mismatch.

Stops are identified by (day id, client row) -- the same keys the schedule
tool uses. Both are checked against the live board on every write.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Literal, Optional
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auth import AuthorizedUser
from app.libs import roles, schedule_board
from app.libs.db import ensure_schema_once, get_conn

router = APIRouter(prefix="/lead", tags=["lead"])

#: Leads and everyone above them (app.libs.roles). Crew logins cannot call it.
MIN_ROLE = "lead"

#: Shift dates are Texas dates; "today" must be too, not the server's UTC.
TZ = ZoneInfo("America/Chicago")

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.shift_time_entries (
    id          bigserial PRIMARY KEY,
    season      text NOT NULL,
    day_id      text NOT NULL,
    client_row  integer NOT NULL,
    client_name text,
    person_id   text NOT NULL,
    person_name text,
    started_at  timestamptz NOT NULL,
    ended_at    timestamptz,
    recorded_by text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE INDEX IF NOT EXISTS shift_time_entries_day_idx
    ON ll_app.shift_time_entries (season, day_id);
-- One running clock per person: they can't be at two properties at once.
CREATE UNIQUE INDEX IF NOT EXISTS shift_time_entries_one_open
    ON ll_app.shift_time_entries (season, person_id) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS ll_app.shift_notes (
    id          bigserial PRIMARY KEY,
    season      text NOT NULL,
    day_id      text NOT NULL,
    client_row  integer NOT NULL,
    client_name text,
    client_id   integer,
    activity_id bigint,
    kind        text NOT NULL CHECK (kind IN ('note', 'client_request')),
    text        text NOT NULL,
    author      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS shift_notes_day_idx ON ll_app.shift_notes (season, day_id);
"""

NOTE_LABEL = {"note": "Crew note", "client_request": "Client request"}


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("lead_shifts", _ddl)


def today() -> str:
    return datetime.now(TZ).date().isoformat()


def maps_url(c: dict) -> str:
    """Google Maps directions to the stop, from wherever the phone is."""
    addr = ", ".join(x for x in (c.get("street"), c.get("city"), " ".join(
        x for x in (c.get("st"), c.get("zip")) if x)) if x)
    if addr:
        return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(addr)}"
    if c.get("lat") is not None and c.get("lon") is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={c['lat']},{c['lon']}"
    return ""


# ─── access ──────────────────────────────────────────────────────────────────


class Viewer(BaseModel):
    email: str
    role: str
    person: Optional[dict] = None

    @property
    def supervisor(self) -> bool:
        """Office staff and up see and correct every crew-day."""
        return roles.at_least(self.role, "staff")


async def _viewer(user: AuthorizedUser, board: Optional[schedule_board.Board]) -> Viewer:
    role = await roles.resolve_role(user.email)
    person = board.person_for_email(user.email or "") if board else None
    return Viewer(email=roles.norm_email(user.email), role=role, person=person)


async def _board() -> schedule_board.Board:
    board = await schedule_board.load_board()
    if not board:
        raise HTTPException(status_code=404, detail="No install schedule has been published yet")
    return board


def _can_see(viewer: Viewer, board: schedule_board.Board, day_id: str) -> bool:
    if day_id not in board.days:
        return False
    if viewer.supervisor:
        return True
    lead = board.lead_of(day_id)
    return bool(lead and viewer.person and lead["id"] == viewer.person["id"])


def _require_stop(viewer: Viewer, board: schedule_board.Board, day_id: str, row: int) -> dict:
    """The day, if this viewer may act on it and the stop is really on it."""
    if not _can_see(viewer, board, day_id):
        # 404, not 403: a lead has no business learning which day ids exist.
        raise HTTPException(status_code=404, detail="That shift isn't one of yours")
    day = board.days[day_id]
    if row not in day["stops"]:
        raise HTTPException(status_code=404, detail="That property isn't on this shift")
    return day


def _require_today(viewer: Viewer, day: dict) -> None:
    """Leads record and fix time on the day itself; the office can fix any day."""
    if not viewer.supervisor and day["date"] != today():
        raise HTTPException(
            status_code=409,
            detail="Time can only be recorded or changed on the day of the shift. Ask the office to fix older entries.",
        )


# ─── read ────────────────────────────────────────────────────────────────────


def _iso(v):
    return v.isoformat() if isinstance(v, (datetime, date)) else v


def _entry_out(r) -> dict:
    return {
        "id": r["id"], "dayId": r["day_id"], "row": r["client_row"],
        "personId": r["person_id"], "personName": r["person_name"],
        "startedAt": _iso(r["started_at"]), "endedAt": _iso(r["ended_at"]),
        "recordedBy": r["recorded_by"],
    }


def _note_out(r) -> dict:
    return {
        "id": r["id"], "dayId": r["day_id"], "row": r["client_row"],
        "kind": r["kind"], "text": r["text"], "author": r["author"],
        "savedToClient": r["activity_id"] is not None,
        "createdAt": _iso(r["created_at"]),
    }


def _day_out(board: schedule_board.Board, day: dict, entries: list, notes: list) -> dict:
    lead = board.lead_of(day["id"])
    crew = [board.person(pid) for pid in board.staffing.get(day["id"], [])]
    stops = []
    for row in day["stops"]:
        c = board.clients.get(row) or {}
        stops.append({
            "row": row,
            "name": c.get("name") or f"Row {row}",
            "street": c.get("street") or "",
            "city": c.get("city") or "",
            "st": c.get("st") or "",
            "zip": c.get("zip") or "",
            "phone": c.get("phone") or "",
            "mapsUrl": maps_url(c),
            "advice": c.get("advice") or "",
            "repairNotes": c.get("repairNotes") or "",
            "hours": c.get("h26"),
            "people": c.get("people"),
            "timeEntries": [e for e in entries if e["row"] == row],
            "notes": [n for n in notes if n["row"] == row],
        })
    return {
        "id": day["id"],
        "date": day["date"],
        "crewLabel": board.crew_label(day),
        "note": board.day_notes.get(day["id"], ""),
        "lead": lead,
        "crew": [p for p in crew if p],
        "stops": stops,
    }


@router.get("/shifts")
async def my_shifts(user: AuthorizedUser, person_id: Optional[str] = None) -> dict:
    """Crew-days for the signed-in lead, with stops, time and notes.

    Office staff and admins see everyone's days, or one lead's with
    ``person_id`` -- that is how the office reviews what a lead recorded.
    """
    board = await _board()
    viewer = await _viewer(user, board)

    if viewer.supervisor:
        if person_id:
            days = board.days_led_by(person_id)
        else:
            days = sorted(board.days.values(), key=lambda d: (d["date"], board.crew_label(d)))
    elif viewer.person:
        days = board.days_led_by(viewer.person["id"])
    else:
        days = []

    ids = [d["id"] for d in days]
    entries, notes = [], []
    if ids:
        conn = await get_conn()
        try:
            await ensure_schema(conn)
            entries = [_entry_out(r) for r in await conn.fetch(
                "SELECT * FROM ll_app.shift_time_entries WHERE season = $1 AND day_id = ANY($2::text[]) "
                "ORDER BY started_at", board.season, ids)]
            notes = [_note_out(r) for r in await conn.fetch(
                "SELECT * FROM ll_app.shift_notes WHERE season = $1 AND day_id = ANY($2::text[]) "
                "ORDER BY created_at", board.season, ids)]
        finally:
            await conn.close()

    by_day_e: dict[str, list] = {}
    for e in entries:
        by_day_e.setdefault(e["dayId"], []).append(e)
    by_day_n: dict[str, list] = {}
    for n in notes:
        by_day_n.setdefault(n["dayId"], []).append(n)

    leads = []
    if viewer.supervisor:
        seen = {}
        for did in board.days:
            lead = board.lead_of(did)
            if lead:
                seen[lead["id"]] = lead
        leads = sorted(seen.values(), key=lambda p: p["name"])

    return {
        "season": board.season,
        "today": today(),
        "role": viewer.role,
        "supervisor": viewer.supervisor,
        "me": viewer.person,
        "leads": leads,
        "days": [_day_out(board, d, by_day_e.get(d["id"], []), by_day_n.get(d["id"], [])) for d in days],
    }


# ─── time ────────────────────────────────────────────────────────────────────


class ClockIn(BaseModel):
    dayId: str
    row: int
    personIds: list[str] = Field(min_length=1, max_length=40)


def _people_on_day(board: schedule_board.Board, day_id: str, ids: list[str]) -> list[dict]:
    staffed = set(board.staffing.get(day_id, []))
    out = []
    for pid in dict.fromkeys(ids):
        if pid not in staffed:
            raise HTTPException(status_code=400, detail="Someone in that list isn't on this crew")
        out.append(board.person(pid))
    return out


@router.post("/time/start")
async def start_time(body: ClockIn, user: AuthorizedUser) -> dict:
    board = await _board()
    viewer = await _viewer(user, board)
    day = _require_stop(viewer, board, body.dayId, body.row)
    _require_today(viewer, day)
    people = _people_on_day(board, body.dayId, body.personIds)
    name = (board.clients.get(body.row) or {}).get("name")
    now = datetime.now(timezone.utc)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        async with conn.transaction():
            for p in people:
                # Already running here: leave it. Running elsewhere: they've
                # moved on, so that stop's clock ends now.
                running_here = await conn.fetchval(
                    "SELECT id FROM ll_app.shift_time_entries WHERE season = $1 AND person_id = $2 "
                    "AND ended_at IS NULL AND day_id = $3 AND client_row = $4",
                    board.season, p["id"], body.dayId, body.row)
                if running_here:
                    continue
                await conn.execute(
                    "UPDATE ll_app.shift_time_entries SET ended_at = $3, updated_at = now() "
                    "WHERE season = $1 AND person_id = $2 AND ended_at IS NULL",
                    board.season, p["id"], now)
                await conn.execute(
                    "INSERT INTO ll_app.shift_time_entries (season, day_id, client_row, client_name, "
                    "person_id, person_name, started_at, recorded_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    board.season, body.dayId, body.row, name, p["id"], p["name"], now, viewer.email)
    finally:
        await conn.close()
    return {"ok": True}


@router.post("/time/stop")
async def stop_time(body: ClockIn, user: AuthorizedUser) -> dict:
    board = await _board()
    viewer = await _viewer(user, board)
    day = _require_stop(viewer, board, body.dayId, body.row)
    _require_today(viewer, day)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await conn.execute(
            "UPDATE ll_app.shift_time_entries SET ended_at = now(), updated_at = now() "
            "WHERE season = $1 AND day_id = $2 AND client_row = $3 "
            "AND person_id = ANY($4::text[]) AND ended_at IS NULL",
            board.season, body.dayId, body.row, list(dict.fromkeys(body.personIds)))
    finally:
        await conn.close()
    return {"ok": True}


class EntryEdit(BaseModel):
    startedAt: Optional[datetime] = None
    endedAt: Optional[datetime] = None
    clearEnd: bool = False


async def _entry_for_edit(conn, board, viewer, entry_id: int):
    row = await conn.fetchrow(
        "SELECT * FROM ll_app.shift_time_entries WHERE id = $1 AND season = $2", entry_id, board.season)
    if not row or not _can_see(viewer, board, row["day_id"]):
        raise HTTPException(status_code=404, detail="No such time entry")
    _require_today(viewer, board.days[row["day_id"]])
    return row


@router.patch("/time/{entry_id}")
async def edit_time(entry_id: int, body: EntryEdit, user: AuthorizedUser) -> dict:
    board = await _board()
    viewer = await _viewer(user, board)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await _entry_for_edit(conn, board, viewer, entry_id)
        start = body.startedAt or row["started_at"]
        end = None if body.clearEnd else (body.endedAt or row["ended_at"])
        if end is not None and end < start:
            raise HTTPException(status_code=400, detail="Stop time is before start time")
        await conn.execute(
            "UPDATE ll_app.shift_time_entries SET started_at = $2, ended_at = $3, "
            "recorded_by = $4, updated_at = now() WHERE id = $1",
            entry_id, start, end, viewer.email)
    finally:
        await conn.close()
    return {"ok": True}


@router.delete("/time/{entry_id}")
async def delete_time(entry_id: int, user: AuthorizedUser) -> dict:
    board = await _board()
    viewer = await _viewer(user, board)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await _entry_for_edit(conn, board, viewer, entry_id)
        await conn.execute("DELETE FROM ll_app.shift_time_entries WHERE id = $1", entry_id)
    finally:
        await conn.close()
    return {"deleted": True}


# ─── notes ───────────────────────────────────────────────────────────────────


class NoteIn(BaseModel):
    dayId: str
    row: int
    kind: Literal["note", "client_request"] = "note"
    text: str


@router.post("/notes")
async def add_note(body: NoteIn, user: AuthorizedUser) -> dict:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Write something first")
    if len(text) > 2000:
        raise HTTPException(status_code=413, detail="That note is too long")
    board = await _board()
    viewer = await _viewer(user, board)
    day = _require_stop(viewer, board, body.dayId, body.row)
    name = (board.clients.get(body.row) or {}).get("name") or ""

    conn = await get_conn()
    try:
        await ensure_schema(conn)
        async with conn.transaction():
            client_id = await conn.fetchval(
                "SELECT id FROM clients WHERE lower(btrim(name)) = lower(btrim($1)) LIMIT 1", name
            ) if name else None
            activity_id = None
            if client_id:
                now = datetime.utcnow()
                activity_id = await conn.fetchval(
                    "INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at) "
                    "VALUES ($1, 'comment', $2, $3, $4, NULL) RETURNING id",
                    client_id, now.isoformat(), f"{NOTE_LABEL[body.kind]} ({day['date']}): {text}",
                    json.dumps({"author": viewer.email, "tag": body.kind, "source": "lead",
                                "day_id": body.dayId, "season": board.season}),
                )
            row = await conn.fetchrow(
                "INSERT INTO ll_app.shift_notes (season, day_id, client_row, client_name, client_id, "
                "activity_id, kind, text, author) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *",
                board.season, body.dayId, body.row, name, client_id, activity_id,
                body.kind, text, viewer.email)
    finally:
        await conn.close()
    return _note_out(row)


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int, user: AuthorizedUser) -> dict:
    """The author can take back their own note; the office can remove any."""
    board = await _board()
    viewer = await _viewer(user, board)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "SELECT * FROM ll_app.shift_notes WHERE id = $1 AND season = $2", note_id, board.season)
        if not row or not _can_see(viewer, board, row["day_id"]):
            raise HTTPException(status_code=404, detail="No such note")
        if not viewer.supervisor and roles.norm_email(row["author"]) != viewer.email:
            raise HTTPException(status_code=403, detail="Only the person who wrote a note can delete it")
        async with conn.transaction():
            if row["activity_id"]:
                await conn.execute(
                    "DELETE FROM client_activity WHERE id = $1 AND kind = 'comment'", row["activity_id"])
            await conn.execute("DELETE FROM ll_app.shift_notes WHERE id = $1", note_id)
    finally:
        await conn.close()
    return {"deleted": True}
