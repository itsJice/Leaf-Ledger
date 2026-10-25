"""The Install Schedule's "Changes" feed: what changed on the board, in words.

Comment #19 asked for an email to the office whenever the schedule changes,
"so we don't have to look at all events everyday". The user's answer
(2026-10-12) was a change list instead: anyone can open it, follow it, and
see what's new since they last looked.

There is no change log to read. The tool saves its whole shared state on
every edit (``ll_app.install_schedule_history``, one row per save, newest 200
per build), so the feed is a diff of each saved state against the one before
it. The state's ``timeline`` key is NOT a log -- it is the stop times the
tool computed at save time -- and its ``moves`` list has no who or when, so
neither is reused as the source; ``timeline`` is only read to spot arrival
times that shifted.

Everything here is pure: callers hand in the published payload's clients and
base days, plus history rows, and get plain-language events back. Names are
resolved the way ``app.libs.schedule_board`` resolves them (payload clients,
then the tool's own ``newClients``; roster people through ``_norm_person``),
and crew numbers are positional per date, like ``crewLabel()`` in the tool.

What counts as a change (``type`` is the filter group the page offers):

    moves     a client moved date or crew, a whole crew-day moved, stop order,
              arrival times that shifted by 30 minutes or more
    adds      a client added to or taken off the board
    holds     put on / taken off hold; not installing / back on the schedule
    approvals a crew-day approved or un-approved; a date confirmed with the
              client
    staffing  a person added to or taken off a crew-day
    locks     a stop's First / Middle / Last position lock
    dates     dates added or removed, training days, crews added or removed

Left out on purpose: roster edits (availability, ratings, phones), comments,
view toggles and anything else that isn't the schedule itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

try:
    from zoneinfo import ZoneInfo

    CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - tzdata missing
    CENTRAL = timezone(timedelta(hours=-6))

TYPES = ("moves", "adds", "holds", "approvals", "staffing", "locks", "dates")

#: Arrival times that move less than this are routing noise, not news.
TIME_SHIFT_MIN = 30
#: One save that would take more lines than this to describe was a bulk edit
#: (a restore, a rebuild remap). It is summarised as one line instead.
BULK_LIMIT = 15
#: Same idea for a whole save: more lines than this, of any kind, is a restore
#: or a script's bulk edit, and reads as one line.
SAVE_LIMIT = 12
#: A person added to more crew-days than this in one save reads as one line.
STAFF_COLLAPSE = 3

PIN_SHORT = {"first": "First", "middle": "Middle", "last": "Last"}

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


# ─── Formatting ──────────────────────────────────────────────────────────────

def fmt_day(iso: str) -> str:
    """'2026-11-07' -> 'Sat 11/7'."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)
    return f"{d.strftime('%a')} {d.month}/{d.day}"


def fmt_clock(minutes: float) -> str:
    """Minutes after midnight (night shifts run past 1440) -> '9:15 AM'."""
    m = int(round(minutes)) % 1440
    h, mm = divmod(m, 60)
    return f"{(h % 12) or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def central(at: datetime) -> datetime:
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(CENTRAL)


def fmt_time_ct(at: datetime) -> str:
    """'4:02 PM' in Central time (the page adds 'CT' where it fits)."""
    c = central(at)
    return f"{(c.hour % 12) or 12}:{c.minute:02d} {'AM' if c.hour < 12 else 'PM'}"


# ─── Who saved it ────────────────────────────────────────────────────────────

def is_login_id(writer: Optional[str]) -> bool:
    return bool(writer and _UUID.match(writer.strip()))


def script_writer_name(writer: Optional[str]) -> Optional[str]:
    """A readable name for a save made by a script, or None for a login id.

    Scripts label their saves (``claude-1099-import``, ``claude:takedown``,
    ``claude (requested by Justice): ...``, ``roster-import``). Those labels
    are for rollback, not for reading, so they become "Claude (import)",
    "Claude", "Claude (for Justice)", "Import" and so on.
    """
    w = (writer or "").strip()
    if not w:
        return "Someone"
    if is_login_id(w):
        return None
    low = w.lower()
    if low.startswith("claude"):
        asked = re.search(r"requested by ([A-Za-z][A-Za-z .'-]{0,30}?)\s*[):]", w)
        if asked:
            return f"Claude (for {asked.group(1).strip()})"
        if "import" in low:
            return "Claude (import)"
        return "Claude"
    if low.startswith("restore"):
        return "Restore"
    if "import" in low:
        return "Import"
    if low == "local-dev-user":
        return "Local test"
    return "Script"


