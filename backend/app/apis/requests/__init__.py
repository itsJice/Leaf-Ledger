"""Product requests — how a design order enters Leaf & Ledger.

Replaces Charles's bilingual Google Form. A designer opens the Request Form
tab, fills in a client/project once, then adds items to a spreadsheet-style
table — one row per thing she needs, added by typing into the blank row at
the bottom, exactly like the sourcing worksheet's need list. Every field
autosaves; the Save button is a confirmation, not a required step.

Once saved, the request is open for Charles: the Jobs page offers a "Load a
request" picker that turns it into a job (new or existing) and shows its
rows as a read-only reference panel on that job's board while he pins
catalog options against each line.

Storage: same ll_app schema and runtime-DDL pattern as jobs/orders — the app
role cannot create tables in public.
"""
from __future__ import annotations

import json
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.apis.user_context import get_request_user_id
from app.libs.db import ensure_schema_once, get_conn

router = APIRouter(prefix="/requests", tags=["requests"])

MATCH_RULES = ["exact", "similar", "inspiration"]
MATCH_LABEL = {
    "exact": "Yes, exact",
    "similar": "Maybe, similar is OK",
    "inspiration": "No, inspiration only",
}
USED_ON_OPTIONS = ["Tree", "Garland", "Wreath", "Swag", "Enhancer", "Table/Mantel", "Other"]

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.product_requests (
    id            serial PRIMARY KEY,
    client_name   text NOT NULL DEFAULT '',
    project_name  text NOT NULL DEFAULT '',
    deadline      date,
    samples_note  text,
    job_id        integer,
    saved_at      timestamptz,
    created_by    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ll_app.product_request_items (
    id                  serial PRIMARY KEY,
    request_id          integer NOT NULL REFERENCES ll_app.product_requests(id) ON DELETE CASCADE,
    item                text NOT NULL DEFAULT '',
    used_on             text,
    qty                 text,
    match_rule          text,
    description         text,
    quality             text,
    preferred_vendor    text,
    style_color         text,
    catalog_page        text,
    sort_order          integer NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS product_request_items_request_idx
    ON ll_app.product_request_items(request_id);
"""


async def ensure_schema(conn):
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("requests", _ddl)


def _touch(conn, request_id: int):
    return conn.execute("UPDATE ll_app.product_requests SET updated_at = now() WHERE id = $1", request_id)


async def _load_request(conn, request_id: int) -> Optional[dict]:
    req = await conn.fetchrow("SELECT * FROM ll_app.product_requests WHERE id = $1", request_id)
    if not req:
        return None
    items = await conn.fetch(
        "SELECT * FROM ll_app.product_request_items WHERE request_id = $1 ORDER BY sort_order, id",
        request_id,
    )
    job = None
    if req["job_id"]:
        from app.apis.jobs import ensure_schema as ensure_jobs_schema
        await ensure_jobs_schema(conn)
        job = await conn.fetchrow("SELECT id, name FROM ll_app.jobs WHERE id = $1", req["job_id"])
    return {
        **dict(req),
        "items": [dict(i) for i in items],
        "job_name": job["name"] if job else None,
    }


# ── Models ──────────────────────────────────────────────────────────────────
class RequestCreate(BaseModel):
    client_name: Optional[str] = ""
    project_name: Optional[str] = ""
    deadline: Optional[date] = None
    samples_note: Optional[str] = None


class RequestUpdate(BaseModel):
    client_name: Optional[str] = None
    project_name: Optional[str] = None
    deadline: Optional[date] = None
    samples_note: Optional[str] = None


class ItemIn(BaseModel):
    item: Optional[str] = ""
    used_on: Optional[str] = None
    qty: Optional[str] = None
    match_rule: Optional[str] = None
    description: Optional[str] = None
    quality: Optional[str] = None
    preferred_vendor: Optional[str] = None
    style_color: Optional[str] = None
    catalog_page: Optional[str] = None


class ItemUpdate(ItemIn):
    pass


class LinkIn(BaseModel):
    job_id: Optional[int] = None  # link to this existing job
    create_new: Optional[bool] = None  # or create a new job from the request's header


@router.get("/meta")
async def requests_meta():
    return {"match_rules": MATCH_RULES, "match_labels": MATCH_LABEL, "used_on_options": USED_ON_OPTIONS}


@router.get("/list")
async def list_requests():
    """The Request Form tab's rail: every request, newest first."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        from app.apis.jobs import ensure_schema as ensure_jobs_schema
        await ensure_jobs_schema(conn)
        rows = await conn.fetch("""
            SELECT r.*, j.name AS job_name,
                   (SELECT COUNT(*) FROM ll_app.product_request_items i
                      WHERE i.request_id = r.id AND i.item <> '')::int AS item_count
            FROM ll_app.product_requests r
            LEFT JOIN ll_app.jobs j ON j.id = r.job_id
            ORDER BY r.updated_at DESC
        """)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.get("/open")
async def open_requests():
    """Requests not yet linked to a job — what the Jobs page's picker offers."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await conn.fetch("""
            SELECT r.id, r.client_name, r.project_name, r.deadline, r.updated_at,
                   (SELECT COUNT(*) FROM ll_app.product_request_items i
                      WHERE i.request_id = r.id AND i.item <> '')::int AS item_count
            FROM ll_app.product_requests r
            WHERE r.job_id IS NULL
            ORDER BY r.updated_at DESC
        """)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.get("/for-job/{job_id}")
async def request_for_job(job_id: int):
    """The reference panel a job's board shows: the request that produced it,
    if any (a job can be created without one — pinned straight from the catalog)."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("SELECT id FROM ll_app.product_requests WHERE job_id = $1", job_id)
        if not row:
            return None
        return await _load_request(conn, row["id"])
    finally:
        await conn.close()


@router.post("/create")
async def create_request(body: RequestCreate, request: Request):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow("""
            INSERT INTO ll_app.product_requests (client_name, project_name, deadline, samples_note, created_by)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
        """, body.client_name or "", body.project_name or "", body.deadline, body.samples_note,
             get_request_user_id(request))
        return await _load_request(conn, row["id"])
    finally:
        await conn.close()


@router.get("/{request_id}")
async def get_request(request_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        req = await _load_request(conn, request_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return req
    finally:
        await conn.close()


@router.patch("/{request_id}")
async def update_request(request_id: int, body: RequestUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        fields = body.model_dump(exclude_unset=True)
        sets, params, idx = [], [], 1
        for col in ("client_name", "project_name", "deadline", "samples_note"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col]); idx += 1
        if sets:
            params.append(request_id)
            await conn.execute(
                f"UPDATE ll_app.product_requests SET {', '.join(sets)}, updated_at = now() WHERE id = ${idx}",
                *params)
        req = await _load_request(conn, request_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return req
    finally:
        await conn.close()


@router.post("/{request_id}/save")
async def save_request(request_id: int):
    """The Save button. Every field already autosaves on its own; this just
    stamps saved_at and confirms nothing was lost — safe to call any time."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        if not await conn.fetchval("SELECT 1 FROM ll_app.product_requests WHERE id = $1", request_id):
            raise HTTPException(status_code=404, detail="Request not found")
        await conn.execute(
            "UPDATE ll_app.product_requests SET saved_at = now(), updated_at = now() WHERE id = $1", request_id)
        return await _load_request(conn, request_id)
    finally:
        await conn.close()


@router.delete("/{request_id}")
async def delete_request(request_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await conn.execute("DELETE FROM ll_app.product_requests WHERE id = $1", request_id)
        return {"ok": True}
    finally:
        await conn.close()


# ── Items (the spreadsheet rows) ────────────────────────────────────────────
@router.post("/{request_id}/items")
async def add_item(request_id: int, body: ItemIn):
    """A row. Called as soon as the blank row at the bottom gets an Item
    value and loses focus — the caller doesn't click an 'add' button first."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        if not await conn.fetchval("SELECT 1 FROM ll_app.product_requests WHERE id = $1", request_id):
            raise HTTPException(status_code=404, detail="Request not found")
        order = await conn.fetchval(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM ll_app.product_request_items WHERE request_id = $1",
            request_id)
        row = await conn.fetchrow("""
            INSERT INTO ll_app.product_request_items
                (request_id, item, used_on, qty, match_rule, description, quality,
                 preferred_vendor, style_color, catalog_page, sort_order)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING id
        """, request_id, body.item or "", body.used_on, body.qty, body.match_rule, body.description,
             body.quality, body.preferred_vendor, body.style_color, body.catalog_page, order)
        await _touch(conn, request_id)
        req = await _load_request(conn, request_id)
        req["created_item_id"] = row["id"]
        return req
    finally:
        await conn.close()


@router.patch("/items/{item_id}")
async def update_item(item_id: int, body: ItemUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        request_id = await conn.fetchval(
            "SELECT request_id FROM ll_app.product_request_items WHERE id = $1", item_id)
        if not request_id:
            raise HTTPException(status_code=404, detail="Item not found")
        fields = body.model_dump(exclude_unset=True)
        if "match_rule" in fields and fields["match_rule"] not in (*MATCH_RULES, None, ""):
            raise HTTPException(status_code=400, detail="Unknown match rule")
        sets, params, idx = [], [], 1
        for col in ("item", "used_on", "qty", "match_rule", "description", "quality",
                    "preferred_vendor", "style_color", "catalog_page"):
            if col in fields:
                sets.append(f"{col} = ${idx}"); params.append(fields[col] or ""); idx += 1
        if sets:
            params.append(item_id)
            await conn.execute(
                f"UPDATE ll_app.product_request_items SET {', '.join(sets)} WHERE id = ${idx}", *params)
        await _touch(conn, request_id)
        return await _load_request(conn, request_id)
    finally:
        await conn.close()


@router.delete("/items/{item_id}")
async def delete_item(item_id: int):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "DELETE FROM ll_app.product_request_items WHERE id = $1 RETURNING request_id", item_id)
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        await _touch(conn, row["request_id"])
        return await _load_request(conn, row["request_id"])
    finally:
        await conn.close()


# ── Linking to a Job ─────────────────────────────────────────────────────────
@router.post("/{request_id}/link")
async def link_request(request_id: int, body: LinkIn, request: Request):
    """Charles's 'Load a request' action. Either attaches to a job he already
    has open, or creates a new one seeded from the request's header — same
    job creation the Jobs page itself uses, so it shows up in the rail
    exactly like any other job."""
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        from app.apis.jobs import ensure_schema as ensure_jobs_schema
        await ensure_jobs_schema(conn)
        req = await conn.fetchrow("SELECT * FROM ll_app.product_requests WHERE id = $1", request_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        if req["job_id"]:
            raise HTTPException(status_code=400, detail="This request is already linked to a job")

        job_id = body.job_id
        if not job_id:
            name = " · ".join(x for x in [req["client_name"], req["project_name"]] if x) or "New job"
            job_id = await conn.fetchval("""
                INSERT INTO ll_app.jobs (name, client_name, collection, created_by)
                VALUES ($1, $2, $3, $4) RETURNING id
            """, name, req["client_name"], req["project_name"], get_request_user_id(request))
        elif not await conn.fetchval("SELECT 1 FROM ll_app.jobs WHERE id = $1", job_id):
            raise HTTPException(status_code=404, detail="That job no longer exists")

        await conn.execute(
            "UPDATE ll_app.product_requests SET job_id = $2, updated_at = now() WHERE id = $1",
            request_id, job_id)
        await conn.execute("UPDATE ll_app.jobs SET updated_at = now() WHERE id = $1", job_id)
        return {"job_id": job_id, "request": await _load_request(conn, request_id)}
    finally:
        await conn.close()
