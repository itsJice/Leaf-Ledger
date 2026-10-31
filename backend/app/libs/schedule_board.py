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
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

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
    # Timing inputs for the calendar feed (app.libs.install_calendar): the
    # tool's OSRM matrix (seconds, node 0 = the branch), each client's node,
    # the per-day metadata (window, stacked crews, half rows, depot-anchored),
    # and the stop times the tool itself saved, which win when present.
    node: dict[int, int] = field(default_factory=dict)
    durs: list = field(default_factory=list)
    depot: dict = field(default_factory=dict)
    day_meta: dict[str, dict] = field(default_factory=dict)
    const: dict = field(default_factory=dict)
    timeline: dict[str, dict] = field(default_factory=dict)
    # The build's own crew-days before anything staff did ({id: date, crew,
    # stops}), for naming crews in an older saved state (app.libs.schedule_changes).
    base_days: dict[str, dict] = field(default_factory=dict)
    # Crew names staff gave a shift on the Staffing tab (``state.crewNames``,
    # {shift key: name}; see crewNames in the tool) and the Dallas dates the
    # shift keys are worked out against.
    crew_names: dict[str, str] = field(default_factory=dict)
    dallas: set[str] = field(default_factory=set)
    # Notes staff wrote for a shift on the Staffing tab (``state.shiftNotes``,
    # {shift key: {text, by, at}}; see shiftNotes in the tool), keyed like
    # crew_names. Not a client's install notes, not the build's day note.
    shift_notes: dict[str, dict] = field(default_factory=dict)

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

    def is_dallas_night(self, day: dict) -> bool:
        """The tool's isDallasNight(): a night crew-day on a Dallas date."""
        night = self.const.get("NIGHT")
        win = (self.day_meta.get(day["id"]) or {}).get("win")
        return day["date"] in self.dallas and night is not None and win == night

    def shift_key(self, day: dict) -> str:
        """The tool's shiftKeyOf(): the crew-day's own id. Every Dallas night
        is its own shift, staffed like any day (user, 2026-10-24)."""
        return day["id"]

    def dallas_week_key(self, day: dict) -> Optional[str]:
        """The tool's dallasWeekKeyOf(): the OLD whole-week shift key of a
        Dallas night ('dallas|<run start>|<crew>'), else None. Only read, so
        names and notes saved before Dallas was staffed night by night still
        show on every night of that run."""
        if self.is_dallas_night(day):
            return f"dallas|{dallas_run_start(day['date'], self.dallas)}|{day['crew']}"
        return None

    def joint_groups(self) -> dict[str, list[str]]:
        """The tool's jointShiftGroups(): {day id: every crew-day id in its
        joint shift} for crew-days on one date working exactly the same
        (non-empty) stops -- staffed as ONE shift, so the same people sit on
        each of them. Training days are never joint shifts; Dallas nights follow
        the same rule night by night."""
        by_date: dict[str, list[dict]] = {}
        for d in self.days.values():
            if d.get("crew") == "Training" or not d.get("stops"):
                continue
            by_date.setdefault(d["date"], []).append(d)
        out: dict[str, list[str]] = {}
        for ds in by_date.values():
            by_set: dict[tuple, list[str]] = {}
            for d in ds:
                by_set.setdefault(tuple(sorted(d["stops"])), []).append(d["id"])
            for ids in by_set.values():
                if len(ids) > 1:
                    for i in ids:
                        out[i] = sorted(ids)
        return out

    def crew_name(self, day: dict) -> str:
        """The name staff gave this crew-day's shift, or ''. Training has none."""
        if day.get("crew") == "Training":
            return ""
        name = self.crew_names.get(self.shift_key(day), "")
        wk = None if name else self.dallas_week_key(day)
        return self.crew_names.get(wk, "") if wk else name

    def shift_note(self, day: dict) -> str:
        """The note staff wrote for this crew-day's shift, or ''. A Dallas
        night falls back to a note saved under its run's old week key."""
        n = self.shift_notes.get(self.shift_key(day))
        if not n:
            wk = self.dallas_week_key(day)
            n = self.shift_notes.get(wk) if wk else None
        return n["text"] if n else ""

    def crew_title(self, day: dict) -> str:
        """"Lesly's crew (Crew 1)", or "Crew 1" with no name -- crewTitle()."""
        name, label = self.crew_name(day), self.crew_label(day)
        return f"{name} ({label})" if name else label


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
    title = p.get("title") if p.get("title") in ("Lead", "Lead Assist", "Designer", "General Installer") else "General Installer"
    return {"id": pid, "name": name, "title": title,
            "email": str(p.get("email") or "").strip(), "phone": str(p.get("phone") or "").strip()}


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
CREW_NAME_MAX = 40


