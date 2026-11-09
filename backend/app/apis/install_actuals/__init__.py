"""Install Times: how long each install and takedown really took.

One row per stop visit in ``ll_app.install_actuals`` (migrations/028), with
history: a correction inserts a new row pointing at the one it replaces
(``supersedes_id``), and ``ll_app.install_actuals_latest`` is the newest row
of each visit. Filling in blanks on your own open entry (the Leave after
the Arrive) completes that row in place: it changes nothing already saved. The rules (typed-time parsing, the midnight rollover, report
rollups) are pure functions in ``app.libs.install_times``.

Stops come from the live board (``app.libs.schedule_board.load_board``), so
joint crews, added stops and moved stops are exactly what staff see. A visit
is keyed by (season, kind, day id, board row). A joint shift (two crew-days
on one date with the same stops, staffed as one) is ONE visit, keyed by its
first crew-day id. A stop split between two crews with different routes is
two visits, one per crew, each with half the estimate.

Who may do what:

* **staff, admin, super_admin**: see and enter/correct every stop; reports
  and per-client history.
* **lead**: only crew-days they lead or are staffed on (the board's
  staffing, the same roster match as ``app.apis.lead``); no reports.
* **crew, viewer, production**: no access at all (``MIN_ROLE`` refuses crew
  and viewer; production's allowlist in ``app.libs.roles`` doesn't list
  these routes). The safest choice: nobody outside the office and the leads
  needs on-site times, and refusing is simpler to reason about than a
  read-only view.

No pay data is read or returned here.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import AuthorizedUser
from app.libs import install_times as T
from app.libs import roles, schedule_board
from app.libs.db import ensure_schema_once, get_conn

router = APIRouter(prefix="/install-times", tags=["install-times"])

#: Leads and up. Leads are narrowed to their own crew-days in every handler.
MIN_ROLE = "lead"

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.install_actuals (
    id                bigserial PRIMARY KEY,
    client_id         integer,
    client_name       text NOT NULL,
    client_row        integer,
    season            text NOT NULL,
    kind              text NOT NULL CHECK (kind IN ('install', 'takedown')),
    date              date NOT NULL,
    day_id            text,
    crew_label        text,
    crew_lead         text,
    arrive_at         timestamptz,
    depart_at         timestamptz,
    people_count      integer CHECK (people_count IS NULL OR people_count BETWEEN 0 AND 40),
    photos_done       boolean,
    scope_note        text,
    est_hours_at_time numeric(6, 2),
    job_type          text CHECK (job_type IS NULL OR job_type IN ('residential', 'commercial', 'restaurant')),
    night             boolean NOT NULL DEFAULT false,
    source            text NOT NULL CHECK (source IN ('office', 'lead', 'claude', 'imported_sheet', 'comment_parsed')),
    entered_by        text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    supersedes_id     bigint REFERENCES ll_app.install_actuals (id),
    CHECK (arrive_at IS NULL OR depart_at IS NULL OR depart_at >= arrive_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS install_actuals_one_successor
    ON ll_app.install_actuals (supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS install_actuals_day_idx ON ll_app.install_actuals (season, day_id);
CREATE INDEX IF NOT EXISTS install_actuals_client_idx ON ll_app.install_actuals (client_id);

CREATE OR REPLACE VIEW ll_app.install_actuals_latest AS
    SELECT a.*
      FROM ll_app.install_actuals a
     WHERE NOT EXISTS (SELECT 1 FROM ll_app.install_actuals b WHERE b.supersedes_id = a.id);
"""


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("install_actuals", _ddl)


def now_ct() -> datetime:
    """Module-level so tests can pin "now"."""
    return datetime.now(T.TZ)


# ─── access ──────────────────────────────────────────────────────────────────


class Viewer(BaseModel):
    email: str
    role: str
    person: Optional[dict] = None

    @property
    def office(self) -> bool:
        return roles.at_least(self.role, "staff")


async def _board() -> schedule_board.Board:
    board = await schedule_board.load_board()
    if not board:
        raise HTTPException(status_code=404, detail="No install schedule has been published yet")
    return board


async def _viewer(user, board: schedule_board.Board) -> Viewer:
    role = await roles.resolve_role(user.email)
    return Viewer(email=roles.norm_email(user.email), role=role,
                  person=board.person_for_email(user.email or ""))


