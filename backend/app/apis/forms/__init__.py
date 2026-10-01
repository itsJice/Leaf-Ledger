"""Forms -- the Product Purchase Request Form, and any later form, built in.

Replaces the team's Google Form + its responses Sheet. Designers and
installers submit one item per response; the buyer works the responses list,
marking each New -> Ordered -> Received (or Cancelled), which is what the
strikethrough in the Sheet used to mean.

The form is data, not JSX: ll_app.forms / form_sections / form_questions
(seeded from app.libs.forms.PRODUCT_REQUEST_FORM on first use), so a question
can be added or reworded later without a code change. Responses live in
form_responses + form_answers (one row per question answered).

Who can do what: anyone signed in, field logins included, can read a form
and submit it (MIN_ROLE crew -- installers fill this out in the field). The
responses themselves, the status, the accepting switch and the export are
office-staff only. A viewer (the shop TV) can't submit.

Every submission to the Product Request form is also filed as an item on an
open request for its client and project (ll_app.product_requests), which is
what the Jobs page's "Load a request" picker reads -- so a job can pull in
everything asked for on a project, as it could with the old Request Form.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.apis.user_context import get_request_user_id
from app.auth.supabase_auth import get_optional_user
from app.libs import forms as F
from app.libs.db import ensure_schema_once, get_conn
from app.libs.roles import require_role, resolve_role

router = APIRouter(prefix="/forms", tags=["forms"])
MIN_ROLE = "crew"
STAFF = Depends(require_role("staff"))

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.forms (
    id            serial PRIMARY KEY,
    slug          text NOT NULL UNIQUE,
    title         text NOT NULL,
    description   text,
    is_accepting  boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ll_app.form_sections (
    id           serial PRIMARY KEY,
    form_id      integer NOT NULL REFERENCES ll_app.forms(id) ON DELETE CASCADE,
    position     integer NOT NULL,
    title        text NOT NULL,
    description  text
);

CREATE TABLE IF NOT EXISTS ll_app.form_questions (
    id               serial PRIMARY KEY,
    form_id          integer NOT NULL REFERENCES ll_app.forms(id) ON DELETE CASCADE,
    section_id       integer NOT NULL REFERENCES ll_app.form_sections(id) ON DELETE CASCADE,
    position         integer NOT NULL,
    key              text NOT NULL,
    label            text NOT NULL,
    helper_text      text,
    type             text NOT NULL CHECK (type IN ('short_text','long_text','dropdown','radio','checkboxes','date')),
    required         boolean NOT NULL DEFAULT false,
    options          jsonb,
    export_position  integer,
    UNIQUE (form_id, key)
);

CREATE TABLE IF NOT EXISTS ll_app.form_responses (
    id            serial PRIMARY KEY,
    form_id       integer NOT NULL REFERENCES ll_app.forms(id) ON DELETE CASCADE,
    submitted_at  timestamptz NOT NULL DEFAULT now(),
    status        text NOT NULL DEFAULT 'New' CHECK (status IN ('New','Ordered','Received','Cancelled')),
    buyer_notes   text,
    submitted_by  text,
    source        text NOT NULL DEFAULT 'app',
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    text
);
CREATE INDEX IF NOT EXISTS form_responses_form_idx ON ll_app.form_responses (form_id, submitted_at);

CREATE TABLE IF NOT EXISTS ll_app.form_answers (
    response_id  integer NOT NULL REFERENCES ll_app.form_responses(id) ON DELETE CASCADE,
    question_id  integer NOT NULL REFERENCES ll_app.form_questions(id) ON DELETE CASCADE,
    value        jsonb,
    PRIMARY KEY (response_id, question_id)
);
"""


async def seed_form(conn, spec: dict) -> None:
    """Create a form from its spec if it does not exist yet. Never touches an
    existing form: after the first seed, the rows are the source of truth."""
    if await conn.fetchval("SELECT 1 FROM ll_app.forms WHERE slug = $1", spec["slug"]):
        return
    form_id = await conn.fetchval(
        "INSERT INTO ll_app.forms (slug, title, description) VALUES ($1, $2, $3) "
        "ON CONFLICT (slug) DO NOTHING RETURNING id",
        spec["slug"], spec["title"], spec["description"])
    if form_id is None:
        return
    qpos = 0
    for spos, sec in enumerate(spec["sections"], 1):
        sid = await conn.fetchval(
            "INSERT INTO ll_app.form_sections (form_id, position, title, description) "
            "VALUES ($1, $2, $3, $4) RETURNING id", form_id, spos, sec["title"], sec["description"])
        for key, label, helper, qtype, required, options, export_pos in sec["questions"]:
            qpos += 1
            await conn.execute(
                "INSERT INTO ll_app.form_questions (form_id, section_id, position, key, label, helper_text, "
                "type, required, options, export_position) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10)",
                form_id, sid, qpos, key, label, helper, qtype, required,
                json.dumps(options) if options is not None else None, export_pos)


