#!/usr/bin/env python3
"""
Make every client on the Christmas workbook a complete client card.

    .venv/bin/python3 import_workbook.py --file "~/Downloads/CHRISTMAS CLIENTS ... (3).xlsx"
    .venv/bin/python3 import_workbook.py --file ... --apply

Dry run by default: it reads the workbook and the database, writes nothing,
and prints what it WOULD do. --apply does it, in one transaction.

This is not the season sync (sync_clients.py). That one rebuilds each
season's row from the pipeline cache and exists to keep a running season in
step with the sheet. This one answers a different question -- "is everything
the sheet knows about each client on that client's card?" -- and so it only
ever FILLS BLANKS:

* A client on the sheet who is not in the app is created.
* A contact field (street, city, state, zip, phone, email) blank on the card
  and filled on the sheet is copied across. A field both have and disagree
  on is reported, never overwritten: the app is the source of truth.
* A season field blank on the card and filled on the sheet is copied. Keys
  set in the app (detail.app_edits) and the app-only flags are never touched.
* The current season's install date comes from the LIVE scheduler board,
  not the sheet and not the pipeline's original plan -- the board is where
  staff actually book, and the card used to show the plan. Where the sheet
  names a different date the board does not have, that is reported for a
  person to settle; nothing is moved on the board.

The workbook is messy in ways this has to survive, all seen in the
2026-09-28 copy:

* The "with Cost" tab (the one the team keeps current) has the client-name
  cell of 28 rows overwritten with the header text "TBDG CLIENT". Those rows
  are named back by street number + ZIP from the plain season tab.
* Some names carry a contact appended ("... - Jessica Hui", or a second line
  "Renee Lewis - New Contact"). The first line is tried, then the address.
* Rows marked "No 2026 Install" are clients who are not installing; they get
  a season row saying so, so the card shows the year instead of a gap.
"""
import argparse
import asyncio
import collections
import datetime
import json
import os
import re
import sys
from typing import Optional

import asyncpg
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import current_season, load_env, ENV_FILE  # noqa: E402
import board_state as B  # noqa: E402
import sync_clients as S  # noqa: E402  (also puts backend/ on sys.path)
from app.libs import client_season  # noqa: E402

CONTACT = {"ADDRESS": "street", "CITY": "city", "ST": "state", "ZIP": "zip",
           "PHONE": "phone", "EMAIL": "email"}
PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]*\d{3}[\s.\-]*\d{4}")
#: Stamp for values this import writes: app-owned from now on, so the sheet
#: sync (which rebuilds a season from an older tab) can never blank them.
IMPORT_STAMP = "import:" + datetime.date.today().isoformat()
#: Running logs on the sheet: a newer copy that contains the card's older one
#: replaces it.
LOG_KEYS = {"confirmation_notes", "production_notes", "notes"}
EXCLUDE = {"GENERAL INSTALL LABOR", "PICKUP & DELIVERY - INSTALL", "PICKUP & DELIVERY - TAKEDOWN",
           "SPECIALTY INSTALL LABOR", "STORAGE FEE PER BOX", "CREW LEAD", "DESIGNER ART DIRECTOR LEAD",
           "TBDG CLIENT"}
NO_INSTALL_RE = re.compile(r"\bno\b.*\binstall\b", re.I)


def norm(n) -> str:
    return re.sub(r"[,.]", "", re.sub(r"\s+", " ", str(n or "").strip().lower()))


def addr_key(street, zipc) -> Optional[tuple]:
    """Street number + first letters of the street, and the 5-digit ZIP.
    Loose on purpose: "6332 La Vista Dr" / "6332 LaVista Drive" are one site.
    A row with no ZIP keys on the street alone (ZIP ""), and only ever
    matches another ZIP-less key -- see street_key()."""
    s = re.sub(r"[^a-z0-9]", "", str(street or "").lower())
    m = re.match(r"^(\d+)([a-z]{0,6})", s)
    z = re.sub(r"\D", "", str(zipc or ""))[:5]
    return (m.group(1) + m.group(2), z) if m else None