def login_display_name(email: Optional[str], full_name: Optional[str], roster_name: Optional[str]) -> str:
    """A login's name without its email: the roster name for that email, the
    account's own full name, else the part before the @, capitalised."""
    if roster_name:
        return roster_name
    if full_name and full_name.strip():
        return full_name.strip()
    local = (email or "").split("@")[0]
    local = re.sub(r"[._-]+", " ", local).strip()
    return local.title() if local else "Someone"


# ─── The schedule as one saved state saw it ──────────────────────────────────

@dataclass
class Context:
    """What the published page knows, for naming things in every state."""
    clients: dict[int, str] = field(default_factory=dict)       # row -> name
    base_days: dict[str, dict] = field(default_factory=dict)    # day id -> {date, crew}
    people: dict[str, str] = field(default_factory=dict)        # person id -> name
    dallas: set[str] = field(default_factory=set)               # the build's Dallas night dates


def _row(x: Any) -> Optional[int]:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _split_day(did: str) -> tuple[str, str]:
    parts = str(did).split("|")
    return (parts[0], parts[1]) if len(parts) >= 2 else (str(did), "")


@dataclass
class View:
    """One saved state, resolved enough to compare against another."""
    placement: dict[int, tuple[str, ...]]
    crews_on: dict[str, list[str]]          # date -> sorted crew names in use
    approved: set[str]
    confirmed: set[int]
    hold: set[int]
    not_installing: set[int]
    pins: dict[int, str]
    staffing: dict[str, tuple[str, ...]]
    new_dates: set[str]
    training: set[str]
    manual: dict[str, tuple[int, ...]]
    times: dict[tuple[str, int], float]     # (day id, row) -> arrival minutes
    last_from: dict[int, dict]
    has_placement: bool
    crew_names: dict[str, str] = field(default_factory=dict)  # state.crewNames
    dallas: set[str] = field(default_factory=set)

    def label(self, did: str) -> str:
        """The positional crew number. Comparisons use this, never title(),
        so renaming a crew never reads as a stop changing crews."""
        d, crew = _split_day(did)
        on = self.crews_on.get(d) or []
        return f"Crew {on.index(crew) + 1}" if crew in on else (crew or "a crew")

    def title(self, did: str) -> str:
        """'Lesly's crew (Crew 1)' when staff named the crew, else label().
        A Dallas night is keyed by its own id like any day; a name saved under
        its run's old week key is the fallback (the tool's dallasWeekKeyOf(),
        without the night-window check this view has no meta for)."""
        from app.libs.schedule_board import dallas_run_start

        d, crew = _split_day(did)
        name = self.crew_names.get(str(did), "")
        if not name and d in self.dallas and crew:
            name = self.crew_names.get(f"dallas|{dallas_run_start(d, self.dallas)}|{crew}", "")
        return f"{name} ({self.label(did)})" if name else self.label(did)

    def where(self, ids: Iterable[str]) -> str:
        """'Fri 11/13, Crew 1', or 'Fri 11/13, Crew 1 + Crew 2' for a joint stop."""
        ids = sorted(ids)
        if not ids:
            return "no date"
        dates = sorted({_split_day(i)[0] for i in ids})
        crews = " + ".join(self.title(i) for i in ids)
        return f"{' / '.join(fmt_day(d) for d in dates)}, {crews}"

    def where_paren(self, ids: Iterable[str]) -> str:
        """'Fri 11/13 (Crew 1)', for either side of an arrow."""
        ids = sorted(ids)
        dates = sorted({_split_day(i)[0] for i in ids})
        return f"{' / '.join(fmt_day(d) for d in dates)} ({' + '.join(self.title(i) for i in ids)})"

    def dates_of(self, ids: Iterable[str]) -> list[str]:
        return sorted({_split_day(i)[0] for i in ids})


