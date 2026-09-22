#!/usr/bin/env python3
"""
Push the Christmas-install client list into the main app's `clients` table
(and a per-season `client_activity` row per client), so a client's greenery
work and their Christmas install history live in one record in the Clients
tab instead of two disconnected systems.

Run after prep.py (so cache/schedule.json is current for this season):

    .venv/bin/python3 sync_clients.py
    .venv/bin/python3 sync_clients.py --file "/path/to/some/other/workbook.xlsx"
    TBDG_SEASON=2027 .venv/bin/python3 sync_clients.py   # file under 2027

The CURRENT season comes from cache/schedule.json (already parsed, already
has everything, including the actual scheduled date from the crew-day
placement) and is labelled from season.py, not from a hardcoded year: the
label is the `season` column on client_activity, and a 2027 run that wrote
"2026" would land on top of the real 2026 history rather than beside it.
TBDG_SEASON overrides it (the same variable the rest of the pipeline reads).

2025/2024/2023/2022 come straight from the workbook's other season sheets,
since the pipeline cache only ever holds the current season -- each of those
sheets has its own header layout (or, for 2022, no headers at all), handled
by the per-season extractors below. Those are finished history and stay
pinned to their literal years.

Mergeable-field conflict rule (phone/email/street/city/state/zip): a value
edited in the app must survive a re-sync UNLESS the spreadsheet itself has
since changed that field -- see `merge_field` for the three-way compare
against `christmas_synced_snapshot`, which is exactly what the pipeline
pushed last time.

Per-season fields (everything in client_activity.detail) follow a simpler
rule, shared with the backend through app.libs.client_season: a value set in
the app is stamped in detail.app_edits and this script never overwrites it;
everything else is the sheet's to refresh on every run.

Which season a column describes is NOT which sheet it is on. The current
sheet carries last season's real hours, crew, invoice total and takedown, and
the two-back install and takedown dates, alongside this season's columns.
prep.py names those prior_* / prior2_*; this script files them on THAT
season's row (`supplement`) rather than on the current one, so the Clients
tab's year-over-year table reads true.
"""
import argparse
import asyncio
import datetime
import json
import os
import re
from typing import Any, Optional

import sys

import asyncpg
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # common.py/season.py are siblings; this may be run from anywhere
from common import current_season, load_env  # noqa: E402
import season as _season_bridge  # noqa: E402,F401  (puts backend/ on sys.path)
from app.libs import client_season  # noqa: E402

ENV_FILE = os.path.join(HERE, "..", "backend", ".env.supabase")
DEFAULT_XLSX = os.path.join(
    HERE, "CHRISTMAS CLIENTS - Storage - Delivery - Install +Takedown.xlsx"
)
CACHE = os.path.join(HERE, "cache", "schedule.json")

MERGE_FIELDS = ["phone", "email", "street", "city", "state", "zip"]

#: Same variable the rest of the pipeline reads (schedule.py, publish_pages.py).
SEASON_ENV = "TBDG_SEASON"

#: Seasons whose sheets are finished history. These stay literal -- the 2023
#: sheet is the 2023 season no matter what year it is read in.
HISTORICAL_SEASONS = ("2022", "2023", "2024", "2025")


def clean_name(name) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", str(name).strip().splitlines()[0]).strip()


def clean_str(v) -> Optional[str]:
    if v is None:
        return None
    # openpyxl hands back a whole-number-looking cell (zip codes, phone
    # numbers typed as digits) as a Python float -- "77418" reads back as
    # 77418.0 and str()'s straight to "77418.0" if not caught here. Applies
    # to any field, not just zip: whichever column got read as General/
    # Number format in the source sheet.
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = re.sub(r"\s+", " ", str(v).strip())
    return s or None


