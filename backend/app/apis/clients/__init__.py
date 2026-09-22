"""Saved clients — team-wide, stored in Postgres.

Clients used to live in a single JSON document on local disk. That lost data two
ways: concurrent edits overwrote each other (the whole list was rewritten on
every change), and a hosted restart wiped the disk. They now live in the
`clients` table (see migrations/003_clients_table.sql), shared by the whole team,
with one row per client and a unique index on the normalised name.
"""

from datetime import date, datetime
import json
from typing import Any, List, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.libs import client_season
from app.libs.db import get_conn, has_item_status_column

router = APIRouter(prefix="/clients", tags=["clients"])

ADDRESS_FIELDS = ("street", "city", "state", "zip")

#: The columns every client read returns. One list, so the SELECT here, the
#: RETURNING on create/update and the response model cannot drift apart.
CLIENT_COLUMNS = (
    "id, name, email, phone, notes, street, city, state, zip, time_preference, "
    "secondary_contacts, created_at, updated_at"
)


async def load_saved_clients(conn) -> List[dict]:
    rows = await conn.fetch(f"SELECT {CLIENT_COLUMNS} FROM clients")
    out = []
    for r in rows:
        data = dict(r)
        sc = data.get("secondary_contacts")
        data["secondary_contacts"] = json.loads(sc) if isinstance(sc, str) else (sc or [])
        out.append(data)
    return out


async def load_activity_by_client(conn) -> dict:
    """Every client's activity feed (Christmas install history today), one
    query -- grouped in Python rather than a SQL json_agg so a NULL detail
    or an odd jsonb decode doesn't need its own SQL-side special case."""
    rows = await conn.fetch(
        "SELECT client_id, id, kind, season, summary, detail, occurred_at, created_at "
        "FROM client_activity ORDER BY occurred_at DESC NULLS LAST, season DESC"
    )
    by_client: dict = {}
    for r in rows:
        detail = r["detail"]
        if isinstance(detail, str):
            detail = json.loads(detail)
        by_client.setdefault(r["client_id"], []).append({
            "id": r["id"], "kind": r["kind"], "season": r["season"],
            "summary": r["summary"], "detail": detail,
            "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
            "created_at": r["created_at"],
        })
    return by_client


class SecondaryContact(BaseModel):
    label: str = ""       # free text: "Debbie's cell", "Wife", "Assistant"
    phone: Optional[str] = None
    email: Optional[str] = None


class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    #: "morning" | "afternoon" | "late" | None -- see migrations/015.
    time_preference: Optional[str] = None
    secondary_contacts: Optional[List[SecondaryContact]] = None


