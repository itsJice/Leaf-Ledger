"""Super-admin management of client share links (app/apis/client_share).

    GET  /api/client-share-links               list every link
    POST /api/client-share-links               make one; the answer carries its URLs
    POST /api/client-share-links/{id}/revoke   switch one off (its URLs then 404)

A link's rule picks its clients: ``name_prefix`` (board names starting with
it, any case, e.g. "M Crowd ") and/or ``client_ids`` (app client ids).
``strip_prefix`` comes off the front of each shown name. Revoking is final;
make a new link to share again.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.apis import client_share as share_api
from app.auth import AuthorizedUser
from app.libs import roles
from app.libs.db import get_conn

router = APIRouter(prefix="/client-share-links", tags=["client-share-links"])

#: The links are secrets that show client addresses; owner only.
MIN_ROLE = "super_admin"
only_owner = [Depends(roles.require_role("super_admin"))]

COLUMNS = ("id, token, label, name_prefix, client_ids, strip_prefix, revoked, "
           "revoked_at, created_by, created_at")


class ShareLinkIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    name_prefix: str = Field(default="", max_length=80)
    client_ids: list[int] = Field(default_factory=list, max_length=500)
    strip_prefix: str = Field(default="", max_length=80)


class ShareLinkOut(BaseModel):
    id: int
    label: str
    name_prefix: str
    client_ids: list[int]
    strip_prefix: str
    revoked: bool
    revoked_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    calendar_path: Optional[str] = None   # None once revoked
    csv_path: Optional[str] = None


def paths(token: str) -> tuple[str, str]:
    return f"/api/share/{token}/calendar.ics", f"/api/share/{token}/schedule.csv"


def _out(row) -> ShareLinkOut:
    r = dict(row)
    ics, csv_ = paths(r["token"]) if not r["revoked"] else (None, None)
    return ShareLinkOut(id=r["id"], label=r["label"], name_prefix=r["name_prefix"] or "",
                        client_ids=list(r["client_ids"] or []), strip_prefix=r["strip_prefix"] or "",
                        revoked=r["revoked"], revoked_at=r.get("revoked_at"),
                        created_by=r.get("created_by"), created_at=r.get("created_at"),
                        calendar_path=ics, csv_path=csv_)


def validate(body: ShareLinkIn) -> ShareLinkIn:
    label = " ".join(body.label.split())
    prefix = body.name_prefix if body.name_prefix.strip() else ""
    if not label:
        raise HTTPException(status_code=422, detail="A label is required")
    # A short prefix ("M") would sweep in other clients.
    if prefix and len(prefix.strip()) < 3:
        raise HTTPException(status_code=422, detail="The name prefix must be at least 3 characters")
    if not prefix and not body.client_ids:
        raise HTTPException(status_code=422, detail="Give a name prefix or client ids")
    return ShareLinkIn(label=label, name_prefix=prefix, client_ids=sorted(set(body.client_ids)),
                       strip_prefix=body.strip_prefix)


@router.get("", dependencies=only_owner)
async def list_share_links() -> list[ShareLinkOut]:
    conn = await get_conn()
    try:
        await share_api.ensure_schema(conn)
        rows = await conn.fetch(f"SELECT {COLUMNS} FROM ll_app.client_share_links ORDER BY created_at DESC, id DESC")
    finally:
        await conn.close()
    return [_out(r) for r in rows]


@router.post("", dependencies=only_owner)
async def create_share_link(body: ShareLinkIn, user: AuthorizedUser) -> ShareLinkOut:
    body = validate(body)
    conn = await get_conn()
    try:
        await share_api.ensure_schema(conn)
        row = await conn.fetchrow(
            "INSERT INTO ll_app.client_share_links "
            "(token, label, name_prefix, client_ids, strip_prefix, created_by) "
            f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {COLUMNS}",
            secrets.token_urlsafe(32), body.label, body.name_prefix, body.client_ids,
            body.strip_prefix, user.email)
    finally:
        await conn.close()
    return _out(row)


@router.post("/{link_id}/revoke", dependencies=only_owner)
async def revoke_share_link(link_id: int, user: AuthorizedUser) -> ShareLinkOut:
    conn = await get_conn()
    try:
        await share_api.ensure_schema(conn)
        row = await conn.fetchrow(
            "UPDATE ll_app.client_share_links SET revoked = true, "
            "revoked_at = COALESCE(revoked_at, now()), revoked_by = COALESCE(revoked_by, $2) "
            f"WHERE id = $1 RETURNING {COLUMNS}", link_id, user.email)
    finally:
        await conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No such share link")
    return _out(row)
