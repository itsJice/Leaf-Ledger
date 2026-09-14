from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Any
import asyncio
import time
import json
import databutton as db
from datetime import datetime
from app.libs.db import get_conn
from app.libs.supplier_identity import resolve_scraper_key

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _infer_scraper_key(name: Optional[str], scraper_key: Optional[str] = None) -> Optional[str]:
    """Normalize the configured scraper key, falling back to supplier name."""
    return resolve_scraper_key(name, scraper_key)


def _json_list(value: Any) -> list:
    """Decode a json/jsonb array returned by asyncpg into a Python list."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return list(value)


def _supplier_row(row: Any, **overrides: Any) -> dict:
    """asyncpg hands back jsonb as a JSON *string*, which fails validation
    against SupplierOut.secondary_contacts (a list of models). Decode it on the
    way out so every supplier-returning endpoint agrees on the shape."""
    out = dict(row)
    out["secondary_contacts"] = _json_list(out.get("secondary_contacts"))
    out.update(overrides)
    return out


























# ---------- Models ----------

# ---------- Catalog filter models ----------





# ---------- Supplier models ----------

class SupplierContact(BaseModel):
    """An extra person at a vendor beyond the primary rep -- AP, credit,
    shipping, or just an alternate. `label` is what the team calls that role."""
    label: str = ""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

# Trade/ops terms live on the supplier because none of it is scrapeable -- how
# fast they really ship, our terms, our credit line and how payment is actually
# taken are all things the team learns by working with the vendor.
class SupplierTermsFields(BaseModel):
    shipping_speed: Optional[str] = None
    shipping_notes: Optional[str] = None
    net_terms: Optional[str] = None
    credit_limit: Optional[float] = None
    payment_process: Optional[str] = None
    secondary_contacts: List[SupplierContact] = []

class SupplierCreate(SupplierTermsFields):
    name: str
    scraper_key: Optional[str] = None
    login_url: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    categories: List[str] = []

class SupplierOut(SupplierTermsFields):
    id: int
    name: str
    scraper_key: Optional[str] = None
    login_url: Optional[str]
    login_username: Optional[str] = None
    has_credentials: bool = False  # True if login_username + login_password are stored
    credential_status: Optional[str] = None
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    notes: Optional[str]
    categories: List[str] = []
    created_at: datetime
    updated_at: datetime
    product_count: int = 0
    last_price_synced_at: Optional[datetime] = None
    last_full_sync_at: Optional[datetime] = None

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    scraper_key: Optional[str] = None
    login_url: Optional[str] = None
    login_username: Optional[str] = None
    login_password: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    categories: Optional[List[str]] = None
    shipping_speed: Optional[str] = None
    shipping_notes: Optional[str] = None
    net_terms: Optional[str] = None
    credit_limit: Optional[float] = None
    payment_process: Optional[str] = None
    secondary_contacts: Optional[List[SupplierContact]] = None

class SupplierCredentialsOut(BaseModel):
    login_username: Optional[str] = None
    login_password: Optional[str] = None





# ---------- Endpoints ----------

# Counting products per supplier means walking all ~166k active rows, which on
# this instance costs 16-29s and made the Suppliers page look broken. The
# catalog only changes on import, so the counts are cached and refreshed in the
# background; the supplier list itself (32 rows) is always fetched fresh.
_SUPPLIER_COUNT_CACHE: dict = {"ts": 0.0, "counts": None}
_SUPPLIER_COUNT_TTL = 900  # 15 minutes
_SUPPLIER_COUNT_LOCK = asyncio.Lock()


async def _fetch_supplier_counts(conn) -> dict:
    rows = await conn.fetch(
        """SELECT supplier_id, COUNT(*) AS n FROM products
            WHERE is_active = TRUE GROUP BY supplier_id"""
    )
    return {r["supplier_id"]: r["n"] for r in rows}


async def _refresh_supplier_counts() -> None:
    """Rebuild the count cache on its own connection, one refresh at a time."""
    if _SUPPLIER_COUNT_LOCK.locked():
        return
    async with _SUPPLIER_COUNT_LOCK:
        conn = await get_conn()
        try:
            counts = await _fetch_supplier_counts(conn)
            _SUPPLIER_COUNT_CACHE.update(ts=time.time(), counts=counts)
        except Exception:
            pass
        finally:
            await conn.close()


@router.get("/list", response_model=List[SupplierOut])
async def list_suppliers():
    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT s.*,
                   (s.login_username IS NOT NULL AND s.login_username != '' AND s.login_password IS NOT NULL AND s.login_password != '') as has_credentials
            FROM suppliers s
            ORDER BY s.name
        """)
        cached = _SUPPLIER_COUNT_CACHE.get("counts")
        fresh = cached is not None and (time.time() - _SUPPLIER_COUNT_CACHE["ts"]) < _SUPPLIER_COUNT_TTL
        if not fresh:
            if cached is None:
                # Nothing cached yet: pay for it once so the first load is correct.
                try:
                    cached = await _fetch_supplier_counts(conn)
                    _SUPPLIER_COUNT_CACHE.update(ts=time.time(), counts=cached)
                except Exception:
                    cached = {}
            else:
                # Stale but usable - serve it now, refresh behind the request.
                asyncio.create_task(_refresh_supplier_counts())
        counts = cached or {}
        return [_supplier_row(r, product_count=counts.get(r["id"], 0)) for r in rows]
    finally:
        await conn.close()