def to_date(v) -> Optional[datetime.date]:
    """asyncpg's `date` codec needs a real datetime.date to bind -- passing
    the ISO strings the extractors produce straight through raised
    `'str' object has no attribute 'toordinal'`. Every extractor hands
    install_date around as a plain ISO string (or None) right up to this
    one conversion point, since that's also the shape json.dumps(detail)
    wants for the activity row's JSONB snapshot."""
    if not v:
        return None
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def money(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def header_lookup(ws, header_row=1):
    """{normalised header text: column index} -- same convention prep.py
    uses (col name, not a fixed letter, since the sheet has reshuffled
    columns between revisions before)."""
    col = {}
    for cell in next(ws.iter_rows(min_row=header_row, max_row=header_row)):
        if cell.value:
            col[re.sub(r"\s+", " ", str(cell.value).strip())] = cell.column
    return col


def make_h(ws, col):
    def h(r, *headers):
        for name in headers:
            c = col.get(name)
            if c:
                return ws.cell(r, c).value
        return None
    return h


# ---------------------------------------------------------------------------
# Per-season extraction. Each returns a list of dicts in the common shape:
# name, street, city, state, zip, phone, email, install_fee, takedown_fee,
# storage_fee, total, notes, install_date (ISO str or None), cancelled.
# ---------------------------------------------------------------------------

#: Season-templated field names, remembered so each is only complained about
#: once per run rather than once per client.
_FIELD_WARNED: set[str] = set()


def season_field(rec: dict, season: str, *templates, default=None):
    """Read a field whose name has the season year baked into it.

    prep.py names these `install_fee_2026`, `takedown_fee_2026`,
    `install_2026_no_install` -- the year is part of the key. prep.py is owned
    elsewhere in the pipeline, so this reads them by template instead of
    depending on one spelling: `"install_fee_{}"` is tried with this season's
    year first, then any literal alternatives given (the obvious de-year-baked
    form, `"install_fee"`).

    The failure this exists to prevent is the quiet one. If prep.py renames a
    key and this just did `rec.get("install_fee_2026")`, every client would
    sync with a blank fee and a summary reading "No date recorded" with no
    dollar figure, and nothing would say why -- a whole season filed empty. So
    a key that resolves to nothing shouts once, naming the keys the record
    actually has, and the operator can see it in the run output.

    It does NOT quietly fall back to a different year's key (`install_fee_2025`
    is right there in every record): last season's fees filed under this
    season's label is worse than a blank, because it looks correct.
    """
    keys = [t.format(season) if "{}" in t else t for t in templates]
    for key in keys:
        if key in rec:
            return rec[key]
    canonical = keys[0]
    if canonical not in _FIELD_WARNED:
        _FIELD_WARNED.add(canonical)
        prefix = templates[0].split("{}")[0]
        near = sorted(k for k in rec if k.startswith(prefix))
        print(f"  *** WARNING: no {canonical!r} on the cached record "
              f"(tried {keys!r}) -- prep.py may have renamed it. "
              f"Falling back to {default!r} for every client this run.")
        if near:
            print(f"      similar keys present: {near}")
    return default


def storing_from_sheet(v) -> tuple[Optional[bool], Optional[str]]:
    """"TBDG STORAGE YES/NO" -> (storing, note).

    The column is mostly YES/NO but also holds "Ask", "?", and the odd
    "NO — client now stores at her own house". Anything that is not a plain
    yes/no keeps its text as a note so the reason is not lost, and anything
    that cannot be read as yes or no is None (unknown), not False.
    """
    s = clean_str(v)
    if not s:
        return None, None
    u = s.upper()
    note = None if u in ("YES", "NO", "Y", "N") else s
    if u.startswith("Y"):
        return True, note
    if u.startswith("N"):
        return False, note
    return None, note


def as_int(v) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def extract_current_season(season: str):
    """This season's clients, from the pipeline cache prep.py/schedule.py left.

    `season` is the label, not a filter: the cache only ever holds one season
    (the one prep.py was last run for), so this reads whatever is in it and
    files it under the season the caller derived.

    Each record also carries `supplements`: {season_label: {key: value}} for
    the columns on this sheet that describe an EARLIER season (see the
    module docstring). upsert_client files those on that season's row.
    """
    with open(CACHE) as f:
        sched = json.load(f)
    row_dates = {}
    for day in sched["days"]:
        for s in day["stops"]:
            row_dates.setdefault(s["row"], day["date"])
    prior = str(int(season) - 1)
    prior2 = str(int(season) - 2)
    out = []
    for c in sched["all_clients"]:
        # Default False, not None: an unresolvable key must not silently drop
        # (or silently keep) clients -- season_field has already shouted.
        if season_field(c, season, "install_{}_no_install", "no_install",
                        default=False):
            continue
        name = clean_name(c.get("name"))
        if not name:
            continue
        storing, storage_note = storing_from_sheet(c.get("storage"))
        role_need = c.get("role_need") if isinstance(c.get("role_need"), dict) else None
        rec = {
            "name": name,
            "street": clean_str(c.get("street")), "city": clean_str(c.get("city")),
            "state": clean_str(c.get("st")), "zip": clean_str(c.get("zip")),
            "phone": clean_str(c.get("phone")), "email": clean_str(c.get("email")),
            "install_fee": money(
                season_field(c, season, "install_fee_{}", "install_fee")),
            "takedown_fee": money(
                season_field(c, season, "takedown_fee_{}", "takedown_fee")),
            "storage_fee": money(c.get("storage_fee")),
            # Was hardcoded None for years: the sheet's total column was never
            # read for the current season. (It is a broken formula on most
            # rows today, so this is usually None anyway -- but honestly so.)
            "total": money(c.get("pickup_delivery_total")),
            "ideal_total": money(c.get("ideal_total")),
            "install_date": row_dates.get(c["row"]),
            "cancelled": False,
            # Storage and staffing for THIS season.
            "storing": storing,
            "storage_note": storage_note,
            "boxes": as_int(c.get("box_count")),
            "boxes_verified": bool(c.get("box_verified")),
            "est_hours": c.get("est_hours"),
            "role_need": role_need,
            "people_needed": as_int(c.get("people_needed")),
            "specialty": clean_str(c.get("specialty_needed")),
            "confirmation_notes": clean_str(c.get("confirmation_notes")),
            "supplements": {
                prior: {
                    "real_hours": c.get("real_hours"),
                    "real_start": clean_str(c.get("prior_real_start")),
                    "real_end": clean_str(c.get("prior_real_end")),
                    "crew": clean_str(c.get("crew_2025")),
                    "crew_size": as_int(c.get("crew_size_2025")),
                    "invoice_total": money(c.get("invoice_2025_total")),
                    "production_notes": clean_str(c.get("production_notes")),
                    "takedown_date": clean_str(c.get("prior_takedown_date")),
                    "takedown_order": as_int(c.get("prior_takedown_order")),
                    "takedown_est_hours": c.get("prior_takedown_est_hours"),
                    "takedown_est_note": clean_str(c.get("prior_takedown_est_note")),
                    "takedown_real_hours": c.get("prior_takedown_real_hours"),
                    "takedown_real_note": clean_str(c.get("prior_takedown_real_note")),
                    "takedown_real_start": clean_str(c.get("prior_takedown_real_start")),
                    "takedown_real_end": clean_str(c.get("prior_takedown_real_end")),
                    "takedown_on_calendar": clean_str(c.get("prior_takedown_on_calendar")),
                    "takedown_called": clean_str(c.get("prior_takedown_called")),
                },
                prior2: {
                    "install_date": clean_str(c.get("date_2024")),
                    "takedown_date": clean_str(c.get("prior2_takedown_date")),
                },
            },
        }
        out.append(rec)
    return out


def extract_headered(ws, name_headers, field_map, header_row=1, data_start=2):
    """field_map: {out_key: (header_name, ...) } -- first matching header wins."""
    col = header_lookup(ws, header_row)
    h = make_h(ws, col)
    out = []
    for r in range(data_start, ws.max_row + 1):
        name = clean_name(h(r, *name_headers))
        if not name:
            continue
        rec = {"name": name}
        for out_key, headers in field_map.items():
            rec[out_key] = h(r, *headers)
        out.append(rec)
    return out


def extract_2025(ws):
    raw = extract_headered(ws, ("TBDG CLIENT",), {
        "street": ("ADDRESS",), "city": ("CITY",), "state": ("ST",), "zip": ("ZIP",),
        "phone": ("PHONE",), "email": ("EMAIL",),
        "install_fee": ("INSTALL LABOR FEE",), "takedown_fee": ("TAKEDOWN LABOR FEE",),
        "storage_fee": ("STORAGE FEE (BASED ON # OF BOXES)",),
        "total": ("TOTAL PICK UP & DELIVERY INSTALL + TAKEDOWN",),
        "production_notes": ("Production Notes",),
        "install_date": ("Install Date 2025",),
        "storage": ("TBDG STORAGE YES/NO",),
        "boxes": ("BOX COUNT",),
    })
    for rec in raw:
        for k in ("street", "city", "state", "zip", "phone", "email", "production_notes"):
            rec[k] = clean_str(rec.get(k))
        for k in ("install_fee", "takedown_fee", "storage_fee", "total"):
            rec[k] = money(rec.get(k))
        d = rec.get("install_date")
        rec["install_date"] = d.date().isoformat() if hasattr(d, "date") else (str(d) if d else None)
        rec["storing"], rec["storage_note"] = storing_from_sheet(rec.pop("storage", None))
        rec["boxes"] = as_int(rec.get("boxes"))
        rec["cancelled"] = False
    return raw


def extract_2024(ws):
    raw = extract_headered(ws, ("CUSTOMER NAME",), {
        "street": ("ADDRESS",), "city": ("CITY",), "state": ("ST",), "zip": ("ZIP",),
        "phone": ("PHONE",), "email": ("EMAIL",),
        "install_fee": ("TOTAL INSTALL LABOR FEE",), "takedown_fee": ("TOTAL TAKEDOWN LABOR FEE",),
        "storage_fee": ("TOTAL TBDG STORAGE FEE (BASED ON # OF BOXES)",),
        "total": ("TOTAL PICK UP & DELIVERY INSTALL + TAKEDOWN",),
    })
    for rec in raw:
        for k in ("street", "city", "state", "zip", "phone", "email"):
            rec[k] = clean_str(rec.get(k))
        for k in ("install_fee", "takedown_fee", "storage_fee", "total"):
            rec[k] = money(rec.get(k))
        rec["notes"] = None
        rec["install_date"] = None  # not tracked on this sheet
        rec["cancelled"] = False
    return raw


def extract_2023(ws):
    raw = extract_headered(ws, ("Customer Name",), {
        "street": ("Address",), "zip": ("Zip Code",),
        "phone": ("Phone #",), "email": ("E-mail",),
        "install_fee": ("Install Fee",), "takedown_fee": ("Take Dn Fee",),
        "storage_fee": ("Storage",), "total": ("Totals",),
        "notes": ("Special Notes for Installers",),
    })
    for rec in raw:
        rec["city"] = None
        rec["state"] = None
        rec["zip"] = clean_str(rec.get("zip"))
        rec["street"] = clean_str(rec.get("street"))
        rec["phone"] = clean_str(rec.get("phone"))
        rec["email"] = clean_str(rec.get("email"))
        rec["notes"] = clean_str(rec.get("notes"))
        for k in ("install_fee", "takedown_fee", "storage_fee", "total"):
            rec[k] = money(rec.get(k))
        rec["install_date"] = None
        rec["cancelled"] = False
    return raw


def extract_2022_cancelled(ws):
    """No header row on this sheet -- position is the only signal:
    0 name, 1 address, 2 zip, 3 phone, 4 email, 5 install fee, 6 takedown
    fee, 9 residential/commercial code, 11 total. These are cancellations,
    not completed installs -- flagged as such, never read as a real job."""
    out = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        name = clean_name(row[0] if len(row) > 0 else None)
        if not name:
            continue
        out.append({
            "name": name,
            "street": clean_str(row[1] if len(row) > 1 else None),
            "city": None, "state": None,
            "zip": clean_str(row[2] if len(row) > 2 else None),
            "phone": clean_str(row[3] if len(row) > 3 else None),
            "email": clean_str(row[4] if len(row) > 4 else None),
            "install_fee": money(row[5] if len(row) > 5 else None),
            "takedown_fee": money(row[6] if len(row) > 6 else None),
            "storage_fee": None,
            "total": money(row[11] if len(row) > 11 else None),
            "notes": None,
            "install_date": None,
            "cancelled": True,
        })
    return out


#
# WORDING lives in backend/app/libs/client_season.py now (imported above via
# the season.py sys.path bridge), so this script, the install-schedule API and
# the Clients tab's season editor all write the same summary for the same row.
NOT_INSTALLING_SUMMARY = client_season.NOT_INSTALLING_SUMMARY
NO_DATE_SUMMARY = client_season.NO_DATE_SUMMARY


def summarize(season: str, rec: dict) -> str:
    """`season` is unused in the text (the badge next to it says the year)
    but stays in the signature for the callers that pass it."""
    return client_season.summarize(rec)


def merge_field(live: Optional[str], last_synced: Optional[str], new_value: Optional[str]) -> str:
    """Three-way compare. `live` is what's in the app now, `last_synced` is
    what the previous sync pushed (None if never synced), `new_value` is
    what this sync run found in the spreadsheet.

    - No new value at all -> keep whatever's live (nothing to say here).
    - Live unchanged since last sync (or first sync ever) -> take the new
      spreadsheet value, that's the normal path.
    - Live WAS hand-edited since last sync, and the spreadsheet's value for
      this field hasn't moved -> keep the hand-edit; the spreadsheet isn't
      the one asking for a change.
    - Live was hand-edited AND the spreadsheet also changed -> the
      spreadsheet's new value wins; that's a real, intentional correction
      at the source, not a coincidence.
    """
    if new_value is None:
        return live
    if live == last_synced:
        return new_value
    if new_value == last_synced:
        return live
    return new_value


async def upsert_client(conn, rec: dict, season: str, counts: dict):
    name = rec["name"]
    # "Beaver, Austin" (this season's sheet, comma convention) and "Beaver
    # Austin" (an older row -- pre-Christmas-sync manual entry, or an
    # earlier import that didn't use commas) are the same person, but a
    # plain LOWER(TRIM(name)) match treats them as different clients and
    # inserts a duplicate every time. Stripping commas/periods before
    # comparing catches that; the stored `name` is left untouched either
    # way, so this doesn't disturb arrangements.client_name's free-text
    # matching against whichever row already exists.
    row = await conn.fetchrow(
        "SELECT id, phone, email, street, city, state, zip, christmas_synced_snapshot "
        "FROM clients WHERE regexp_replace(LOWER(TRIM(name)), '[,.]', '', 'g') "
        "= regexp_replace(LOWER(TRIM($1)), '[,.]', '', 'g')",
        name,
    )
    if row is None:
        row = await conn.fetchrow(
            "INSERT INTO clients (name, created_by) VALUES ($1, $2) "
            "ON CONFLICT (LOWER(TRIM(name))) DO NOTHING "
            "RETURNING id, phone, email, street, city, state, zip, christmas_synced_snapshot",
            name, "sync_clients.py",
        )
        if row is None:  # lost a create race against another process -- reselect
            row = await conn.fetchrow(
                "SELECT id, phone, email, street, city, state, zip, christmas_synced_snapshot "
                "FROM clients WHERE LOWER(TRIM(name)) = LOWER(TRIM($1))", name,
            )
        counts["clients_created"] += 1
    else:
        counts["clients_seen"] += 1

    last_synced = row["christmas_synced_snapshot"] or {}
    if isinstance(last_synced, str):
        last_synced = json.loads(last_synced)

    merged = {}
    changed = False
    for field in MERGE_FIELDS:
        new_val = rec.get(field)
        live_val = row[field]
        merged_val = merge_field(live_val, last_synced.get(field), new_val)
        merged[field] = merged_val
        if merged_val != live_val:
            changed = True

    new_snapshot = {f: rec.get(f) if rec.get(f) is not None else last_synced.get(f)
                     for f in MERGE_FIELDS}

    await conn.execute(
        "UPDATE clients SET phone=$2, email=$3, street=$4, city=$5, state=$6, zip=$7, "
        "christmas_synced_snapshot=$8::jsonb, christmas_synced_at=now(), updated_at=now() "
        "WHERE id=$1",
        row["id"], merged["phone"], merged["email"], merged["street"], merged["city"],
        merged["state"], merged["zip"], json.dumps(new_snapshot),
    )
    if changed:
        counts["fields_updated"] += 1

    supplements = rec.get("supplements") or {}
    fresh = {k: v for k, v in rec.items() if k not in ("name", "supplements")}

    # The app is the source of truth for anything a person set there -- a
    # client marked not installing or on hold, a storage flag, a corrected fee.
    # This script builds `fresh` from the spreadsheet, which knows none of
    # that, and would otherwise overwrite it on every run. merge_sheet_detail
    # keeps every app-owned value (stamped in detail.app_edits, plus the
    # flags) on top of the refreshed sheet record.
    prior = await load_detail(conn, row["id"], season)
    detail = client_season.merge_sheet_detail(prior, fresh)
    summary = client_season.summarize(detail)

    await conn.execute(
        "INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at) "
        "VALUES ($1, 'christmas_install', $2, $3, $4::jsonb, $5::date) "
        "ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment' DO UPDATE SET "
        "summary=EXCLUDED.summary, detail=EXCLUDED.detail, occurred_at=EXCLUDED.occurred_at, "
        "updated_at=now()",
        row["id"], season, summary, json.dumps(detail, default=str),
        to_date(detail.get("install_date")),
    )
    counts["activity_rows"] += 1

    # Columns on this sheet that describe an EARLIER season go on that
    # season's row -- added to what is already there, never replacing it.
    for other_season, extra in supplements.items():
        extra = {k: v for k, v in extra.items() if v is not None}
        if not extra:
            continue
        await supplement_season(conn, row["id"], other_season, extra, counts)


async def load_detail(conn, client_id: int, season: str) -> Optional[dict]:
    prior = await conn.fetchval(
        "SELECT detail FROM client_activity "
        " WHERE client_id=$1 AND kind='christmas_install' AND season=$2",
        client_id, season,
    )
    if not prior:
        return None
    prior = prior if isinstance(prior, dict) else json.loads(prior)
    return prior if isinstance(prior, dict) else None


async def supplement_season(conn, client_id: int, season: str, extra: dict, counts: dict):
    """Merge sheet-sourced values into an existing season row (or start one).

    Ordering makes this safe: seasons are written oldest first, so by the
    time the current sheet's "last season's real hours" arrives, last
    season's own sheet has already written that row and this only adds to
    it. App-owned keys are left alone (client_season.supplement_detail).
    """
    prior = await load_detail(conn, client_id, season)
    detail = client_season.supplement_detail(prior, extra)
    if detail == (prior or {}):
        return
    summary = client_season.summarize(detail)
    await conn.execute(
        "INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at) "
        "VALUES ($1, 'christmas_install', $2, $3, $4::jsonb, $5::date) "
        "ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment' DO UPDATE SET "
        "summary=EXCLUDED.summary, detail=EXCLUDED.detail, occurred_at=EXCLUDED.occurred_at, "
        "updated_at=now()",
        client_id, season, summary, json.dumps(detail, default=str),
        to_date(detail.get("install_date")),
    )
    counts["supplemented_rows"] += 1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_XLSX,
                     help="Workbook holding the 2025/2024/2023/2022 season sheets")
    args = ap.parse_args()

    load_env(ENV_FILE)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(f"DATABASE_URL not set (checked env and {ENV_FILE})")

    seasons: list[tuple[str, list[dict]]] = []

    season = current_season()
    source = SEASON_ENV if os.environ.get(SEASON_ENV) else "season.py"
    print(f"Current season: {season} (from {source})")
    print(f"{season}: reading {CACHE}")
    current_recs = extract_current_season(season)
    print(f"  {len(current_recs)} clients")

    print(f"2025/2024/2023/2022: reading {args.file}")
    wb = openpyxl.load_workbook(args.file, data_only=True)

    def sheet_or_none(name):
        if name not in wb.sheetnames:
            print(f"  WARNING: sheet {name!r} not found, skipping that season")
            return None
        return wb[name]

    ws = sheet_or_none("2025 Christmas")
    rec_2025 = extract_2025(ws) if ws else []
    ws = sheet_or_none("2024 Christmas")
    rec_2024 = extract_2024(ws) if ws else []
    ws = sheet_or_none("2023.Christmas Analysis")
    rec_2023 = extract_2023(ws) if ws else []
    ws = sheet_or_none("Cancelled 2022")
    rec_2022 = extract_2022_cancelled(ws) if ws else []

    # The historical years are literals -- those sheets are finished seasons.
    # The last entry is the CURRENT one and its label is derived, so a 2027 run
    # writes 2027 rows beside the 2026 history instead of on top of it. (Point
    # TBDG_SEASON at a historical year and it deliberately re-files the cache
    # over that season -- the same override that lets you rebuild one.)
    historical = dict(zip(HISTORICAL_SEASONS,
                          (rec_2022, rec_2023, rec_2024, rec_2025)))
    for name, recs in [*historical.items(), (season, current_recs)]:
        print(f"  {name}: {len(recs)} rows")
        seasons.append((name, recs))

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    counts = {"clients_created": 0, "clients_seen": 0, "fields_updated": 0,
              "activity_rows": 0, "supplemented_rows": 0}
    try:
        # Ascending order: oldest history first, the current season last, so a
        # client's newest row is the one written most recently.
        for season_label, recs in seasons:
            for rec in recs:
                await upsert_client(conn, rec, season_label, counts)
    finally:
        await conn.close()

    print()
    print(f"Clients created: {counts['clients_created']}")
    print(f"Existing clients matched: {counts['clients_seen']}")
    print(f"Clients with a contact-field change this run: {counts['fields_updated']}")
    print(f"Activity rows written/updated: {counts['activity_rows']}")
    print(f"Earlier-season rows supplemented from this sheet: {counts['supplemented_rows']}")


if __name__ == "__main__":
    asyncio.run(main())
