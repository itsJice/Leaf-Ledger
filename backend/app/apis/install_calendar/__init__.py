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
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.libs import install_calendar, schedule_board

router = APIRouter(prefix="/install-calendar")

def _authorized(token: str) -> bool:
    secret = os.getenv("INSTALL_CALENDAR_TOKEN", "")
    return bool(secret) and hmac.compare_digest(token.encode(), secret.encode())


@router.get("/feed.ics", response_class=Response)
async def calendar_feed(token: str = "") -> Response:
    if not _authorized(token):
        raise HTTPException(status_code=404, detail="Not found")
    board = await schedule_board.load_board()
    if board is None:
        raise HTTPException(status_code=404, detail="No published install schedule")
    return Response(
        content=install_calendar.build_ics(board),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300",
                 "Content-Disposition": 'inline; filename="ll-installs.ics"'},
    )