def _require_office(viewer: Viewer) -> None:
    if not viewer.office:
        raise HTTPException(status_code=403, detail="Only office staff can open this")


def visit_day_id(board: schedule_board.Board, day_id: str) -> str:
    """A joint shift's crew-days are one visit, keyed by the first id."""
    group = board.joint_groups().get(day_id)
    return group[0] if group else day_id


def may_enter(viewer: Viewer, board: schedule_board.Board, day_id: str) -> bool:
    """Office: any crew-day. Lead: one they lead or are staffed on (any
    crew-day of a joint shift counts for the whole shift)."""
    if day_id not in board.days:
        return False
    if viewer.office:
        return True
    if viewer.role != "lead" or not viewer.person:
        return False
    pid = viewer.person["id"]
    ids = board.joint_groups().get(day_id) or [day_id]
    return any(pid in board.staffing.get(i, []) for i in ids)


def default_date(dates: list[str], now: datetime) -> Optional[str]:
    """Today, or last night before noon: the newest crew-day date on or
    before today (yesterday before 12 PM, when the office types last night's
    sheet). Else the soonest coming date."""
    if not dates:
        return None
    today = now.date()
    cutoff = (today - timedelta(days=1)) if now.hour < 12 else today
    past = [d for d in dates if d <= cutoff.isoformat()]
    if now.hour < 12 and today.isoformat() in dates and not past:
        return today.isoformat()
    return past[-1] if past else dates[0]


# ─── board → visits ──────────────────────────────────────────────────────────


def _est_for(board: schedule_board.Board, day_id: str, row: int) -> Optional[float]:
    """This crew's share of the schedule's estimate: half on a stop split
    with another crew (the board's ``half`` rows), else the whole thing."""
    h = (board.clients.get(row) or {}).get("h26")
    try:
        h = float(h) if h is not None else None
    except (TypeError, ValueError):
        return None
    if h is None:
        return None
    half = (board.day_meta.get(day_id) or {}).get("half") or []
    return round(h / 2, 2) if row in half else round(h, 2)


def crew_groups(board: schedule_board.Board, on: str, viewer: Viewer) -> list[dict]:
    """The crew-days of one date this viewer may enter, in board order: one
    entry per visit-day (joint shifts merged), each with its stops."""
    groups = board.joint_groups()
    out = []
    days = sorted((d for d in board.days.values() if d["date"] == on and d["stops"]
                   and d.get("crew") != "Training"), key=lambda d: board.crew_label(d))
    seen = set()
    for d in days:
        vid = visit_day_id(board, d["id"])
        if vid in seen or not may_enter(viewer, board, d["id"]):
            continue
        seen.add(vid)
        ids = groups.get(d["id"]) or [d["id"]]
        members = [board.days[i] for i in ids]
        if len(members) > 1:
            nums = [board.crew_label(m).replace("Crew ", "") for m in members]
            label = "Crews " + " + ".join(sorted(nums, key=lambda x: (len(x), x)))
            names = [n for n in (board.crew_name(m) for m in members) if n]
            if names:
                label = f"{names[0]} ({label})"
        else:
            label = board.crew_title(d)
        lead = None
        for i in ids:
            lead = lead or board.lead_of(i)
        staffed = list(dict.fromkeys(p for i in ids for p in board.staffing.get(i, [])))
        out.append({
            "dayId": vid,
            "dayIds": ids,
            "date": on,
            "label": label,
            "lead": lead["name"] if lead else None,
            "night": board.is_dallas_night(d),
            "kind": T.kind_for_date(on, board.season),
            "headcount": len(staffed) or None,
            "stops": [{
                "row": r,
                "name": (board.clients.get(r) or {}).get("name") or f"Row {r}",
                "city": (board.clients.get(r) or {}).get("city") or "",
                "estHours": _est_for(board, d["id"], r),
                "jobType": T.job_type_of(board.clients.get(r) or {}),
            } for r in d["stops"]],
        })
    return out


def visible_dates(board: schedule_board.Board, viewer: Viewer) -> list[str]:
    return sorted({d["date"] for d in board.days.values()
                   if d["stops"] and d.get("crew") != "Training" and may_enter(viewer, board, d["id"])})


# ─── rows ────────────────────────────────────────────────────────────────────


def _iso(v):
    return v.isoformat() if isinstance(v, (datetime, date)) else v