async def ensure_schema(conn):
    async def _ddl():
        await conn.execute(DDL)
        # The Jobs bridge: which form response filed each request item.
        from app.apis.requests import ensure_schema as ensure_requests_schema
        await ensure_requests_schema(conn)
        await conn.execute(
            "ALTER TABLE ll_app.product_request_items ADD COLUMN IF NOT EXISTS form_response_id integer")
        await seed_form(conn, F.PRODUCT_REQUEST_FORM)

    await ensure_schema_once("forms", _ddl)


def _jsonv(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


async def _load_form(conn, slug: str) -> dict:
    form = await conn.fetchrow("SELECT * FROM ll_app.forms WHERE slug = $1", slug)
    if not form:
        raise HTTPException(status_code=404, detail="No such form")
    sections = await conn.fetch(
        "SELECT id, position, title, description FROM ll_app.form_sections WHERE form_id = $1 ORDER BY position",
        form["id"])
    questions = await conn.fetch(
        "SELECT id, section_id, position, key, label, helper_text, type, required, options, export_position "
        "FROM ll_app.form_questions WHERE form_id = $1 ORDER BY position", form["id"])
    return {
        "id": form["id"], "slug": form["slug"], "title": form["title"], "description": form["description"],
        "is_accepting": form["is_accepting"],
        "sections": [dict(s) for s in sections],
        "questions": [{**dict(q), "options": _jsonv(q["options"])} for q in questions],
    }


async def _responses(conn, form: dict) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, submitted_at, status, buyer_notes, submitted_by, source, updated_at, updated_by "
        "FROM ll_app.form_responses WHERE form_id = $1 ORDER BY submitted_at, id", form["id"])
    answers = await conn.fetch(
        "SELECT a.response_id, q.key, a.value FROM ll_app.form_answers a "
        "JOIN ll_app.form_responses r ON r.id = a.response_id "
        "JOIN ll_app.form_questions q ON q.id = a.question_id WHERE r.form_id = $1", form["id"])
    by = {}
    for a in answers:
        by.setdefault(a["response_id"], {})[a["key"]] = _jsonv(a["value"])
    return [{**dict(r), "answers": by.get(r["id"], {})} for r in rows]


# ── the form ─────────────────────────────────────────────────────────────────


@router.get("/{slug}")
async def get_form(slug: str):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        return await _load_form(conn, slug)
    finally:
        await conn.close()


class SubmitIn(BaseModel):
    answers: dict


MATCH_RULE_BY_OPTION = dict(zip(F.MATCH_OPTIONS, ("exact", "similar", "inspiration")))


async def _file_on_request(conn, response_id: int, a: dict, user: Optional[str]) -> None:
    """File a Product Request response as an item on the open request for its
    client + project (creating one), for the Jobs page's "Load a request"."""
    client, project = a.get("client_name") or "", a.get("project_name") or ""
    rid = await conn.fetchval(
        "SELECT id FROM ll_app.product_requests WHERE job_id IS NULL "
        "AND lower(trim(client_name)) = lower(trim($1)) AND lower(trim(project_name)) = lower(trim($2)) "
        "ORDER BY updated_at DESC LIMIT 1", client, project)
    install = a.get("install_date")
    install = _dt.date.fromisoformat(install[:10]) if install else None
    if rid is None:
        rid = await conn.fetchval(
            "INSERT INTO ll_app.product_requests (client_name, project_name, deadline, samples_note, saved_at, created_by) "
            "VALUES ($1, $2, $3, $4, now(), $5) RETURNING id",
            client, project, install, ", ".join(a.get("samples_pictures") or []) or None, user)
    elif install:
        await conn.execute(
            "UPDATE ll_app.product_requests SET deadline = LEAST(COALESCE(deadline, $2), $2), updated_at = now() "
            "WHERE id = $1", rid, install)
    pos = await conn.fetchval(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM ll_app.product_request_items WHERE request_id = $1", rid)
    await conn.execute(
        "INSERT INTO ll_app.product_request_items (request_id, item, qty, match_rule, description, quality, "
        "preferred_vendor, style_color, catalog_page, sort_order, form_response_id) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
        rid, a.get("location_item") or "", a.get("quantity_needed"),
        MATCH_RULE_BY_OPTION.get(a.get("match_existing")), a.get("product_description"),
        a.get("most_important_quality"), a.get("preferred_vendor"), a.get("style_number_color"),
        a.get("catalog_page"), pos, response_id)


@router.post("/{slug}/responses")
async def submit(slug: str, body: SubmitIn, request: Request):
    signed_in = get_optional_user(request)
    email = signed_in.email if signed_in else None
    if email and await resolve_role(email) == "viewer":
        raise HTTPException(status_code=403, detail="This login can't submit forms")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        form = await _load_form(conn, slug)
        if not form["is_accepting"]:
            raise HTTPException(status_code=409, detail="This form is no longer accepting responses")
        qs = form["questions"]
        answers = {q["key"]: F.clean_value(q, body.answers.get(q["key"])) for q in qs}
        errors = F.validate(qs, answers)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO ll_app.form_responses (form_id, submitted_by) VALUES ($1, $2) "
                "RETURNING id, submitted_at", form["id"], email)
            for q in qs:
                if answers.get(q["key"]) is not None:
                    await conn.execute(
                        "INSERT INTO ll_app.form_answers (response_id, question_id, value) VALUES ($1, $2, $3::jsonb)",
                        row["id"], q["id"], json.dumps(answers[q["key"]]))
            if slug == F.PRODUCT_REQUEST_SLUG:
                await _file_on_request(conn, row["id"], answers, email)
        return {"id": row["id"], "submitted_at": row["submitted_at"]}
    finally:
        await conn.close()


