#!/usr/bin/env python3
"""
Sort each client's notes into the three kinds the Clients tab now shows,
plus the staff alert.

    General notes                -> clients.notes
    Install notes, by year       -> that season's client_activity detail "notes"
    Production & repair notes    -> that season's detail "production_notes"
    Staff alert                  -> clients.staff_alert (+ _by, _at)

The notes are scattered today (general notes copied from the sheet's
"Special Notes for Installers", the season's install note sitting in the
master sheet's Install Date column, repair notes on last season's row), so
this is done in two passes: look at everything, then apply a hand-checked
list of edits. Nothing is ever changed without --apply.

Usage (from backend/; reads DATABASE_URL, else backend/.env.supabase):

  1. Look. Writes a CSV report (one row per client per season that has
     anything) and, with --export, the JSON the edits file is written from:

       .venv/bin/python scripts/migrate_client_notes.py \\
           --report notes_report.csv --export current.json

  2. Write edits.json from current.json -- a list of
       {"client_id": 12,
        "general_notes": "...",                       # optional
        "seasons": {"2026": {"notes": "...",           # optional, install notes
                             "production_notes": "..."}},
        "staff_alert": "..."}                         # optional
     A key that is present is written ("" or null clears it); a key left
     out is not touched.

  3. Preview, then apply:

       .venv/bin/python scripts/migrate_client_notes.py --edits edits.json
       .venv/bin/python scripts/migrate_client_notes.py --edits edits.json --apply

     General notes go through UPDATE clients; season fields go through the
     same function as PUT /api/clients/{id}/seasons/{season}
     (app.apis.clients.save_season_fields), so they are stamped in
     detail.app_edits and the sheet sync keeps them; staff alerts are set
     like the API, signed "Claude (notes cleanup)". All edits run in one
     transaction: any error and nothing is written.

  Note: clearing a season field drops its app_edits stamp (same as the
  Clients tab), so a value the spreadsheet still carries can come back on
  the next sync. Move text out of a season field by setting it to the text
  that should stay, not by clearing it, if the sheet still has the old text.

The spreadsheet's side comes from the pipeline cache
(scheduler/cache/clients.json, written by prep.py): install_2026_note --
which means "this season's" install note whatever the year -- and
production_notes, which describes last season. Clients are matched by
sheet name, name or a former name, ignoring case, commas and periods, the
way scheduler/sync_clients.py matches them.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DEFAULT_SHEET_CACHE = BACKEND.parent / "scheduler" / "cache" / "clients.json"
ALERT_BY = "Claude (notes cleanup)"
SEASON_KEYS = ("notes", "production_notes")
EDIT_KEYS = {"client_id", "name", "general_notes", "seasons", "staff_alert"}
REPORT_COLUMNS = (
    "client_id", "name", "staff_alert", "general_notes", "season",
    "install_notes", "production_notes", "sheet_install_note",
    "sheet_production_notes", "flags",
)


# ─── pure helpers (unit-tested) ──────────────────────────────────────────────


def norm_name(name: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[,.]", "", str(name or "").strip().lower()))


def flat(text: Any) -> str:
    """For comparing notes: case and spacing ignored."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def clean(text: Any) -> Optional[str]:
    s = str(text).strip() if text is not None else ""
    return s or None


def index_sheet(sheet_clients: Iterable[dict]) -> dict:
    out: dict = {}
    for c in sheet_clients:
        k = norm_name(c.get("name"))
        if k and k not in out:
            out[k] = c
    return out


def match_sheet(client: dict, sheet_index: dict) -> Optional[dict]:
    """The sheet row for a client: sheet spelling first, then the app's name,
    then any former name."""
    for cand in [client.get("sheet_name"), client.get("name"), *(client.get("former_names") or [])]:
        hit = sheet_index.get(norm_name(cand))
        if hit is not None:
            return hit
    return None


def build_export(clients: list[dict], seasons_by_client: dict, sheet_index: dict,
                 current_season: str) -> list[dict]:
    """Per client, everything needed to write edits.json: the record's own
    notes, every season's install and production notes, and what the sheet
    has. Seasons with neither note are left out."""
    prior = str(int(current_season) - 1)
    out = []
    for c in sorted(clients, key=lambda r: (str(r.get("name") or "").lower(), r.get("id") or 0)):
        seasons = {}
        for season, detail in sorted((seasons_by_client.get(c["id"]) or {}).items(), reverse=True):
            d = detail if isinstance(detail, dict) else {}
            vals = {k: clean(d.get(k)) for k in SEASON_KEYS}
            if any(vals.values()):
                edits = d.get("app_edits") if isinstance(d.get("app_edits"), dict) else {}
                vals["app_edited"] = sorted(k for k in SEASON_KEYS if k in edits)
                seasons[season] = vals
        sheet = match_sheet(c, sheet_index)
        sheet_out = None
        if sheet is not None:
            sheet_out = {
                "name": sheet.get("name"),
                "install_note": clean(sheet.get("install_2026_note")),
                "install_note_season": current_season,
                "production_notes": clean(sheet.get("production_notes")),
                "production_notes_season": prior,
            }
        out.append({
            "client_id": c["id"],
            "name": c.get("name"),
            "general_notes": clean(c.get("notes")),
            "staff_alert": clean(c.get("staff_alert")),
            "seasons": seasons,
            "sheet": sheet_out,
        })
    return out