def view_of(state: Optional[dict], ctx: Context) -> View:
    from app.libs.schedule_board import norm_crew_names

    s = state if isinstance(state, dict) else {}
    raw = s.get("placement")
    has_placement = isinstance(raw, dict) and bool(raw)
    placement: dict[int, tuple[str, ...]] = {}
    if has_placement:
        for r, ids in raw.items():
            rr = _row(r)
            if rr is not None and isinstance(ids, list) and ids:
                placement[rr] = tuple(sorted(str(i) for i in ids))
    else:
        tmp: dict[int, list[str]] = {}
        for did, d in ctx.base_days.items():
            for r in d.get("stops") or []:
                rr = _row(r)
                if rr is not None:
                    tmp.setdefault(rr, []).append(did)
        placement = {r: tuple(sorted(v)) for r, v in tmp.items()}

    day_ids = set(ctx.base_days) | {i for ids in placement.values() for i in ids}
    crews_on: dict[str, set[str]] = {}
    for did in day_ids:
        d, crew = _split_day(did)
        if crew:
            crews_on.setdefault(d, set()).add(crew)

    def rows(key: str) -> set[int]:
        return {r for r in (_row(x) for x in (s.get(key) or [])) if r is not None}

    pins = {}
    for r, pos in (s.get("stopPin") or {}).items():
        rr = _row(r)
        if rr is not None and pos in PIN_SHORT:
            pins[rr] = pos
    staffing = {
        str(did): tuple(dict.fromkeys(str(p) for p in (ids or [])))
        for did, ids in (s.get("staffing") or {}).items()
        if isinstance(ids, list) and ids
    }
    manual = {
        str(did): tuple(r for r in (_row(x) for x in (order or [])) if r is not None)
        for did, order in (s.get("manualOrder") or {}).items()
        if isinstance(order, list)
    }
    times: dict[tuple[str, int], float] = {}
    for did, t in (s.get("timeline") or {}).items():
        for stop in (t or {}).get("stops") or [] if isinstance(t, dict) else []:
            rr = _row(stop.get("row")) if isinstance(stop, dict) else None
            if rr is not None and isinstance(stop.get("start"), (int, float)):
                times[(str(did), rr)] = float(stop["start"])
    last_from = {}
    for r, info in (s.get("lastScheduledFrom") or {}).items():
        rr = _row(r)
        if rr is not None and isinstance(info, dict):
            last_from[rr] = info
    return View(
        placement=placement,
        crews_on={d: sorted(c) for d, c in crews_on.items()},
        approved={str(x) for x in (s.get("approved") or [])},
        confirmed=rows("confirmed"),
        hold=rows("hold"),
        not_installing=rows("notInstalling"),
        pins=pins,
        staffing=staffing,
        new_dates={str(x) for x in (s.get("newDates") or [])},
        training={str(x) for x in (s.get("trainingDays") or [])},
        manual=manual,
        times=times,
        last_from=last_from,
        has_placement=has_placement or bool(ctx.base_days),
        crew_names=norm_crew_names(s.get("crewNames")),
        dallas=set(ctx.dallas) | {x for x in (s.get("dallasNights") or []) if isinstance(x, str)},
    )


def names_from_state(state: Optional[dict]) -> tuple[dict[int, str], dict[str, str]]:
    """Clients the tool added itself, and roster names, from one saved state."""
    from app.libs.schedule_board import _norm_person

    s = state if isinstance(state, dict) else {}
    clients = {}
    # A backfilled plan carries its own client list; the tool's moves log
    # names each row it touched. Both name rows of builds whose page is gone
    # (row numbers are the season sheet's rows, stable across rebuilds).
    for r, n in (s.get("planClients") or {}).items():
        rr = _row(r)
        if rr is not None and n:
            clients[rr] = str(n)
    for m in s.get("moves") or []:
        if isinstance(m, dict):
            rr = _row(m.get("row"))
            if rr is not None and m.get("name"):
                clients.setdefault(rr, str(m["name"]))
    for c in s.get("newClients") or []:
        if isinstance(c, dict):
            r = _row(c.get("row"))
            if r is not None and c.get("name"):
                clients[r] = str(c["name"])
    people = {}
    for p in s.get("roster") or []:
        n = _norm_person(p) if isinstance(p, dict) else None
        if n:
            people[n["id"]] = n["name"]
    return clients, people


