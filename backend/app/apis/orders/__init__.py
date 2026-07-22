"""Shared team purchase orders.

Users add catalog products (with a quantity) to a shared order; the order is
then grouped BY VENDOR into per-supplier purchase orders — each line carrying
the picture, name, real vendor SKU, size, quantity, unit price and a direct
link to the product on the supplier's site. Exports (PDF / Word / Excel) live
in export.py.

Storage note: the `app` DB role is not the owner of the public schema and can't
create tables there, but it CAN create its own schema — so the order tables
live in `ll_app`. `product_id` is a plain int (no cross-schema FK); product
detail is joined from public.products at read time so pictures/links/prices
stay live, while name/sku/price are also snapshotted on the line so a submitted
PO still reads correctly if the catalog later changes.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Optional, List
import json

from app.apis.products import get_conn

router = APIRouter(prefix="/orders", tags=["orders"])

_SCHEMA_READY = False

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.orders (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    notes       text,
    status      text NOT NULL DEFAULT 'draft',
    created_by  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ll_app.order_items (
    id           serial PRIMARY KEY,
    order_id     integer NOT NULL REFERENCES ll_app.orders(id) ON DELETE CASCADE,
    product_id   integer NOT NULL,
    quantity     integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
    variant_note text,
    unit_price   numeric,
    name_snapshot     text,
    sku_snapshot      text,
    supplier_snapshot text,
    added_by     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_id, product_id)
);
CREATE INDEX IF NOT EXISTS order_items_order_idx ON ll_app.order_items(order_id);
"""


async def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    await conn.execute(DDL)
    _SCHEMA_READY = True


# ── Models ──────────────────────────────────────────────────────────────────
class OrderCreate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None


class OrderSummary(BaseModel):
    id: int
    name: str
    notes: Optional[str] = None
    status: str
    created_by: Optional[str] = None
    created_at: Any = None
    updated_at: Any = None
    item_count: int = 0
    total_qty: int = 0
    vendor_count: int = 0
    total_cost: Optional[float] = None


class AddItem(BaseModel):
    product_id: int
    quantity: int = 1
    variant_note: Optional[str] = None
    added_by: Optional[str] = None


class UpdateItem(BaseModel):
    quantity: Optional[int] = None
    variant_note: Optional[str] = None


class OrderUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────────
def _first_image(image_urls, photo_url, raw) -> Optional[str]:
    for candidate in (
        image_urls[0] if isinstance(image_urls, (list, tuple)) and image_urls else None,
        photo_url,
        (raw or {}).get("source_photo_url"),
    ):
        if candidate:
            return str(candidate)
    return None


def _size_label(raw: dict, row) -> Optional[str]:
    norm = (raw or {}).get("normalized") or {}
    if norm.get("size_in") is not None:
        try:
            return f'{float(norm["size_in"]):g}"'
        except (TypeError, ValueError):
            pass
    for key in ("Size", "size", "Dimensions", "dimensions"):
        if raw.get(key):
            return str(raw[key])
    dims = [row.get("height_in"), row.get("width_in"), row.get("diameter_in"), row.get("length_in")]
    if any(d is not None for d in dims):
        parts = [f"{d:g}" for d in dims if d is not None]
        if parts:
            return "×".join(parts) + '"'
    return None


async def _order_summaries(conn, rows) -> List[dict]:
    return [dict(r) for r in rows]


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("/list", response_model=List[OrderSummary])
async def list_orders():
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch("""
            SELECT o.*,
                   COUNT(i.id)::int                              AS item_count,
                   COALESCE(SUM(i.quantity), 0)::int             AS total_qty,
                   COUNT(DISTINCT p.supplier_id)::int            AS vendor_count,
                   SUM(i.quantity * COALESCE(i.unit_price, p.current_price)) AS total_cost
            FROM ll_app.orders o
            LEFT JOIN ll_app.order_items i ON i.order_id = o.id
            LEFT JOIN products p ON p.id = i.product_id
            GROUP BY o.id
            ORDER BY o.updated_at DESC
        """)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.post("/create", response_model=OrderSummary)
