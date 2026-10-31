#!/usr/bin/env python3
"""
Fill each client's Google Drive links (clients.drive_folder_url and
drive_photos_url, migrations/026) from the client -> folder CSV.

The CSV needs a header row with at least:

    client_name        the client, as the Clients tab or the sheet spells it
    folder_url         the client's Drive folder        (optional per row)
    photos_folder_url  the photos folder inside it      (optional per row)

Any other columns (row, notes, confidence, ...) are ignored but the "row"
column, when there, is echoed in the report so a line can be found again.

Clients are matched on name, the sheet's spelling or a former name,
ignoring case, commas, periods and extra spaces -- the way the Install
Schedule page and scripts/migrate_client_notes.py match. A name that
matches nobody, or more than one client, is skipped and listed.

Dry run by default: nothing is written, and every row is listed with what
would happen. --go writes, in one transaction (any error and nothing is
written), through the same writer as PUT /api/clients/{id}/drive-links.

  - A blank cell never clears a link.
  - A link already set to something else is left alone and listed as
    "differs"; add --overwrite to replace those too.
  - Only https://drive.google.com/ links are accepted (app.libs.drive_links).

Usage (from backend/; reads DATABASE_URL, else backend/.env.supabase):

    .venv/bin/python scripts/import_drive_folders.py folders.csv
    .venv/bin/python scripts/import_drive_folders.py folders.csv --report plan.csv
    .venv/bin/python scripts/import_drive_folders.py folders.csv --go
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.libs import drive_links  # noqa: E402

#: CSV column -> clients column.
CSV_COLUMNS = {"folder_url": "drive_folder_url", "photos_folder_url": "drive_photos_url"}
REPORT_COLUMNS = ("csv_row", "client_name", "status", "client_id", "matched_name",
                  "field", "current", "new", "note")


def norm_name(name: Any) -> str:
    """Case, commas, periods and runs of spaces don't count."""
    return re.sub(r"\s+", " ", re.sub(r"[,.]", "", str(name or "").strip().lower())).strip()


def index_clients(clients: Iterable[dict]) -> dict:
    """norm name -> list of clients answering to it (name, sheet name, former names)."""
    idx: dict = {}
    for c in clients:
        keys = {norm_name(n) for n in [c.get("name"), c.get("sheet_name"), *(c.get("former_names") or [])]}
        for k in keys:
            if k:
                idx.setdefault(k, []).append(c)
    return idx


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        if "client_name" not in headers or not any(h in headers for h in CSV_COLUMNS):
            sys.exit(f"{path}: needs a client_name column and folder_url and/or photos_folder_url")
        rows = []
        for n, raw in enumerate(reader, start=2):  # line 1 is the header
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
            row["_line"] = n
            rows.append(row)
        return rows


def plan(rows: list[dict], clients: list[dict], overwrite: bool = False) -> list[dict]:
    """One report line per CSV row and field. Status is one of:
    set, same, differs (kept), overwrite, blank, bad_url, no_match,
    ambiguous, duplicate. Only "set" and "overwrite" lines are written."""
    idx = index_clients(clients)
    out: list[dict] = []
    seen: dict = {}  # (client_id, column) -> csv line that set it

    def line(row, status, client=None, field="", current=None, new=None, note=""):
        out.append({
            "csv_row": row.get("row") or row.get("_line"),
            "client_name": row.get("client_name", ""),
            "status": status,
            "client_id": client["id"] if client else "",
            "matched_name": client["name"] if client else "",
            "field": field, "current": current or "", "new": new or "", "note": note,
        })

    for row in rows:
        name = row.get("client_name", "")
        hits = idx.get(norm_name(name), [])
        unique = {c["id"]: c for c in hits}
        if not name.strip():
            line(row, "no_match", note="blank client_name")
            continue
        if not unique:
            line(row, "no_match")
            continue
        if len(unique) > 1:
            line(row, "ambiguous", note="matches " + "; ".join(f"#{c['id']} {c['name']}" for c in unique.values()))
            continue
        client = next(iter(unique.values()))
        for csv_col, col in CSV_COLUMNS.items():
            raw = row.get(csv_col, "")
            current = client.get(col)
            if not raw:
                line(row, "blank", client, col, current)
                continue
            try:
                new = drive_links.clean_drive_url(raw, drive_links.LABELS[col])
            except drive_links.DriveLinkError as exc:
                line(row, "bad_url", client, col, current, raw, str(exc))
                continue
            key = (client["id"], col)
            if key in seen:
                line(row, "duplicate", client, col, current, new, f"already set by CSV row {seen[key]}")
                continue
            seen[key] = row.get("row") or row.get("_line")
            if current == new:
                line(row, "same", client, col, current, new)
            elif current and not overwrite:
                line(row, "differs", client, col, current, new, "kept; --overwrite to replace")
            else:
                line(row, "overwrite" if current else "set", client, col, current, new)
    return out


