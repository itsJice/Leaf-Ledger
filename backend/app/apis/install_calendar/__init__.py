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

Narrower feeds are the same URL plus ``region`` and/or ``kind`` (same token):

    ...&region=dallas|houston      the crew-days in that city (day_region)
    ...&kind=install|takedown      only that kind of stop (stop_kind)

The schedule page offers three links: ``&region=dallas`` ("TBDG Dallas"),
``&region=houston`` ("TBDG Houston") and the plain feed. ``kind`` is not
offered there, but works (``&region=dallas&kind=takedown`` is "TBDG Dallas
Takedowns"). With neither, the feed is byte-for-byte the one everyone
already subscribes to.
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


async def client_lookup(board: schedule_board.Board) -> tuple[set, dict]:
    """``(storing, names)`` for the board, from one query over the app's
    clients: the board rows whose client is storing with us this season, and
    {row: current name} for clients renamed on the Clients tab since the
    board was built. The board keeps the spelling it was built with, so both
    match it through every spelling the app knows (name, sheet_name,
    former_names) -- the same lookup the schedule page does. Any failure (no
    table, no database) just means no storing lines and the board's own
    names; the feed itself must never break over it."""
    try:
        conn = await db.get_conn()
        try:
            rows = await conn.fetch(
                "SELECT cl.name, cl.sheet_name, cl.former_names, ca.detail FROM clients cl "
                "  LEFT JOIN client_activity ca ON ca.client_id = cl.id "
                "   AND ca.kind = 'christmas_install' AND ca.season = $1",
                str(board.season)[:4],
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001 -- optional enrichment
        log.warning("install calendar: client lookup skipped: %s", e)
        return set(), {}
    rows = [dict(r) for r in rows]
    pairs = []
    for r in rows:
        detail = loads_json(r.get("detail"))
        flag = detail.get("storing") if isinstance(detail, dict) else None
        for n in [r.get("name"), r.get("sheet_name"), *(r.get("former_names") or [])]:
            if n:
                pairs.append((n, flag))
    names = install_calendar.current_names(board, install_calendar.name_aliases(rows))
    return install_calendar.storing_rows(board, pairs), names


def _choice(value: str, allowed: tuple, what: str):
    v = (value or "").strip().lower()
    if not v:
        return None
    if v not in allowed:
        raise HTTPException(status_code=400, detail=f"{what} must be one of: {', '.join(allowed)}")
    return v


@router.get("/feed.ics", response_class=Response)
async def calendar_feed(token: str = "", region: str = "", kind: str = "") -> Response:
    if not _authorized(token):
        raise HTTPException(status_code=404, detail="Not found")
    # Checked only after the token, so a bad value tells a stranger nothing.
    region = _choice(region, install_calendar.REGIONS, "region")
    kind = _choice(kind, install_calendar.KINDS, "kind")
    board = await schedule_board.load_board()
    if board is None:
        raise HTTPException(status_code=404, detail="No published install schedule")
    storing, names = await client_lookup(board)
    return Response(
        content=install_calendar.build_ics(board, storing=storing, names=names, region=region, kind=kind),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300",
                 "Content-Disposition": 'inline; filename="ll-installs.ics"'},
    )
