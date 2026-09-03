"""Jobs — a client order carried from intake to the client shelf.

The studio's process, as it runs on paper today:

  1. An order arrives (the Xmas Manufacturing Order form).
  2. The builders pull what they already have from inventory onto a shelf
     assigned to that client, then write down the *difference* they still need.
  3. The buyer sources each need line: checks what the owner already bought at
     market (open vendor orders), pivots on sold-out items, does pack math,
     adds to open vendor orders, and tracks follow-ups.
  4. The owner approves and places purchase orders as cash allows.
  5. Boxes arrive and are checked in; the job is ready to build when every
     need line is on the shelf.

This module gives each of those steps a record:

  jobs            one client order                (stage is DERIVED from lines)
  job_pieces      what was ordered (12 ft tree x1, vertical spray x2 ...)
  material_needs  the "purple sheet": one line per material, need qty and the
                  qty already pulled from inventory onto the client shelf
  sourcing_lines  the buyer's answer for a need: a catalog product with pack
                  math, an allocation from an open order, or a substitution
  job_tasks       follow-ups ("email Jason to add to the open order")
  receipts        check-in events against purchase order lines
  stock           overage that lands on the shelf after check-in

Purchase orders stay in ll_app.orders / order_items (see orders/__init__.py);
this module adds the columns that link a PO line back to the job and need it
serves, plus order status / arrival / receiving fields.

Storage: same ll_app schema and runtime-DDL pattern as orders — the app role
cannot create tables in public. product_id is a plain int; product detail is
joined from public.products at read time and snapshotted on the line.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.apis.products import get_conn
from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/jobs", tags=["jobs"])

_SCHEMA_READY = False

STAGES = ["received", "scoped", "sourcing", "ordered", "receiving", "ready", "built", "installed"]

PIECE_TYPES = [
    "Tree", "Tree Skirt", "Tree Decor", "Lighting", "Garland", "Wreath",
    "Vertical Spray", "Horizontal Swag", "Enhancers", "Low Arrangement",
    "Tall Arrangement", "Table Arrangement", "Tablescape", "Container", "Other",
]

SOURCING_STATUSES = ["proposed", "sold_out", "ready", "ordered", "follow_up", "allocated", "on_hold"]

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.jobs (
    id              serial PRIMARY KEY,
    order_no        text,
    name            text NOT NULL,
    client_id       integer,
    client_name     text,
    project_id      integer,
    season          text,
    collection      text,
    order_date      date,
    install_date    date,
    due_date        date,
    designer        text,
    sidemark        text,
    delivery_method text,
    color_palette   text,
    intake          jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes           text,
    built_at        timestamptz,
    installed_at    timestamptz,
    created_by      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ll_app.job_pieces (
    id          serial PRIMARY KEY,
    job_id      integer NOT NULL REFERENCES ll_app.jobs(id) ON DELETE CASCADE,
    piece_type  text NOT NULL,
    qty         numeric NOT NULL DEFAULT 1,
    spec        jsonb NOT NULL DEFAULT '{}'::jsonb,
    design_id   integer,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS job_pieces_job_idx ON ll_app.job_pieces(job_id);

CREATE TABLE IF NOT EXISTS ll_app.material_needs (
    id          serial PRIMARY KEY,
    job_id      integer NOT NULL REFERENCES ll_app.jobs(id) ON DELETE CASCADE,
    piece_id    integer REFERENCES ll_app.job_pieces(id) ON DELETE SET NULL,
    label       text NOT NULL,
    spec        text,
    need_qty    numeric NOT NULL DEFAULT 0,
    unit        text NOT NULL DEFAULT 'each',
    shelf_qty   numeric NOT NULL DEFAULT 0,
    source      text NOT NULL DEFAULT 'manual',
    notes       text,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS material_needs_job_idx ON ll_app.material_needs(job_id);

CREATE TABLE IF NOT EXISTS ll_app.sourcing_lines (
    id              serial PRIMARY KEY,
    need_id         integer NOT NULL REFERENCES ll_app.material_needs(id) ON DELETE CASCADE,
    product_id      integer,
    supplier_id     integer,
    vendor_name     text,
    sku             text,
    description     text,
    image_url       text,
    status          text NOT NULL DEFAULT 'proposed',
    price_per       text NOT NULL DEFAULT 'each',
    pack_qty        integer NOT NULL DEFAULT 1,
    covers_qty      numeric NOT NULL DEFAULT 0,
    packs           integer NOT NULL DEFAULT 0,
    order_qty       numeric NOT NULL DEFAULT 0,
    unit_cost       numeric,
    adj_unit_cost   numeric,
    allocated_from_order_item_id integer,
    allocated_qty   numeric NOT NULL DEFAULT 0,
    order_item_id   integer,
    substitute_for  integer,
    notes           text,
    created_by      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sourcing_lines_need_idx ON ll_app.sourcing_lines(need_id);

CREATE TABLE IF NOT EXISTS ll_app.job_tasks (
    id                serial PRIMARY KEY,
    job_id            integer NOT NULL REFERENCES ll_app.jobs(id) ON DELETE CASCADE,
    sourcing_line_id  integer,
    title             text NOT NULL,
    assignee          text,
    due               date,
    done_at           timestamptz,
    created_by        text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS job_tasks_job_idx ON ll_app.job_tasks(job_id);

CREATE TABLE IF NOT EXISTS ll_app.receipts (
    id             serial PRIMARY KEY,
    order_item_id  integer NOT NULL,
    qty            numeric NOT NULL,
    note           text,
    received_by    text,
    received_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ll_app.stock (
    id          serial PRIMARY KEY,
    product_id  integer,
    label       text NOT NULL,
    qty         numeric NOT NULL DEFAULT 0,
    location    text,
    job_id      integer,
    note        text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Purchase orders gain a lifecycle and a link back to the job.
ALTER TABLE ll_app.orders ADD COLUMN IF NOT EXISTS supplier_id integer;
ALTER TABLE ll_app.orders ADD COLUMN IF NOT EXISTS vendor_order_no text;
ALTER TABLE ll_app.orders ADD COLUMN IF NOT EXISTS placed_at timestamptz;
ALTER TABLE ll_app.orders ADD COLUMN IF NOT EXISTS expected_arrival date;
ALTER TABLE ll_app.orders ADD COLUMN IF NOT EXISTS freight numeric;
ALTER TABLE ll_app.order_items ADD COLUMN IF NOT EXISTS job_id integer;
ALTER TABLE ll_app.order_items ADD COLUMN IF NOT EXISTS need_id integer;
ALTER TABLE ll_app.order_items ADD COLUMN IF NOT EXISTS sourcing_line_id integer;
ALTER TABLE ll_app.order_items ADD COLUMN IF NOT EXISTS received_qty numeric NOT NULL DEFAULT 0;
ALTER TABLE ll_app.order_items ADD COLUMN IF NOT EXISTS follow_up_note text;
"""