def _num(v) -> Optional[float]:
    return None if v is None else float(v)


def actual_out(r, corrections: int = 0) -> dict:
    arrive, depart = r["arrive_at"], r["depart_at"]
    return {
        "id": r["id"],
        "clientId": r["client_id"],
        "clientName": r["client_name"],
        "row": r["client_row"],
        "season": r["season"],
        "kind": r["kind"],
        "date": _iso(r["date"]),
        "dayId": r["day_id"],
        "crewLabel": r["crew_label"],
        "crewLead": r["crew_lead"],
        "arriveAt": _iso(arrive),
        "departAt": _iso(depart),
        "arrive": T.fmt_clock(T.clock_of(arrive)),
        "depart": T.fmt_clock(T.clock_of(depart)),
        "actualHours": T.on_site_hours(arrive, depart),
        "peopleCount": r["people_count"],
        "photosDone": r["photos_done"],
        "scopeNote": r["scope_note"] or "",
        "estHours": _num(r["est_hours_at_time"]),
        "jobType": r["job_type"],
        "night": bool(r["night"]),
        "source": r["source"],
        "enteredBy": r["entered_by"],
        "createdAt": _iso(r["created_at"]),
        "supersedesId": r["supersedes_id"],
        "corrections": corrections,
    }


async def _client_ids(conn, names: list[str]) -> dict[str, int]:
    """Board stop name -> clients.id, matched like the lead pages do (sheet
    spelling, then the app's name, then former names). Best effort."""
    from app.apis.lead import index_client_extras, norm_name

    if not names:
        return {}
    rows = await conn.fetch("SELECT id, name, sheet_name, former_names FROM clients")
    idx = index_client_extras([dict(r) for r in rows])
    out = {}
    for n in names:
        hit = idx.get(norm_name(n))
        if hit:
            out[n] = hit["id"]
    return out


# ─── read ────────────────────────────────────────────────────────────────────


@router.get("/day")
async def day_view(user: AuthorizedUser, on: Optional[str] = Query(None, alias="date")) -> dict:
    """One date's stops, grouped by crew in board order, each with its latest
    actual. Leads get only their own crew-days."""
    board = await _board()
    viewer = await _viewer(user, board)
    dates = visible_dates(board, viewer)
    if on is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", on):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    pick = on or default_date(dates, now_ct())
    crews = crew_groups(board, pick, viewer) if pick else []
    ids = [c["dayId"] for c in crews]
    latest: dict = {}
    if ids:
        conn = await get_conn()
        try:
            await ensure_schema(conn)
            rows = await conn.fetch(
                "SELECT l.*, (SELECT count(*) FROM ll_app.install_actuals x WHERE x.season = l.season "
                "AND x.day_id = l.day_id AND x.client_row = l.client_row AND x.kind = l.kind) - 1 AS corrections "
                "FROM ll_app.install_actuals_latest l WHERE l.season = $1 AND l.day_id = ANY($2::text[])",
                board.season, ids)
            for r in rows:
                latest[(r["day_id"], r["client_row"], r["kind"])] = actual_out(r, int(r["corrections"] or 0))
        finally:
            await conn.close()
    for c in crews:
        for s in c["stops"]:
            s["actual"] = latest.get((c["dayId"], s["row"], c["kind"]))
    missing_days = await _missing_days(board, viewer) if viewer.office else None
    return {
        "season": board.season,
        "date": pick,
        "today": now_ct().date().isoformat(),
        "dates": dates,
        "role": viewer.role,
        "office": viewer.office,
        "me": viewer.person,
        "crews": crews,
        "missingDays": missing_days,
    }


def missing_by_day(board: schedule_board.Board, viewer: Viewer, done: set, today: str) -> list[dict]:
    """Install days up to today with stops still missing Arrive or Leave,
    oldest first: ``[{"date", "missing", "stops"}]``. ``done`` holds the
    (dayId, row, kind) visits that have both times."""
    out = []
    for on in visible_dates(board, viewer):
        if on > today:
            break
        stops = [(c["dayId"], s["row"], c["kind"]) for c in crew_groups(board, on, viewer) for s in c["stops"]]
        missing = sum(1 for k in stops if k not in done)
        if missing:
            out.append({"date": on, "missing": missing, "stops": len(stops)})
    return out