def street_key(k):
    return (k[0], "") if k else None


def cell_date(v) -> Optional[str]:
    if isinstance(v, (datetime.datetime, datetime.date)):
        return (v.date() if isinstance(v, datetime.datetime) else v).isoformat()
    return None


def cell_time(v) -> Optional[str]:
    if v is None or v == "":
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    return S.clean_str(v)


def num_or_note(v):
    if v is None or v == "":
        return None, None
    try:
        return round(float(v), 2), None
    except (TypeError, ValueError):
        return None, S.clean_str(v)


def read_tab(wb, name):
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    head = [re.sub(r"\s+", " ", str(c).strip()) if c else None for c in rows[0]]
    return head, [{head[i]: r[i] for i in range(min(len(head), len(r))) if head[i]} for r in rows[1:]]


def season_columns(season: int) -> dict:
    """The year-named headers, spelled the way the sheet spells them (see
    prep.COL: the year leads on some, trails on others, one is shouted)."""
    p, p2 = season - 1, season - 2
    return {
        "install": f"{season} Install Date", "prior_install": f"Install Date {p}",
        "prior2_install": f"{p2} INSTALL DATE", "prior_takedown": f"{season} Takedown Date",
        "prior2_takedown": f"{p2} TAKEDOWN DATE", "prior_real_hours": f"{p} Real Hours For Install",
        "prior_real_start": f"{p} Real Start", "prior_real_end": f"{p} Real End",
        "prior_crew": f"{p} Crew Name", "prior_notes": f"{p} Production Notes",
        "prior_invoice": f"{p} Invoice Total Actual Created", "ideal": f"{season} IDEAL TOTAL",
        "confirm": f"Confirmation Notes {season}/{season + 1}",
        "prior_td_hours": f"{season} Real Hours For Takedown",
        "prior_td_start": f"{season} Real Start", "prior_td_end": f"{season} Real End",
    }


def records_from_row(r: dict, season: int) -> dict:
    """{season_label: {key: value}} for everything one row says, filed on the
    season each column describes (the rules in RULES.md §10.1)."""
    c = season_columns(season)
    storing, storage_note = S.storing_from_sheet(r.get("TBDG STORAGE YES/NO"))
    role_need = {k: S.as_int(r.get(h)) for k, h in (
        ("leads", "# CREW LEADS NEEDED"), ("specialty", "# SPECIALTY LABOR (SCAFFOLDING EXTRA TALL LADDER)"),
        ("designer", "# DESIGNER / ART DIRECTOR"), ("general", "# GENERAL INSTALLERS NEEDED"))}
    staff = [v for v in role_need.values() if v]
    td_est, td_est_note = num_or_note(r.get("ESTIMATED TOTAL HOURS FOR Takedown"))
    td_real, td_real_note = num_or_note(r.get(c["prior_td_hours"]))
    est, _ = num_or_note(r.get("ESTIMATED TOTAL HOURS FOR INSTALL"))
    real, _ = num_or_note(r.get(c["prior_real_hours"]))
    crew = S.clean_str(r.get(c["prior_crew"]) and str(r.get(c["prior_crew"])).splitlines()[0])
    m = re.search(r"\((\d+)\)", crew or "")
    install_cell = r.get(c["install"])
    cur = {
        "install_date_sheet": cell_date(install_cell),
        "not_installing": bool(isinstance(install_cell, str) and NO_INSTALL_RE.search(install_cell)) or None,
        "storing": storing, "storage_note": storage_note,
        "boxes": S.as_int(r.get("BOX COUNT")),
        "est_hours": est, "role_need": role_need if staff else None,
        "people_needed": sum(staff) if staff else None,
        "specialty": S.clean_str(r.get("Specialty Needed")),
        "install_fee": S.money(r.get("INSTALL LABOR FEE")),
        "takedown_fee": S.money(r.get("TAKEDOWN LABOR FEE")),
        "storage_fee": S.money(r.get("STORAGE FEE (BASED ON # OF BOXES)")),
        "total": S.money(r.get("TOTAL PICK UP & DELIVERY INSTALL + TAKEDOWN")),
        "ideal_total": S.money(r.get(c["ideal"])),
        "confirmation_notes": S.clean_str(r.get(c["confirm"])),
    }
    prior = {
        "install_date": cell_date(r.get(c["prior_install"])),
        "real_hours": real, "real_start": cell_time(r.get(c["prior_real_start"])),
        "real_end": cell_time(r.get(c["prior_real_end"])),
        "crew": crew, "crew_size": int(m.group(1)) if m else None,
        "invoice_total": S.money(r.get(c["prior_invoice"])),
        "production_notes": S.clean_str(r.get(c["prior_notes"])),
        "takedown_date": cell_date(r.get(c["prior_takedown"])),
        "takedown_order": S.as_int(r.get("Take Down Order by Day")),
        "takedown_est_hours": td_est, "takedown_est_note": td_est_note,
        "takedown_real_hours": td_real, "takedown_real_note": td_real_note,
        "takedown_real_start": cell_time(r.get(c["prior_td_start"])),
        "takedown_real_end": cell_time(r.get(c["prior_td_end"])),
    }
    prior2 = {"install_date": cell_date(r.get(c["prior2_install"])),
              "takedown_date": cell_date(r.get(c["prior2_takedown"]))}
    drop = lambda d: {k: v for k, v in d.items() if v not in (None, "")}  # noqa: E731
    return {str(season): drop(cur), str(season - 1): drop(prior), str(season - 2): drop(prior2)}