# ─── The diff ────────────────────────────────────────────────────────────────

def _ev(kind: str, type_: str, text: str, clients=(), dates=(), days=()) -> dict:
    return {
        "kind": kind,
        "type": type_,
        "text": text,
        "clients": [c for c in clients if c],
        "dates": sorted(set(d for d in dates if d)),
        "days": sorted(set(days)),
    }


def diff(prev_state: Optional[dict], cur_state: Optional[dict], ctx: Context) -> list[dict]:
    """Plain-language events for what changed between two saved states."""
    a, b = view_of(prev_state, ctx), view_of(cur_state, ctx)
    name = lambda r: ctx.clients.get(r) or f"Stop {r}"  # noqa: E731
    out: list[dict] = []
    touched_days: set[str] = set()

    # Not installing / back on, and holds (they explain placement changes,
    # so they come first and the placement pass skips the rows they cover).
    covered: set[int] = set()
    for r in sorted(b.not_installing - a.not_installing, key=name):
        was = a.placement.get(r) or ()
        prior = (b.last_from.get(r) or {}).get("date")
        when = f" (was {a.where(was)})" if was else (f" (was {fmt_day(prior)})" if prior else "")
        out.append(_ev("not_installing", "holds", f"Not installing: {name(r)}{when}",
                       [name(r)], a.dates_of(was) or ([prior] if prior else []), was))
        covered.add(r)
        touched_days.update(was)
    for r in sorted(a.not_installing - b.not_installing, key=name):
        now = b.placement.get(r) or ()
        where = f", {b.where(now)}" if now else ""
        out.append(_ev("reinstated", "holds", f"Back on the schedule: {name(r)}{where}",
                       [name(r)], b.dates_of(now), now))
        covered.add(r)
        touched_days.update(now)
    for r in sorted(b.hold - a.hold, key=name):
        now = b.placement.get(r) or ()
        on = f" ({b.where(now)})" if now else ""
        out.append(_ev("hold", "holds", f"{name(r)} put on hold{on}", [name(r)], b.dates_of(now), now))
    for r in sorted(a.hold - b.hold, key=name):
        now = b.placement.get(r) or ()
        on = f" ({b.where(now)})" if now else ""
        out.append(_ev("unhold", "holds", f"{name(r)} taken off hold{on}", [name(r)], b.dates_of(now), now))

    # Placement: moves, crew switches, adds and removals.
    place: list[dict] = []
    group: dict[tuple, list[int]] = {}
    if a.has_placement and b.has_placement:
        for r in sorted(set(a.placement) | set(b.placement)):
            if r in covered:
                continue
            was, now = a.placement.get(r) or (), b.placement.get(r) or ()
            if was == now:
                continue
            touched_days.update(was)
            touched_days.update(now)
            if was and now:
                group.setdefault((was, now), []).append(r)
            elif now:
                place.append(_ev("added", "adds", f"Added {name(r)} to {b.where(now)}",
                                 [name(r)], b.dates_of(now), now))
            else:
                place.append(_ev("removed", "adds", f"Removed {name(r)} from {a.where(was)}",
                                 [name(r)], a.dates_of(was), was))
    for (was, now), rs in group.items():
        da, db_ = a.dates_of(was), b.dates_of(now)
        names = sorted((name(r) for r in rs), key=str.lower)
        if da == db_:
            crews_a = " + ".join(a.label(i) for i in was)
            crews_b = " + ".join(b.label(i) for i in now)
            if crews_a == crews_b:
                continue  # a crew was added or removed beside it: same card, renumbered id
            crews_a = " + ".join(a.title(i) for i in was)
            crews_b = " + ".join(b.title(i) for i in now)
            who = names[0] if len(names) == 1 else f"{len(names)} stops"
            tail = "" if len(names) == 1 else f": {'; '.join(names)}"
            place.append(_ev("crew", "moves",
                             f"{who} switched crews on {fmt_day(db_[0])}: {crews_a} → {crews_b}{tail}",
                             names, da, was + now))
            continue
        same_crew = [a.label(i) for i in was] == [b.label(i) for i in now]
        if same_crew:
            span = f"{' / '.join(fmt_day(d) for d in da)} → {' / '.join(fmt_day(d) for d in db_)} ({' + '.join(b.title(i) for i in now)})"
        else:
            span = f"{a.where_paren(was)} → {b.where_paren(now)}"
        if len(names) == 1:
            text = f"{names[0]} moved {span}"
        else:
            text = f"Moved {len(names)} stops {span}: {'; '.join(names)}"
        place.append(_ev("moved", "moves", text, names, da + db_, was + now))
    if len(place) > BULK_LIMIT:
        clients = sorted({c for e in place for c in e["clients"]}, key=str.lower)
        out.append({**_ev("bulk", "moves",
                          f"Large update: {len(clients)} stops changed at once (a restore or bulk edit)",
                          clients, [d for e in place for d in e["dates"]]), "count": len(clients)})
    else:
        out.extend(place)

    # Stop order and arrival times on days whose stops stayed put.
    for did in sorted(set(a.manual) | set(b.manual)):
        if did in touched_days or a.manual.get(did, ()) == b.manual.get(did, ()):
            continue
        rows_now = [r for r in b.manual.get(did, ()) if did in (b.placement.get(r) or ())]
        if not rows_now or not a.manual.get(did):
            continue
        d, _ = _split_day(did)
        names = [name(r) for r in rows_now]
        listed = " ".join(f"{i}. {n}" for i, n in enumerate(names, 1))
        out.append(_ev("order", "moves",
                       f"Stop order changed on {fmt_day(d)} ({b.title(did)}): {listed}",
                       names, [d], [did]))
        touched_days.add(did)
    shifted: dict[str, list[str]] = {}
    shifted_names: dict[str, list[str]] = {}
    for (did, r), t1 in sorted(b.times.items()):
        t0 = a.times.get((did, r))
        if t0 is None or did in touched_days or abs(t1 - t0) < TIME_SHIFT_MIN:
            continue
        shifted.setdefault(did, []).append(f"{name(r)} {fmt_clock(t0)} → {fmt_clock(t1)}")
        shifted_names.setdefault(did, []).append(name(r))
    for did, parts in sorted(shifted.items()):
        d, _ = _split_day(did)
        out.append(_ev("time", "moves",
                       f"Arrival times changed on {fmt_day(d)} ({b.title(did)}): {'; '.join(parts)}",
                       shifted_names[did], [d], [did]))

    # Approvals and confirmations. Moving a stop in or out of a day clears
    # its approval automatically; that is the move's news, not a second line.
    for did in sorted(b.approved - a.approved):
        d, _ = _split_day(did)
        out.append(_ev("approved", "approvals", f"{b.title(did)} approved for {fmt_day(d)}", [], [d], [did]))
    for did in sorted(a.approved - b.approved):
        if did in touched_days:
            continue
        d, _ = _split_day(did)
        out.append(_ev("unapproved", "approvals", f"{a.title(did)} approval removed for {fmt_day(d)}", [], [d], [did]))
    for r in sorted(b.confirmed - a.confirmed, key=name):
        now = b.placement.get(r) or ()
        on = f" on {b.where(now)}" if now else ""
        out.append(_ev("confirmed", "approvals", f"Date confirmed with client: {name(r)}{on}",
                       [name(r)], b.dates_of(now), now))
    for r in sorted(a.confirmed - b.confirmed, key=name):
        now = b.placement.get(r) or a.placement.get(r) or ()
        on = f" on {b.where(now)}" if now else ""
        out.append(_ev("unconfirmed", "approvals", f"Date no longer confirmed: {name(r)}{on}",
                       [name(r)], b.dates_of(now), now))

    # Position locks.
    for r in sorted(set(a.pins) | set(b.pins), key=name):
        p0, p1 = a.pins.get(r), b.pins.get(r)
        if p0 == p1:
            continue
        if p1 and p0:
            text = f"Locked {PIN_SHORT[p1]}: {name(r)} (was {PIN_SHORT[p0]})"
        elif p1:
            text = f"Locked {PIN_SHORT[p1]}: {name(r)}"
        else:
            text = f"Position unlocked: {name(r)} (was {PIN_SHORT[p0]})"
        now = b.placement.get(r) or ()
        out.append(_ev("lock" if p1 else "unlock", "locks", text, [name(r)], b.dates_of(now), now))

    # Staffing, per person, collapsed when one save covers many days.
    person = lambda pid: ctx.people.get(pid)  # noqa: E731
    adds: dict[str, list[str]] = {}
    drops: dict[str, list[str]] = {}
    for did in set(a.staffing) | set(b.staffing):
        s0, s1 = set(a.staffing.get(did, ())), set(b.staffing.get(did, ()))
        for pid in s1 - s0:
            adds.setdefault(pid, []).append(did)
        for pid in s0 - s1:
            drops.setdefault(pid, []).append(did)
    for verb, table, view in (("added to", adds, b), ("taken off", drops, a)):
        kind = "staff_add" if verb == "added to" else "staff_remove"
        # People sharing the same days in one save (a training day cleared,
        # a crew staffed in one go) read as one line.
        same: dict[tuple[str, ...], list[str]] = {}
        for pid, ids in table.items():
            if person(pid):  # someone on no roster has nothing to call them
                same.setdefault(tuple(sorted(ids)), []).append(person(pid))
        for ids, who_all in sorted(same.items(), key=lambda kv: (kv[0], sorted(kv[1]))):
            dates = view.dates_of(ids)
            if len(ids) > STAFF_COLLAPSE:
                days_txt = f"{len(ids)} crew days ({fmt_day(dates[0])} to {fmt_day(dates[-1])})"
            else:
                days_txt = ", ".join(f"{fmt_day(_split_day(i)[0])} ({view.title(i)})" for i in ids)
            who_all = sorted(who_all, key=str.lower)
            if len(who_all) > STAFF_COLLAPSE:
                out.append(_ev(kind, "staffing", f"{len(who_all)} people {verb} {days_txt}: {', '.join(who_all)}",
                               [], dates, ids))
            else:
                out.extend(_ev(kind, "staffing", f"{w} {verb} {days_txt}", [], dates, ids) for w in who_all)

    # Dates, training days and crews.
    for kind, ds, one, many in (
        ("date_added", sorted(b.new_dates - a.new_dates), "New date added", "new dates added"),
        ("date_removed", sorted(a.new_dates - b.new_dates), "Date removed", "dates removed"),
    ):
        if len(ds) > STAFF_COLLAPSE:
            out.append(_ev(kind, "dates", f"{len(ds)} {many} ({fmt_day(ds[0])} to {fmt_day(ds[-1])})", [], ds))
        else:
            out.extend(_ev(kind, "dates", f"{one}: {fmt_day(d)}", [], [d]) for d in ds)
    for d in sorted(b.training - a.training):
        out.append(_ev("training_added", "dates", f"Training day set: {fmt_day(d)}", [], [d]))
    for d in sorted(a.training - b.training):
        out.append(_ev("training_removed", "dates", f"Training day removed: {fmt_day(d)}", [], [d]))
    if a.has_placement and b.has_placement:
        days_a = {i for ids in a.placement.values() for i in ids} | set(ctx.base_days)
        days_b = {i for ids in b.placement.values() for i in ids} | set(ctx.base_days)
        # Only when a date really gained or lost a crew: a card stored
        # under a new id with the same number of crews is the same card.
        for did in sorted(days_b - days_a):
            d, _ = _split_day(did)
            if len(b.crews_on.get(d, [])) > len(a.crews_on.get(d, [])):
                out.append(_ev("crew_added", "dates", f"New crew on {fmt_day(d)} ({b.title(did)})", [], [d], [did]))
        for did in sorted(days_a - days_b):
            d, _ = _split_day(did)
            if len(a.crews_on.get(d, [])) > len(b.crews_on.get(d, [])):
                out.append(_ev("crew_removed", "dates", f"Crew removed from {fmt_day(d)} ({a.title(did)})", [], [d], [did]))
    if len(out) > SAVE_LIMIT:
        clients = sorted({c for e in out for c in e["clients"]}, key=str.lower)
        n = sum(e.get("count", 1) for e in out)
        return [{**_ev("bulk", "moves", f"Large update: {n} changes at once (a restore or bulk edit)",
                       clients, [d for e in out for d in e["dates"]]), "count": n}]
    return out