async def create_order(body: OrderCreate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        name = (body.name or "").strip() or "Untitled order"
        row = await conn.fetchrow(
            "INSERT INTO ll_app.orders (name, notes, created_by) VALUES ($1, $2, $3) RETURNING *",
            name, body.notes, body.created_by,
        )
        d = dict(row)
        d.update(item_count=0, total_qty=0, vendor_count=0, total_cost=None)
        return d
    finally:
        await conn.close()


async def build_order_view(conn, order_id: int, supplier_id: Optional[int] = None) -> Optional[dict]:
    """Full order with line items grouped by vendor. Optionally filtered to a
    single supplier (used by per-vendor exports)."""
    order = await conn.fetchrow("SELECT * FROM ll_app.orders WHERE id = $1", order_id)
    if not order:
        return None
    items = await conn.fetch("""
        SELECT i.id AS item_id, i.product_id, i.quantity, i.variant_note,
               COALESCE(i.unit_price, p.current_price) AS unit_price,
               COALESCE(i.name_snapshot, p.name)       AS name,
               COALESCE(i.sku_snapshot, p.supplier_sku) AS sku,
               p.supplier_id, s.name AS supplier_name,
               s.login_url AS supplier_login_url,
               p.image_urls, p.photo_url, p.raw_data,
               p.height_in, p.width_in, p.diameter_in, p.length_in
        FROM ll_app.order_items i
        LEFT JOIN products p ON p.id = i.product_id
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE i.order_id = $1
        ORDER BY s.name NULLS LAST, i.created_at
    """, order_id)

    vendors: dict = {}
    grand_total = 0.0
    grand_qty = 0
    for r in items:
        if supplier_id is not None and r["supplier_id"] != supplier_id:
            continue
        raw = r["raw_data"]
        raw = json.loads(raw) if isinstance(raw, str) else (raw or {})
        product_url = raw.get("product_url") or raw.get("detail_url") or raw.get("url")
        unit = float(r["unit_price"]) if r["unit_price"] is not None else None
        qty = int(r["quantity"] or 0)
        line_total = (unit * qty) if unit is not None else None
        key = r["supplier_id"] if r["supplier_id"] is not None else -1
        v = vendors.setdefault(key, {
            "supplier_id": r["supplier_id"],
            "supplier_name": r["supplier_name"] or "Unknown supplier",
            "supplier_login_url": r["supplier_login_url"],
            "items": [], "subtotal": 0.0, "subtotal_qty": 0,
        })
        v["items"].append({
            "item_id": r["item_id"], "product_id": r["product_id"],
            "name": r["name"], "sku": r["sku"],
            "size": _size_label(raw, r), "quantity": qty,
            "variant_note": r["variant_note"], "unit_price": unit,
            "line_total": line_total, "product_url": product_url,
            "image_url": _first_image(r["image_urls"], r["photo_url"], raw),
        })
        if line_total is not None:
            v["subtotal"] += line_total
            grand_total += line_total
        v["subtotal_qty"] += qty
        grand_qty += qty

    vendor_list = sorted(vendors.values(), key=lambda x: (x["supplier_name"] or "").lower())
    item_count = sum(len(v["items"]) for v in vendor_list)
    return {
        "id": order["id"], "name": order["name"], "notes": order["notes"],
        "status": order["status"], "created_by": order["created_by"],
        "created_at": order["created_at"], "updated_at": order["updated_at"],
        "vendors": vendor_list,
        "total_cost": grand_total, "total_qty": grand_qty,
        "item_count": item_count, "vendor_count": len(vendor_list),
    }


@router.get("/{order_id}")
async def get_order(order_id: int):
    """Full order with line items grouped by vendor (for the on-screen PO view)."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        view = await build_order_view(conn, order_id)
        if view is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return view
    finally:
        await conn.close()


@router.get("/{order_id}/export")
async def export_order(order_id: int, format: str = "pdf", supplier_id: Optional[int] = None):
    """Download the PO as PDF, Word (docx) or Excel (xlsx). With supplier_id,
    only that vendor's items are exported (a single-vendor PO)."""
    from fastapi import Response
    from app.apis.orders import export as export_mod

    fmt = (format or "").lower()
    if fmt not in ("pdf", "docx", "xlsx"):
        raise HTTPException(status_code=400, detail="format must be pdf, docx or xlsx")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        view = await build_order_view(conn, order_id, supplier_id=supplier_id)
    finally:
        await conn.close()
    if view is None:
        raise HTTPException(status_code=404, detail="Order not found")

    body, media, ext = export_mod.render(view, fmt)
    slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in (view["name"] or "order")).strip().replace(" ", "_") or "order"
    if supplier_id is not None and view["vendors"]:
        vslug = "".join(c if c.isalnum() else "" for c in view["vendors"][0]["supplier_name"])[:24]
        slug = f"{slug}_{vslug}"
    return Response(
        content=body, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{slug}.{ext}"'},
    )