def flags_for(entry: dict) -> list[str]:
    """Things a person should look at, in plain words."""
    flags = []
    general = flat(entry.get("general_notes"))
    sheet = entry.get("sheet") or {}
    seasons = entry.get("seasons") or {}
    for season, vals in seasons.items():
        for k, label in (("notes", "install"), ("production_notes", "production")):
            v = flat(vals.get(k))
            if general and v and (v in general or general in v):
                flags.append(f"general notes repeat the {season} {label} notes")
    note = flat(sheet.get("install_note"))
    if note:
        have = flat((seasons.get(sheet.get("install_note_season")) or {}).get("notes"))
        if note not in have:
            flags.append(f"sheet install note not on {sheet.get('install_note_season')}")
    prod = flat(sheet.get("production_notes"))
    if prod:
        have = flat((seasons.get(sheet.get("production_notes_season")) or {}).get("production_notes"))
        if prod not in have:
            flags.append(f"sheet production notes not on {sheet.get('production_notes_season')}")
    if not entry.get("sheet"):
        flags.append("not on the sheet")
    return flags


def report_rows(export: list[dict]) -> list[dict]:
    """CSV rows: one per client per season with notes (one row with a blank
    season when the client has none). Clients with nothing at all are left out."""
    rows = []
    for e in export:
        sheet = e.get("sheet") or {}
        flags = "; ".join(flags_for(e))
        base = {
            "client_id": e["client_id"], "name": e["name"],
            "staff_alert": e.get("staff_alert") or "", "general_notes": e.get("general_notes") or "",
            "sheet_install_note": sheet.get("install_note") or "",
            "sheet_production_notes": sheet.get("production_notes") or "",
            "flags": flags,
        }
        seasons = e.get("seasons") or {}
        if not seasons:
            if any(base[k] for k in ("staff_alert", "general_notes", "sheet_install_note", "sheet_production_notes")):
                rows.append({**base, "season": "", "install_notes": "", "production_notes": ""})
            continue
        for season, vals in seasons.items():
            rows.append({**base, "season": season, "install_notes": vals.get("notes") or "",
                         "production_notes": vals.get("production_notes") or ""})
    return rows


class EditError(ValueError):
    pass


def validate_edits(edits: Any, max_alert: int = 500) -> list[dict]:
    """Check an edits file and normalise it. Raises EditError naming every
    problem, so nothing is half-applied because of entry 40 of 60."""
    if not isinstance(edits, list):
        raise EditError("edits must be a JSON list")
    problems, out, seen = [], [], set()
    for i, e in enumerate(edits):
        where = f"edit {i + 1}"
        if not isinstance(e, dict):
            problems.append(f"{where}: not an object")
            continue
        cid = e.get("client_id")
        if not isinstance(cid, int) or isinstance(cid, bool):
            problems.append(f"{where}: client_id must be a whole number")
            continue
        where = f"edit {i + 1} (client {cid})"
        if cid in seen:
            problems.append(f"{where}: client listed twice")
        seen.add(cid)
        unknown = sorted(set(e) - EDIT_KEYS)
        if unknown:
            problems.append(f"{where}: unknown key(s) {', '.join(unknown)}")
        item: dict = {"client_id": cid}
        for k in ("general_notes", "staff_alert"):
            if k in e:
                v = e[k]
                if v is not None and not isinstance(v, str):
                    problems.append(f"{where}: {k} must be text or null")
                    continue
                item[k] = clean(v)
        if item.get("staff_alert") and len(item["staff_alert"]) > max_alert:
            problems.append(f"{where}: staff_alert is over {max_alert} characters")
        if "seasons" in e:
            seasons = e["seasons"]
            if not isinstance(seasons, dict):
                problems.append(f"{where}: seasons must be an object keyed by year")
                seasons = {}
            item["seasons"] = {}
            for season, fields in seasons.items():
                if not (isinstance(season, str) and len(season) == 4 and season.isdigit()):
                    problems.append(f"{where}: season {season!r} is not a year")
                    continue
                if not isinstance(fields, dict) or not fields:
                    problems.append(f"{where}: season {season} must be a non-empty object")
                    continue
                bad = sorted(set(fields) - set(SEASON_KEYS))
                if bad:
                    problems.append(f"{where}: season {season}: only notes / production_notes, not {', '.join(bad)}")
                    continue
                if any(v is not None and not isinstance(v, str) for v in fields.values()):
                    problems.append(f"{where}: season {season}: values must be text or null")
                    continue
                item["seasons"][season] = {k: clean(v) for k, v in fields.items()}
        if len(item) == 1 or (set(item) == {"client_id", "seasons"} and not item["seasons"]):
            problems.append(f"{where}: nothing to change")
        out.append(item)
    if problems:
        raise EditError("\n".join(problems))
    return out