# ─── The feed ────────────────────────────────────────────────────────────────

#: The writer label of saves made by a local dev server against the live
#: database. Hidden from the feed unless a super admin asks for them.
TEST_WRITER = "local-dev-user"
#: Who a backfilled save is credited to when the backup didn't say.
UNKNOWN_BACKUP = "Unknown (from backup)"
#: Who a plan (a spreadsheet build of the schedule) is credited to.
PLAN_BY = "Schedule build"


def _plan_context(state: dict) -> tuple[dict[int, str], dict[str, dict]]:
    clients = {r: n for r, n in ((_row(k), v) for k, v in (state.get("planClients") or {}).items()) if r is not None}
    days = {}
    for d in state.get("planDays") or []:
        if isinstance(d, dict) and d.get("id"):
            days[str(d["id"])] = {"date": d.get("date"), "crew": d.get("crew"), "stops": list(d.get("stops") or [])}
    return clients, days


def _placement_of(state: Optional[dict]) -> dict:
    p = (state or {}).get("placement") if isinstance(state, dict) else None
    return {str(k): sorted(map(str, v)) for k, v in p.items()} if isinstance(p, dict) else {}


def _plan_summary(state: dict) -> str:
    place = _placement_of(state)
    n_days = len({d for ids in place.values() for d in ids})
    return f"{len(place)} clients on {n_days} crew days"