def _flat(s) -> str:
    return re.sub(r"[\s.]+", " ", str(s or "")).strip().lower()


def fill_blanks(prior: Optional[dict], extra: dict, stamp: bool = True):
    """(new detail, [keys filled], [(key, card, sheet) conflicts]).

    Never replaces a value the card already has, with one exception: a
    running log (confirmation / production notes) whose sheet copy CONTAINS
    the card's copy is the same log with newer entries, and replaces it.
    Never touches an app-owned key. Everything written is stamped
    IMPORT_STAMP in app_edits, so the season sync keeps it."""
    out = dict(prior or {})
    owned = client_season.app_owned_keys(prior)
    filled, conflicts = [], []
    for k, v in extra.items():
        if v in (None, "") or k in owned:
            continue
        have = out.get(k)
        if have in (None, ""):
            out[k] = v
            filled.append(k)
        elif k in LOG_KEYS and _flat(have) in _flat(v) and _flat(have) != _flat(v):
            out[k] = v
            filled.append(k + " (newer log)")
        elif k in LOG_KEYS and _flat(v) in _flat(have):
            continue  # the card already has everything the sheet says
        elif k in LOG_KEYS and _flat(have) != _flat(v):
            # The sheet's cell was overwritten with a newer entry rather than
            # appended to. Both are real history: keep the card's, add the sheet's.
            out[k] = f"{have}\n{v}"
            filled.append(k + " (appended)")
        elif str(have) != str(v) and not isinstance(v, dict) and _flat(have) != _flat(v):
            conflicts.append((k, have, v))
    if stamp and filled:
        client_season.stamp(out, [f.split(" ")[0] for f in filled if not f.startswith("install_date")],
                            IMPORT_STAMP)
    return out, filled, conflicts


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--season", default=None, help="defaults to the current season")
    ap.add_argument("--tab", default=None, help='defaults to "<season> Christmas with Cost" if present')
    ap.add_argument("--apply", action="store_true", help="write; without this it is a dry run")
    ap.add_argument("--report", default=None, help="write the full report here as JSON")
    args = ap.parse_args()

    season = int(args.season or current_season())
    wb = openpyxl.load_workbook(os.path.expanduser(args.file), read_only=True, data_only=True)
    tab = args.tab or next((t for t in (f"{season} Christmas with Cost", f"{season} Christmas")
                            if t in wb.sheetnames), None)
    if not tab:
        raise SystemExit(f"no {season} tab in {wb.sheetnames}")
    head, rows = read_tab(wb, tab)
    # The plain season tab names the rows the "with Cost" tab lost.
    alt = f"{season} Christmas" if tab != f"{season} Christmas" and f"{season} Christmas" in wb.sheetnames else None
    by_addr = collections.defaultdict(set)
    if alt:
        for r in read_tab(wb, alt)[1]:
            nm = S.clean_name(r.get("TBDG CLIENT"))
            k = addr_key(r.get("ADDRESS"), r.get("ZIP"))
            if nm and k and nm.upper() not in EXCLUDE:
                by_addr[k].add(nm)

    load_env(ENV_FILE)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    rep = collections.defaultdict(list)
    counts = collections.Counter()
    try:
        clients = await conn.fetch(
            "SELECT id, name, sheet_name, former_names, street, city, state, zip, phone, email FROM clients")
        by_name, by_client_addr = {}, collections.defaultdict(set)
        for c in clients:
            for n in [c["name"], c["sheet_name"], *(c["former_names"] or [])]:
                if n:
                    by_name.setdefault(norm(n), c)
            k = addr_key(c["street"], c["zip"])
            if k:
                by_client_addr[k].add(c["id"])
                by_client_addr[street_key(k)].add(c["id"])  # for a sheet row with no ZIP
        by_id = {c["id"]: c for c in clients}

        # The live board: row -> date(s), by the names the published page uses.
        payload, _ = await B.fetch_published_payload(conn, str(season))
        board_date = {}
        if payload:
            state, _ = await B.fetch_state(conn, B.payload_version(payload))
            names = B.name_map(payload, state)
            out = {int(x) for x in (state or {}).get("notInstalling") or []}
            for r, ids in B.board_placement(payload, state).items():
                nm = names.get(int(r))
                if nm and int(r) not in out and ids:
                    board_date[norm(nm)] = sorted({i.split("|")[0] for i in ids})[0]

        tx = conn.transaction()
        await tx.start()
        try:
            for r in rows:
                raw = str(r.get("TBDG CLIENT") or "").strip()
                if not raw and not r.get("ADDRESS"):
                    continue
                first = S.clean_name(raw)
                if first.upper() in {"GENERAL INSTALL LABOR", "PICKUP & DELIVERY - INSTALL",
                                     "PICKUP & DELIVERY - TAKEDOWN", "SPECIALTY INSTALL LABOR",
                                     "STORAGE FEE PER BOX", "CREW LEAD", "DESIGNER ART DIRECTOR LEAD"}:
                    continue
                if str(r.get("ADDRESS") or "").strip().upper() == "ADDRESS":
                    continue  # a pasted header row
                k = addr_key(r.get("ADDRESS"), r.get("ZIP"))
                name = None if first.upper() == "TBDG CLIENT" else first
                how = "name"
                # An unnamed row is named by the plain tab first -- that tab has
                # the same row with its name intact, including the ZIP-less ones
                # that share a street with another site (Woodlands CC Tavern and
                # Tournament are both 1730 S. Millbend).
                if name is None and k and len(by_addr.get(k, ())) == 1:
                    name = next(iter(by_addr[k]))
                    how = "address via the plain tab"
                client = by_name.get(norm(name)) if name else None
                if client is None and name and " - " in name:
                    client = by_name.get(norm(name.rsplit(" - ", 1)[0]))
                    how = "name before dash"
                if client is None and k:
                    ids = by_client_addr.get(k, set())
                    if len(ids) == 1:
                        client = by_id[next(iter(ids))]
                        how = "address"
                if name is None and client is None:
                    rep["unnamed_unmatched"].append({"address": S.clean_str(r.get("ADDRESS")), "zip": S.clean_str(r.get("ZIP"))})
                    continue
                if client is None:
                    rep["created"].append(name)
                    counts["created"] += 1
                    cid = await conn.fetchval(
                        "INSERT INTO clients (name, created_by, sheet_name) VALUES ($1, 'import_workbook.py', $1) "
                        "ON CONFLICT (LOWER(TRIM(name))) DO NOTHING RETURNING id", name)
                    if cid is None:
                        cid = await conn.fetchval("SELECT id FROM clients WHERE LOWER(TRIM(name)) = LOWER(TRIM($1))", name)
                    client = {"id": cid, "name": name, "street": None, "city": None, "state": None,
                              "zip": None, "phone": None, "email": None}
                    by_name[norm(name)] = client
                elif how != "name":
                    rep["matched_by_" + how.replace(" ", "_")].append(
                        {"sheet": raw.splitlines()[0][:80] if raw else None, "client": client["name"]})
                if raw and "\n" in raw:
                    rep["contact_text_in_name"].append({"client": client["name"], "text": " | ".join(raw.splitlines()[1:]).strip()})

                # contact: fill blanks, report disagreements
                sets = {}
                extra_contacts = []
                phone_cell = S.clean_str(r.get("PHONE")) or ""
                phones = list(PHONE_RE.finditer(phone_cell))
                if len(phones) > 1:
                    name_text = " ".join(raw.splitlines()[1:]) if raw else ""
                    for m in phones[1:]:
                        before = phone_cell[phones[0].end():m.start()]
                        lab = re.sub(r"[^A-Za-z ]", " ", before).strip().split()
                        label = lab[-1] if lab else "Other"
                        full = re.search(rf"\b{re.escape(label)}\s+[A-Z][a-z]+", name_text) if label != "Other" else None
                        extra_contacts.append({"label": full.group(0) if full else label, "phone": m.group(0).strip(),
                                               "email": None})
                for col, f in CONTACT.items():
                    v = S.clean_str(r.get(col))
                    if f == "phone" and phones:
                        v = phones[0].group(0).strip()
                    if f == "email" and v:
                        v = v.strip(" ,;")
                    if f == "zip" and v:
                        v = re.sub(r"\D", "", v)[:5] or v
                    if not v or v.upper() in ("?", "N/A"):
                        continue
                    have = client.get(f) if isinstance(client, dict) else client[f]
                    if not have:
                        sets[f] = v
                    elif norm(have) != norm(v):
                        rep["contact_conflicts"].append({"client": client["name"], "field": f, "card": have, "sheet": v})
                if sets:
                    counts["contact_fields_filled"] += len(sets)
                    cols = ", ".join(f"{f} = ${i + 2}" for i, f in enumerate(sets))
                    await conn.execute(f"UPDATE clients SET {cols}, updated_at = now() WHERE id = $1",
                                       client["id"], *sets.values())
                    rep["contact_filled"].append({"client": client["name"], **sets})
                if extra_contacts:
                    have_sc = await conn.fetchval("SELECT secondary_contacts FROM clients WHERE id = $1", client["id"])
                    have_sc = json.loads(have_sc) if isinstance(have_sc, str) else (have_sc or [])
                    known = {re.sub(r"\D", "", str(x.get("phone") or ""))[-10:] for x in have_sc}
                    known.add(re.sub(r"\D", "", str(client["phone"] or ""))[-10:])
                    new_sc = [x for x in extra_contacts if re.sub(r"\D", "", x["phone"])[-10:] not in known]
                    if new_sc:
                        await conn.execute("UPDATE clients SET secondary_contacts = $2::jsonb, updated_at = now() WHERE id = $1",
                                           client["id"], json.dumps(have_sc + new_sc))
                        counts["additional_contacts_added"] += len(new_sc)
                        rep["additional_contacts_added"].append({"client": client["name"], "added": new_sc})

                # seasons
                recs = records_from_row(r, season)
                cur = recs[str(season)]
                sheet_date = cur.pop("install_date_sheet", None)
                bd = board_date.get(norm(client["name"])) or board_date.get(norm(name or ""))
                if not bd:
                    for n in (client.get("sheet_name") if isinstance(client, dict) else client["sheet_name"],
                              *((client.get("former_names") if isinstance(client, dict) else client["former_names"]) or [])):
                        bd = bd or board_date.get(norm(n))
                if bd:
                    cur["install_date"] = bd
                    if sheet_date and sheet_date != bd:
                        rep["date_conflicts"].append({"client": client["name"], "sheet": sheet_date, "board": bd})
                elif sheet_date:
                    cur["install_date"] = sheet_date
                for label, extra in recs.items():
                    if not extra:
                        continue
                    prior = await S.load_detail(conn, client["id"], label)
                    detail, filled, conflicts = fill_blanks(prior, extra)
                    # The card's current-season install date follows the board.
                    if label == str(season) and bd and prior and prior.get("install_date") not in (None, bd) \
                            and "install_date" in client_season.app_owned_keys(prior):
                        rep["hand_set_date_vs_board"].append({"client": client["name"],
                                                              "card (set on Clients tab)": prior.get("install_date"),
                                                              "board": bd})
                    if label == str(season) and bd and prior and prior.get("install_date") != bd \
                            and "install_date" not in client_season.app_owned_keys(prior):
                        detail["install_date"] = bd
                        filled.append("install_date (board)")
                        conflicts = [c for c in conflicts if c[0] != "install_date"]
                    for kk, have, v in conflicts:
                        if label == str(season) and kk == "install_date":
                            continue
                        rep["season_conflicts"].append({"client": client["name"], "season": label,
                                                        "field": kk, "card": have, "sheet": v})
                    if not filled and prior is not None:
                        continue
                    counts[f"season_{label}_fields_filled"] += len(filled)
                    if prior is None:
                        counts[f"season_{label}_rows_created"] += 1
                    await conn.execute(
                        "INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at) "
                        "VALUES ($1, 'christmas_install', $2, $3, $4::jsonb, $5::date) "
                        "ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment' DO UPDATE SET "
                        "summary=EXCLUDED.summary, detail=EXCLUDED.detail, occurred_at=EXCLUDED.occurred_at, "
                        "updated_at=now()",
                        client["id"], label, client_season.summarize(detail),
                        json.dumps(detail, default=str), S.to_date(detail.get("install_date")))
                    for kk in filled:
                        rep["season_fields_filled_by_key"].append(f"{label}:{kk}")
            if args.apply:
                await tx.commit()
            else:
                await tx.rollback()
        except BaseException:
            await tx.rollback()
            raise
    finally:
        await conn.close()

    by_key = collections.Counter(rep.pop("season_fields_filled_by_key", []))
    print(f"{'APPLIED' if args.apply else 'DRY RUN -- nothing written'}: tab {tab!r}, season {season}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print("  season fields filled, by key:", dict(sorted(by_key.items())))
    for k in ("created", "unnamed_unmatched"):
        if rep.get(k):
            print(f"  {k}: {rep[k]}")
    for k in ("matched_by_address", "matched_by_address_via_the_plain_tab", "matched_by_name_before_dash"):
        if rep.get(k):
            print(f"  {k}: {len(rep[k])}")
    print(f"  date conflicts (sheet names a date the board does not have): {len(rep.get('date_conflicts', []))}")
    print(f"  hand-set card dates that disagree with the board: {rep.get('hand_set_date_vs_board', [])}")
    print(f"  contact conflicts (card kept): {len(rep.get('contact_conflicts', []))}")
    print(f"  season conflicts (card kept): {len(rep.get('season_conflicts', []))}")
    if args.report:
        with open(args.report, "w") as f:
            json.dump(rep, f, indent=1, default=str)
        print(f"  full report: {args.report}")


if __name__ == "__main__":
    asyncio.run(main())