async def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    # orders tables must exist before we ALTER them
    from app.apis.orders import ensure_schema as ensure_orders
    await ensure_orders(conn)
    await conn.execute(DDL)
    _SCHEMA_READY = True


# ── Models ──────────────────────────────────────────────────────────────────
class JobCreate(BaseModel):
    name: Optional[str] = None
    order_no: Optional[str] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    project_id: Optional[int] = None
    season: Optional[str] = None
    collection: Optional[str] = None
    order_date: Optional[date] = None
    install_date: Optional[date] = None
    due_date: Optional[date] = None
    designer: Optional[str] = None
    sidemark: Optional[str] = None
    delivery_method: Optional[str] = None
    color_palette: Optional[str] = None
    intake: Optional[dict] = None
    notes: Optional[str] = None


class JobUpdate(JobCreate):
    built: Optional[bool] = None
    installed: Optional[bool] = None


class PieceIn(BaseModel):
    piece_type: str
    qty: float = 1
    spec: Optional[dict] = None
    design_id: Optional[int] = None
    sort_order: Optional[int] = None


class PieceUpdate(BaseModel):
    piece_type: Optional[str] = None
    qty: Optional[float] = None
    spec: Optional[dict] = None
    design_id: Optional[int] = None
    sort_order: Optional[int] = None


class NeedIn(BaseModel):
    label: str
    spec: Optional[str] = None
    need_qty: float = 0
    unit: Optional[str] = "each"
    shelf_qty: float = 0
    piece_id: Optional[int] = None
    source: Optional[str] = "manual"
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class NeedsBulk(BaseModel):
    needs: List[NeedIn]


class NeedUpdate(BaseModel):
    label: Optional[str] = None
    spec: Optional[str] = None
    need_qty: Optional[float] = None
    unit: Optional[str] = None
    shelf_qty: Optional[float] = None
    piece_id: Optional[int] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class SourcingIn(BaseModel):
    product_id: Optional[int] = None
    vendor_name: Optional[str] = None
    supplier_id: Optional[int] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    unit_cost: Optional[float] = None
    price_per: Optional[str] = None      # 'each' | 'pack'
    pack_qty: Optional[int] = None
    covers_qty: Optional[float] = None   # how much of the need this line is for
    status: Optional[str] = None
    substitute_for: Optional[int] = None
    notes: Optional[str] = None


class SourcingUpdate(BaseModel):
    vendor_name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    unit_cost: Optional[float] = None
    price_per: Optional[str] = None
    pack_qty: Optional[int] = None
    covers_qty: Optional[float] = None
    order_qty: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AllocateIn(BaseModel):
    order_item_id: int
    qty: float
    notes: Optional[str] = None


class SendToPO(BaseModel):
    sourcing_line_ids: Optional[List[int]] = None
    # supplier_id -> existing order id to append to (else a new PO per vendor)
    append_to: Optional[dict] = None


class ReceiveIn(BaseModel):
    qty: float
    note: Optional[str] = None


class TaskIn(BaseModel):
    title: str
    assignee: Optional[str] = None
    due: Optional[date] = None
    sourcing_line_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    assignee: Optional[str] = None
    due: Optional[date] = None
    done: Optional[bool] = None


class PoUpdate(BaseModel):
    status: Optional[str] = None
    vendor_order_no: Optional[str] = None
    expected_arrival: Optional[date] = None
    freight: Optional[float] = None
    placed: Optional[bool] = None


# ── Helpers ─────────────────────────────────────────────────────────────────
def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _jsonb(v) -> dict:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            return {}
    return v if isinstance(v, dict) else {}


def _pack_math(covers_qty: float, pack_qty: int, unit_cost: Optional[float], price_per: str) -> dict:
    """Round a need up to whole packs and derive the per-piece cost.

    Sugar pine cones: need 30, 20 per pack at $66/pack -> 2 packs = 40,
    $3.30 each. A per-piece price with pack 1 passes straight through.
    """
    pack = max(1, int(pack_qty or 1))
    covers = max(0.0, _num(covers_qty))
    packs = int(math.ceil(covers / pack)) if covers > 0 else 0
    order_qty = packs * pack
    adj = None
    if unit_cost is not None:
        adj = float(unit_cost) / pack if price_per == "pack" else float(unit_cost)
    return {"pack_qty": pack, "packs": packs, "order_qty": order_qty, "adj_unit_cost": adj}


def _line_cost(line: dict) -> Optional[float]:
    if line.get("unit_cost") is None:
        return None
    if line.get("price_per") == "pack":
        return _num(line["unit_cost"]) * int(line.get("packs") or 0)
    return _num(line["unit_cost"]) * _num(line.get("order_qty"))