def build_feed(rows: list[dict], ctx: Context, writer_names: dict[str, str],
               *, current_version: Optional[str] = None) -> list[dict]:
    """Every event across consecutive saved states, newest first.

    ``rows`` are snapshots oldest first: ``state``, ``updated_by``,
    ``created_at`` and an ``id`` or ``key`` (unique; event ids derive from
    it), plus optionally ``version`` (the schedule build), ``kind``
    (``"save"``, or ``"plan"`` for a backfilled build of the schedule) and
    ``from_backup`` (restored from a backup rather than read from history).

    Saves are diffed against the one before them. Where the build changes,
    rows were re-planned and every row's day changed meaning, so a diff would
    be a flood of fake moves: that boundary is ONE "Schedule rebuilt" line --
    unless the placement came across unchanged (a page splice, a restore),
    in which case it is diffed like any other save. The first row is the
    baseline and yields nothing, unless it is a plan ("First plan built").

    ``ctx`` names things for ``current_version`` (the published page's
    clients and crew-days). Older builds whose page is gone are named from
    the same rows -- they are the season sheet's rows, stable across
    rebuilds -- and from what the states themselves carry.
    """
    clients, people = dict(ctx.clients), dict(ctx.people)
    for r in rows:
        c, p = names_from_state(r.get("state"))
        for k, v in c.items():
            clients.setdefault(k, v)
        for k, v in p.items():
            people.setdefault(k, v)

    ctx_cache: dict[tuple, Context] = {}

    def ctx_for(row: dict) -> Context:
        v = row.get("version")
        state = row.get("state") or {}
        if row.get("kind") == "plan":
            pc, pd = _plan_context(state)
            key = ("plan", row.get("key", row.get("id")))
            if key not in ctx_cache:
                ctx_cache[key] = Context(clients={**clients, **pc}, base_days=pd, people=people, dallas=ctx.dallas)
            return ctx_cache[key]
        key = ("v", v)
        if key not in ctx_cache:
            same = current_version is None or v is None or v == current_version
            ctx_cache[key] = Context(clients=clients, base_days=ctx.base_days if same else {}, people=people,
                                     dallas=ctx.dallas)
        return ctx_cache[key]

    def who(row: dict) -> str:
        if row.get("kind") == "plan":
            return f"{PLAN_BY} (from backup)" if row.get("from_backup") else PLAN_BY
        writer = (row.get("updated_by") or "").strip()
        if not writer and row.get("from_backup"):
            return UNKNOWN_BACKUP
        return writer_names.get(writer) or script_writer_name(writer) or "Someone"

    events: list[dict] = []

    def emit(row: dict, idx: int, evs: list[dict]) -> None:
        at = row["created_at"]
        writer = row.get("updated_by") or ""
        rid = row.get("key", row.get("id"))
        for i, ev in enumerate(evs):
            events.append({
                **ev,
                "id": f"{rid}-{i}",
                "at": at.astimezone(timezone.utc).isoformat(),
                "day": central(at).date().isoformat(),
                "time": fmt_time_ct(at),
                "by": who(row),
                "writer": writer,
                "fromBackup": bool(row.get("from_backup")),
                "test": writer == TEST_WRITER,
                "seq": (idx, i),
            })

    for idx, cur in enumerate(rows):
        state = cur.get("state") or {}
        if cur.get("kind") == "plan":
            first = idx == 0
            text = (f"First plan built: {_plan_summary(state)}" if first
                    else f"Schedule re-planned: {_plan_summary(state)}")
            # Several builds on one day read as one line.
            last = events[-1] if events else None
            if (not first and last and last["kind"] == "replan"
                    and last["day"] == central(cur["created_at"]).date().isoformat()):
                n = last.get("count", 1) + 1
                events.pop()
                text = f"Schedule re-planned {n} times; latest: {_plan_summary(state)}"
                emit(cur, idx, [{**_ev("replan", "dates", text), "count": n}])
                continue
            emit(cur, idx, [_ev("first_plan" if first else "replan", "dates", text)])
            continue
        if idx == 0:
            continue
        prev = rows[idx - 1]
        crossing = prev.get("kind") == "plan" or (
            prev.get("version") != cur.get("version")
            and prev.get("version") is not None and cur.get("version") is not None)
        if crossing and _placement_of(prev.get("state")) != _placement_of(state):
            emit({**cur, "kind": "plan"}, idx,
                 [_ev("rebuilt", "dates", f"Schedule rebuilt: {_plan_summary(state)}")])
            continue
        evs = diff(prev.get("state"), state, ctx_for(cur))
        if evs and (cur.get("updated_by") or "").lower().startswith("restore"):
            # Restoring an older version is one decision, not N edits.
            n = sum(e.get("count", 1) for e in evs)
            evs = [_ev("restore", "moves", f"Restored an earlier version of the schedule ({n} changes)",
                       sorted({c for e in evs for c in e["clients"]}, key=str.lower),
                       [d for e in evs for d in e["dates"]])]
        emit(cur, idx, evs)

    events.sort(key=lambda e: e["seq"], reverse=True)
    for e in events:
        del e["seq"]
        e.pop("count", None)
    return events


