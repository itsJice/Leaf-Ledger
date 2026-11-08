"""One client's install this season, at a glance (Comments #23).

Cynthia asked to see a client's install confirmation and scheduling
preferences on the client page without opening the schedule ("Jennifer
Allums, confirmed 11/19, prefers morning"). Everything here already exists
somewhere; this module only gathers it for one client:

* the board date, crew and lead -- the Install Schedule board owns dates
  (user, 2026-10-06), read through ``app.libs.schedule_board``;
* whether staff confirmed the date with the client (the tool's ``confirmed``
  set, the CONFIRMED lock) and who confirmed it when, from the schedule's
  Changes feed (``app.libs.schedule_changes`` "Date confirmed with client");
* business or residence, as the build classified the stop (``bus``);
* the size of the job: hours, crew size, how many crews and crew-days, and
  "Whole day" / "Multi-crew", always derived, never typed;
* the season card's date (``detail.install_date``) for "not on board".

Pure: callers hand in the resolved board, the client's spellings, the
season detail and the change events. No money: nothing here reads a price.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from app.libs import client_season

#: Hours at which one crew's share of a job fills its day on its own -- the
#: board's soft day minimum (about 7.5 h, see the ll-schedule-board rules).
WHOLE_DAY_HOURS = 7.5
#: How many contact-log entries the panel shows before "See all".
RECENT_CONTACTS = 3


def fold_name(s: Any) -> str:
    """normName() in the tool / _fold_name in the schedule API: case, commas,
    periods and spacing don't count."""
    out = str(s or "").strip().lower().replace(",", "").replace(".", "")
    return " ".join(out.split())


def spellings(client: dict) -> set[str]:
    """Every folded spelling the app has for a client: name, the sheet's
    spelling, former names -- what _sync_board_dates matches on."""
    raw = [client.get("name"), client.get("sheet_name"), *(client.get("former_names") or [])]
    return {k for k in (fold_name(x) for x in raw) if k}


def board_rows_for(board, client: dict) -> list[int]:
    """The board rows (stops) that are this client, by any spelling."""
    want = spellings(client)
    if not want or board is None:
        return []
    return sorted(r for r, c in board.clients.items() if fold_name(c.get("name")) in want)


def _num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # NaN


def crew_size_of(detail: dict, board_client: dict) -> tuple[Optional[int], dict, str]:
    """(headcount, per-role counts, where it came from). The season card's
    role_need first (what staff keep), then the build's roleNeed, then the
    build's people count."""
    for src, raw in (("card", (detail or {}).get("role_need")), ("schedule", board_client.get("roleNeed"))):
        if isinstance(raw, dict):
            roles = {k: int(n) for k, n in raw.items()
                     if k in client_season.ROLE_KEYS and isinstance(n, (int, float)) and n > 0}
            if roles:
                return sum(roles.values()), roles, src
    people = _num(board_client.get("people"))
    if people and people > 0:
        return int(round(people)), {}, "schedule"
    return None, {}, ""


def confirmation_event(events: Iterable[dict], names: set[str]) -> Optional[dict]:
    """The newest "confirmed" / "unconfirmed" event for any of ``names``
    (folded), newest first as the feed returns them. Only a "confirmed"
    event says who and when; an unconfirm after it means it no longer holds."""
    for ev in events or []:
        if ev.get("kind") not in ("confirmed", "unconfirmed"):
            continue
        if any(fold_name(c) in names for c in ev.get("clients") or []):
            return ev if ev["kind"] == "confirmed" else None
    return None


def summarize(board, client: dict, detail: Optional[dict], events: Optional[list] = None,
              *, season: str) -> dict:
    """The install panel for one client and season."""
    detail = detail if isinstance(detail, dict) else {}
    rows = board_rows_for(board, client)
    names = spellings(client) | {fold_name(board.clients[r].get("name")) for r in rows} if board else set()

    stops = []
    for r in rows:
        c = board.clients[r]
        on = sorted((d for d in board.days.values() if r in d.get("stops", [])),
                    key=lambda d: (d["date"], board.crew_label(d)))
        crews = []
        for d in on:
            lead = board.lead_of(d["id"])
            crews.append({
                "day_id": d["id"],
                "date": d["date"],
                "crew": board.crew_label(d),
                "crew_title": board.crew_title(d),
                "lead": lead["name"] if lead else None,
                "staffed": len(board.staffing.get(d["id"], [])),
                "stops": len(d.get("stops", [])),
                "only_stop": len(d.get("stops", [])) == 1,
            })
        stops.append({"row": r, "name": c.get("name") or "", "board_client": c, "crews": crews})

    placed = [s for s in stops if s["crews"]]
    # The client's stop for this panel: the first one on the board, else the
    # first row the build has for them (taken off, or not installing).
    main = placed[0] if placed else (stops[0] if stops else None)
    bc = main["board_client"] if main else {}
    crews = main["crews"] if main else []
    dates = sorted({c["date"] for c in crews})

    per_date: dict[str, int] = {}
    for c in crews:
        per_date[c["date"]] = per_date.get(c["date"], 0) + 1
    hours = _num(bc.get("h26"))
    hours_basis = str(bc.get("basis") or "") if hours is not None else ""
    if hours is None:
        hours = _num(detail.get("est_hours"))
        hours_basis = "season card" if hours is not None else ""
    size, roles, size_src = crew_size_of(detail, bc)
    multi_crew = any(n > 1 for n in per_date.values())
    per_crew = (hours / max(per_date.values())) if hours and per_date else hours
    whole_day = bool(crews) and (any(c["only_stop"] for c in crews)
                                 or (per_crew is not None and per_crew >= WHOLE_DAY_HOURS))

    confirmed = bool(main and main["row"] in board.confirmed and crews)
    ev = confirmation_event(events or [], names) if confirmed else None

    bus = bc.get("bus")
    card_date = detail.get("install_date") if isinstance(detail.get("install_date"), str) else None
    board_date = dates[0] if dates else None
    log = client_season.contact_log_of(detail)
    legacy = detail.get("confirmation_notes")

    return {
        "season": season,
        "board_available": board is not None,
        "on_board": bool(crews),
        "board_date": board_date,
        "board_dates": dates,
        "card_date": card_date,
        "date_mismatch": bool(board_date and card_date and card_date != board_date),
        "crews": [{k: v for k, v in c.items() if k != "only_stop"} for c in crews],
        "confirmed": confirmed,
        "confirmed_at": ev.get("at") if ev else None,
        "confirmed_by": ev.get("by") if ev else None,
        "hold": bool(main and main["row"] in board.hold) or bool(detail.get("hold")),
        "not_installing": bool(detail.get("not_installing")),
        "visit_type": (bc.get("visitType") if bc.get("visitType") not in (None, "", "Standard") else None),
        "property_type": bus if bus in ("Business", "Residence") else None,
        "size": {
            "est_hours": hours,
            "hours_basis": hours_basis,
            "crew_size": size,
            "roles": roles,
            "crew_size_basis": size_src,
            "crews": max(per_date.values()) if per_date else 0,
            "crew_days": len(crews),
            "days": len(dates),
            "whole_day": whole_day,
            "multi_crew": multi_crew,
        },
        "contacts": log,
        "contact_count": len(log),
        "legacy_confirmation_notes": legacy.strip() if isinstance(legacy, str) and legacy.strip() else None,
    }