async def _product_snapshot(conn, product_id: int) -> dict:
    row = await conn.fetchrow("""
        SELECT p.id, p.name, p.supplier_sku, p.current_price, p.supplier_id, s.name AS supplier_name,
               p.case_qty, p.moq, p.availability, p.image_urls, p.photo_url, p.raw_data
        FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.id = $1
    """, product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    raw = _jsonb(row["raw_data"])
    box = None
    try:
        box = int(str(raw.get("BoxQty", "")).strip())
    except (TypeError, ValueError):
        box = None
    imgs = list(row["image_urls"] or [])
    image = imgs[0] if imgs else (row["photo_url"] or raw.get("source_photo_url"))
    return {
        "product_id": row["id"], "description": row["name"], "sku": row["supplier_sku"],
        "unit_cost": float(row["current_price"]) if row["current_price"] is not None else None,
        "supplier_id": row["supplier_id"], "vendor_name": row["supplier_name"],
        "pack_qty": box or row["case_qty"] or 1, "availability": row["availability"],
        "image_url": image,
    }


def _derive_need(need: dict, lines: List[dict]) -> dict:
    """Fold the sourcing lines into the numbers the worksheet shows."""
    need_qty = _num(need["need_qty"])
    shelf = _num(need["shelf_qty"])
    allocated = sum(_num(l["allocated_qty"]) for l in lines if l["status"] == "allocated")
    ordered = sum(_num(l["covers_qty"]) for l in lines if l["order_item_id"])
    received = sum(min(_num(l["covers_qty"]), _num(l.get("received_qty"))) for l in lines if l["order_item_id"])
    proposed = sum(_num(l["covers_qty"]) for l in lines
                   if not l["order_item_id"] and l["status"] in ("proposed", "ready", "follow_up"))
    gap = max(0.0, need_qty - shelf - allocated - ordered)
    unsourced = max(0.0, gap - proposed)
    on_shelf = shelf + allocated + received
    return {
        "allocated_qty": allocated, "ordered_qty": ordered, "received_qty": received,
        "proposed_qty": proposed, "gap_qty": gap, "unsourced_qty": unsourced,
        "on_shelf_qty": on_shelf,
        "ready": need_qty <= 0 or on_shelf >= need_qty,
    }


def _derive_stage(job: dict, pieces: list, needs: List[dict]) -> str:
    if job.get("installed_at"):
        return "installed"
    if job.get("built_at"):
        return "built"
    if not needs:
        return "scoped" if pieces else "received"
    if all(n["ready"] for n in needs):
        return "ready"
    if any(n["unsourced_qty"] > 0 or n["proposed_qty"] > 0 for n in needs):
        return "sourcing"
    if any(n["received_qty"] > 0 for n in needs):
        return "receiving"
    return "ordered"


async def _load_job(conn, job_id: int) -> Optional[dict]:
    job = await conn.fetchrow("SELECT * FROM ll_app.jobs WHERE id = $1", job_id)
    if not job:
        return None
    job = dict(job)
    job["intake"] = _jsonb(job.get("intake"))
    pieces = [dict(r) for r in await conn.fetch(
        "SELECT * FROM ll_app.job_pieces WHERE job_id = $1 ORDER BY sort_order, id", job_id)]
    for p in pieces:
        p["spec"] = _jsonb(p.get("spec"))
    need_rows = await conn.fetch(
        "SELECT * FROM ll_app.material_needs WHERE job_id = $1 ORDER BY sort_order, id", job_id)
    line_rows = await conn.fetch("""
        SELECT l.*, oi.quantity AS po_quantity, oi.received_qty, oi.order_id,
               o.name AS order_name, o.status AS order_status, o.expected_arrival,
               o.vendor_order_no, o.placed_at,
               src.name AS allocated_order_name, src.status AS allocated_order_status,
               srci.received_qty AS allocated_received_qty, srci.quantity AS allocated_line_qty
        FROM ll_app.sourcing_lines l
        JOIN ll_app.material_needs n ON n.id = l.need_id
        LEFT JOIN ll_app.order_items oi ON oi.id = l.order_item_id
        LEFT JOIN ll_app.orders o ON o.id = oi.order_id
        LEFT JOIN ll_app.order_items srci ON srci.id = l.allocated_from_order_item_id
        LEFT JOIN ll_app.orders src ON src.id = srci.order_id
        WHERE n.job_id = $1
        ORDER BY l.created_at, l.id
    """, job_id)
    by_need: dict = {}
    for r in line_rows:
        d = dict(r)
        for k in ("unit_cost", "adj_unit_cost", "covers_qty", "order_qty", "allocated_qty",
                  "received_qty", "po_quantity", "allocated_received_qty", "allocated_line_qty"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        d["line_cost"] = _line_cost(d)
        d["overage_qty"] = max(0.0, _num(d["order_qty"]) - _num(d["covers_qty"])) if d["order_qty"] else 0.0
        by_need.setdefault(d["need_id"], []).append(d)
    needs = []
    for r in need_rows:
        n = dict(r)
        for k in ("need_qty", "shelf_qty"):
            n[k] = float(n[k]) if n[k] is not None else 0.0
        n["lines"] = by_need.get(n["id"], [])
        n.update(_derive_need(n, n["lines"]))
        needs.append(n)
    tasks = [dict(r) for r in await conn.fetch(
        "SELECT * FROM ll_app.job_tasks WHERE job_id = $1 ORDER BY done_at NULLS FIRST, due NULLS LAST, id",
        job_id)]
    # Purchase orders this job has lines on, with per-line receiving state.
    po_rows = await conn.fetch("""
        SELECT o.id, o.name, o.status, o.supplier_id, o.vendor_order_no, o.placed_at,
               o.expected_arrival, o.freight, o.updated_at,
               s.name AS supplier_name,
               COUNT(oi.id)::int AS line_count,
               COALESCE(SUM(oi.quantity), 0)::float AS total_qty,
               COALESCE(SUM(oi.received_qty), 0)::float AS received_qty
        FROM ll_app.orders o
        JOIN ll_app.order_items oi ON oi.order_id = o.id AND oi.job_id = $1
        LEFT JOIN suppliers s ON s.id = o.supplier_id
        GROUP BY o.id, s.name
        ORDER BY o.updated_at DESC
    """, job_id)
    pos = [dict(r) for r in po_rows]
    stage = _derive_stage(job, pieces, needs)
    cost = 0.0
    cost_known = False
    for n in needs:
        for l in n["lines"]:
            if l["status"] in ("allocated", "sold_out", "on_hold"):
                continue
            if l["line_cost"] is not None:
                cost += l["line_cost"]; cost_known = True
    ready_lines = sum(1 for n in needs if n["ready"])
    return {
        **job, "stage": stage, "pieces": pieces, "needs": needs, "tasks": tasks,
        "purchase_orders": pos,
        "summary": {
            "piece_count": len(pieces), "need_count": len(needs), "ready_count": ready_lines,
            "gap_count": sum(1 for n in needs if n["gap_qty"] > 0),
            "unsourced_count": sum(1 for n in needs if n["unsourced_qty"] > 0),
            "open_tasks": sum(1 for t in tasks if not t["done_at"]),
            "buy_cost": cost if cost_known else None,
        },
    }


async def _touch(conn, job_id: int):
    await conn.execute("UPDATE ll_app.jobs SET updated_at = now() WHERE id = $1", job_id)


async def _job_id_for_need(conn, need_id: int) -> int:
    jid = await conn.fetchval("SELECT job_id FROM ll_app.material_needs WHERE id = $1", need_id)
    if not jid:
        raise HTTPException(status_code=404, detail="Need line not found")
    return jid


# ── Jobs ────────────────────────────────────────────────────────────────────
@router.get("/meta")
async def jobs_meta():
    return {"stages": STAGES, "piece_types": PIECE_TYPES, "sourcing_statuses": SOURCING_STATUSES}


@router.get("/list")
async def list_jobs():
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch("SELECT id FROM ll_app.jobs ORDER BY updated_at DESC")
        out = []
        for r in rows:
            j = await _load_job(conn, r["id"])
            if not j:
                continue
            out.append({k: j[k] for k in (
                "id", "name", "order_no", "client_name", "client_id", "project_id", "season",
                "collection", "install_date", "order_date", "due_date", "stage", "summary",
                "updated_at", "created_at")})
        return out
    finally:
        await conn.close()


@router.post("/create")
async def create_job(body: JobCreate, request: Request):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        name = (body.name or "").strip() or " ".join(
            x for x in [body.client_name, body.collection] if x) or "Untitled job"
        row = await conn.fetchrow("""
            INSERT INTO ll_app.jobs (order_no, name, client_id, client_name, project_id, season,
                collection, order_date, install_date, due_date, designer, sidemark,
                delivery_method, color_palette, intake, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,$16,$17)
            RETURNING id
        """, body.order_no, name, body.client_id, body.client_name, body.project_id, body.season,
             body.collection, body.order_date, body.install_date, body.due_date, body.designer,
             body.sidemark, body.delivery_method, body.color_palette,
             json.dumps(body.intake or {}), body.notes, get_request_user_id(request))
        return await _load_job(conn, row["id"])
    finally:
        await conn.close()


@router.get("/{job_id}")
async def get_job(job_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job = await _load_job(conn, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        await conn.close()


@router.patch("/{job_id}")
async def update_job(job_id: int, body: JobUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        sets, params, idx = [], [], 1
        fields = body.model_dump(exclude_unset=True)
        for col in ("order_no", "name", "client_id", "client_name", "project_id", "season",
                    "collection", "order_date", "install_date", "due_date", "designer",
                    "sidemark", "delivery_method", "color_palette", "notes"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col]); idx += 1
        if "intake" in fields:
            sets.append(f"intake = ${idx}::jsonb"); params.append(json.dumps(fields["intake"] or {})); idx += 1
        if "built" in fields:
            sets.append("built_at = " + ("now()" if fields["built"] else "NULL"))
        if "installed" in fields:
            sets.append("installed_at = " + ("now()" if fields["installed"] else "NULL"))
        if sets:
            params.append(job_id)
            await conn.execute(
                f"UPDATE ll_app.jobs SET {', '.join(sets)}, updated_at = now() WHERE id = ${idx}", *params)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.delete("/{job_id}")
async def delete_job(job_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await conn.execute("DELETE FROM ll_app.jobs WHERE id = $1", job_id)
        return {"ok": True}
    finally:
        await conn.close()


# ── Pieces ──────────────────────────────────────────────────────────────────
@router.post("/{job_id}/pieces")
async def add_piece(job_id: int, body: PieceIn):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        order = body.sort_order
        if order is None:
            order = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM ll_app.job_pieces WHERE job_id = $1", job_id)
        await conn.execute("""
            INSERT INTO ll_app.job_pieces (job_id, piece_type, qty, spec, design_id, sort_order)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6)
        """, job_id, body.piece_type, body.qty, json.dumps(body.spec or {}), body.design_id, order)
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.patch("/pieces/{piece_id}")
async def update_piece(piece_id: int, body: PieceUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job_id = await conn.fetchval("SELECT job_id FROM ll_app.job_pieces WHERE id = $1", piece_id)
        if not job_id:
            raise HTTPException(status_code=404, detail="Piece not found")
        fields = body.model_dump(exclude_unset=True)
        sets, params, idx = [], [], 1
        for col in ("piece_type", "qty", "design_id", "sort_order"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col]); idx += 1
        if "spec" in fields:
            sets.append(f"spec = ${idx}::jsonb"); params.append(json.dumps(fields["spec"] or {})); idx += 1
        if sets:
            params.append(piece_id)
            await conn.execute(f"UPDATE ll_app.job_pieces SET {', '.join(sets)} WHERE id = ${idx}", *params)
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.delete("/pieces/{piece_id}")
async def delete_piece(piece_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("DELETE FROM ll_app.job_pieces WHERE id = $1 RETURNING job_id", piece_id)
        if not row:
            raise HTTPException(status_code=404, detail="Piece not found")
        await _touch(conn, row["job_id"])
        return await _load_job(conn, row["job_id"])
    finally:
        await conn.close()


# ── Need list (the purple sheet) ────────────────────────────────────────────
@router.post("/{job_id}/needs")
async def add_needs(job_id: int, body: NeedsBulk):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        base = await conn.fetchval(
            "SELECT COALESCE(MAX(sort_order), 0) FROM ll_app.material_needs WHERE job_id = $1", job_id)
        for i, n in enumerate(body.needs, start=1):
            label = (n.label or "").strip()
            if not label:
                continue
            await conn.execute("""
                INSERT INTO ll_app.material_needs
                    (job_id, piece_id, label, spec, need_qty, unit, shelf_qty, source, notes, sort_order)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """, job_id, n.piece_id, label, n.spec, n.need_qty, n.unit or "each", n.shelf_qty,
                 n.source or "manual", n.notes, n.sort_order if n.sort_order is not None else base + i)
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.patch("/needs/{need_id}")
async def update_need(need_id: int, body: NeedUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job_id = await _job_id_for_need(conn, need_id)
        fields = body.model_dump(exclude_unset=True)
        sets, params, idx = [], [], 1
        for col in ("label", "spec", "need_qty", "unit", "shelf_qty", "piece_id", "notes", "sort_order"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col]); idx += 1
        if sets:
            params.append(need_id)
            await conn.execute(
                f"UPDATE ll_app.material_needs SET {', '.join(sets)}, updated_at = now() WHERE id = ${idx}",
                *params)
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.delete("/needs/{need_id}")
async def delete_need(need_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("DELETE FROM ll_app.material_needs WHERE id = $1 RETURNING job_id", need_id)
        if not row:
            raise HTTPException(status_code=404, detail="Need line not found")
        await _touch(conn, row["job_id"])
        return await _load_job(conn, row["job_id"])
    finally:
        await conn.close()


# ── Sourcing (the buyer's worksheet) ────────────────────────────────────────
@router.post("/needs/{need_id}/sourcing")
async def add_sourcing(need_id: int, body: SourcingIn, request: Request):
    """Attach the buyer's answer for a need line: a catalog product (pack math
    filled from the catalog) or a hand-typed vendor/SKU. `covers_qty` defaults
    to the need's remaining gap."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job_id = await _job_id_for_need(conn, need_id)
        job = await _load_job(conn, job_id)
        need = next(n for n in job["needs"] if n["id"] == need_id)
        snap: dict = {}
        if body.product_id:
            snap = await _product_snapshot(conn, body.product_id)
        vendor = body.vendor_name or snap.get("vendor_name")
        supplier_id = body.supplier_id or snap.get("supplier_id")
        sku = body.sku or snap.get("sku")
        desc = body.description or snap.get("description")
        unit_cost = body.unit_cost if body.unit_cost is not None else snap.get("unit_cost")
        pack_qty = body.pack_qty or snap.get("pack_qty") or 1
        price_per = body.price_per or "each"
        covers = body.covers_qty if body.covers_qty is not None else need["unsourced_qty"]
        status = body.status or "proposed"
        if status not in SOURCING_STATUSES:
            raise HTTPException(status_code=400, detail="Unknown sourcing status")
        pm = _pack_math(covers, pack_qty, unit_cost, price_per)
        row = await conn.fetchrow("""
            INSERT INTO ll_app.sourcing_lines
                (need_id, product_id, supplier_id, vendor_name, sku, description, image_url, status,
                 price_per, pack_qty, covers_qty, packs, order_qty, unit_cost, adj_unit_cost,
                 substitute_for, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            RETURNING id
        """, need_id, body.product_id, supplier_id, vendor, sku, desc, snap.get("image_url"), status,
             price_per, pm["pack_qty"], covers, pm["packs"], pm["order_qty"], unit_cost,
             pm["adj_unit_cost"], body.substitute_for, body.notes, get_request_user_id(request))
        # Marking a substitution retires the line it replaces.
        if body.substitute_for:
            await conn.execute(
                "UPDATE ll_app.sourcing_lines SET status = 'sold_out', updated_at = now() "
                "WHERE id = $1 AND status IN ('proposed','ready','follow_up')", body.substitute_for)
        await _touch(conn, job_id)
        out = await _load_job(conn, job_id)
        out["created_line_id"] = row["id"]
        return out
    finally:
        await conn.close()


@router.patch("/sourcing/{line_id}")
async def update_sourcing(line_id: int, body: SourcingUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        cur = await conn.fetchrow("""
            SELECT l.*, n.job_id FROM ll_app.sourcing_lines l
            JOIN ll_app.material_needs n ON n.id = l.need_id WHERE l.id = $1
        """, line_id)
        if not cur:
            raise HTTPException(status_code=404, detail="Sourcing line not found")
        fields = body.model_dump(exclude_unset=True)
        if "status" in fields and fields["status"] not in SOURCING_STATUSES:
            raise HTTPException(status_code=400, detail="Unknown sourcing status")
        merged = dict(cur)
        merged.update({k: v for k, v in fields.items() if k != "order_qty"})
        pm = _pack_math(merged["covers_qty"], merged["pack_qty"], merged["unit_cost"], merged["price_per"])
        # An explicit order_qty wins over the rounding (buyer chose to order more or less).
        order_qty = fields.get("order_qty", pm["order_qty"]) if "order_qty" in fields else pm["order_qty"]
        packs = pm["packs"] if "order_qty" not in fields else int(math.ceil(_num(order_qty) / pm["pack_qty"]))
        await conn.execute("""
            UPDATE ll_app.sourcing_lines SET
                vendor_name = $2, sku = $3, description = $4, unit_cost = $5, price_per = $6,
                pack_qty = $7, covers_qty = $8, packs = $9, order_qty = $10, adj_unit_cost = $11,
                status = $12, notes = $13, updated_at = now()
            WHERE id = $1
        """, line_id, merged["vendor_name"], merged["sku"], merged["description"], merged["unit_cost"],
             merged["price_per"], pm["pack_qty"], merged["covers_qty"], packs, order_qty,
             pm["adj_unit_cost"], merged["status"], merged["notes"])
        # Keep a placed PO line in step with an edited order quantity.
        if cur["order_item_id"] and "order_qty" in fields and _num(order_qty) > 0:
            await conn.execute("UPDATE ll_app.order_items SET quantity = $2 WHERE id = $1",
                               cur["order_item_id"], int(math.ceil(_num(order_qty))))
        await _touch(conn, cur["job_id"])
        return await _load_job(conn, cur["job_id"])
    finally:
        await conn.close()


@router.delete("/sourcing/{line_id}")
async def delete_sourcing(line_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        cur = await conn.fetchrow("""
            SELECT l.order_item_id, n.job_id FROM ll_app.sourcing_lines l
            JOIN ll_app.material_needs n ON n.id = l.need_id WHERE l.id = $1
        """, line_id)
        if not cur:
            raise HTTPException(status_code=404, detail="Sourcing line not found")
        if cur["order_item_id"]:
            raise HTTPException(status_code=400, detail="This line is already on a purchase order. Remove it from the PO first.")
        await conn.execute("DELETE FROM ll_app.sourcing_lines WHERE id = $1", line_id)
        await _touch(conn, cur["job_id"])
        return await _load_job(conn, cur["job_id"])
    finally:
        await conn.close()


# ── Open orders and allocation (what the owner already bought) ─────────────
@router.get("/open-orders/search")
async def open_orders(product_id: Optional[int] = None, q: Optional[str] = None, limit: int = 20):
    """Lines on purchase orders that are not closed, with how much of each is
    still unallocated. Offered to the buyer before buying, so a market order of
    48 hydrangeas is seen and used instead of bought again."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        where = ["COALESCE(o.status, 'draft') <> 'closed'"]
        params: list = []
        if product_id:
            params.append(product_id); where.append(f"oi.product_id = ${len(params)}")
        elif q and q.strip():
            params.append(f"%{q.strip()}%")
            where.append(f"(COALESCE(oi.name_snapshot, p.name) ILIKE ${len(params)} "
                         f"OR COALESCE(oi.sku_snapshot, p.supplier_sku) ILIKE ${len(params)})")
        else:
            return []
        params.append(max(1, min(int(limit), 100)))
        rows = await conn.fetch(f"""
            SELECT oi.id AS order_item_id, oi.order_id, o.name AS order_name, o.status AS order_status,
                   o.expected_arrival, oi.product_id, oi.quantity::float AS quantity,
                   oi.received_qty::float AS received_qty, oi.job_id,
                   j.name AS job_name,
                   COALESCE(oi.name_snapshot, p.name) AS name,
                   COALESCE(oi.sku_snapshot, p.supplier_sku) AS sku,
                   COALESCE(oi.supplier_snapshot, s.name) AS supplier_name,
                   COALESCE(oi.unit_price, p.current_price)::float AS unit_price,
                   COALESCE((SELECT SUM(sl.allocated_qty) FROM ll_app.sourcing_lines sl
                             WHERE sl.allocated_from_order_item_id = oi.id AND sl.status = 'allocated'), 0)::float
                       AS allocated_qty
            FROM ll_app.order_items oi
            JOIN ll_app.orders o ON o.id = oi.order_id
            LEFT JOIN products p ON p.id = oi.product_id
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            LEFT JOIN ll_app.jobs j ON j.id = oi.job_id
            WHERE {' AND '.join(where)}
            ORDER BY o.updated_at DESC
            LIMIT ${len(params)}
        """, *params)
        out = []
        for r in rows:
            d = dict(r)
            # A line bought for a specific job is fully spoken for by that job.
            reserved = d["quantity"] if d["job_id"] else d["allocated_qty"]
            d["remaining_qty"] = max(0.0, _num(d["quantity"]) - _num(reserved))
            out.append(d)
        return out
    finally:
        await conn.close()


@router.post("/needs/{need_id}/allocate")
async def allocate(need_id: int, body: AllocateIn, request: Request):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job_id = await _job_id_for_need(conn, need_id)
        src = await conn.fetchrow("""
            SELECT oi.*, o.name AS order_name, p.name AS pname, p.supplier_sku, p.supplier_id,
                   s.name AS supplier_name, p.current_price, p.image_urls, p.photo_url
            FROM ll_app.order_items oi JOIN ll_app.orders o ON o.id = oi.order_id
            LEFT JOIN products p ON p.id = oi.product_id
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE oi.id = $1
        """, body.order_item_id)
        if not src:
            raise HTTPException(status_code=404, detail="Order line not found")
        taken = await conn.fetchval("""
            SELECT COALESCE(SUM(allocated_qty), 0) FROM ll_app.sourcing_lines
            WHERE allocated_from_order_item_id = $1 AND status = 'allocated'
        """, body.order_item_id)
        reserved = _num(src["quantity"]) if src["job_id"] else _num(taken)
        remaining = _num(src["quantity"]) - reserved
        if body.qty <= 0 or body.qty > remaining + 1e-9:
            raise HTTPException(status_code=400, detail=f"Only {remaining:g} left unallocated on that order line")
        imgs = list(src["image_urls"] or [])
        await conn.execute("""
            INSERT INTO ll_app.sourcing_lines
                (need_id, product_id, supplier_id, vendor_name, sku, description, image_url, status,
                 price_per, pack_qty, covers_qty, packs, order_qty, unit_cost, adj_unit_cost,
                 allocated_from_order_item_id, allocated_qty, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,'allocated','each',1,$8,0,0,$9,$9,$10,$8,$11,$12)
        """, need_id, src["product_id"], src["supplier_id"],
             src["supplier_snapshot"] or src["supplier_name"],
             src["sku_snapshot"] or src["supplier_sku"], src["name_snapshot"] or src["pname"],
             (imgs[0] if imgs else src["photo_url"]), body.qty,
             float(src["unit_price"]) if src["unit_price"] is not None else
             (float(src["current_price"]) if src["current_price"] is not None else None),
             body.order_item_id, body.notes or f"Allocated from {src['order_name']}",
             get_request_user_id(request))
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


# ── Send to purchase orders ─────────────────────────────────────────────────
@router.post("/{job_id}/send-to-po")
async def send_to_po(job_id: int, body: SendToPO, request: Request):
    """Turn ready sourcing lines into purchase-order lines, one PO per vendor
    (or appended to an open PO the buyer chose). Each PO line remembers the
    job and need it serves, which is what makes 'on order' a query."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job = await _load_job(conn, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        wanted = set(body.sourcing_line_ids or [])
        lines = [l for n in job["needs"] for l in n["lines"]
                 if not l["order_item_id"] and l["status"] in ("proposed", "ready", "follow_up")
                 and (not wanted or l["id"] in wanted) and _num(l["order_qty"]) > 0]
        if not lines:
            raise HTTPException(status_code=400, detail="No sourcing lines are ready to send")
        append_to = {str(k): int(v) for k, v in (body.append_to or {}).items()}
        user = get_request_user_id(request)
        created: dict = {}
        for l in lines:
            key = str(l["supplier_id"] or f"v:{l['vendor_name'] or 'unknown'}")
            order_id = append_to.get(key) or created.get(key)
            if not order_id:
                vendor = l["vendor_name"] or "Vendor"
                name = f"{job['name']} · {vendor}"
                order_id = await conn.fetchval("""
                    INSERT INTO ll_app.orders (name, notes, status, created_by, supplier_id)
                    VALUES ($1, $2, 'draft', $3, $4) RETURNING id
                """, name, f"Created from job #{job_id}", user, l["supplier_id"])
                created[key] = order_id
            qty = int(math.ceil(_num(l["order_qty"])))
            item_id = None
            if l["product_id"]:
                existing = await conn.fetchval(
                    "SELECT id FROM ll_app.order_items WHERE order_id = $1 AND product_id = $2",
                    order_id, l["product_id"])
                if existing:
                    await conn.execute(
                        "UPDATE ll_app.order_items SET quantity = quantity + $2 WHERE id = $1", existing, qty)
                    item_id = existing
            if item_id is None:
                # Hand-typed lines have no catalog product; use a negative marker so
                # the (order_id, product_id) uniqueness never collides.
                pid = l["product_id"] or -l["id"]
                item_id = await conn.fetchval("""
                    INSERT INTO ll_app.order_items
                        (order_id, product_id, quantity, variant_note, unit_price,
                         name_snapshot, sku_snapshot, supplier_snapshot, added_by,
                         job_id, need_id, sourcing_line_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id
                """, order_id, pid, qty, l["notes"],
                     l["unit_cost"] if l["price_per"] == "each" else l["adj_unit_cost"],
                     l["description"], l["sku"], l["vendor_name"], user, job_id, l["need_id"], l["id"])
            await conn.execute("""
                UPDATE ll_app.sourcing_lines SET order_item_id = $2,
                    status = CASE WHEN status = 'follow_up' THEN 'follow_up' ELSE 'ordered' END,
                    updated_at = now() WHERE id = $1
            """, l["id"], item_id)
            await conn.execute("UPDATE ll_app.orders SET updated_at = now() WHERE id = $1", order_id)
        await _touch(conn, job_id)
        out = await _load_job(conn, job_id)
        out["created_orders"] = list(created.values())
        return out
    finally:
        await conn.close()


@router.get("/vendors/{supplier_id}/open-pos")
async def open_pos_for_vendor(supplier_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch("""
            SELECT o.id, o.name, o.status, o.updated_at, COUNT(oi.id)::int AS line_count
            FROM ll_app.orders o LEFT JOIN ll_app.order_items oi ON oi.order_id = o.id
            WHERE o.supplier_id = $1 AND COALESCE(o.status,'draft') IN ('draft','approved','placed','follow_up')
            GROUP BY o.id ORDER BY o.updated_at DESC
        """, supplier_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.patch("/po/{order_id}")
async def update_po(order_id: int, body: PoUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        fields = body.model_dump(exclude_unset=True)
        sets, params, idx = [], [], 1
        for col in ("status", "vendor_order_no", "expected_arrival", "freight"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col]); idx += 1
        if fields.get("placed"):
            sets.append("placed_at = COALESCE(placed_at, now())")
            if "status" not in fields:
                sets.append("status = 'placed'")
        if sets:
            params.append(order_id)
            await conn.execute(
                f"UPDATE ll_app.orders SET {', '.join(sets)}, updated_at = now() WHERE id = ${idx}", *params)
        row = await conn.fetchrow("SELECT * FROM ll_app.orders WHERE id = $1", order_id)
        return dict(row) if row else {"ok": True}
    finally:
        await conn.close()


# ── Receiving ───────────────────────────────────────────────────────────────
@router.post("/order-items/{item_id}/receive")
async def receive(item_id: int, body: ReceiveIn, request: Request):
    """Check a box in against a PO line. When the line is fully received, any
    overage beyond what the job needed goes on the shelf as stock."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        item = await conn.fetchrow("SELECT * FROM ll_app.order_items WHERE id = $1", item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Order line not found")
        if body.qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        user = get_request_user_id(request)
        await conn.execute(
            "INSERT INTO ll_app.receipts (order_item_id, qty, note, received_by) VALUES ($1,$2,$3,$4)",
            item_id, body.qty, body.note, user)
        new_total = await conn.fetchval(
            "UPDATE ll_app.order_items SET received_qty = received_qty + $2 WHERE id = $1 RETURNING received_qty",
            item_id, body.qty)
        # Overage to stock once the line is fully in.
        if _num(new_total) >= _num(item["quantity"]) and item["sourcing_line_id"]:
            line = await conn.fetchrow("SELECT * FROM ll_app.sourcing_lines WHERE id = $1", item["sourcing_line_id"])
            if line:
                overage = _num(new_total) - _num(line["covers_qty"])
                already = await conn.fetchval(
                    "SELECT 1 FROM ll_app.stock WHERE note = $1", f"overage:line:{line['id']}")
                if overage > 0 and not already:
                    await conn.execute("""
                        INSERT INTO ll_app.stock (product_id, label, qty, location, job_id, note)
                        VALUES ($1, $2, $3, 'Overage', $4, $5)
                    """, line["product_id"], line["description"] or "Item", overage, item["job_id"],
                         f"overage:line:{line['id']}")
        # Whole order arrived?
        order_id = item["order_id"]
        outstanding = await conn.fetchval(
            "SELECT COUNT(*) FROM ll_app.order_items WHERE order_id = $1 AND received_qty < quantity", order_id)
        if outstanding == 0:
            await conn.execute("UPDATE ll_app.orders SET status = 'arrived', updated_at = now() WHERE id = $1", order_id)
        if item["job_id"]:
            await _touch(conn, item["job_id"])
            return await _load_job(conn, item["job_id"])
        return {"ok": True, "received_qty": float(new_total)}
    finally:
        await conn.close()


@router.get("/po/{order_id}/lines")
async def po_lines(order_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch("""
            SELECT oi.id, oi.product_id, oi.quantity::float AS quantity, oi.received_qty::float AS received_qty,
                   COALESCE(oi.name_snapshot, p.name) AS name, COALESCE(oi.sku_snapshot, p.supplier_sku) AS sku,
                   COALESCE(oi.unit_price, p.current_price)::float AS unit_price, oi.job_id, oi.need_id,
                   oi.sourcing_line_id, oi.follow_up_note, n.label AS need_label
            FROM ll_app.order_items oi
            LEFT JOIN products p ON p.id = oi.product_id
            LEFT JOIN ll_app.material_needs n ON n.id = oi.need_id
            WHERE oi.order_id = $1 ORDER BY oi.created_at, oi.id
        """, order_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── Tasks ───────────────────────────────────────────────────────────────────
@router.post("/{job_id}/tasks")
async def add_task(job_id: int, body: TaskIn, request: Request):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await conn.execute("""
            INSERT INTO ll_app.job_tasks (job_id, sourcing_line_id, title, assignee, due, created_by)
            VALUES ($1,$2,$3,$4,$5,$6)
        """, job_id, body.sourcing_line_id, body.title.strip(), body.assignee, body.due, get_request_user_id(request))
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job_id = await conn.fetchval("SELECT job_id FROM ll_app.job_tasks WHERE id = $1", task_id)
        if not job_id:
            raise HTTPException(status_code=404, detail="Task not found")
        fields = body.model_dump(exclude_unset=True)
        sets, params, idx = [], [], 1
        for col in ("title", "assignee", "due"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col]); idx += 1
        if "done" in fields:
            sets.append("done_at = " + ("now()" if fields["done"] else "NULL"))
        if sets:
            params.append(task_id)
            await conn.execute(f"UPDATE ll_app.job_tasks SET {', '.join(sets)} WHERE id = ${idx}", *params)
        await _touch(conn, job_id)
        return await _load_job(conn, job_id)
    finally:
        await conn.close()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("DELETE FROM ll_app.job_tasks WHERE id = $1 RETURNING job_id", task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        await _touch(conn, row["job_id"])
        return await _load_job(conn, row["job_id"])
    finally:
        await conn.close()


# ── Stock (what is on the shelf from overage) ───────────────────────────────
@router.get("/stock/list")
async def list_stock(q: Optional[str] = None):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        if q:
            rows = await conn.fetch(
                "SELECT * FROM ll_app.stock WHERE label ILIKE $1 AND qty > 0 ORDER BY updated_at DESC LIMIT 50",
                f"%{q}%")
        else:
            rows = await conn.fetch("SELECT * FROM ll_app.stock WHERE qty > 0 ORDER BY updated_at DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── Exports ─────────────────────────────────────────────────────────────────
@router.get("/{job_id}/export")
async def export_job(job_id: int, format: str = "xlsx"):
    """`xlsx` is the buyer's tracking sheet in the binder layout. `mo` is the
    Xmas Manufacturing Order (PDF) with the product list filled from sourcing."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        job = await _load_job(conn, job_id)
    finally:
        await conn.close()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    from app.apis.jobs import export as export_mod
    fmt = (format or "xlsx").lower()
    if fmt == "xlsx":
        body, media, ext = export_mod.tracking_xlsx(job), \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    elif fmt == "mo":
        body, media, ext = export_mod.manufacturing_order_pdf(job), "application/pdf", "pdf"
    else:
        raise HTTPException(status_code=400, detail="format must be xlsx or mo")
    slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in (job["name"] or "job")).strip().replace(" ", "_")
    suffix = "tracking" if fmt == "xlsx" else "manufacturing_order"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{slug}_{suffix}.{ext}"'})
