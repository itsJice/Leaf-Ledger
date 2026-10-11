"""A client group's private, read-only install schedule, behind a share link.

    /api/share/{token}/calendar.ics   subscribe in Google / Apple / Outlook
    /api/share/{token}/schedule.csv   the same visits as a spreadsheet

Like the office calendar feed (app/apis/install_calendar), calendar apps fetch
these without signing in, so this router is in main.PUBLIC_ROUTERS and the
token in the URL is the access control: 256 random bits per link, stored in
``ll_app.client_share_links`` with the group's label, its match rule and a
revoked flag. Unknown, malformed and revoked tokens all 404 the same way.

Each link shows only its own group's locations, and of those only the name,
street address, date, arrive/finish window and install/takedown
(app.libs.client_share). Links are made and revoked by a super admin through
app/apis/client_share_links or scripts/client_share_link.py.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.libs import client_share, install_calendar, schedule_board
from app.libs.db import ensure_schema_once, get_conn

log = logging.getLogger(__name__)

router = APIRouter(prefix="/share")

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.client_share_links (
    id           bigserial PRIMARY KEY,
    token        text NOT NULL UNIQUE,
    label        text NOT NULL,
    name_prefix  text NOT NULL DEFAULT '',
    client_ids   integer[] NOT NULL DEFAULT '{}',
    strip_prefix text NOT NULL DEFAULT '',
    revoked      boolean NOT NULL DEFAULT false,
    revoked_at   timestamptz,
    revoked_by   text,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
"""

#: secrets.token_urlsafe(32) is 43 characters; anything unlike a token never
#: reaches the database.
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
NOT_FOUND = HTTPException(status_code=404, detail="Not found")
HEADERS = {"Cache-Control": "private, max-age=300", "X-Robots-Tag": "noindex, nofollow",
           "Referrer-Policy": "no-referrer"}


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("client_share_links", _ddl)


async def _link(token: str) -> tuple[dict, dict]:
    """``(link, clients)`` for a live token, else 404. ``clients`` is every
    app client's spellings, for renames and client-id rules."""
    if not TOKEN_RE.match(token or ""):
        raise NOT_FOUND
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "SELECT label, name_prefix, client_ids, strip_prefix, revoked "
            "FROM ll_app.client_share_links WHERE token = $1 AND NOT revoked", token)
        if not row or row["revoked"]:
            raise NOT_FOUND
        link = dict(row)
        try:
            clients = [dict(r) for r in await conn.fetch(
                "SELECT id, name, sheet_name, former_names FROM clients")]
        except Exception as e:  # noqa: BLE001 -- board names still work
            log.warning("client share: client lookup skipped: %s", e)
            clients = []
    finally:
        await conn.close()
    return link, clients


def rule_for(link: dict, clients: list[dict]) -> client_share.Rule:
    ids = {int(x) for x in (link.get("client_ids") or [])}
    spellings = set()
    for c in clients:
        if c.get("id") in ids:
            for n in [c.get("name"), c.get("sheet_name"), *(c.get("former_names") or [])]:
                if install_calendar.norm_name(n):
                    spellings.add(install_calendar.norm_name(n))
    return client_share.Rule(name_prefix=link.get("name_prefix") or "",
                             client_names=frozenset(spellings),
                             strip_prefix=link.get("strip_prefix") or "")


async def share_visits(token: str) -> tuple[str, list[client_share.Visit]]:
    link, clients = await _link(token)
    board = await schedule_board.load_board()
    if board is None:
        return link["label"], []
    names = install_calendar.current_names(board, install_calendar.name_aliases(clients))
    return link["label"], client_share.visits(board, rule_for(link, clients), names)


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "schedule"


@router.get("/{token}/calendar.ics", response_class=Response)
async def share_calendar(token: str) -> Response:
    label, vs = await share_visits(token)
    return Response(
        content=client_share.build_ics(label, vs),
        media_type="text/calendar; charset=utf-8",
        headers={**HEADERS, "Content-Disposition": f'inline; filename="tbdg-{_slug(label)}.ics"'},
    )


@router.get("/{token}/schedule.csv", response_class=Response)
async def share_csv(token: str) -> Response:
    label, vs = await share_visits(token)
    return Response(
        content="﻿" + client_share.build_csv(vs),   # BOM: Excel reads the en dash right
        media_type="text/csv; charset=utf-8",
        headers={**HEADERS, "Content-Disposition": f'attachment; filename="tbdg-{_slug(label)}-schedule.csv"'},
    )
