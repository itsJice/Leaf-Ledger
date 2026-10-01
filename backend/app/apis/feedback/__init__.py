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

Claude reviews: a daily Claude Code run on the office Mac reads the open
submissions and writes a review back onto the row (`claude_status`,
`claude_note`, `claude_link`) through `scripts/claude_comments.py` -- it
talks to the database directly, so there is no API route that writes a
review. People answer a review from the Comments tab (`PUT /{id}/reply`),
which queues the item for Claude's next run.

Claude's notes, the replies and the check-off belong to the owner (any
super_admin -- in practice Justice). Everyone else still sees every submission, but only as
"under review" or "complete": the list strips the review fields for them,
and the routes that change a submission refuse them.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import AuthorizedUser
from app.libs import roles
from app.libs.db import ensure_schema_once, get_conn

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

ALTER TABLE ll_app.feature_requests
    ADD COLUMN IF NOT EXISTS claude_status      text,
    ADD COLUMN IF NOT EXISTS claude_note        text,
    ADD COLUMN IF NOT EXISTS claude_link        text,
    ADD COLUMN IF NOT EXISTS claude_reviewed_at timestamptz,
    ADD COLUMN IF NOT EXISTS reply              text,
    ADD COLUMN IF NOT EXISTS reply_name         text,
    ADD COLUMN IF NOT EXISTS replied_at         timestamptz;
"""

#: What Claude can say about a submission after looking at it.
CLAUDE_REVIEW_STATUSES = {
    "fixed",           # made the change; `claude_link` points at the PR to test
    "needs_approval",  # has a plan, wants a person's OK before building it
    "needs_human",     # too big or too risky for Claude to take on alone
    "unclear",         # can't tell what's being asked; needs more detail
}
#: Set by a person answering a review; Claude picks these up on its next run.
CLAUDE_QUEUE_STATUSES = {"approved", "replied"}

async def is_owner(user) -> bool:
    return await roles.role_of(user) == "super_admin"


async def _require_owner(user: AuthorizedUser) -> None:
    if not await is_owner(user):
        raise HTTPException(status_code=403, detail="Only the owner can change comments")


owner_only = [Depends(_require_owner)]

#: Fields only the owner sees; blanked for everyone else in the list.
OWNER_FIELDS = ("claude_status", "claude_note", "claude_link", "claude_reviewed_at",
                "reply", "reply_name", "replied_at")

#: Column list shared by every query that returns a FeedbackRow.
ROW_COLUMNS = (
    "id, message, (screenshot IS NOT NULL) AS has_screenshot, page_path, "
    "submitted_name, status, created_at, claude_status, claude_note, "
    "claude_link, claude_reviewed_at, reply, reply_name, replied_at"
)

async def ensure_schema(conn):
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("feedback", _ddl)


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
    claude_status: Optional[str] = None
    claude_note: Optional[str] = None
    claude_link: Optional[str] = None
    claude_reviewed_at: Optional[str] = None
    reply: Optional[str] = None
    reply_name: Optional[str] = None
    replied_at: Optional[str] = None


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def to_row(r) -> FeedbackRow:
    return FeedbackRow(
        id=r["id"], message=r["message"], has_screenshot=r["has_screenshot"],
        page_path=r["page_path"], submitted_name=r["submitted_name"],
        status=r["status"], created_at=r["created_at"].isoformat(),
        claude_status=r.get("claude_status"), claude_note=r.get("claude_note"),
        claude_link=r.get("claude_link"), claude_reviewed_at=_iso(r.get("claude_reviewed_at")),
        reply=r.get("reply"), reply_name=r.get("reply_name"), replied_at=_iso(r.get("replied_at")),
    )


@router.get("/access")
async def feedback_access(user: AuthorizedUser) -> dict:
    """Whether the Comments tab shows this person the owner view."""
    return {"owner": await is_owner(user)}


@router.get("", response_model=list[FeedbackRow])
async def list_feedback(user: AuthorizedUser, limit: int = 100) -> Any:
    """Everyone signed in can read the inbox -- this is a small internal
    team tool, not a multi-tenant product, and every other resource here
    (clients, pricing, the install schedule) is already visible to any
    authenticated user on the same basis. Only the owner gets Claude's
    notes and the replies; everyone else gets the submission and its
    open/done status."""
    limit = max(1, min(limit, 500))
    try:
        conn = await get_conn()
    except Exception:
        return []
    try:
        await ensure_schema(conn)
        rows = await conn.fetch(
            f"SELECT {ROW_COLUMNS} "
            "FROM ll_app.feature_requests ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    finally:
        await conn.close()
    out = [to_row(r) for r in rows]
    if not await is_owner(user):
        out = [row.model_copy(update=dict.fromkeys(OWNER_FIELDS)) for row in out]
    return out


ALLOWED_STATUSES = {"new", "done"}


class StatusIn(BaseModel):
    status: str


@router.put("/{feedback_id}", response_model=FeedbackRow, dependencies=owner_only)
async def update_feedback_status(feedback_id: int, body: StatusIn) -> Any:
    """Check/uncheck a submission (owner only). It's a plain status flip
    rather than a per-user completion record -- checking something off
    shows it as complete to everyone who can see the list."""
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
            f"RETURNING {ROW_COLUMNS}",
            feedback_id, body.status,
        )
    finally:
        await conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No submission with that id")
    return to_row(row)


class ReplyIn(BaseModel):
    reply: str = ""
    approve: bool = False


@router.put("/{feedback_id}/reply", response_model=FeedbackRow, dependencies=owner_only)
async def reply_to_claude(feedback_id: int, body: ReplyIn, user: AuthorizedUser) -> Any:
    """Answer Claude's review -- approve its plan, add the missing detail,
    or both. Either way the item goes back in Claude's queue for the next
    daily run, which reads `reply` alongside the original message."""
    reply = (body.reply or "").strip()
    if not reply and not body.approve:
        raise HTTPException(status_code=400, detail="Write a reply or approve the plan")
    if len(reply) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail="Reply is too long")
    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable") from exc
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "UPDATE ll_app.feature_requests SET claude_status = $2, reply = $3, "
            "reply_name = $4, replied_at = now() WHERE id = $1 "
            f"RETURNING {ROW_COLUMNS}",
            feedback_id, "approved" if body.approve else "replied", reply or None,
            user.display_name,
        )
    finally:
        await conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No submission with that id")
    return to_row(row)


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
