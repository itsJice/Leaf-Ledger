#!/usr/bin/env python3
"""Import the Google Form's existing responses from the Sheet's CSV export.

    cd backend
    .venv/bin/python scripts/import_form_responses.py --csv "Product Request Form (Responses) - Form Responses 1.csv"
    .venv/bin/python scripts/import_form_responses.py --csv ... --ordered "9/14/2026 19:04:29" --ordered 7 --apply

Dry run by default. Columns are matched by header text (the sheet's headers
are the full question text), so a reordered export still imports. Choice
answers keep their full option text; a checkbox cell's picks are recovered by
finding each known option in it -- the options contain commas themselves, so
splitting on ", " would break them. Blank Requestor (column N) is fine: only
the newest rows have one.

The CSV carries no formatting, so rows that are struck through in the Sheet
are named with --ordered, either by their Timestamp exactly as the sheet
shows it or by data row number (1 = the first response). They import as
Ordered; everything else as New. A response already imported (same form,
same timestamp, same client and item) is skipped, so re-running is safe.

Imported rows are marked source='sheet' and are NOT filed onto requests for
the Jobs page (they predate it); new submissions are.
"""
import argparse
import asyncio
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import asyncpg  # noqa: E402

from app.apis.forms import DDL, seed_form  # noqa: E402
from app.libs import forms as F  # noqa: E402


def load_env():
    path = os.path.join(HERE, "..", ".env.supabase")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def parse_rows(text: str, questions: list[dict]) -> tuple[list[dict], list[str]]:
    """CSV text -> [{submitted_at, answers}], plus any headers not recognised."""
    rows = list(csv.reader(text.splitlines(True)))  # keeps quoted multi-line cells whole
    if not rows:
        return [], []
    header = rows[0]
    colmap, unknown = {}, []
    for i, h in enumerate(header):
        if i == 0 and h.strip().lower() == "timestamp":
            continue
        q = F.match_header(h, questions)
        if q:
            colmap[i] = q
        elif h.strip():
            unknown.append(h)
    out = []
    for n, r in enumerate(rows[1:], 1):
        if not any(c.strip() for c in r):
            continue
        answers = {}
        for i, q in colmap.items():
            cell = r[i] if i < len(r) else ""
            if not cell.strip():
                continue
            if q["type"] == "checkboxes":
                answers[q["key"]] = F.parse_checkboxes(cell, q.get("options") or [])
            elif q["type"] in ("radio", "dropdown"):
                answers[q["key"]] = F.parse_choice(cell, q.get("options") or [])
            elif q["type"] == "date":
                answers[q["key"]] = F.parse_date(cell) or cell.strip()
            else:
                answers[q["key"]] = cell.strip()
        out.append({"row": n, "timestamp_text": r[0].strip(), "submitted_at": F.parse_timestamp(r[0]),
                    "answers": answers})
    return out, unknown


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--slug", default=F.PRODUCT_REQUEST_SLUG)
    ap.add_argument("--ordered", action="append", default=[],
                    help="a struck-through row: its Timestamp as shown, or its data row number")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    load_env()
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        await conn.execute(DDL)
        await seed_form(conn, F.PRODUCT_REQUEST_FORM)
        form = await conn.fetchrow("SELECT id FROM ll_app.forms WHERE slug = $1", args.slug)
        qs = [dict(q) | {"options": json.loads(q["options"]) if isinstance(q["options"], str) else q["options"]}
              for q in await conn.fetch("SELECT * FROM ll_app.form_questions WHERE form_id = $1 ORDER BY position",
                                        form["id"])]
        rows, unknown = parse_rows(open(args.csv, encoding="utf-8-sig").read(), qs)
        if unknown:
            print("!! columns not matched to a question (ignored):", unknown)
        ordered = {o.strip() for o in args.ordered}
        tx = conn.transaction()
        await tx.start()
        made = skipped = 0
        try:
            for r in rows:
                status = "Ordered" if (r["timestamp_text"] in ordered or str(r["row"]) in ordered) else "New"
                dup = await conn.fetchval(
                    "SELECT r.id FROM ll_app.form_responses r "
                    "JOIN ll_app.form_answers a ON a.response_id = r.id "
                    "JOIN ll_app.form_questions q ON q.id = a.question_id AND q.key = 'location_item' "
                    "WHERE r.form_id = $1 AND r.submitted_at = $2 AND a.value = $3::jsonb",
                    form["id"], r["submitted_at"], json.dumps(r["answers"].get("location_item")))
                if dup:
                    skipped += 1
                    continue
                rid = await conn.fetchval(
                    "INSERT INTO ll_app.form_responses (form_id, submitted_at, status, source) "
                    "VALUES ($1, $2, $3, 'sheet') RETURNING id", form["id"], r["submitted_at"], status)
                for q in qs:
                    v = r["answers"].get(q["key"])
                    if v not in (None, "", []):
                        await conn.execute(
                            "INSERT INTO ll_app.form_answers (response_id, question_id, value) VALUES ($1,$2,$3::jsonb)",
                            rid, q["id"], json.dumps(v))
                made += 1
                print(f"  row {r['row']:>3} {r['timestamp_text']:>20}  {status:8} "
                      f"{(r['answers'].get('client_name') or '')[:24]:24} {(r['answers'].get('location_item') or '')[:40]}")
            if args.apply:
                await tx.commit()
            else:
                await tx.rollback()
        except BaseException:
            await tx.rollback()
            raise
        print(f"{'IMPORTED' if args.apply else 'DRY RUN -- nothing written'}: {made} responses, {skipped} already there")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
