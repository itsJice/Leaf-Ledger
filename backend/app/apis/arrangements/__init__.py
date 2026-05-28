from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
import os
import json
from datetime import datetime
from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/arrangements", tags=["arrangements"])
DATABASE_URL = os.environ.get("DATABASE_URL")
_PROJECT_SCHEMA_CHECKED = False
ROOM_LABEL_PREFIX = "LL_ROOM:"
SCOPE_LABEL_PREFIX = "LL_SCOPE:"
ITEM_META_PATH = os.path.join(os.path.dirname(__file__), "container_item_meta.local.json")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

async def ensure_container_item_meta(conn):
    # Compatibility table for databases where the app role can create helper
    # tables but cannot alter imported/exported legacy tables.
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS container_item_meta (
                item_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'selected',
                part_key TEXT,
                part_label TEXT,
                part_order INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    except asyncpg.InsufficientPrivilegeError:
        # Fall back to the local JSON sidecar below.
        pass

def load_item_meta_sidecar() -> dict:
    try:
        with open(ITEM_META_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

def save_item_meta_sidecar(data: dict):
    with open(ITEM_META_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))

def get_item_meta_sidecar(item_id: int) -> dict:
    return load_item_meta_sidecar().get(str(item_id), {})

def set_item_meta_sidecar(item_id: int, status: str, part_key: Optional[str], part_label: Optional[str], part_order: int):
    data = load_item_meta_sidecar()
    data[str(item_id)] = {
        "status": status,
        "part_key": part_key,
        "part_label": part_label,
        "part_order": int(part_order or 0),
        "updated_at": datetime.utcnow().isoformat(),
    }
    save_item_meta_sidecar(data)

def delete_item_meta_sidecar(item_id: int):
    data = load_item_meta_sidecar()
    if data.pop(str(item_id), None) is not None:
        save_item_meta_sidecar(data)

async def ensure_project_schema(conn):
    global _PROJECT_SCHEMA_CHECKED
    if _PROJECT_SCHEMA_CHECKED:
        rooms_exists = await conn.fetchval("SELECT to_regclass('public.project_rooms') IS NOT NULL")
        if rooms_exists:
            return
    try:
        await conn.execute("""
            DO $$
            BEGIN
                IF to_regclass('public.container_items') IS NOT NULL THEN
                    ALTER TABLE container_items
                    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'selected',
                    ADD COLUMN IF NOT EXISTS part_key TEXT,
                    ADD COLUMN IF NOT EXISTS part_label TEXT,
                    ADD COLUMN IF NOT EXISTS part_order INTEGER NOT NULL DEFAULT 0;
                END IF;
                IF to_regclass('public.arrangement_containers') IS NOT NULL THEN
                    ALTER TABLE arrangement_containers
                    ADD COLUMN IF NOT EXISTS bucket_type TEXT,
                    ADD COLUMN IF NOT EXISTS requested_quantity INTEGER NOT NULL DEFAULT 1,
                    ADD COLUMN IF NOT EXISTS scope_notes TEXT;
                END IF;
                IF to_regclass('public.project_rooms') IS NULL THEN
                    CREATE TABLE project_rooms (
                        id SERIAL PRIMARY KEY,
                        arrangement_id INTEGER NOT NULL REFERENCES arrangements(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        notes TEXT,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                END IF;
                IF to_regclass('public.arrangement_containers') IS NOT NULL THEN
                    ALTER TABLE arrangement_containers
                    ADD COLUMN IF NOT EXISTS room_id INTEGER REFERENCES project_rooms(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """)
        await ensure_container_item_meta(conn)
        _PROJECT_SCHEMA_CHECKED = True
    except asyncpg.InsufficientPrivilegeError:
        # Local/exported database roles can read/write rows but may not own tables.
        # If the column already exists, keep going; if not, later queries will reveal it.
        await ensure_container_item_meta(conn)
        _PROJECT_SCHEMA_CHECKED = True
        pass

async def project_rooms_table_exists(conn) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass('public.project_rooms') IS NOT NULL"))

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

async def container_item_columns(conn) -> set[str]:
    rows = await conn.fetch("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'container_items'
    """)
    return {row["column_name"] for row in rows}

async def item_meta_table_exists(conn) -> bool:
    try:
        return bool(await conn.fetchval("SELECT to_regclass('public.container_item_meta') IS NOT NULL"))
    except Exception:
        return False

async def can_use_item_meta_table(conn) -> bool:
    try:
        if not await item_meta_table_exists(conn):
            return False
        await conn.fetchval("SELECT 1 FROM container_item_meta LIMIT 1")
        return True
    except Exception:
        return False

async def arrangement_container_columns(conn) -> set[str]:
    rows = await conn.fetch("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'arrangement_containers'
    """)
    return {row["column_name"] for row in rows}

# ---------- Models ----------

class ContainerItemIn(BaseModel):
    product_id: int
    quantity: int = 1
    status: str = "selected"
    part_key: Optional[str] = None
    part_label: Optional[str] = None
    part_order: int = 0

class ItemStatusUpdate(BaseModel):
    status: str

class ContainerIn(BaseModel):
    container_product_id: Optional[int] = None
    label: Optional[str] = None
    room_id: Optional[int] = None
    bucket_type: Optional[str] = None
    requested_quantity: int = 1
    scope_notes: Optional[str] = None
    items: List[ContainerItemIn] = []

class RoomIn(BaseModel):
    name: str
    notes: Optional[str] = None

class RoomOut(BaseModel):
    id: int
    arrangement_id: int
    name: str
    notes: Optional[str] = None
    sort_order: int
    created_at: datetime
    updated_at: datetime

class ContainerUpdate(BaseModel):
    label: Optional[str] = None
    bucket_type: Optional[str] = None
    requested_quantity: Optional[int] = None
    scope_notes: Optional[str] = None

class ArrangementCreate(BaseModel):
    name: str
    client_name: Optional[str] = None
    notes: Optional[str] = None
    containers: List[ContainerIn] = []

class ArrangementUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    notes: Optional[str] = None

class ContainerItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_category: str
    unit: str
    current_price: Optional[float]
    supplier_name: Optional[str]
    supplier_sku: Optional[str] = None
    photo_url: Optional[str] = None
    quantity: int
    line_total: Optional[float]
    status: str = "selected"
    part_key: Optional[str] = None
    part_label: Optional[str] = None
    part_order: int = 0

class ContainerOut(BaseModel):
    id: int
    arrangement_id: int
    container_product_id: Optional[int]
    container_name: Optional[str]
    label: Optional[str]
    room_id: Optional[int] = None
    bucket_type: Optional[str] = None
    requested_quantity: int = 1
    scope_notes: Optional[str] = None
    sort_order: int
    items: List[ContainerItemOut] = []
    subtotal: float = 0.0

class ArrangementOut(BaseModel):
    id: int
    name: str
    client_name: Optional[str]
    notes: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    rooms: List[RoomOut] = []
    containers: List[ContainerOut] = []
    total_cost: float = 0.0
    total_with_markup: float = 0.0

class ArrangementSummary(BaseModel):
    id: int
    name: str
    client_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    total_cost: float = 0.0
    container_count: int = 0

# ---------- Helpers ----------

def normalize_item_status(status: Optional[str]) -> str:
    value = (status or "selected").strip().lower()
    if value not in {"candidate", "selected"}:
        raise HTTPException(status_code=400, detail="Item status must be candidate or selected")
    return value

def clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None

def normalize_requested_quantity(value: Optional[int]) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1

def encode_room_label(name: str, notes: Optional[str] = None) -> str:
    return ROOM_LABEL_PREFIX + json.dumps(
        {"name": name, "notes": clean_optional_text(notes)},
        separators=(",", ":"),
    )

def parse_room_label(label: Optional[str]) -> Optional[dict]:
    if not label or not label.startswith(ROOM_LABEL_PREFIX):
        return None
    try:
        data = json.loads(label[len(ROOM_LABEL_PREFIX):])
        name = clean_optional_text(data.get("name"))
        if not name:
            return None
        return {"name": name, "notes": clean_optional_text(data.get("notes"))}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

def encode_scope_label(
    label: Optional[str],
    room_id: Optional[int] = None,
    bucket_type: Optional[str] = None,
    requested_quantity: Optional[int] = 1,
    scope_notes: Optional[str] = None,
) -> str:
    scope_name = clean_optional_text(label) or clean_optional_text(bucket_type) or "Scope"
    return SCOPE_LABEL_PREFIX + json.dumps(
        {
            "label": scope_name,
            "room_id": room_id,
            "bucket_type": clean_optional_text(bucket_type),
            "requested_quantity": normalize_requested_quantity(requested_quantity),
            "scope_notes": clean_optional_text(scope_notes),
        },
        separators=(",", ":"),
    )

def parse_scope_label(label: Optional[str]) -> Optional[dict]:
    if not label or not label.startswith(SCOPE_LABEL_PREFIX):
        return None
    try:
        data = json.loads(label[len(SCOPE_LABEL_PREFIX):])
        return {
            "label": clean_optional_text(data.get("label")) or clean_optional_text(data.get("bucket_type")) or "Scope",
            "room_id": data.get("room_id"),
            "bucket_type": clean_optional_text(data.get("bucket_type")),
            "requested_quantity": normalize_requested_quantity(data.get("requested_quantity")),
            "scope_notes": clean_optional_text(data.get("scope_notes")),
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

async def fetch_arrangement_full(conn, arrangement_id: int, user_id: str) -> dict:
    await ensure_project_schema(conn)
    supports_status = await has_item_status_column(conn)
    item_columns = await container_item_columns(conn)
    container_columns = await arrangement_container_columns(conn)
    arr = await conn.fetchrow("SELECT * FROM arrangements WHERE id = $1", arrangement_id)
    if not arr:
        raise HTTPException(status_code=404, detail="Arrangement not found")

    # Get markup
    global_markup = float(await conn.fetchval("SELECT markup_percentage FROM markup_settings WHERE category IS NULL") or 30.0)

    containers_rows = await conn.fetch(
        "SELECT ac.*, p.name as container_name FROM arrangement_containers ac "
        "LEFT JOIN products p ON p.id = ac.container_product_id "
        "WHERE ac.arrangement_id = $1 ORDER BY ac.sort_order",
        arrangement_id
    )
    rooms_table_exists = await project_rooms_table_exists(conn)
    rooms_rows = []
    if rooms_table_exists:
        rooms_rows = await conn.fetch(
            "SELECT * FROM project_rooms WHERE arrangement_id = $1 ORDER BY sort_order, id",
            arrangement_id
        )

    rooms = [dict(r) for r in rooms_rows]

    containers = []
    total_cost = 0.0

    for cr in containers_rows:
        cr_data = dict(cr)
        fallback_room = None if rooms_table_exists else parse_room_label(cr_data.get("label"))
        if fallback_room:
            created_at = cr_data.get("created_at") or dict(arr).get("created_at")
            rooms.append({
                "id": cr_data["id"],
                "arrangement_id": arrangement_id,
                "name": fallback_room["name"],
                "notes": fallback_room.get("notes"),
                "sort_order": cr_data["sort_order"],
                "created_at": created_at,
                "updated_at": created_at,
            })
            continue
        fallback_scope = None if rooms_table_exists else parse_scope_label(cr_data.get("label"))
        supports_parts = {"part_key", "part_label", "part_order"}.issubset(item_columns)
        supports_meta = await can_use_item_meta_table(conn)
        native_status = "ci.status" if supports_status else "NULL::text"
        native_part_key = "ci.part_key" if supports_parts else "NULL::text"
        native_part_label = "ci.part_label" if supports_parts else "NULL::text"
        native_part_order = "ci.part_order" if supports_parts else "NULL::integer"
        item_status_select = f"COALESCE(cim.status, {native_status}, 'selected')::text AS status"
        part_select = (
            f"COALESCE(cim.part_key, {native_part_key})::text AS part_key, "
            f"COALESCE(cim.part_label, {native_part_label})::text AS part_label, "
            f"COALESCE(cim.part_order, {native_part_order}, 0)::integer AS part_order"
        )
        meta_join = "LEFT JOIN container_item_meta cim ON cim.item_id = ci.id" if supports_meta else "LEFT JOIN (SELECT NULL::integer AS item_id, NULL::text AS status, NULL::text AS part_key, NULL::text AS part_label, NULL::integer AS part_order) cim ON false"
        item_order_by = "part_order, ci.id"
        items_rows = await conn.fetch(f"""
            SELECT ci.id, ci.container_id, ci.product_id, ci.quantity, {item_status_select}, {part_select},
                   p.name as product_name, p.category as product_category,
                   p.unit, p.current_price, p.supplier_sku, p.photo_url, s.name as supplier_name
            FROM container_items ci
            {meta_join}
            JOIN products p ON p.id = ci.product_id
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE ci.container_id = $1
            ORDER BY {item_order_by}
        """, cr["id"])

        items = []
        subtotal = 0.0
        for ir in items_rows:
            sidecar_meta = {} if supports_meta else get_item_meta_sidecar(ir["id"])
            price = float(ir["current_price"] or 0.0)
            quantity = int(ir["quantity"] or 0)
            status = sidecar_meta.get("status") or ir["status"] or "selected"
            line_total = price * quantity if status == "selected" else 0.0
            if status == "selected":
                subtotal += line_total
            items.append({
                "id": ir["id"],
                "product_id": ir["product_id"],
                "product_name": ir["product_name"],
                "product_category": ir["product_category"],
                "unit": ir["unit"],
                "current_price": float(ir["current_price"]) if ir["current_price"] is not None else None,
                "supplier_name": ir["supplier_name"],
                "supplier_sku": ir["supplier_sku"],
                "photo_url": ir["photo_url"],
                "quantity": quantity,
                "line_total": line_total,
                "status": status,
                "part_key": sidecar_meta.get("part_key") if sidecar_meta else ir["part_key"],
                "part_label": sidecar_meta.get("part_label") if sidecar_meta else ir["part_label"],
                "part_order": int((sidecar_meta.get("part_order") if sidecar_meta else ir["part_order"]) or 0),
            })

        total_cost += subtotal
        containers.append({
            "id": cr_data["id"],
            "arrangement_id": arrangement_id,
            "container_product_id": cr_data["container_product_id"],
            "container_name": cr_data["container_name"],
            "label": fallback_scope["label"] if fallback_scope else cr_data["label"],
            "room_id": cr_data.get("room_id") if "room_id" in container_columns else (fallback_scope.get("room_id") if fallback_scope else None),
            "bucket_type": cr_data.get("bucket_type") if "bucket_type" in container_columns else (fallback_scope.get("bucket_type") if fallback_scope else None),
            "requested_quantity": normalize_requested_quantity(cr_data.get("requested_quantity") if "requested_quantity" in container_columns else (fallback_scope.get("requested_quantity") if fallback_scope else 1)),
            "scope_notes": cr_data.get("scope_notes") if "scope_notes" in container_columns else (fallback_scope.get("scope_notes") if fallback_scope else None),
            "sort_order": cr_data["sort_order"],
            "items": items,
            "subtotal": subtotal,
        })

    markup_factor = 1 + (global_markup / 100)
    return {
        **dict(arr),
        "rooms": rooms,
        "containers": containers,
        "total_cost": float(total_cost),
        "total_with_markup": round(total_cost * markup_factor, 2),
    }

# ---------- Endpoints ----------

@router.get("/list", response_model=List[ArrangementSummary])
async def list_arrangements(request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        supports_status = await has_item_status_column(conn)
        cost_expression = (
            "CASE WHEN ci.status = 'selected' THEN ci.quantity * p.current_price ELSE 0 END"
            if supports_status
            else "ci.quantity * p.current_price"
        )
        rows = await conn.fetch(f"""
            SELECT a.*, COUNT(DISTINCT CASE WHEN ac.label IS NULL OR ac.label NOT LIKE 'LL_ROOM:%' THEN ac.id END) as container_count,
                   COALESCE(SUM({cost_expression}), 0) as total_cost
            FROM arrangements a
            LEFT JOIN arrangement_containers ac ON ac.arrangement_id = a.id
            LEFT JOIN container_items ci ON ci.container_id = ac.id
            LEFT JOIN products p ON p.id = ci.product_id
            WHERE a.created_by = $1
            GROUP BY a.id
            ORDER BY a.updated_at DESC
        """, user_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()

@router.post("/create", response_model=ArrangementOut)
async def create_arrangement(body: ArrangementCreate, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        supports_status = await has_item_status_column(conn)
        item_columns = await container_item_columns(conn)
        container_columns = await arrangement_container_columns(conn)
        arr = await conn.fetchrow("""
            INSERT INTO arrangements (name, client_name, notes, created_by)
            VALUES ($1, $2, $3, $4) RETURNING *
        """, body.name, body.client_name, body.notes, user_id)
        arr_id = arr["id"]

        for i, c in enumerate(body.containers):
            if {"bucket_type", "requested_quantity", "scope_notes", "room_id"}.issubset(container_columns):
                container = await conn.fetchrow("""
                    INSERT INTO arrangement_containers
                        (arrangement_id, container_product_id, label, room_id, bucket_type, requested_quantity, scope_notes, sort_order)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id
                """, arr_id, c.container_product_id, clean_optional_text(c.label), c.room_id, clean_optional_text(c.bucket_type),
                    normalize_requested_quantity(c.requested_quantity), clean_optional_text(c.scope_notes), i)
            elif {"bucket_type", "requested_quantity", "scope_notes"}.issubset(container_columns):
                container = await conn.fetchrow("""
                    INSERT INTO arrangement_containers
                        (arrangement_id, container_product_id, label, bucket_type, requested_quantity, scope_notes, sort_order)
                    VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
                """, arr_id, c.container_product_id, clean_optional_text(c.label), clean_optional_text(c.bucket_type),
                    normalize_requested_quantity(c.requested_quantity), clean_optional_text(c.scope_notes), i)
            else:
                fallback_label = (
                    encode_scope_label(c.label, c.room_id, c.bucket_type, c.requested_quantity, c.scope_notes)
                    if c.room_id is not None
                    else (clean_optional_text(c.label) or clean_optional_text(c.bucket_type))
                )
                container = await conn.fetchrow("""
                    INSERT INTO arrangement_containers
                        (arrangement_id, container_product_id, label, sort_order)
                    VALUES ($1, $2, $3, $4) RETURNING id
                """, arr_id, c.container_product_id, fallback_label, i)
            for item in c.items:
                status = normalize_item_status(item.status)
                if supports_status and {"part_key", "part_label", "part_order"}.issubset(item_columns):
                    await conn.execute("""
                        INSERT INTO container_items (container_id, product_id, quantity, status, part_key, part_label, part_order)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, container["id"], item.product_id, item.quantity, status, clean_optional_text(item.part_key),
                        clean_optional_text(item.part_label), int(item.part_order or 0))
                elif supports_status:
                    await conn.execute("""
                        INSERT INTO container_items (container_id, product_id, quantity, status)
                        VALUES ($1, $2, $3, $4)
                    """, container["id"], item.product_id, item.quantity, status)
                else:
                    await conn.execute("""
                        INSERT INTO container_items (container_id, product_id, quantity)
                        VALUES ($1, $2, $3)
                    """, container["id"], item.product_id, item.quantity)

        return await fetch_arrangement_full(conn, arr_id, user_id)
    finally:
        await conn.close()

@router.get("/get/{arrangement_id}", response_model=ArrangementOut)
async def get_arrangement(arrangement_id: int, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        return await fetch_arrangement_full(conn, arrangement_id, user_id)
    finally:
        await conn.close()

@router.post("/room/add/{arrangement_id}", response_model=ArrangementOut)
async def add_room(arrangement_id: int, body: RoomIn, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        name = clean_optional_text(body.name)
        if not name:
            raise HTTPException(status_code=400, detail="Room name is required")
        if await project_rooms_table_exists(conn):
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), -1) FROM project_rooms WHERE arrangement_id = $1",
                arrangement_id
            )
            await conn.execute("""
                INSERT INTO project_rooms (arrangement_id, name, notes, sort_order)
                VALUES ($1, $2, $3, $4)
            """, arrangement_id, name, clean_optional_text(body.notes), max_order + 1)
        else:
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), -1) FROM arrangement_containers WHERE arrangement_id = $1",
                arrangement_id
            )
            await conn.execute("""
                INSERT INTO arrangement_containers (arrangement_id, label, sort_order)
                VALUES ($1, $2, $3)
            """, arrangement_id, encode_room_label(name, body.notes), max_order + 1)
        await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", arrangement_id)
        return await fetch_arrangement_full(conn, arrangement_id, user_id)
    finally:
        await conn.close()

@router.delete("/room/delete/{room_id}")
async def delete_room(room_id: int, request: Request):
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        if await project_rooms_table_exists(conn):
            row = await conn.fetchrow("SELECT arrangement_id FROM project_rooms WHERE id = $1", room_id)
            if not row:
                raise HTTPException(status_code=404, detail="Room not found")
            await conn.execute("DELETE FROM project_rooms WHERE id = $1", room_id)
        else:
            row = await conn.fetchrow("SELECT arrangement_id, label FROM arrangement_containers WHERE id = $1", room_id)
            if not row or not parse_room_label(row["label"]):
                raise HTTPException(status_code=404, detail="Room not found")
            await conn.execute("DELETE FROM arrangement_containers WHERE id = $1", room_id)
        if not row:
            raise HTTPException(status_code=404, detail="Room not found")
        await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", row["arrangement_id"])
        return {"ok": True}
    finally:
        await conn.close()

@router.put("/update/{arrangement_id}", response_model=ArrangementOut)
async def update_arrangement(arrangement_id: int, body: ArrangementUpdate, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await conn.execute("""
            UPDATE arrangements SET
                name = COALESCE($1, name),
                client_name = COALESCE($2, client_name),
                notes = COALESCE($3, notes),
                updated_at = NOW()
            WHERE id = $4
        """, body.name, body.client_name, body.notes, arrangement_id)
        return await fetch_arrangement_full(conn, arrangement_id, user_id)
    finally:
        await conn.close()

@router.delete("/delete/{arrangement_id}")
async def delete_arrangement(arrangement_id: int, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM arrangements WHERE id = $1 AND created_by = $2", arrangement_id, user_id)
        return {"ok": True}
    finally:
        await conn.close()

# --- Container management ---

@router.post("/container/add/{arrangement_id}", response_model=ArrangementOut)
async def add_container(arrangement_id: int, body: ContainerIn, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        supports_status = await has_item_status_column(conn)
        item_columns = await container_item_columns(conn)
        container_columns = await arrangement_container_columns(conn)
        max_order = await conn.fetchval(
            "SELECT COALESCE(MAX(sort_order), -1) FROM arrangement_containers WHERE arrangement_id = $1",
            arrangement_id
        )
        if {"bucket_type", "requested_quantity", "scope_notes", "room_id"}.issubset(container_columns):
            container = await conn.fetchrow("""
                INSERT INTO arrangement_containers
                    (arrangement_id, container_product_id, label, room_id, bucket_type, requested_quantity, scope_notes, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id
            """, arrangement_id, body.container_product_id, clean_optional_text(body.label), body.room_id,
                clean_optional_text(body.bucket_type), normalize_requested_quantity(body.requested_quantity),
                clean_optional_text(body.scope_notes), max_order + 1)
        elif {"bucket_type", "requested_quantity", "scope_notes"}.issubset(container_columns):
            container = await conn.fetchrow("""
                INSERT INTO arrangement_containers
                    (arrangement_id, container_product_id, label, bucket_type, requested_quantity, scope_notes, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
            """, arrangement_id, body.container_product_id, clean_optional_text(body.label), clean_optional_text(body.bucket_type),
                normalize_requested_quantity(body.requested_quantity), clean_optional_text(body.scope_notes), max_order + 1)
        else:
            fallback_label = (
                encode_scope_label(body.label, body.room_id, body.bucket_type, body.requested_quantity, body.scope_notes)
                if body.room_id is not None
                else (clean_optional_text(body.label) or clean_optional_text(body.bucket_type))
            )
            container = await conn.fetchrow("""
                INSERT INTO arrangement_containers
                    (arrangement_id, container_product_id, label, sort_order)
                VALUES ($1, $2, $3, $4) RETURNING id
            """, arrangement_id, body.container_product_id, fallback_label, max_order + 1)
        for item in body.items:
            status = normalize_item_status(item.status)
            if supports_status and {"part_key", "part_label", "part_order"}.issubset(item_columns):
                await conn.execute("""
                    INSERT INTO container_items (container_id, product_id, quantity, status, part_key, part_label, part_order)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, container["id"], item.product_id, item.quantity, status, clean_optional_text(item.part_key),
                    clean_optional_text(item.part_label), int(item.part_order or 0))
            elif supports_status:
                await conn.execute("""
                    INSERT INTO container_items (container_id, product_id, quantity, status)
                    VALUES ($1, $2, $3, $4)
                """, container["id"], item.product_id, item.quantity, status)
            else:
                await conn.execute("""
                    INSERT INTO container_items (container_id, product_id, quantity)
                    VALUES ($1, $2, $3)
                """, container["id"], item.product_id, item.quantity)
        await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", arrangement_id)
        return await fetch_arrangement_full(conn, arrangement_id, user_id)
    finally:
        await conn.close()

@router.put("/container/update/{container_id}", response_model=ArrangementOut)
async def update_container(container_id: int, body: ContainerUpdate, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        container_columns = await arrangement_container_columns(conn)
        existing = await conn.fetchrow(
            "SELECT arrangement_id, label FROM arrangement_containers WHERE id = $1", container_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Container not found")
        requested_quantity = None
        if body.requested_quantity is not None:
            requested_quantity = normalize_requested_quantity(body.requested_quantity)
        if {"bucket_type", "requested_quantity", "scope_notes"}.issubset(container_columns):
            await conn.execute("""
                UPDATE arrangement_containers SET
                    label = COALESCE($1, label),
                    bucket_type = COALESCE($2, bucket_type),
                    requested_quantity = COALESCE($3, requested_quantity),
                    scope_notes = COALESCE($4, scope_notes)
                WHERE id = $5
            """, clean_optional_text(body.label), clean_optional_text(body.bucket_type), requested_quantity,
                clean_optional_text(body.scope_notes), container_id)
        else:
            parsed_scope = parse_scope_label(existing["label"])
            if parsed_scope:
                fallback_label = encode_scope_label(
                    clean_optional_text(body.label) or parsed_scope.get("label"),
                    parsed_scope.get("room_id"),
                    clean_optional_text(body.bucket_type) or parsed_scope.get("bucket_type"),
                    requested_quantity if requested_quantity is not None else parsed_scope.get("requested_quantity"),
                    clean_optional_text(body.scope_notes) or parsed_scope.get("scope_notes"),
                )
            else:
                fallback_label = clean_optional_text(body.label) or clean_optional_text(body.bucket_type)
            await conn.execute("""
                UPDATE arrangement_containers SET
                    label = COALESCE($1, label)
                WHERE id = $2
            """, fallback_label, container_id)
        await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", existing["arrangement_id"])
        return await fetch_arrangement_full(conn, existing["arrangement_id"], user_id)
    finally:
        await conn.close()

@router.delete("/container/remove/{container_id}")
async def remove_container(container_id: int, request: Request):
    conn = await get_conn()
    try:
        arr_id = await conn.fetchval(
            "SELECT arrangement_id FROM arrangement_containers WHERE id = $1", container_id
        )
        if await can_use_item_meta_table(conn):
            await conn.execute(
                "DELETE FROM container_item_meta WHERE item_id IN (SELECT id FROM container_items WHERE container_id = $1)",
                container_id
            )
        for row in await conn.fetch("SELECT id FROM container_items WHERE container_id = $1", container_id):
            delete_item_meta_sidecar(row["id"])
        await conn.execute("DELETE FROM arrangement_containers WHERE id = $1", container_id)
        if arr_id:
            await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", arr_id)
        return {"ok": True}
    finally:
        await conn.close()

@router.post("/item/add/{container_id}")
async def add_item_to_container(container_id: int, body: ContainerItemIn, request: Request):
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        supports_status = await has_item_status_column(conn)
        item_columns = await container_item_columns(conn)
        status = normalize_item_status(body.status)
        supports_parts = {"part_key", "part_label", "part_order"}.issubset(item_columns)
        supports_meta = await can_use_item_meta_table(conn)
        part_key = clean_optional_text(body.part_key)
        part_label = clean_optional_text(body.part_label)
        part_order = int(body.part_order or 0)
        if supports_meta:
            existing = await conn.fetchrow(
                """
                SELECT ci.id, ci.quantity
                FROM container_items ci
                LEFT JOIN container_item_meta cim ON cim.item_id = ci.id
                WHERE ci.container_id = $1
                  AND ci.product_id = $2
                  AND COALESCE(cim.status, 'selected') = $3
                  AND COALESCE(cim.part_key, '') = COALESCE($4, '')
                """,
                container_id, body.product_id, status, part_key
            )
        elif supports_status and supports_parts:
            existing = await conn.fetchrow(
                """
                SELECT id, quantity FROM container_items
                WHERE container_id = $1
                  AND product_id = $2
                  AND status = $3
                  AND COALESCE(part_key, '') = COALESCE($4, '')
                """,
                container_id, body.product_id, status, part_key
            )
        elif supports_status:
            existing = await conn.fetchrow(
                "SELECT id, quantity FROM container_items WHERE container_id = $1 AND product_id = $2 AND status = $3",
                container_id, body.product_id, status
            )
        else:
            existing_rows = await conn.fetch(
                "SELECT id, quantity FROM container_items WHERE container_id = $1 AND product_id = $2",
                container_id, body.product_id
            )
            existing = None
            for row in existing_rows:
                meta = get_item_meta_sidecar(row["id"])
                row_status = meta.get("status") or "selected"
                row_part_key = meta.get("part_key")
                if row_status == status and (row_part_key or "") == (part_key or ""):
                    existing = row
                    break
        if existing:
            await conn.execute(
                "UPDATE container_items SET quantity = quantity + $1 WHERE id = $2",
                body.quantity, existing["id"]
            )
            item_id = existing["id"]
        else:
            if supports_status and supports_parts:
                item_id = await conn.fetchval(
                    """
                    INSERT INTO container_items (container_id, product_id, quantity, status, part_key, part_label, part_order)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    container_id, body.product_id, body.quantity, status, part_key, part_label, part_order
                )
            elif supports_status:
                item_id = await conn.fetchval(
                    "INSERT INTO container_items (container_id, product_id, quantity, status) VALUES ($1, $2, $3, $4) RETURNING id",
                    container_id, body.product_id, body.quantity, status
                )
            else:
                item_id = await conn.fetchval(
                    "INSERT INTO container_items (container_id, product_id, quantity) VALUES ($1, $2, $3) RETURNING id",
                    container_id, body.product_id, body.quantity
                )
        if supports_meta and item_id:
            await conn.execute(
                """
                INSERT INTO container_item_meta (item_id, status, part_key, part_label, part_order, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (item_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    part_key = EXCLUDED.part_key,
                    part_label = EXCLUDED.part_label,
                    part_order = EXCLUDED.part_order,
                    updated_at = NOW()
                """,
                item_id, status, part_key, part_label, part_order
            )
        elif item_id:
            set_item_meta_sidecar(item_id, status, part_key, part_label, part_order)
        arr_id = await conn.fetchval(
            "SELECT arrangement_id FROM arrangement_containers WHERE id = $1", container_id
        )
        if arr_id:
            await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", arr_id)
        return {"ok": True}
    finally:
        await conn.close()

@router.delete("/item/remove/{item_id}")
async def remove_item(item_id: int, request: Request):
    conn = await get_conn()
    try:
        container_id = await conn.fetchval(
            "SELECT container_id FROM container_items WHERE id = $1", item_id
        )
        if await can_use_item_meta_table(conn):
            await conn.execute("DELETE FROM container_item_meta WHERE item_id = $1", item_id)
        delete_item_meta_sidecar(item_id)
        await conn.execute("DELETE FROM container_items WHERE id = $1", item_id)
        if container_id:
            arr_id = await conn.fetchval(
                "SELECT arrangement_id FROM arrangement_containers WHERE id = $1", container_id
            )
            if arr_id:
                await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", arr_id)
        return {"ok": True}
    finally:
        await conn.close()

@router.put("/item/quantity/{item_id}")
async def update_item_quantity(item_id: int, quantity: int, request: Request):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("""
            SELECT ci.container_id, ac.arrangement_id
            FROM container_items ci
            JOIN arrangement_containers ac ON ac.id = ci.container_id
            WHERE ci.id = $1
        """, item_id)
        if quantity <= 0:
            if await can_use_item_meta_table(conn):
                await conn.execute("DELETE FROM container_item_meta WHERE item_id = $1", item_id)
            delete_item_meta_sidecar(item_id)
            await conn.execute("DELETE FROM container_items WHERE id = $1", item_id)
        else:
            await conn.execute("UPDATE container_items SET quantity = $1 WHERE id = $2", quantity, item_id)
        if row:
            await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", row["arrangement_id"])
        return {"ok": True}
    finally:
        await conn.close()

@router.put("/item/status/{item_id}")
async def update_item_status(item_id: int, body: ItemStatusUpdate, request: Request):
    conn = await get_conn()
    try:
        await ensure_project_schema(conn)
        supports_status = await has_item_status_column(conn)
        status = normalize_item_status(body.status)
        row = await conn.fetchrow("""
            SELECT ci.container_id, ac.arrangement_id
            FROM container_items ci
            JOIN arrangement_containers ac ON ac.id = ci.container_id
            WHERE ci.id = $1
        """, item_id)
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        if supports_status:
            await conn.execute("UPDATE container_items SET status = $1 WHERE id = $2", status, item_id)
        if await can_use_item_meta_table(conn):
            await conn.execute(
                """
                INSERT INTO container_item_meta (item_id, status, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (item_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = NOW()
                """,
                item_id, status
            )
        else:
            meta = get_item_meta_sidecar(item_id)
            set_item_meta_sidecar(
                item_id,
                status,
                meta.get("part_key"),
                meta.get("part_label"),
                int(meta.get("part_order") or 0),
            )
        await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", row["arrangement_id"])
        return {"ok": True, "status_supported": supports_status or await can_use_item_meta_table(conn) or bool(get_item_meta_sidecar(item_id))}
    finally:
        await conn.close()