async def _missing_days(board: schedule_board.Board, viewer: Viewer) -> list[dict]:
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(
            "SELECT day_id, client_row, kind FROM ll_app.install_actuals_latest WHERE season = $1 "
            "AND arrive_at IS NOT NULL AND depart_at IS NOT NULL", board.season)
    finally:
        await conn.close()
    done = {(r["day_id"], r["client_row"], r["kind"]) for r in rows}
    return missing_by_day(board, viewer, done, now_ct().date().isoformat())


@router.get("/visit")
async def visit_history(user: AuthorizedUser, dayId: str, row: int,
                        kind: Optional[Literal["install", "takedown"]] = None) -> dict:
    """Every saved version of one visit, newest first: who typed what, when."""
    board = await _board()
    viewer = await _viewer(user, board)
    if not may_enter(viewer, board, dayId):
        raise HTTPException(status_code=404, detail="That crew-day isn't one of yours")
    vid = visit_day_id(board, dayId)
    k = kind or T.kind_for_date(board.days[dayId]["date"], board.season)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(
            "SELECT * FROM ll_app.install_actuals WHERE season = $1 AND day_id = $2 AND client_row = $3 "
            "AND kind = $4 ORDER BY id DESC", board.season, vid, row, k)
    finally:
        await conn.close()
    return {"versions": [actual_out(r) for r in rows]}


# ─── write ───────────────────────────────────────────────────────────────────


class ActualIn(BaseModel):
    dayId: str
    row: int
    kind: Optional[Literal["install", "takedown"]] = None
    arrive: str = Field("", max_length=20)
    depart: str = Field("", max_length=20)
    peopleCount: Optional[int] = Field(None, ge=0, le=T.PEOPLE_MAX)
    photosDone: Optional[bool] = None
    scopeNote: str = Field("", max_length=T.NOTE_MAX)
    #: The latest row id the page was showing (None for a first entry). If
    #: someone saved since, the write is refused with the current row.
    supersedesId: Optional[int] = None
    #: Office only: "claude" when Claude enters times from a crew sheet.
    source: Optional[Literal["office", "claude"]] = None


@router.post("/actuals")
async def save_actual(body: ActualIn, user: AuthorizedUser) -> dict:
    """Enter or correct one visit. A correction inserts a new row pointing
    at the one it replaces, so nothing typed is ever lost. Filling in the
    blanks of your own open entry (Leave after Arrive, ticking photos)
    completes that row instead (``install_times.fills_in_only``)."""
    board = await _board()
    viewer = await _viewer(user, board)
    if not may_enter(viewer, board, body.dayId):
        raise HTTPException(status_code=404, detail="That crew-day isn't one of yours")
    day = board.days[body.dayId]
    if body.row not in day["stops"]:
        raise HTTPException(status_code=404, detail="That stop isn't on this crew-day")
    if day["date"] > now_ct().date().isoformat():
        raise HTTPException(status_code=409, detail="That crew-day hasn't happened yet")
    night = board.is_dallas_night(day)
    try:
        entry = T.build_entry(day["date"], body.arrive, body.depart, night=night)
    except T.TimeParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    vid = visit_day_id(board, body.dayId)
    kind = body.kind or T.kind_for_date(day["date"], board.season)
    group = next((g for g in crew_groups(board, day["date"], viewer) if g["dayId"] == vid), None)
    client = board.clients.get(body.row) or {}
    name = client.get("name") or f"Row {body.row}"
    source = "lead" if not viewer.office else (body.source or "office")

    conn = await get_conn()
    try:
        await ensure_schema(conn)
        cid = (await _client_ids(conn, [name])).get(name)
        async with conn.transaction():
            # One writer per visit at a time: the check-then-insert below
            # must not interleave with another save of the same stop.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))",
                               f"install_actuals|{board.season}|{kind}|{vid}|{body.row}")
            current = await conn.fetchrow(
                "SELECT * FROM ll_app.install_actuals_latest WHERE season = $1 AND day_id = $2 "
                "AND client_row = $3 AND kind = $4", board.season, vid, body.row, kind)
            if (current["id"] if current else None) != body.supersedesId:
                raise HTTPException(status_code=409, detail={
                    "message": "Someone else just saved this stop. Here is what they entered.",
                    "current": actual_out(current) if current else None,
                })
            if T.fills_in_only(dict(current) if current else None, entry, people=body.peopleCount,
                               photos=body.photosDone, note=body.scopeNote, email=viewer.email,
                               now=now_ct()):
                # Filling in the blanks of one's own open entry (Leave after
                # Arrive, ticking photos): the same version, completed in place.
                row = await conn.fetchrow(
                    "UPDATE ll_app.install_actuals SET arrive_at = $2, depart_at = $3, people_count = $4, "
                    "photos_done = $5, scope_note = $6 WHERE id = $1 RETURNING *",
                    current["id"], entry.arrive_at, entry.depart_at, body.peopleCount, body.photosDone,
                    body.scopeNote.strip() or None)
            else:
                row = await conn.fetchrow(
                    "INSERT INTO ll_app.install_actuals (client_id, client_name, client_row, season, kind, date, "
                    "day_id, crew_label, crew_lead, arrive_at, depart_at, people_count, photos_done, scope_note, "
                    "est_hours_at_time, job_type, night, source, entered_by, supersedes_id) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20) RETURNING *",
                    cid, name, body.row, board.season, kind, date.fromisoformat(day["date"]), vid,
                    group["label"] if group else board.crew_title(day),
                    group["lead"] if group else None,
                    entry.arrive_at, entry.depart_at, body.peopleCount, body.photosDone,
                    body.scopeNote.strip() or None,
                    _est_for(board, body.dayId, body.row),
                    T.job_type_of(client), night, source, viewer.email, body.supersedesId)
            corrections = 0
            if body.supersedesId:
                corrections = int(await conn.fetchval(
                    "SELECT count(*) FROM ll_app.install_actuals WHERE season = $1 AND day_id = $2 "
                    "AND client_row = $3 AND kind = $4", board.season, vid, body.row, kind) or 1) - 1
    finally:
        await conn.close()
    return {"actual": actual_out(row, corrections), "warnings": entry.warnings}


