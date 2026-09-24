"""The install board as staff see it right now, read server-side.

The install schedule tool is a published HTML page (its dataset embedded as
``const DATA = {...}``) plus one shared state document per build holding what
staff changed: which stop sits on which crew-day, manual stop order, the
roster and who is staffed where. The lead pages need the same answer the tool
shows, so this module reads both and resolves them -- the backend twin of
``scheduler/board_state.py`` (``extract_payload``, ``name_map``,
``board_placement``), kept deliberately small. If the tool's state shape
changes, change both.

The page is several MB, so a resolved board is cached for ``CACHE_TTL_S``.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from app.libs import roles
from app.libs import db
from app.libs.jsonutil import loads_json

PAYLOAD_MARK = "const DATA = "
CACHE_TTL_S = 30.0
_cache: dict[str, tuple[float, "Board"]] = {}


@dataclass
class Board:
    season: str
    version: Optional[str]
    clients: dict[int, dict] = field(default_factory=dict)
    days: dict[str, dict] = field(default_factory=dict)
    roster: list[dict] = field(default_factory=list)
    staffing: dict[str, list[str]] = field(default_factory=dict)
    comments: dict[str, list] = field(default_factory=dict)
    day_notes: dict[str, str] = field(default_factory=dict)

    def person(self, pid: str) -> Optional[dict]:
        return next((p for p in self.roster if p["id"] == pid), None)

    def person_for_email(self, email: str) -> Optional[dict]:
        e = roles.norm_email(email)
        if not e:
            return None
        return next((p for p in self.roster if roles.norm_email(p.get("email")) == e), None)

    def lead_of(self, day_id: str) -> Optional[dict]:
        for pid in self.staffing.get(day_id, []):
            p = self.person(pid)
            if p and p.get("title") == "Lead":
                return p
        return None

    def days_led_by(self, pid: str) -> list[dict]:
        return sorted(
            (d for d in self.days.values()
             if (lead := self.lead_of(d["id"])) and lead["id"] == pid),
            key=lambda d: (d["date"], d["id"]),
        )

    def crew_label(self, day: dict) -> str:
        """Crew numbers are positional per date (see crewLabel() in the tool)."""
        on_date = sorted({d["crew"] for d in self.days.values() if d["date"] == day["date"]})
        return f"Crew {on_date.index(day['crew']) + 1}" if day["crew"] in on_date else day["crew"]


def extract_payload(html: str) -> dict:
    i = html.find(PAYLOAD_MARK)
    if i < 0:
        raise ValueError("no embedded DATA payload -- not a review tool page")
    obj, _ = json.JSONDecoder().raw_decode(html[i + len(PAYLOAD_MARK):])
    return obj


def _norm_person(p: dict) -> Optional[dict]:
    """The fields the lead pages need, normalised like normRoster() does."""
    if not isinstance(p, dict):
        return None
    first, last = str(p.get("first") or "").strip(), str(p.get("last") or "").strip()
    if not first and not last:
        parts = str(p.get("name") or "").split()
        first, last = (parts[0] if parts else ""), " ".join(parts[1:])
    pid, name = str(p.get("id") or ""), " ".join(x for x in (first, last) if x)
    if not pid or not name:
        return None
    title = p.get("title") if p.get("title") in ("Lead", "Lead Assist", "General Installer") else "General Installer"
    return {"id": pid, "name": name, "title": title,
            "email": str(p.get("email") or "").strip(), "phone": str(p.get("phone") or "").strip()}


def resolve(season: str, payload: dict, state: Optional[dict], inherited: Optional[dict] = None) -> Board:
    state = state or {}
    people = state if state.get("roster") else (inherited or {})
    spec = payload.get("spec") or {}

    clients: dict[int, dict] = {}
    for r, c in (payload.get("clients") or {}).items():
        clients[int(r)] = c
    for c in state.get("newClients") or []:
        try:
            clients.setdefault(int(c["row"]), {**c, "advice": c.get("notes", "")})
        except (KeyError, TypeError, ValueError):
            continue

    base = {d["id"]: d for d in payload.get("days") or []}
    if state.get("placement"):
        placement = {int(r): list(ids) for r, ids in state["placement"].items()}
    else:
        placement = {}
        for d in base.values():
            for r in d.get("stops") or []:
                placement.setdefault(int(r), []).append(d["id"])

    by_day: dict[str, list[int]] = {}
    for r, ids in placement.items():
        for did in ids:
            by_day.setdefault(did, []).append(r)

    manual = state.get("manualOrder") or {}
    meta = spec.get("dayMeta") or {}
    days: dict[str, dict] = {}
    for did, rows in by_day.items():
        try:
            date, crew, _ = did.split("|")
        except ValueError:
            continue
        order = [int(x) for x in (manual.get(did) or (base.get(did) or {}).get("stops") or [])]
        start = (meta.get(did) or {}).get("startRow")
        if not manual.get(did) and start in rows:
            order = [start] + [r for r in order if r != start]
        stops = [r for r in order if r in rows] + sorted(r for r in rows if r not in order)
        days[did] = {"id": did, "date": date, "crew": crew,
                     "stops": [r for r in stops if r in clients]}

    roster = [p for p in (_norm_person(x) for x in (people.get("roster") or spec.get("rosterSeed") or [])) if p]
    known = {p["id"] for p in roster}
    staffing = {}
    for did, ids in (people.get("staffing") or {}).items():
        keep = [str(x) for x in (ids or []) if str(x) in known]
        if did in days and keep:
            staffing[did] = list(dict.fromkeys(keep))

    return Board(
        season=season,
        version=spec.get("version"),
        clients=clients,
        days=days,
        roster=roster,
        staffing=staffing,
        comments=state.get("comments") or {},
        day_notes={k: v.get("note") or "" for k, v in meta.items() if isinstance(v, dict)},
    )


async def load_board(season: Optional[str] = None, *, fresh: bool = False) -> Optional[Board]:
    """The resolved board for ``season`` (default: newest published)."""
    key = season or "__latest__"
    hit = _cache.get(key)
    if hit and not fresh and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]

    from app.apis import install_schedule as sched

    conn = await db.get_conn()
    try:
        await sched.ensure_schema(conn)
        if season is None:
            season = await sched._latest_published_season(conn, "index.html")
            if not season:
                return None
        row = await conn.fetchrow(
            "SELECT html FROM ll_app.install_schedule_pages WHERE season = $1 AND name = 'index.html'",
            season,
        )
        if not row:
            return None
        # Multi-MB JSON parse: off the event loop so other requests keep moving.
        payload = await asyncio.to_thread(extract_payload, row["html"])
        version = (payload.get("spec") or {}).get("version")
        state, inherited = None, None
        if version:
            srow = await conn.fetchrow(
                "SELECT state FROM ll_app.install_schedule_state WHERE version = $1", version
            )
            state = loads_json(srow["state"]) if srow else None
            if not (state or {}).get("roster"):
                inherited = await sched._inheritable_people(conn, version, season)
    finally:
        await conn.close()

    board = resolve(season, payload, state, inherited)
    _cache[key] = (time.monotonic(), board)
    return board


def clear_cache() -> None:
    _cache.clear()


async def roster_person_for_email(email: str) -> Optional[dict]:
    board = await load_board()
    return board.person_for_email(email) if board else None
