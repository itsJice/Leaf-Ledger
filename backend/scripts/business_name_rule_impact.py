#!/usr/bin/env python3
"""
READ-ONLY report: which clients' display names change under the business
name rule (user, 2026-10-09: "businesses go by their business name").

Since that rule, ``compose_name`` makes "Business" (+ " | Location") whenever
a company is set; the person is kept on the card as the contact. Names
saved under the old rule ("Business | Last, First") don't change by
themselves -- nothing here writes -- but they now read differently from their
parts, and the next time someone saves the name boxes the app renames them
everywhere. This lists them first, with collisions: two cards that would end
up with the same name (the unique index refuses the second one, so those
need a Location before any rename). "Business | Location" names are
unchanged.

Parts are the saved ones, or derived from the name (``name_parts``) for a
client that has none saved -- the same parts the edit form shows.

Usage (from backend/; reads DATABASE_URL, else backend/.env.supabase):

    .venv/bin/python scripts/business_name_rule_impact.py --report impact.csv

The connection is opened read-only (default_transaction_read_only); renames
go through PUT /clients/update/{id} (rename-everywhere) with the user's OK.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.libs.client_names import (  # noqa: E402
    PART_FIELDS, compose_name, compose_name_before_20261009, name_parts,
)
from split_client_names import load_database_url  # noqa: E402

REPORT_COLUMNS = ["id", "old_name", "new_name", "kind", "first_name", "last_name", "company", "site",
                  "parts_saved", "contact_person", "collision", "note"]


def _key(name: str) -> str:
    return (name or "").strip().lower()


def impact(rows: list[dict]) -> list[dict]:
    """One report row per client whose name would change: a company plus a
    person and/or a location, where the new rule reads differently."""
    out = []
    for r in rows:
        p = name_parts(r)
        parts = {k: p.get(k) for k in PART_FIELDS}
        person = bool(parts["first_name"] or parts["last_name"])
        if not parts["company"] or not (person or parts["site"]):
            continue
        new = compose_name(**parts)
        if new == r["name"]:
            continue
        old_rule = compose_name_before_20261009(**parts)
        out.append({
            "id": r["id"], "old_name": r["name"], "new_name": new,
            "kind": "business + person" if person else "business + location",
            **{k: parts[k] or "" for k in PART_FIELDS},
            "parts_saved": "yes" if p["name_parts_saved"] else "no (derived from the name)",
            "contact_person": " ".join(x for x in (parts["first_name"], parts["last_name"]) if x),
            "collision": "",
            "note": "" if old_rule == r["name"] else f'name doesn\'t match its parts today (they read "{old_rule}")',
        })

    # Collisions: with another client's current name, or with another
    # renamed client's new name.
    renamed = {row["id"] for row in out}
    current = defaultdict(list)
    for r in rows:
        if r["id"] not in renamed:
            current[_key(r["name"])].append(r)
    new_names = defaultdict(list)
    for row in out:
        new_names[_key(row["new_name"])].append(row)
    for row in out:
        hits = [f'#{r["id"]} "{r["name"]}" (current name)' for r in current[_key(row["new_name"])]]
        hits += [f'#{o["id"]} "{o["old_name"]}" (also renamed to it)'
                 for o in new_names[_key(row["new_name"])] if o["id"] != row["id"]]
        row["collision"] = "; ".join(hits)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="CSV path to write")
    args = ap.parse_args()

    import asyncpg

    conn = await asyncpg.connect(load_database_url(), statement_cache_size=0,
                                 server_settings={"default_transaction_read_only": "on"})
    try:
        rows = [dict(r) for r in await conn.fetch(
            "SELECT id, name, first_name, last_name, company, site FROM clients ORDER BY LOWER(name), id")]
    finally:
        await conn.close()

    report = impact(rows)
    with open(args.report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
        w.writeheader()
        w.writerows(report)
    by_kind = defaultdict(int)
    for row in report:
        by_kind[row["kind"]] += 1
    print(f"{len(rows)} clients; {len(report)} would be renamed "
          f"({', '.join(f'{n} {k}' for k, n in sorted(by_kind.items())) or 'none'}); "
          f"{sum(1 for r in report if r['collision'])} with a collision. Wrote {args.report}")
    for row in report:
        flag = f"  COLLISION: {row['collision']}" if row["collision"] else ""
        print(f'  #{row["id"]}: "{row["old_name"]}" -> "{row["new_name"]}"{flag}')


if __name__ == "__main__":
    asyncio.run(main())
