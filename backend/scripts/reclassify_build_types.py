#!/usr/bin/env python3
"""Re-run build-type classification over the imported historical recipes.

Why: the original keyword classifier had two defects that mislabelled real builds.

1. **Negated vessel mentions matched.** "Container Only" fired on the word
   "container" *inside* "(Container Not Included)" -- the exact inverse of its
   meaning -- filing four 9-10' Dracaena pom-pom trees as containers.
2. **Missing species.** `dracaena`, `croton`, `schefflera`, `zamia` were in no
   keyword list, so one species scattered across three build types
   (dracaena: Container Only 5 / Tree 4 / Plant & Bush 1). Succulent names
   (`echeveria`, `sedum`, `tillandsia`, `aeonium`, `donkey tail`, `greenery`)
   were missing too, so those builds fell through to the taxonomy fallback and
   came back as "Container Only" or NULL.

Both are fixed in `app.libs.recipe_intake` (vessel-negation stripping, added
species, and word-boundary matching that replaces the `"pot "` hack). This script
recomputes `historical_recipes.build_type` with the corrected logic.

ONLY `build_type` is written. Nothing else is touched -- no components, no
pricing, no dimensions. Pricing cannot be affected.

Usage:
    .venv/bin/python scripts/reclassify_build_types.py            # dry run
    .venv/bin/python scripts/reclassify_build_types.py --commit   # write
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.libs.recipe_intake import derive_build_type  # noqa: E402


def _load_env() -> str:
    backend = HERE.parent
    for name in (".env.supabase", ".env.dev", ".env"):
        p = backend / name
        if p.exists():
            dotenv.load_dotenv(p, override=True)
            break
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set (looked for backend/.env.supabase)")
    return url


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    url = _load_env()
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            """SELECT id, description, item_code, product_family, build_type, raw_header
                 FROM historical_recipes ORDER BY id"""
        )

        # Component descriptions, in sheet order -- the importer's fallback
        # signal for sheets with no DESCRIPTION cell (22 recipes rely on it).
        comp_rows = await conn.fetch(
            """SELECT recipe_id, description FROM historical_recipe_components
                 ORDER BY recipe_id, line_order, id"""
        )
        comps: dict[int, list[str]] = {}
        for cr in comp_rows:
            comps.setdefault(cr["recipe_id"], []).append(cr["description"])

        def classify(r) -> str | None:
            """Exactly `recipe_intake._apply_derived`: description alone first,
            then description + item_code + the first 6 component descriptions."""
            signals = [r["description"], r["item_code"]]
            signals += comps.get(r["id"], [])[:6]
            return derive_build_type(r["description"]) or derive_build_type(*signals)

        changes: list[dict] = []
        for r in rows:
            new = classify(r)
            if new != r["build_type"]:
                changes.append(
                    {
                        "id": r["id"],
                        "description": r["description"],
                        "old": r["build_type"],
                        "new": new,
                    }
                )

        before = Counter((r["build_type"] or "(NULL)") for r in rows)
        after = Counter()
        for r in rows:
            after[classify(r) or "(NULL)"] += 1

        print(f"recipes: {len(rows)}   would change: {len(changes)}\n")
        print(f"{'build_type':24} {'before':>7} {'after':>7}  delta")
        for key in sorted(set(before) | set(after)):
            b, a = before.get(key, 0), after.get(key, 0)
            mark = "" if b == a else f"  {a - b:+d}"
            print(f"  {key:22} {b:>7} {a:>7}{mark}")

        if changes:
            print(f"\n--- {len(changes)} reclassifications ---")
            for c in changes:
                desc = (c["description"] or "(no description)")[:50]
                print(f"  #{c['id']:>4}  {str(c['old']):<18} -> {str(c['new']):<18}  {desc}")

        # A NULL result where we previously had a value would be a regression.
        lost = [c for c in changes if c["new"] is None and c["old"] is not None]
        if lost:
            print(f"\n!! {len(lost)} recipes would LOSE their build_type -- refusing to write")
            for c in lost:
                print(f"     #{c['id']} {c['old']} -> NULL  {str(c['description'])[:44]}")
            raise SystemExit(1)

        if not args.commit:
            print("\nDRY RUN -- nothing written. Re-run with --commit to apply.")
            return
        if not changes:
            print("\nNothing to do (already up to date).")
            return

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = HERE / f"build_type_backup_{stamp}.json"
        backup.write_text(
            json.dumps(
                [{"id": r["id"], "build_type": r["build_type"]} for r in rows], indent=2
            )
        )
        print(f"\nbackup written: {backup.name}")

        async with conn.transaction():
            for c in changes:
                await conn.execute(
                    "UPDATE historical_recipes SET build_type = $2, updated_at = now() WHERE id = $1",
                    c["id"],
                    c["new"],
                )
            # Post-condition: every row now matches the classifier, and the
            # component/pricing data is untouched.
            check = await conn.fetch(
                "SELECT id, description, item_code, product_family, build_type FROM historical_recipes"
            )
            mismatched = [r["id"] for r in check if classify(r) != r["build_type"]]
            if mismatched:
                raise RuntimeError(f"post-check failed for {len(mismatched)} rows -- rolling back")
            null_after = sum(1 for r in check if r["build_type"] is None)
            print(f"wrote {len(changes)} rows; NULL build_type remaining: {null_after}")

        print("committed.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