@router.post("/{order_id}/items")
async def add_item(order_id: int, body: AddItem):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        exists = await conn.fetchval("SELECT 1 FROM ll_app.orders WHERE id = $1", order_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Order not found")
        snap = await conn.fetchrow("""
            SELECT p.name, p.supplier_sku, p.current_price, s.name AS supplier_name
            FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.id = $1
        """, body.product_id)
        if not snap:
            raise HTTPException(status_code=404, detail="Product not found")
        qty = max(1, int(body.quantity or 1))
        # Upsert: adding a product already on the order bumps its quantity.
        await conn.execute("""
            INSERT INTO ll_app.order_items
                (order_id, product_id, quantity, variant_note, unit_price,
                 name_snapshot, sku_snapshot, supplier_snapshot, added_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (order_id, product_id) DO UPDATE
                SET quantity = ll_app.order_items.quantity + EXCLUDED.quantity,
                    variant_note = COALESCE(EXCLUDED.variant_note, ll_app.order_items.variant_note)
        """, order_id, body.product_id, qty, body.variant_note, snap["current_price"],
             snap["name"], snap["supplier_sku"], snap["supplier_name"], body.added_by)
        await conn.execute("UPDATE ll_app.orders SET updated_at = now() WHERE id = $1", order_id)
        return {"ok": True}
    finally:
        await conn.close()


@router.patch("/items/{item_id}")
async def update_item(item_id: int, body: UpdateItem):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("SELECT order_id FROM ll_app.order_items WHERE id = $1", item_id)
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        if body.quantity is not None:
            if body.quantity <= 0:
                await conn.execute("DELETE FROM ll_app.order_items WHERE id = $1", item_id)
            else:
                await conn.execute("UPDATE ll_app.order_items SET quantity = $2 WHERE id = $1", item_id, int(body.quantity))
        if body.variant_note is not None:
            await conn.execute("UPDATE ll_app.order_items SET variant_note = $2 WHERE id = $1", item_id, body.variant_note)
        await conn.execute("UPDATE ll_app.orders SET updated_at = now() WHERE id = $1", row["order_id"])
        return {"ok": True}
    finally:
        await conn.close()


@router.delete("/items/{item_id}")
async def delete_item(item_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("DELETE FROM ll_app.order_items WHERE id = $1 RETURNING order_id", item_id)
        if row:
            await conn.execute("UPDATE ll_app.orders SET updated_at = now() WHERE id = $1", row["order_id"])
        return {"ok": True}
    finally:
        await conn.close()


@router.patch("/{order_id}")
async def update_order(order_id: int, body: OrderUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        sets, params, idx = [], [], 1
        for col, val in (("name", body.name), ("notes", body.notes), ("status", body.status)):
            if val is not None:
                sets.append(f"{col} = ${idx}"); params.append(val); idx += 1
        if not sets:
            return {"ok": True}
        params.append(order_id)
        await conn.execute(
            f"UPDATE ll_app.orders SET {', '.join(sets)}, updated_at = now() WHERE id = ${idx}", *params
        )
        return {"ok": True}
    finally:
        await conn.close()


@router.delete("/{order_id}")
async def delete_order(order_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await conn.execute("DELETE FROM ll_app.orders WHERE id = $1", order_id)
        return {"ok": True}
    finally:
        await conn.close()