def matches(ev: dict, q: str = "", start: Optional[str] = None, end: Optional[str] = None,
            types: Optional[set[str]] = None) -> bool:
    """The page's filters: client/text search, change-date range (Central
    days, inclusive) and type groups."""
    if types and ev["type"] not in types:
        return False
    if start and ev["day"] < start:
        return False
    if end and ev["day"] > end:
        return False
    if q:
        needle = q.strip().lower()
        hay = " ".join([ev["text"], *ev.get("clients", [])]).lower()
        if needle and needle not in hay:
            return False
    return True


def page(events: list[dict], *, limit: int = 50, before: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """One page, newest first, continuing after the event id ``before``.

    A cursor rather than an offset: new saves land at the top while someone
    is scrolling, and an offset would show them the same lines twice.
    """
    start = 0
    if before:
        idx = next((i for i, e in enumerate(events) if e["id"] == before), None)
        start = idx + 1 if idx is not None else len(events)
    chunk = events[start:start + limit]
    more = start + limit < len(events)
    return chunk, (chunk[-1]["id"] if more and chunk else None)


def unseen_count(events: list[dict], last_seen: Optional[datetime], me: Optional[str]) -> int:
    """Changes since ``last_seen``, not counting the caller's own."""
    if last_seen is None:
        return 0
    cut = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc)
    return sum(
        1 for e in events
        if datetime.fromisoformat(e["at"]) > cut and (not me or e["writer"] != me)
    )