# ─── office only: history and reports ────────────────────────────────────────


@router.get("/client/{client_id}")
async def client_history(client_id: int, user: AuthorizedUser) -> dict:
    """A client's latest actuals for every season (the client card strip)."""
    board = await _board()
    viewer = await _viewer(user, board)
    _require_office(viewer)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(
            "SELECT * FROM ll_app.install_actuals_latest WHERE client_id = $1 ORDER BY date, id", client_id)
    finally:
        await conn.close()
    visits = [actual_out(r) for r in rows]
    seasons: dict = {}
    for v in visits:
        s = seasons.setdefault(v["season"], {"season": v["season"], "install": [], "takedown": []})
        s[v["kind"]].append(v)

    def total(vs, key):
        xs = [v[key] for v in vs]
        return round(sum(xs), 2) if xs and all(x is not None for x in xs) else None

    out = []
    for s in sorted(seasons.values(), key=lambda x: x["season"]):
        for k in ("install", "takedown"):
            vs = s[k]
            if vs:
                act, est = total(vs, "actualHours"), total(vs, "estHours")
                out.append({"season": s["season"], "kind": k, "visits": len(vs),
                            "actualHours": act, "estHours": est, **T.difference(est, act)})
    return {"clientId": client_id, "summary": out, "visits": visits}


@router.get("/reports")
async def reports(user: AuthorizedUser, season: Optional[str] = None) -> dict:
    """Estimate vs actual per stop for one season, rolled up by crew lead
    and job type, plus every client's install hours year over year."""
    board = await _board()
    viewer = await _viewer(user, board)
    _require_office(viewer)
    if season is not None and not re.fullmatch(r"\d{4}", season):
        raise HTTPException(status_code=400, detail="season must be a year")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = [actual_out(r) for r in await conn.fetch(
            "SELECT * FROM ll_app.install_actuals_latest ORDER BY date, crew_label, id")]
    finally:
        await conn.close()
    seasons = sorted({r["season"] for r in rows} | {board.season})
    pick = season or board.season
    picked = [r for r in rows if r["season"] == pick]
    for r in picked:
        r.update(T.difference(r["estHours"], r["actualHours"]))
    summary = T.summarize(picked)
    by_client = T.summarize(rows)["byClient"]
    return {"season": pick, "seasons": seasons, "rows": picked,
            "byLead": summary["byLead"], "byType": summary["byType"], "byClient": by_client}
