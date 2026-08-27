"""Feature-request / bug-report submissions from the floating feedback widget.

Same storage convention as `install_schedule`: an app-owned table in the
`ll_app` schema, created lazily on first use. Unlike install_schedule's
state, each submission is its own row and nobody's document is ever
overwritten -- this is a simple append-only inbox, closer to a support
mailbox than a shared document.

The optional screenshot is stored as a data: URL (base64 PNG) directly in
the row rather than an object-storage bucket. These are user-initiated,
one-at-a-time submissions of a single browser viewport, not bulk uploads,
so the extra moving part (a bucket, its own auth, cleanup policy) isn't
worth it at this scale -- MAX_SCREENSHOT_BYTES keeps any one row small.
"""
import os
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.auth import AuthorizedUser

router = APIRouter(prefix="/feedback")

MAX_MESSAGE_CHARS = 4000
#: ~2MB of base64 -- comfortably covers a full-page screenshot at normal
#: viewport sizes without letting a submission balloon the table.
MAX_SCREENSHOT_BYTES = 3_000_000

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.feature_requests (
    id             bigserial PRIMARY KEY,
    message        text NOT NULL,
    screenshot     text,
    page_path      text,
    user_agent     text,
    submitted_by   text,
    submitted_name text,
    status         text NOT NULL DEFAULT 'new',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feature_requests_created_idx
    ON ll_app.feature_requests (created_at DESC);
"""

_SCHEMA_READY = False


async def get_conn():
    return await asyncpg.connect(
        os.environ.get("DATABASE_URL"), statement_cache_size=0
    )


async def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    await conn.execute(DDL)
    _SCHEMA_READY = True


class FeedbackIn(BaseModel):
    message: str
    screenshot: Optional[str] = None  # data:image/png;base64,....
    page_path: Optional[str] = None


class FeedbackOut(BaseModel):
    id: int
    ok: bool = True


@router.post("", response_model=FeedbackOut)
async def submit_feedback(body: FeedbackIn, request: Request, user: AuthorizedUser) -> FeedbackOut:
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail="Message is too long")

    screenshot = body.screenshot
    if screenshot and len(screenshot) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(status_code=413, detail="Screenshot is too large")
    if screenshot and not screenshot.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Screenshot must be a data: image URL")

    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable") from exc
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "INSERT INTO ll_app.feature_requests "
            "(message, screenshot, page_path, user_agent, submitted_by, submitted_name) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            message,
            screenshot,
            (body.page_path or "")[:500],
            request.headers.get("user-agent", "")[:500],
            user.sub,
            user.display_name,
        )
    finally:
        await conn.close()
    return FeedbackOut(id=row["id"])


class FeedbackRow(BaseModel):
    id: int
    message: str
    has_screenshot: bool
    page_path: Optional[str] = None
    submitted_name: Optional[str] = None
    status: str
    created_at: str


@router.get("", response_model=list[FeedbackRow])
async def list_feedback(limit: int = 100) -> Any:
    """Everyone signed in can read the inbox -- this is a small internal
    team tool, not a multi-tenant product, and every other resource here
    (clients, pricing, the install schedule) is already visible to any
    authenticated user on the same basis."""
    limit = max(1, min(limit, 500))
    try:
        conn = await get_conn()
    except Exception:
        return []
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(
            "SELECT id, message, (screenshot IS NOT NULL) AS has_screenshot, "
            "page_path, submitted_name, status, created_at "
            "FROM ll_app.feature_requests ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    finally:
        await conn.close()
    return [
        FeedbackRow(
            id=r["id"], message=r["message"], has_screenshot=r["has_screenshot"],
            page_path=r["page_path"], submitted_name=r["submitted_name"],
            status=r["status"], created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


ALLOWED_STATUSES = {"new", "done"}


class StatusIn(BaseModel):
    status: str


@router.put("/{feedback_id}", response_model=FeedbackRow)
async def update_feedback_status(feedback_id: int, body: StatusIn) -> Any:
    """Check/uncheck a submission. This is a shared team list (Comments tab,
    every signed-in user), so it's a plain status flip rather than a
    per-user completion record -- one person checking something off marks
    it done for everyone, the same way any of them can see it in the first
    place."""
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable") from exc
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "UPDATE ll_app.feature_requests SET status = $2 WHERE id = $1 "
            "RETURNING id, message, (screenshot IS NOT NULL) AS has_screenshot, "
            "page_path, submitted_name, status, created_at",
            feedback_id, body.status,
        )
    finally:
        await conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No submission with that id")
    return FeedbackRow(
        id=row["id"], message=row["message"], has_screenshot=row["has_screenshot"],
        page_path=row["page_path"], submitted_name=row["submitted_name"],
        status=row["status"], created_at=row["created_at"].isoformat(),
    )


@router.get("/{feedback_id}/screenshot")
async def get_feedback_screenshot(feedback_id: int) -> dict:
    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable") from exc
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "SELECT screenshot FROM ll_app.feature_requests WHERE id = $1", feedback_id
        )
    finally:
        await conn.close()
    if not row or not row["screenshot"]:
        raise HTTPException(status_code=404, detail="No screenshot for this submission")
    return {"screenshot": row["screenshot"]}
