"""Saved clients — team-wide, stored in Postgres.

Clients used to live in a single JSON document on local disk. That lost data two
ways: concurrent edits overwrote each other (the whole list was rewritten on
every change), and a hosted restart wiped the disk. They now live in the
`clients` table (see migrations/003_clients_table.sql), shared by the whole team,
with one row per client and a unique index on the normalised name.
"""

from datetime import datetime
import os
from typing import List, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/clients", tags=["clients"])
DATABASE_URL = os.environ.get("DATABASE_URL")


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


async def load_saved_clients(conn) -> List[dict]:
    rows = await conn.fetch(
        "SELECT id, name, email, phone, notes, created_at, updated_at FROM clients"
    )
    return [dict(r) for r in rows]


async def has_item_status_column(conn) -> bool:
    return bool(await conn.fetchval("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'container_items'
              AND column_name = 'status'
        )
    """))


class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class ClientOut(BaseModel):
    id: Optional[int] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    project_count: int = 0
    bucket_count: int = 0
    selected_cost: float = 0.0
    last_project_at: Optional[datetime] = None
    source: str = "saved"


def clean_name(name: Optional[str]) -> str:
    return (name or "").strip()


async def build_client_list(conn) -> List[dict]:
    """Saved clients plus rollups from every project the team has."""
    saved_clients = await load_saved_clients(conn)
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
        })

    for stats in stats_by_name.values():
        clients.append({
            "id": None,
            "name": stats["name"],
            "email": None,
            "phone": None,
            "notes": None,
            "created_at": None,
            "updated_at": stats.get("last_project_at"),
            "project_count": stats.get("project_count", 0),
            "bucket_count": stats.get("bucket_count", 0),
            "selected_cost": stats.get("selected_cost", 0.0),
            "last_project_at": stats.get("last_project_at"),
            "source": "from_projects",
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

    signed_in = get_optional_user(request)
    conn = await get_conn()
    try:
        # One INSERT, guarded by the unique index — two people adding the same
        # client at the same moment produce one row and one clean 409, instead
        # of one silently overwriting the other.
        row = await conn.fetchrow(
            """
            INSERT INTO clients (name, email, phone, notes, created_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (LOWER(TRIM(name))) DO NOTHING
            RETURNING id, name, email, phone, notes, created_at, updated_at
            """,
            name,
            clean_name(body.email) or None,
            clean_name(body.phone) or None,
            clean_name(body.notes) or None,
            signed_in.email if signed_in else None,
        )
        if row is None:
            raise HTTPException(status_code=409, detail="Client already exists")

        return {
            **dict(row),
            "project_count": 0,
            "bucket_count": 0,
            "selected_cost": 0.0,
            "last_project_at": None,
            "source": "saved",
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