def writes_from(report: list[dict]) -> dict:
    """client_id -> {column: new} for the lines that write."""
    out: dict = {}
    for r in report:
        if r["status"] in ("set", "overwrite"):
            out.setdefault(r["client_id"], {})[r["field"]] = r["new"]
    return out


def summary(report: list[dict]) -> dict:
    counts: dict = {}
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


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


async def read_clients(conn) -> list[dict]:
    """Read-only: before the app has added the columns (first deploy after
    migrations/026), every client reads as having no links -- the dry run
    never runs DDL. --go adds them through the app's own ensure_schema."""
    have = await conn.fetchval(
        "SELECT count(*) FROM information_schema.columns "
        " WHERE table_schema = current_schema() AND table_name = 'clients' "
        "   AND column_name = ANY($1::text[])",
        list(drive_links.DRIVE_LINK_COLUMNS),
    )
    cols = ("drive_folder_url, drive_photos_url" if (have or 0) >= len(drive_links.DRIVE_LINK_COLUMNS)
            else "NULL::text AS drive_folder_url, NULL::text AS drive_photos_url")
    return [dict(r) for r in await conn.fetch(
        f"SELECT id, name, sheet_name, former_names, {cols} FROM clients")]


async def apply(conn, writes: dict) -> None:
    from app.apis import clients as clients_api

    async with conn.transaction():
        for client_id, links in writes.items():
            row = await clients_api.write_drive_links(conn, client_id, links)
            if row is None:
                raise RuntimeError(f"client #{client_id} disappeared -- nothing written")


def print_report(report: list[dict], verbose: bool) -> None:
    for r in report:
        if not verbose and r["status"] in ("same", "blank"):
            continue
        who = f"#{r['client_id']} {r['matched_name']}" if r["client_id"] else ""
        bits = [f"row {r['csv_row']}", r["client_name"], r["status"].upper()]
        if who:
            bits.append(f"-> {who}")
        if r["field"]:
            bits.append(r["field"])
        if r["current"] and r["status"] in ("differs", "overwrite"):
            bits.append(f"now {r['current']}")
        if r["new"]:
            bits.append(r["new"])
        if r["note"]:
            bits.append(f"({r['note']})")
        print("  " + " | ".join(bits))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="client -> folder CSV (client_name, folder_url, photos_folder_url, ...)")
    ap.add_argument("--go", action="store_true", help="write; without it nothing is changed")
    ap.add_argument("--overwrite", action="store_true", help="also replace links that are already set")
    ap.add_argument("--report", default=None, help="write every planned line to this CSV")
    ap.add_argument("-v", "--verbose", action="store_true", help="list unchanged and blank cells too")
    args = ap.parse_args()

    rows = read_csv(args.csv)
    _load_env()
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        clients = await read_clients(conn)
        report = plan(rows, clients, overwrite=args.overwrite)
        writes = writes_from(report)
        print(f"{len(rows)} CSV rows, {len(clients)} clients in the app")
        print_report(report, args.verbose)
        print("Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(summary(report).items())))
        if args.report:
            with open(args.report, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
                w.writeheader()
                w.writerows(report)
            print(f"Report -> {args.report}")
        n_links = sum(len(v) for v in writes.values())
        if not args.go:
            print(f"DRY RUN: would write {n_links} link(s) on {len(writes)} client(s). Add --go to write.")
            return
        if not writes:
            print("Nothing to write.")
            return
        await apply(conn, writes)
        print(f"Wrote {n_links} link(s) on {len(writes)} client(s).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