#: Type-ahead sources. The same client/project/vendor gets typed many ways
#: ("Sims, Darcy" / "Sims,Darcy" / "sims"); suggesting what is already there
#: is what stops that, without ever rewriting an answer already stored.
SUGGEST_KEYS = ("client_name", "project_name", "preferred_vendor")


@router.get("/{slug}/suggestions")
async def suggestions(slug: str):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        form = await _load_form(conn, slug)
        out = {}
        for key in SUGGEST_KEYS:
            rows = await conn.fetch(
                "SELECT trim(a.value #>> '{}') AS v, max(r.submitted_at) AS last, count(*) AS n "
                "FROM ll_app.form_answers a JOIN ll_app.form_questions q ON q.id = a.question_id "
                "JOIN ll_app.form_responses r ON r.id = a.response_id "
                "WHERE q.form_id = $1 AND q.key = $2 AND trim(a.value #>> '{}') <> '' "
                "GROUP BY trim(a.value #>> '{}') ORDER BY max(r.submitted_at) DESC LIMIT 200",
                form["id"], key)
            out[key] = [r["v"] for r in rows]
        # Client names the app already knows, after the ones used on this form.
        try:
            known = await conn.fetch("SELECT name FROM clients ORDER BY updated_at DESC NULLS LAST LIMIT 500")
            seen = {v.lower() for v in out["client_name"]}
            out["client_name"] += [r["name"] for r in known if r["name"].lower() not in seen]
        except Exception:  # noqa: BLE001 -- suggestions are a convenience
            pass
        return out
    finally:
        await conn.close()


# ── responses (office staff) ─────────────────────────────────────────────────


@router.get("/{slug}/responses", dependencies=[STAFF])
async def list_responses(slug: str):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        form = await _load_form(conn, slug)
        return {"form": form, "responses": await _responses(conn, form)}
    finally:
        await conn.close()


class ResponseUpdate(BaseModel):
    status: Optional[str] = None
    buyer_notes: Optional[str] = None


@router.patch("/responses/{response_id}", dependencies=[STAFF])
async def update_response(response_id: int, body: ResponseUpdate, request: Request):
    if body.status is not None and body.status not in F.STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(F.STATUSES)}")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "UPDATE ll_app.form_responses SET "
            "status = COALESCE($2, status), "
            "buyer_notes = CASE WHEN $3::text IS NOT NULL THEN NULLIF(trim($3), '') ELSE buyer_notes END, "
            "updated_at = now(), updated_by = $4 WHERE id = $1 "
            "RETURNING id, status, buyer_notes, updated_at, updated_by",
            response_id, body.status, body.buyer_notes, get_request_user_id(request))
        if not row:
            raise HTTPException(status_code=404, detail="No such response")
        return dict(row)
    finally:
        await conn.close()


class FormUpdate(BaseModel):
    is_accepting: Optional[bool] = None


@router.patch("/{slug}", dependencies=[STAFF])
async def update_form(slug: str, body: FormUpdate):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "UPDATE ll_app.forms SET is_accepting = COALESCE($2, is_accepting), updated_at = now() "
            "WHERE slug = $1 RETURNING is_accepting", slug, body.is_accepting)
        if not row:
            raise HTTPException(status_code=404, detail="No such form")
        return {"slug": slug, "is_accepting": row["is_accepting"]}
    finally:
        await conn.close()


@router.get("/{slug}/export.csv", dependencies=[STAFF])
async def export_csv(slug: str):
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        form = await _load_form(conn, slug)
        body = F.export_csv(form["questions"], await _responses(conn, form))
    finally:
        await conn.close()
    name = f"{form['title']} (Responses).csv".replace('"', "")
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
