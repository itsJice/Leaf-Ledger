"""Install schedule as a subscribable calendar feed, for the business office.

Google Calendar ("Other calendars -> From URL") fetches the feed on its own,
without signing in, so this is the one router main.py leaves off the Supabase
auth dependency (see PUBLIC_ROUTERS there). The secret in the URL is the
access control instead: ``INSTALL_CALENDAR_TOKEN``, compared in constant time.
Unset, the feed does not exist; wrong, it 404s the same way, so the URL
gives nothing away. Rotating the env var revokes every subscribed link.

The feed carries client names, addresses and phone numbers -- share the link
like a password, with the office only.

    /api/install-calendar/feed.ics?token=...

Every crew is in the one feed; each event's title leads with the crew's
emoji (🔴 Crew 1, 🟢 Crew 2, ⚪️ Crew 3) since a subscribed Google calendar
has a single colour.
"""
import hmac
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.libs import db, install_calendar, schedule_board
from app.libs.jsonutil import loads_json

log = logging.getLogger(__name__)

router = APIRouter(prefix="/install-calendar")

def _authorized(token: str) -> bool:
    secret = os.getenv("INSTALL_CALENDAR_TOKEN", "")
    return bool(secret) and hmac.compare_digest(token.encode(), secret.encode())


async def storing_rows(board: schedule_board.Board) -> set:
    """Board rows whose client is storing with us this season -- one query
    for the whole season. Any failure (no table, no database) just means
    the line is left off; the feed itself must never break over it."""
    try:
        conn = await db.get_conn()
        try:
            rows = await conn.fetch(
                "SELECT cl.name, ca.detail FROM client_activity ca "
                "  JOIN clients cl ON cl.id = ca.client_id "
                " WHERE ca.kind = 'christmas_install' AND ca.season = $1",
                str(board.season)[:4],
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001 -- optional enrichment
        log.warning("install calendar: storing lookup skipped: %s", e)
        return set()
    pairs = []
    for r in rows:
        detail = loads_json(r["detail"])
        pairs.append((r["name"], detail.get("storing") if isinstance(detail, dict) else None))
    return install_calendar.storing_rows(board, pairs)


@router.get("/feed.ics", response_class=Response)
async def calendar_feed(token: str = "") -> Response:
    if not _authorized(token):
        raise HTTPException(status_code=404, detail="Not found")
    board = await schedule_board.load_board()
    if board is None:
        raise HTTPException(status_code=404, detail="No published install schedule")
    return Response(
        content=install_calendar.build_ics(board, storing=await storing_rows(board)),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300",
                 "Content-Disposition": 'inline; filename="ll-installs.ics"'},
    )