def plan_changes(edit: dict, current: Optional[dict]) -> list[tuple[str, Any, Any]]:
    """[(what, before, after)] for one edit against the export entry of the
    same client -- only what would actually change."""
    cur = current or {}
    changes = []
    for k in ("general_notes", "staff_alert"):
        if k in edit and clean(cur.get(k)) != edit[k]:
            changes.append((k, cur.get(k), edit[k]))
    for season, fields in (edit.get("seasons") or {}).items():
        have = (cur.get("seasons") or {}).get(season) or {}
        for k, v in fields.items():
            if clean(have.get(k)) != v:
                changes.append((f"{season}.{k}", have.get(k), v))
    return changes


# ─── database ────────────────────────────────────────────────────────────────


def _load_env() -> None:
    if os.environ.get("DATABASE_URL"):
        return
    env_file = BACKEND / f".env.{os.environ.get('ENV', 'supabase')}"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"')
                return
    sys.exit(f"No DATABASE_URL set and none in {env_file}")


async def read_current(conn, sheet_index: dict, current_season: str) -> list[dict]:
    from app.apis import clients as clients_api

    await clients_api.ensure_schema(conn)
    clients = [dict(r) for r in await conn.fetch(
        "SELECT id, name, sheet_name, former_names, notes, staff_alert FROM clients")]
    seasons: dict = {}
    for r in await conn.fetch(
            "SELECT client_id, season, detail FROM client_activity WHERE kind = 'christmas_install'"):
        d = r["detail"]
        if isinstance(d, str):
            d = json.loads(d)
        seasons.setdefault(r["client_id"], {})[r["season"]] = d
    return build_export(clients, seasons, sheet_index, current_season)


async def apply_edits(conn, edits: list[dict]) -> None:
    from app.apis import clients as clients_api

    async with conn.transaction():
        for e in edits:
            cid = e["client_id"]
            if "general_notes" in e:
                await conn.execute(
                    "UPDATE clients SET notes = $2, updated_at = now() WHERE id = $1",
                    cid, e["general_notes"])
            for season, fields in (e.get("seasons") or {}).items():
                await clients_api.save_season_fields(conn, cid, season, fields)
            if "staff_alert" in e:
                text = e["staff_alert"]
                await clients_api.write_staff_alert(conn, cid, text, ALERT_BY if text else None)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default="client_notes_report.csv", help="CSV report path (dry run)")
    ap.add_argument("--export", default=None, help="also write every client's notes as JSON here")
    ap.add_argument("--edits", default=None, help="JSON list of edits to preview (or apply with --apply)")
    ap.add_argument("--apply", action="store_true", help="write the edits; without it nothing is changed")
    ap.add_argument("--sheet-cache", default=str(DEFAULT_SHEET_CACHE), help="prep.py's clients.json")
    ap.add_argument("--season", default=None, help="this season (defaults to app.libs.season)")
    args = ap.parse_args()
    if args.apply and not args.edits:
        ap.error("--apply needs --edits")

    from app.libs import season as season_lib

    current_season = str(args.season or season_lib.season_for())
    sheet_clients: list = []
    try:
        cache = json.loads(Path(args.sheet_cache).read_text())
        sheet_clients = cache.get("clients", []) if isinstance(cache, dict) else cache
    except (OSError, ValueError) as exc:
        print(f"WARNING: no sheet cache read from {args.sheet_cache} ({exc}); sheet columns will be blank")
    sheet_index = index_sheet(sheet_clients)

    edits = None
    if args.edits:
        try:
            edits = validate_edits(json.loads(Path(args.edits).read_text()))
        except EditError as exc:
            sys.exit(f"edits file has problems -- nothing written:\n{exc}")

    _load_env()
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        export = await read_current(conn, sheet_index, current_season)
        by_id = {e["client_id"]: e for e in export}
        if edits is None:
            rows = report_rows(export)
            with open(args.report, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
                w.writeheader()
                w.writerows(rows)
            print(f"Season {current_season}: {len(export)} clients, {len(rows)} report rows -> {args.report}")
            if args.export:
                Path(args.export).write_text(json.dumps(export, indent=2, default=str))
                print(f"Exported every client's notes -> {args.export}")
            return

        missing = [e["client_id"] for e in edits if e["client_id"] not in by_id]
        if missing:
            sys.exit(f"no client with id {', '.join(map(str, missing))} -- nothing written")
        total = 0
        for e in edits:
            changes = plan_changes(e, by_id[e["client_id"]])
            if not changes:
                continue
            print(f"\n{by_id[e['client_id']]['name']} (#{e['client_id']})")
            for what, before, after in changes:
                total += 1
                print(f"  {what}: {before!r} -> {after!r}")
        print(f"\n{total} change(s) across {len(edits)} client(s).")
        if not args.apply:
            print("Dry run -- nothing written. Add --apply to write.")
            return
        await apply_edits(conn, edits)
        print("Applied.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