def norm_crew_names(raw: Any) -> dict[str, str]:
    """``state.crewNames`` as the tool keeps it (normCrewName): string names,
    whitespace collapsed, trimmed, at most 40 characters; empty ones dropped."""
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str):
                n = " ".join(v.split())[:CREW_NAME_MAX].strip()
                if n:
                    out[k] = n
    return out


SHIFT_NOTE_MAX = 2000


def norm_shift_note_text(v: Any) -> str:
    """The tool's normShiftNoteText(): line endings unified, trailing spaces
    off each line, at most one blank line in a row, trimmed, capped."""
    lines = [ln.rstrip(" \t") for ln in str(v or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:SHIFT_NOTE_MAX]


def norm_shift_notes(raw: Any) -> dict[str, dict]:
    """``state.shiftNotes`` as the tool keeps it (normShiftNote): {text, by,
    at} with cleaned text; a bare string is the text; empty ones dropped."""
    out: dict[str, dict] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            o = {"text": v} if isinstance(v, str) else v
            if not isinstance(k, str) or not isinstance(o, dict):
                continue
            text = norm_shift_note_text(o.get("text") if isinstance(o.get("text"), str) else "")
            if text:
                out[k] = {"text": text,
                          "by": o["by"].strip()[:120] if isinstance(o.get("by"), str) else "",
                          "at": o["at"] if isinstance(o.get("at"), str) else ""}
    return out


def dallas_run_start(day_iso: str, dallas: set[str]) -> str:
    """The first date of the run of back-to-back Dallas dates ``day_iso`` is
    in -- the tool's dallasRunStart()."""
    d = date.fromisoformat(day_iso)
    while (d - timedelta(days=1)).isoformat() in dallas:
        d -= timedelta(days=1)
    return d.isoformat()


def dallas_dates(spec: dict, state: dict) -> set[str]:
    """The build's Mi Cocina nights plus any date staff marked a Dallas night
    since (``state.dallasNights``) -- the tool's isDallasDate()."""
    built = {c.get("date") for c in spec.get("calendar") or []
             if isinstance(c, dict) and c.get("kind") == "dallas_night"}
    added = {d for d in state.get("dallasNights") or [] if isinstance(d, str) and _ISO.fullmatch(d)}
    return built | added


def dallas_night_meta(day_meta: dict, calendar: list, crew: str, night: Any) -> dict:
    """A built Mi Cocina night's meta for a crew-day the build has none for
    (this crew's if it has one, else the first) -- the tool's dallasNightMeta()."""
    dates = {c.get("date") for c in calendar or [] if isinstance(c, dict) and c.get("kind") == "dallas_night"}
    nights = sorted(k for k, v in (day_meta or {}).items()
                    if isinstance(v, dict) and k.split("|")[0] in dates and v.get("win") == night)
    pick = next((k for k in nights if k.split("|")[1:2] == [crew]), nights[0] if nights else None)
    base = day_meta[pick] if pick else {"cat": "M Crowd", "lunchMin": 0,
                                        "winReason": "Dallas night shift, 11 PM start"}
    return {**base, "win": night, "anchored": False, "stacked": 1, "note": "", "half": [],
            "joint": "", "startRow": None, "flags": [], "zones": [], "crew": crew}


#: An extra crew added for a big day ("Crew 4"): kept like the build's own.
EXTRA_CREW = re.compile(r"^Crew [1-9]\d*$")


def derived_day_meta(spec: dict, state: dict, by_day: dict[str, list[int]]) -> dict[str, dict]:
    """Meta for the crew-days the build has none for, as the tool's
    refreshDerivedMeta() works it out: a Dallas night runs like a built Mi
    Cocina night, and a row on two or more crews' cards the same date is a
    joint stop (half hours each, both crews open the night there). Days the
    build has meta for are left alone."""
    meta = spec.get("dayMeta") or {}
    crews = (spec.get("const") or {}).get("CREWS") or ["Crew 1", "Crew 2", "Crew 3"]
    night = (spec.get("const") or {}).get("NIGHT")
    dal = dallas_dates(spec, state)
    on_date: dict[str, list[str]] = {}
    for did in by_day:
        parts = did.split("|")
        if len(parts) == 3:
            on_date.setdefault(parts[0], []).append(did)
    out: dict[str, dict] = {}
    for date, ids in on_date.items():
        labels = sorted({i.split("|")[1] for i in ids})
        for did in ids:
            crew = did.split("|")[1]
            if crew not in crews and not EXTRA_CREW.match(crew):
                continue
            half, partners = [], set()
            for r in by_day[did]:
                others = [o for o in ids if o != did and r in by_day[o]]
                if others:
                    half.append(r)
                    partners.update(f"Crew {labels.index(o.split('|')[1]) + 1}" for o in others)
            if did in meta:
                # Built day: keep its window/timing, but the shared stops follow
                # the board (a joint stop moved onto a built night splits there).
                b = meta[did]
                if half:
                    joint = " + ".join(sorted(partners))
                else:
                    half = [r for r in (b.get("half") or []) if r in by_day[did]]
                    joint = b.get("joint", "") if half else ""
                start = b.get("startRow") if b.get("startRow") in by_day[did] else (half[0] if half else None)
                if half != list(b.get("half") or []) or start != b.get("startRow"):
                    out[did] = {**b, "half": half, "joint": joint, "startRow": start}
                continue
            if date in dal and night is not None:
                m = dallas_night_meta(meta, spec.get("calendar") or [], crew, night)
            elif half:
                m = {"cat": "Standard", "anchored": True, "stacked": 1, "win": (spec.get("const") or {}).get("DAY_CAP"),
                     "lunchMin": (spec.get("const") or {}).get("LUNCH"), "startRow": None}
            else:
                continue
            if half:
                m = {**m, "half": half, "joint": " + ".join(sorted(partners)), "startRow": half[0]}
            out[did] = m
    return out


def resolve(season: str, payload: dict, state: Optional[dict], inherited: Optional[dict] = None) -> Board:
    state = state or {}
    people = state if state.get("roster") else (inherited or {})
    spec = payload.get("spec") or {}

    clients: dict[int, dict] = {}
    for r, c in (payload.get("clients") or {}).items():
        clients[int(r)] = c
    built = set(clients)  # added stops (newClients) keep their own hours
    for c in state.get("newClients") or []:
        try:
            clients.setdefault(int(c["row"]), {**c, "advice": c.get("notes", "")})
        except (KeyError, TypeError, ValueError):
            continue
    # Install hours staff edited on the board (the tool's hoursOverride): the
    # spreadsheet's h26 is baked into the build, so the edit rides in state.
    for r, h in (state.get("hoursOverride") or {}).items():
        try:
            row, hours = int(r), float(h)
        except (TypeError, ValueError):
            continue
        if row in built and 0 < hours <= 24:
            clients[row] = {**clients[row], "h26": hours, "basis": "staff entry"}

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
    built_meta = {k: v for k, v in (spec.get("dayMeta") or {}).items() if isinstance(v, dict)}
    meta = {**built_meta, **derived_day_meta(spec, state, by_day)}
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
        day_notes={k: v.get("note") or "" for k, v in built_meta.items()},
        node={int(r): i for r, i in (payload.get("node") or {}).items()},
        durs=payload.get("durs") or [],
        depot=payload.get("depot") or {},
        day_meta={k: v for k, v in meta.items() if isinstance(v, dict)},
        const=spec.get("const") or {},
        timeline=state.get("timeline") if isinstance(state.get("timeline"), dict) else {},
        base_days={did: {"date": d.get("date"), "crew": d.get("crew"), "stops": list(d.get("stops") or [])}
                   for did, d in base.items()},
        crew_names=norm_crew_names(state.get("crewNames")),
        shift_notes=norm_shift_notes(state.get("shiftNotes")),
        dallas=dallas_dates(spec, state),
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
