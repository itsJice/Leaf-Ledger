from datetime import datetime
import re
import os
from typing import List, Optional

import asyncpg
import databutton as db
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/clients", tags=["clients"])
DATABASE_URL = os.environ.get("DATABASE_URL")


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


def clients_storage_key(user_id: str) -> str:
    safe_user = re.sub(r"[^a-zA-Z0-9._=-]", "-", user_id or "local")
    return f"leaf-ledger-clients-{safe_user}"


def load_saved_clients(user_id: str) -> List[dict]:
    rows = db.storage.json.get(clients_storage_key(user_id), default=[])
    return rows if isinstance(rows, list) else []


def save_saved_clients(user_id: str, rows: List[dict]) -> None:
    db.storage.json.put(clients_storage_key(user_id), rows)


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


def saved_clients_only(user_id: str) -> List[dict]:
    clients = []
    for row in load_saved_clients(user_id):
        data = dict(row)
        clients.append({
            **data,
            "project_count": 0,
            "bucket_count": 0,
            "selected_cost": 0.0,
            "last_project_at": None,
            "source": "saved",
        })
    return sorted(clients, key=lambda item: item["name"].lower())


async def build_client_list(conn, user_id: str) -> List[dict]:
    saved_clients = load_saved_clients(user_id)
    status_expression = (
        "CASE WHEN ci.status = 'selected' THEN ci.quantity * p.current_price ELSE 0 END"
        if await has_item_status_column(conn)
        else "ci.quantity * p.current_price"
    )
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
        WHERE a.created_by = $1
        GROUP BY COALESCE(NULLIF(TRIM(a.client_name), ''), 'Unassigned')
    """, user_id)

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
    user_id = get_request_user_id(request)
    try:
        conn = await get_conn()
    except Exception:
        return saved_clients_only(user_id)
    try:
        return await build_client_list(conn, user_id)
    except Exception:
        return saved_clients_only(user_id)
    finally:
        await conn.close()


@router.post("/create", response_model=ClientOut)
async def create_client(body: ClientCreate, request: Request):
    user_id = get_request_user_id(request)
    name = clean_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")

    saved_clients = load_saved_clients(user_id)
    if any((client.get("name") or "").strip().lower() == name.lower() for client in saved_clients):
        raise HTTPException(status_code=409, detail="Client already exists")

    now = datetime.utcnow().isoformat()
    next_id = max([int(client.get("id") or 0) for client in saved_clients] + [0]) + 1
    row = {
        "id": next_id,
        "name": name,
        "email": clean_name(body.email) or None,
        "phone": clean_name(body.phone) or None,
        "notes": clean_name(body.notes) or None,
        "created_at": now,
        "updated_at": now,
    }
    save_saved_clients(user_id, [row, *saved_clients])

    return {
        **row,
        "project_count": 0,
        "bucket_count": 0,
        "selected_cost": 0.0,
        "last_project_at": None,
        "source": "saved",
    }


@router.delete("/delete/{client_name}")
async def delete_client(client_name: str, request: Request, delete_projects: bool = False):
    user_id = get_request_user_id(request)
    name = clean_name(client_name)
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")

    saved_clients = load_saved_clients(user_id)
    remaining = [
        client for client in saved_clients
        if (client.get("name") or "").strip().lower() != name.lower()
    ]
    save_saved_clients(user_id, remaining)

    try:
        conn = await get_conn()
    except Exception:
        return {"deleted": len(saved_clients) - len(remaining), "projects_updated": 0}

    try:
        if delete_projects:
            updated = await conn.execute("""
                DELETE FROM arrangements
                WHERE created_by = $1
                  AND LOWER(TRIM(COALESCE(client_name, ''))) = LOWER($2)
            """, user_id, name)
            count = int(updated.split()[-1]) if updated else 0
            return {"deleted": len(saved_clients) - len(remaining), "projects_deleted": count, "projects_updated": 0}

        updated = await conn.execute("""
            UPDATE arrangements
            SET client_name = NULL, updated_at = NOW()
            WHERE created_by = $1
              AND LOWER(TRIM(COALESCE(client_name, ''))) = LOWER($2)
        """, user_id, name)
        count = int(updated.split()[-1]) if updated else 0
        return {"deleted": len(saved_clients) - len(remaining), "projects_updated": count}
    finally:
        await conn.close()