class ClientUpdate(BaseModel):
    """Same shape as ClientCreate -- every field optional-to-change, name
    included (fixing a typo in a saved client's name is a normal edit).
    Deliberately does NOT touch christmas_synced_snapshot/christmas_synced_at
    -- those belong to sync_clients.py alone; a human editing a field here
    is exactly the case that snapshot exists to protect from being
    silently overwritten by the next sync.

    secondary_contacts is whole-array-replace, not a per-contact patch --
    there's no id to patch against (a label is free text, not a stable
    key), and the edit UI always has the full current list in hand
    already, so sending it back whole is simpler than diffing it."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    #: "" clears it (same NULLIF convention as the other fields).
    time_preference: Optional[str] = None
    secondary_contacts: Optional[List[SecondaryContact]] = None


def clean_time_preference(value: Optional[str]) -> Optional[str]:
    """None -> leave alone; "" -> clear; anything else must be a known value."""
    if value is None:
        return None
    v = value.strip().lower()
    if v == "":
        return ""
    if v not in client_season.TIME_PREFERENCES:
        raise HTTPException(
            status_code=400,
            detail=f"time_preference must be one of {', '.join(client_season.TIME_PREFERENCES)}",
        )
    return v


class ActivityOut(BaseModel):
    id: int
    kind: str
    season: str
    summary: str
    detail: Optional[Any] = None
    occurred_at: Optional[str] = None
    created_at: Optional[datetime] = None


class ClientOut(BaseModel):
    id: Optional[int] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    time_preference: Optional[str] = None
    secondary_contacts: List[SecondaryContact] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    project_count: int = 0
    bucket_count: int = 0
    selected_cost: float = 0.0
    last_project_at: Optional[datetime] = None
    source: str = "saved"
    activity: List[ActivityOut] = []


def clean_name(name: Optional[str]) -> str:
    return (name or "").strip()


async def build_client_list(conn) -> List[dict]:
    """Saved clients plus rollups from every project the team has."""
    saved_clients = await load_saved_clients(conn)
    activity_by_client = await load_activity_by_client(conn)
    status_expression = (
        "CASE WHEN ci.status = 'selected' THEN ci.quantity * p.current_price ELSE 0 END"
        if await has_item_status_column(conn)
        else "ci.quantity * p.current_price"
    )
    # No created_by filter: projects are team-owned, so a client's rollup counts
    # every project for that client regardless of who created it.
    project_stats = await conn.fetch(f"""
        SELECT
            COALESCE(NULLIF(TRIM(a.client_name), ''), 'Unassigned') AS name,
            COUNT(DISTINCT a.id)::int AS project_count,
            COUNT(DISTINCT ac.id)::int AS bucket_count,
            COALESCE(SUM({status_expression}), 0)::float AS selected_cost,
            MAX(a.updated_at) AS last_project_at
        FROM arrangements a
        LEFT JOIN arrangement_containers ac ON ac.arrangement_id = a.id
        LEFT JOIN container_items ci ON ci.container_id = ac.id
        LEFT JOIN products p ON p.id = ci.product_id
        GROUP BY COALESCE(NULLIF(TRIM(a.client_name), ''), 'Unassigned')
    """)

    stats_by_name = {row["name"].strip().lower(): dict(row) for row in project_stats}
    clients = []

    for row in saved_clients:
        data = dict(row)
        stats = stats_by_name.pop(data["name"].strip().lower(), None) or {}
        clients.append({
            **data,
            "project_count": stats.get("project_count", 0),
            "bucket_count": stats.get("bucket_count", 0),
            "selected_cost": stats.get("selected_cost", 0.0),
            "last_project_at": stats.get("last_project_at"),
            "source": "saved",
            "activity": activity_by_client.get(data["id"], []),
        })

    for stats in stats_by_name.values():
        clients.append({
            "id": None,
            "name": stats["name"],
            "email": None,
            "phone": None,
            "notes": None,
            "street": None, "city": None, "state": None, "zip": None,
            "time_preference": None,
            "secondary_contacts": [],
            "created_at": None,
            "updated_at": stats.get("last_project_at"),
            "project_count": stats.get("project_count", 0),
            "bucket_count": stats.get("bucket_count", 0),
            "selected_cost": stats.get("selected_cost", 0.0),
            "last_project_at": stats.get("last_project_at"),
            "source": "from_projects",
            "activity": [],  # no `clients` row -- nothing to have synced onto
        })

    return sorted(clients, key=lambda item: item["name"].lower())


@router.get("/list", response_model=List[ClientOut])
async def list_clients(request: Request):
    conn = await get_conn()
    try:
        return await build_client_list(conn)
    finally:
        await conn.close()


@router.post("/create", response_model=ClientOut)
async def create_client(body: ClientCreate, request: Request):
    from app.auth.supabase_auth import get_optional_user

    name = clean_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")

    time_preference = clean_time_preference(body.time_preference) or None
    signed_in = get_optional_user(request)
    conn = await get_conn()
    try:
        # One INSERT, guarded by the unique index — two people adding the same
        # client at the same moment produce one row and one clean 409, instead
        # of one silently overwriting the other.
        row = await conn.fetchrow(
            f"""
            INSERT INTO clients (name, email, phone, notes, street, city, state, zip, secondary_contacts, created_by, time_preference)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)
            ON CONFLICT (LOWER(TRIM(name))) DO NOTHING
            RETURNING {CLIENT_COLUMNS}
            """,
            name,
            clean_name(body.email) or None,
            clean_name(body.phone) or None,
            clean_name(body.notes) or None,
            clean_name(body.street) or None,
            clean_name(body.city) or None,
            clean_name(body.state) or None,
            clean_name(body.zip) or None,
            json.dumps([c.dict() for c in body.secondary_contacts]) if body.secondary_contacts is not None else "[]",
            signed_in.email if signed_in else None,
            time_preference,
        )
        if row is None:
            raise HTTPException(status_code=409, detail="Client already exists")

        result = dict(row)
        sc = result.get("secondary_contacts")
        result["secondary_contacts"] = json.loads(sc) if isinstance(sc, str) else (sc or [])
        return {
            **result,
            "project_count": 0,
            "bucket_count": 0,
            "selected_cost": 0.0,
            "last_project_at": None,
            "source": "saved",
            "activity": [],
        }
    finally:
        await conn.close()


@router.put("/update/{client_id}", response_model=ClientOut)
async def update_client(client_id: int, body: ClientUpdate, request: Request):
    """Edit an existing client. Every field is optional-to-change -- only
    what's actually present in the body gets written, via COALESCE, so a
    partial edit (just fixing a phone number) can't accidentally blank out
    everything else. There was no way to edit a saved client at all before
    this -- create and delete were the only two operations."""
    time_preference = clean_time_preference(body.time_preference)
    conn = await get_conn()
    try:
        try:
            sc_json = (
                json.dumps([c.dict() for c in body.secondary_contacts])
                if body.secondary_contacts is not None else None
            )
            row = await conn.fetchrow(
                f"""
                UPDATE clients SET
                    name = COALESCE(NULLIF(TRIM($2), ''), name),
                    email = CASE WHEN $3::text IS NOT NULL THEN NULLIF(TRIM($3), '') ELSE email END,
                    phone = CASE WHEN $4::text IS NOT NULL THEN NULLIF(TRIM($4), '') ELSE phone END,
                    notes = CASE WHEN $5::text IS NOT NULL THEN NULLIF(TRIM($5), '') ELSE notes END,
                    street = CASE WHEN $6::text IS NOT NULL THEN NULLIF(TRIM($6), '') ELSE street END,
                    city = CASE WHEN $7::text IS NOT NULL THEN NULLIF(TRIM($7), '') ELSE city END,
                    state = CASE WHEN $8::text IS NOT NULL THEN NULLIF(TRIM($8), '') ELSE state END,
                    zip = CASE WHEN $9::text IS NOT NULL THEN NULLIF(TRIM($9), '') ELSE zip END,
                    secondary_contacts = CASE WHEN $10::jsonb IS NOT NULL THEN $10::jsonb ELSE secondary_contacts END,
                    time_preference = CASE WHEN $11::text IS NOT NULL THEN NULLIF(TRIM($11), '') ELSE time_preference END,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING {CLIENT_COLUMNS}
                """,
                client_id, body.name, body.email, body.phone, body.notes,
                body.street, body.city, body.state, body.zip, sc_json, time_preference,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="Another client already has that name")
        if row is None:
            raise HTTPException(status_code=404, detail="No client with that id")

        activity_by_client = await load_activity_by_client(conn)
        result = dict(row)
        sc = result.get("secondary_contacts")
        result["secondary_contacts"] = json.loads(sc) if isinstance(sc, str) else (sc or [])
        return {
            **result,
            "project_count": 0, "bucket_count": 0, "selected_cost": 0.0,
            "last_project_at": None, "source": "saved",
            "activity": activity_by_client.get(client_id, []),
        }
    finally:
        await conn.close()


@router.delete("/delete/{client_name}")
async def delete_client(client_name: str, request: Request, delete_projects: bool = False):
    name = clean_name(client_name)
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")

    conn = await get_conn()
    try:
        deleted_result = await conn.execute(
            "DELETE FROM clients WHERE LOWER(TRIM(name)) = LOWER($1)", name
        )
        deleted = int(deleted_result.split()[-1]) if deleted_result else 0

        # Team-wide: a client's projects belong to the team, so detach or delete
        # them all rather than only the ones this person happened to create.
        if delete_projects:
            updated = await conn.execute("""
                DELETE FROM arrangements
                WHERE LOWER(TRIM(COALESCE(client_name, ''))) = LOWER($1)
            """, name)
            count = int(updated.split()[-1]) if updated else 0
            return {"deleted": deleted, "projects_deleted": count, "projects_updated": 0}

        updated = await conn.execute("""
            UPDATE arrangements
            SET client_name = NULL, updated_at = NOW()
            WHERE LOWER(TRIM(COALESCE(client_name, ''))) = LOWER($1)
        """, name)
        count = int(updated.split()[-1]) if updated else 0
        return {"deleted": deleted, "projects_updated": count}
    finally:
        await conn.close()


class SeasonFieldsIn(BaseModel):
    """Per-season edits from the Clients tab. ``fields`` is {key: value} over
    the whitelist in app.libs.client_season.SEASON_FIELDS; a null or ""
    value clears that key so the spreadsheet may fill it again."""
    fields: dict


def _clean_season_label(season: str) -> str:
    s = (season or "").strip()
    if len(s) != 4 or not s.isdigit():
        raise HTTPException(status_code=400, detail="Bad season")
    return s


@router.put("/{client_id}/seasons/{season}", response_model=ActivityOut)
async def update_client_season(client_id: int, season: str, body: SeasonFieldsIn, request: Request):
    """Edit one client's record for one season -- storing with us, on hold,
    not installing, fees, boxes, notes -- from the app.

    The app is the source of truth: whatever is set here is stamped in
    detail.app_edits and survives every later spreadsheet sync (see
    app.libs.client_season). Creating the season's row when there is none
    yet is deliberate -- staff can mark "storing with us" for a client the
    sheet has not been synced for.
    """
    season = _clean_season_label(season)
    if not isinstance(body.fields, dict) or not body.fields:
        raise HTTPException(status_code=400, detail="fields must be a non-empty object")
    conn = await get_conn()
    try:
        exists = await conn.fetchval("SELECT 1 FROM clients WHERE id = $1", client_id)
        if not exists:
            raise HTTPException(status_code=404, detail="No client with that id")
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, detail FROM client_activity "
                " WHERE client_id = $1 AND kind = 'christmas_install' AND season = $2 FOR UPDATE",
                client_id, season,
            )
            prior = row["detail"] if row else None
            if isinstance(prior, str):
                prior = json.loads(prior)
            try:
                detail = client_season.apply_edits(prior if isinstance(prior, dict) else {}, body.fields)
            except client_season.FieldError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            summary = client_season.summarize(detail)
            occurred = detail.get("install_date")
            try:
                occurred_at = date.fromisoformat(str(occurred)[:10]) if occurred else None
            except ValueError:
                occurred_at = None
            saved = await conn.fetchrow(
                """
                INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at)
                VALUES ($1, 'christmas_install', $2, $3, $4::jsonb, $5::date)
                ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment' DO UPDATE SET
                    summary = EXCLUDED.summary, detail = EXCLUDED.detail,
                    occurred_at = EXCLUDED.occurred_at, updated_at = now()
                RETURNING id, kind, season, summary, detail, occurred_at, created_at
                """,
                client_id, season, summary, json.dumps(detail, default=str), occurred_at,
            )
        out = dict(saved)
        if isinstance(out.get("detail"), str):
            out["detail"] = json.loads(out["detail"])
        if out.get("occurred_at") is not None and not isinstance(out["occurred_at"], str):
            out["occurred_at"] = out["occurred_at"].isoformat()
        return out
    finally:
        await conn.close()


class CommentIn(BaseModel):
    text: str


# Comments share client_activity with the Christmas-install history (kind
# distinguishes them: 'christmas_install' vs 'comment'), so a comment added
# from the install-schedule tool's popup shows up in the same activity feed
# the Clients tab already renders -- one timeline, not a second parallel
# store. `season` is unused for a comment's own meaning; it only needs to
# be *something*, since the column is NOT NULL, and giving it the comment's
# own timestamp keeps every row's key unique on its own without leaning on
# the migration 009 partial-index carve-out to do that work implicitly.
@router.post("/{client_id}/comments", response_model=ActivityOut)
async def add_client_comment(client_id: int, body: CommentIn, request: Request):
    from app.auth.supabase_auth import get_optional_user

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text is required")
    if len(text) > 2000:
        raise HTTPException(status_code=413, detail="Comment is too long")

    signed_in = get_optional_user(request)
    conn = await get_conn()
    try:
        exists = await conn.fetchval("SELECT 1 FROM clients WHERE id = $1", client_id)
        if not exists:
            raise HTTPException(status_code=404, detail="No client with that id")
        now = datetime.utcnow()
        row = await conn.fetchrow(
            """
            INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at)
            VALUES ($1, 'comment', $2, $3, $4, NULL)
            RETURNING id, kind, season, summary, detail, occurred_at, created_at
            """,
            client_id,
            now.isoformat(),
            text,
            json.dumps({"author": signed_in.email if signed_in else None}),
        )
        return dict(row)
    finally:
        await conn.close()


@router.delete("/{client_id}/comments/{activity_id}")
async def delete_client_comment(client_id: int, activity_id: int, request: Request):
    conn = await get_conn()
    try:
        # kind='comment' scopes this to comments only -- this route can
        # never be used to delete a real Christmas-install history row.
        result = await conn.execute(
            "DELETE FROM client_activity WHERE id = $1 AND client_id = $2 AND kind = 'comment'",
            activity_id, client_id,
        )
        deleted = int(result.split()[-1]) if result else 0
        if not deleted:
            raise HTTPException(status_code=404, detail="No such comment")
        return {"deleted": True}
    finally:
        await conn.close()


class RecentCommentOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    text: str
    author: Optional[str] = None
    created_at: datetime


# Backs the sidebar's "someone added a comment" badge. Deliberately its own
# lean query rather than reusing build_client_list -- that one joins in the
# full project rollup for every client, which the sidebar (mounted on every
# page) has no use for and shouldn't pay for on every poll.
@router.get("/comments/recent", response_model=List[RecentCommentOut])
async def recent_comments(request: Request, limit: int = 20):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT ca.id, ca.client_id, c.name AS client_name, ca.summary, ca.detail, ca.created_at
            FROM client_activity ca
            JOIN clients c ON c.id = ca.client_id
            WHERE ca.kind = 'comment'
            ORDER BY ca.created_at DESC
            LIMIT $1
            """,
            limit,
        )
        out = []
        for r in rows:
            detail = r["detail"]
            if isinstance(detail, str):
                detail = json.loads(detail)
            out.append({
                "id": r["id"],
                "client_id": r["client_id"],
                "client_name": r["client_name"],
                "text": r["summary"],
                "author": (detail or {}).get("author"),
                "created_at": r["created_at"],
            })
        return out
    finally:
        await conn.close()