@router.post("/create", response_model=SupplierOut)
async def create_supplier(body: SupplierCreate):
    conn = await get_conn()
    try:
        scraper_key = _infer_scraper_key(body.name, body.scraper_key)
        row = await conn.fetchrow("""
            INSERT INTO suppliers (name, scraper_key, scraper_enabled, login_url, contact_name, contact_email, contact_phone, notes, categories,
                                   shipping_speed, shipping_notes, net_terms, credit_limit, payment_process, secondary_contacts)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb)
            RETURNING *, 0 as product_count, FALSE as has_credentials
        """, body.name, scraper_key, scraper_key is not None, body.login_url, body.contact_name, body.contact_email, body.contact_phone, body.notes, body.categories,
             body.shipping_speed, body.shipping_notes, body.net_terms, body.credit_limit, body.payment_process,
             json.dumps([c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in body.secondary_contacts]))
        return _supplier_row(row)
    finally:
        await conn.close()

@router.put("/update/{supplier_id}", response_model=SupplierOut)
async def update_supplier(supplier_id: int, body: SupplierUpdate):
    conn = await get_conn()
    try:
        existing = await conn.fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")
        from decimal import Decimal

        # Only touch columns the caller actually sent. The previous form used
        # COALESCE($n, col) on every column, which meant a field could never be
        # CLEARED: passing null read as "leave it alone", so blanking a net term
        # or a credit limit silently kept the old value. Distinguishing "field
        # omitted" from "field set to empty" needs exclude_unset.
        sent = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)

        # name is NOT NULL, so a caller that explicitly sends "" or "   " is
        # not asking to clear it (that's not a valid state) -- it's a bad
        # request. Reject loudly instead of silently keeping the old name.
        if "name" in sent and not (sent["name"] or "").strip():
            raise HTTPException(status_code=400, detail="Supplier name cannot be blank")

        next_name = sent.get("name") or existing["name"]
        next_scraper_key = _infer_scraper_key(
            next_name, sent["scraper_key"] if "scraper_key" in sent else existing["scraper_key"])
        next_username = sent["login_username"] if "login_username" in sent else existing["login_username"]
        next_password = sent["login_password"] if "login_password" in sent else existing["login_password"]
        creds_changed = "login_username" in sent or "login_password" in sent
        if not next_username or not next_password:
            next_credential_status = "missing"
        elif creds_changed:
            next_credential_status = "untested"
        else:
            next_credential_status = existing["credential_status"] or "untested"

        sets: List[str] = []
        vals: List[Any] = []

        def put(col: str, val: Any, cast: str = "") -> int:
            vals.append(val)
            sets.append(f"{col} = ${len(vals)}{cast}")
            return len(vals)

        # name is NOT NULL -- only write it when a real value came through
        if sent.get("name"):
            put("name", sent["name"], "::text")
        for col in ("login_url", "login_username", "login_password",
                    "contact_name", "contact_email", "contact_phone", "notes",
                    "shipping_speed", "shipping_notes", "net_terms", "payment_process"):
            if col in sent:
                put(col, sent[col], "::text")
        if "credit_limit" in sent:
            cl = sent["credit_limit"]
            # asyncpg encodes numeric from Decimal, not float
            put("credit_limit", Decimal(str(cl)) if cl is not None else None, "::numeric")
        if "categories" in sent:
            put("categories", sent["categories"], "::text[]")
        if "secondary_contacts" in sent:
            put("secondary_contacts", json.dumps(sent["secondary_contacts"] or []), "::jsonb")

        scraper_param = put("scraper_key", next_scraper_key, "::text")
        # reference the parameter, not the column: inside one UPDATE, reading
        # scraper_key would see the pre-update value
        sets.append(f"scraper_enabled = CASE WHEN ${scraper_param}::text IS NOT NULL THEN true ELSE scraper_enabled END")
        put("credential_status", next_credential_status, "::text")
        sets.append("updated_at = NOW()")

        vals.append(supplier_id)
        updated = await conn.fetchrow(
            f"UPDATE suppliers SET {', '.join(sets)} WHERE id = ${len(vals)} RETURNING *", *vals)
        count = await conn.fetchval("SELECT COUNT(*) FROM products WHERE supplier_id = $1 AND is_active = TRUE", supplier_id)
        return _supplier_row(
            updated,
            product_count=count,
            has_credentials=bool(updated["login_username"] and updated["login_password"]),
        )
    finally:
        await conn.close()

@router.delete("/delete/{supplier_id}")
async def delete_supplier(supplier_id: int):
    conn = await get_conn()
    try:
        result = await conn.execute("DELETE FROM suppliers WHERE id = $1", supplier_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Supplier not found")
        return {"ok": True}
    finally:
        await conn.close()


@router.get("/{supplier_id}/credentials", response_model=SupplierCredentialsOut)
async def get_supplier_credentials(supplier_id: int):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT login_username, login_password FROM suppliers WHERE id = $1",
            supplier_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Supplier not found")
        return dict(row)
    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Supplier catalog file intake endpoints
# ──────────────────────────────────────────────────────────────────────────────











# ──────────────────────────────────────────────────────────────────────────────
# Catalog filter endpoints
# ──────────────────────────────────────────────────────────────────────────────







# ──────────────────────────────────────────────────────────────────────────────
# Discover catalog endpoint — logs in live and returns category tree
# ──────────────────────────────────────────────────────────────────────────────

