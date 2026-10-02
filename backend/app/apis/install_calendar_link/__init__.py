"""The install calendar's subscribe link, for office staff.

The feed itself (``app.apis.install_calendar``) is public behind a URL
secret, because Google Calendar fetches it without signing in. This router
is the signed-in way to *get* that URL: the schedule tool's Export dialog
calls it to show a "Subscribe in Google Calendar" link with a copy button.

It is its own router, not a route on the public one, so main.py puts the
normal sign-in and role check in front of it. ``MIN_ROLE = "staff"`` and no
``VIEWER_READ``: leads, crew and the warehouse viewer get a 403, and
production's allowlist (app.libs.roles.PRODUCTION_READ) has no entry for
this path, so it is refused too. The URL carries client names, addresses and
phone numbers once followed -- it must only ever reach office staff.
"""
import os
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/install-calendar-link")

MIN_ROLE = "staff"

FEED_PATH = "/api/install-calendar/feed.ics"


def _origin(request: Request) -> str:
    """The app's public origin. Behind Render's proxy the request reaches us
    as plain http, so the forwarded headers win when present."""
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host")
            or request.url.netloc).split(",")[0].strip()
    return f"{proto}://{host}"


@router.get("/feed-url")
async def feed_url(request: Request) -> dict:
    token = os.getenv("INSTALL_CALENDAR_TOKEN", "")
    if not token:
        raise HTTPException(status_code=404, detail="The calendar feed is not set up")

    return {"url": f"{_origin(request)}{FEED_PATH}?token={quote(token, safe='')}"}
