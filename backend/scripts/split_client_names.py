#!/usr/bin/env python3
"""
Propose (and, only when asked, save) each client's name as parts:
first name, last name, business name (company) and location (site).
See migrations/021_client_name_parts.sql and app/libs/client_names.py.

The app works without this: a client with no saved parts gets them derived
from the name every time it's shown. Saving them just pins the split, so a
name the parser can't be sure about ("Bergstrom, Debbie and Steve") opens
in the edit form the way a person decided it should.

This NEVER changes clients.name -- only the five part columns -- so nothing
that matches on the name (projects, jobs, the sheet sync, the Install
Schedule page) is affected.

Usage (from backend/; reads DATABASE_URL, else backend/.env.supabase):

  1. Dry run (the default, read-only). Writes a CSV with one row per client:
     id, name, the proposed parts, what they'd read as, and an "unsure" flag
     with the reasons (several commas, "&" / "and", titles, "Family", a dash
     that may be a site, a person typed without a comma, ...):

       .venv/bin/python scripts/split_client_names.py --report split.csv

  2. Review the unsure rows. Fix any parts right in the CSV (first_name,
     last_name, company, site); blank all four to skip a row.

  3. Save, either
       --apply                 every confident row (unsure rows are skipped)
       --apply --csv split.csv exactly the rows in the reviewed CSV
     Rows that already have saved parts are never overwritten, a row whose
     name changed since the report is skipped, and a row whose parts would
     read differently from its name is skipped (rename it in the app
     instead). One transaction: any error and nothing is written.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.libs.client_names import (  # noqa: E402
    NAME_PART_COLUMNS, PART_FIELDS, compose_name, has_saved_parts, kind_of, split_name,
)

REPORT_COLUMNS = ["id", "name", "kind", "first_name", "last_name", "company", "site",
                  "reads_as", "unsure", "reasons", "saved_already"]


def propose(rows: list[dict]) -> list[dict]:
    """One report row per client, from rows with id, name and (maybe) saved parts."""
    out = []
    for r in rows:
        parts, reasons = split_name(r["name"])
        saved = has_saved_parts(r)
        out.append({
            "id": r["id"], "name": r["name"], "kind": kind_of(parts),
            **{k: parts.get(k) or "" for k in NAME_PART_COLUMNS},
            "reads_as": compose_name(**parts),
            "unsure": "yes" if reasons else "",
            "reasons": "; ".join(reasons),
            "saved_already": "yes" if saved else "",
        })
    return out


def counts(report: list[dict]) -> dict:
    return {
        "clients": len(report),
        "person": sum(1 for r in report if r["kind"] == "person"),
        "business": sum(1 for r in report if r["kind"] == "business"),
        "both": sum(1 for r in report if r["kind"] == "business + person"),
        "with_location": sum(1 for r in report if r["site"]),
        "unsure": sum(1 for r in report if r["unsure"]),
        "person_sure": sum(1 for r in report if r["kind"] == "person" and not r["unsure"]),
        "business_sure": sum(1 for r in report if r["kind"] == "business" and not r["unsure"]),
        "saved_already": sum(1 for r in report if r["saved_already"]),
    }


def write_report(report: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
        w.writeheader()
        # Unsure first, so the review starts with what needs a human.
        for r in sorted(report, key=lambda x: (not x["unsure"], x["name"].lower())):
            w.writerow(r)


def read_reviewed(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if any((r.get(k) or "").strip() for k in PART_FIELDS)]


def plan_writes(current: list[dict], chosen: list[dict]) -> tuple[list[tuple], list[str]]:
    """(id, first, last, company, site) to write, and why others were skipped.

    ``current`` is the live rows; ``chosen`` the report rows to save."""
    by_id = {r["id"]: r for r in current}
    writes, skipped = [], []
    for c in chosen:
        cid = int(c["id"])
        live = by_id.get(cid)
        if live is None:
            skipped.append(f"{cid}: no such client any more")
            continue
        if has_saved_parts(live):
            skipped.append(f"{cid} {live['name']!r}: already has saved parts")
            continue
        if live["name"] != c["name"]:
            skipped.append(f"{cid}: renamed since the report ({c['name']!r} -> {live['name']!r})")
            continue
        parts = {k: (c.get(k) or "").strip() or None for k in PART_FIELDS}
        if not (parts["first_name"] or parts["last_name"] or parts["company"]):
            skipped.append(f"{cid} {live['name']!r}: no name in the parts")
            continue
        if compose_name(**parts) != live["name"]:
            skipped.append(f"{cid} {live['name']!r}: parts would read "
                           f"{compose_name(**parts)!r} -- rename it in the app instead")
            continue
        writes.append((cid, parts["first_name"], parts["last_name"], parts["company"], parts["site"]))
    return writes, skipped


def load_database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = BACKEND / ".env.supabase"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit(f"No DATABASE_URL set and none in {env_file}")


async def read_clients(conn) -> tuple[list[dict], bool]:
    have = await conn.fetchval(
        "SELECT count(*) FROM information_schema.columns "
        " WHERE table_schema = current_schema() AND table_name = 'clients' "
        "   AND column_name = ANY($1::text[])", list(NAME_PART_COLUMNS))
    has_parts = (have or 0) >= len(NAME_PART_COLUMNS)
    cols = "id, name" + (", " + ", ".join(NAME_PART_COLUMNS) if has_parts else "")
    rows = await conn.fetch(f"SELECT {cols} FROM clients ORDER BY id")
    return [dict(r) for r in rows], has_parts


async def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default="split_client_names.csv", help="where the dry-run CSV goes")
    ap.add_argument("--apply", action="store_true", help="save parts (default: dry run, read-only)")
    ap.add_argument("--csv", help="with --apply: save exactly the rows of this reviewed CSV")
    args = ap.parse_args(argv)

    import asyncpg

    conn = await asyncpg.connect(load_database_url(), statement_cache_size=0)
    try:
        if not args.apply:
            await conn.execute("SET default_transaction_read_only = on")
        current, has_parts = await read_clients(conn)
        report = propose(current)
        write_report(report, args.report)
        c = counts(report)
        print(f"{c['clients']} clients: {c['person']} person, {c['business']} business, "
              f"{c['both']} business + person; {c['with_location']} with a location; "
              f"{c['unsure']} unsure (sure: {c['person_sure']} person, {c['business_sure']} business); "
              f"{c['saved_already']} already saved")
        print(f"report: {args.report}")
        if not args.apply:
            print("dry run -- nothing written")
            return
        if not has_parts:
            sys.exit("The name-part columns don't exist yet: deploy the app (it adds them) first.")
        chosen = read_reviewed(args.csv) if args.csv else [r for r in report if not r["unsure"]]
        writes, skipped = plan_writes(current, chosen)
        for s in skipped:
            print("skip", s)
        async with conn.transaction():
            await conn.executemany(
                "UPDATE clients SET first_name = $2, last_name = $3, company = $4, site = $5 "
                "WHERE id = $1 AND first_name IS NULL AND last_name IS NULL "
                "AND company IS NULL AND site IS NULL",
                writes,
            )
        print(f"saved parts for {len(writes)} clients; skipped {len(skipped)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
