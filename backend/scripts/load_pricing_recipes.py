#!/usr/bin/env python3
"""Load the TBDG pricing worksheets into the historical recipe tables.

Dry-run by default; pass --commit to write. Fills ``recipe_source_files`` ->
``historical_recipes`` -> ``historical_recipe_components``, which power the
builder's build intelligence (what a Tree is typically made of, typical
quantities, typical cost) and the materials vocabulary used to search designs by
what they are made from.

    python scripts/load_pricing_recipes.py                       # dry run, all formats
    python scripts/load_pricing_recipes.py --format tbdg_production_2025 --commit
    python scripts/load_pricing_recipes.py --commit --verbose

Notes
-----
* The corpus is mirrored across ``PRICING`` and ``PRICING 2..5``, so files are
  deduplicated by content hash. The duplicates are still registered in
  ``recipe_source_files`` (status ``duplicate``) pointing at the canonical copy,
  so provenance stays complete.
* Re-running is idempotent: source files key off ``source_path``, recipes off
  ``source_file_id``, and a recipe's components are replaced wholesale.
* Values are imported, never formulas. Rows that deviate from the documented
  pricing chain are flagged in ``historical_recipe_components.formulas`` rather
  than corrected -- what the business actually charged is the record.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import dotenv  # noqa: E402

for env_file in (".env", ".env.dev", ".env.supabase"):
    dotenv.load_dotenv(BACKEND / env_file, override=True)

import asyncpg  # noqa: E402

from app.libs import recipe_intake as ri  # noqa: E402

# The worksheets live beside this repo in the Leaf & Ledger project group.
# Override with LL_RECIPES_DIR if you keep them somewhere else.
GROUP = BACKEND.parents[1]
RECIPES_DIR = Path(os.environ.get("LL_RECIPES_DIR") or GROUP / "pricing-recipes" / "RECIPES")

# Path stored in recipe_source_files.source_path -- project-relative so the rows
# stay meaningful on another machine.
PATH_PREFIX = "pricing-recipes/RECIPES"


# ── Discovery ─────────────────────────────────────────────────────────────────


def discover(root: Path) -> list[tuple[Path, str]]:
    """Every worksheet under *root*, as (path, relative_path)."""
    return [
        (p, str(p.relative_to(root)))
        for p in sorted(root.rglob("*.xlsx"))
        if not p.name.startswith("~$")
    ]


def _canonical_rank(relative_path: str) -> tuple[int, int, str]:
    """Sort key picking the canonical copy of a duplicated file.

    Prefers the shallowest path outside the ``PRICING n`` mirror directories --
    that is the copy a human would consider the original.
    """
    parts = Path(relative_path).parts
    mirrored = any(ri._PRICING_DIR.match(p) for p in parts[:-1])
    return (1 if mirrored else 0, len(parts), relative_path)


# ── SQL ───────────────────────────────────────────────────────────────────────

SOURCE_FILE_SQL = """
INSERT INTO recipe_source_files (
    source_path, relative_path, file_name, extension, file_kind, sha256,
    size_bytes, status, item_code, linked_item_code, parser_version,
    error_message, metadata, updated_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb, now())
ON CONFLICT (source_path) DO UPDATE SET
    relative_path = EXCLUDED.relative_path,
    file_name     = EXCLUDED.file_name,
    extension     = EXCLUDED.extension,
    file_kind     = EXCLUDED.file_kind,
    sha256        = EXCLUDED.sha256,
    size_bytes    = EXCLUDED.size_bytes,
    status        = EXCLUDED.status,
    item_code     = EXCLUDED.item_code,
    linked_item_code = EXCLUDED.linked_item_code,
    parser_version   = EXCLUDED.parser_version,
    error_message    = EXCLUDED.error_message,
    metadata         = EXCLUDED.metadata,
    updated_at       = now()
RETURNING id
"""

RECIPE_SQL = """
INSERT INTO historical_recipes (
    source_file_id, item_code, customer_item_code, product_family, build_type,
    description, source_collection, recipe_year, dimensions, container_details,
    pricing_summary, raw_header, visual_reference_count, updated_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13, now())
ON CONFLICT (source_file_id) DO UPDATE SET
    item_code          = EXCLUDED.item_code,
    customer_item_code = EXCLUDED.customer_item_code,
    product_family     = EXCLUDED.product_family,
    build_type         = EXCLUDED.build_type,
    description        = EXCLUDED.description,
    source_collection  = EXCLUDED.source_collection,
    recipe_year        = EXCLUDED.recipe_year,
    dimensions         = EXCLUDED.dimensions,
    container_details  = EXCLUDED.container_details,
    pricing_summary    = EXCLUDED.pricing_summary,
    raw_header         = EXCLUDED.raw_header,
    visual_reference_count = EXCLUDED.visual_reference_count,
    updated_at         = now()
RETURNING id
"""

COMPONENT_SQL = """
INSERT INTO historical_recipe_components (
    recipe_id, line_order, component_label, vendor, supplier_sku, description,
    quantity, first_cost, landed_cost, retail, extended_total, formulas, raw_row)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13::jsonb)
"""


def _num(value: Optional[float]) -> Optional[Decimal]:
    """asyncpg wants Decimal for NUMERIC columns."""
    return None if value is None else Decimal(str(value))


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


# ── Loading ───────────────────────────────────────────────────────────────────


async def write_recipe(conn, source_file_id: int, recipe: ri.ParsedRecipe,
                       collection: str) -> int:
    recipe_id = await conn.fetchval(
        RECIPE_SQL,
        source_file_id, recipe.item_code, recipe.customer_item_code,
        recipe.product_family, recipe.build_type, recipe.description,
        collection, recipe.recipe_year,
        _json(recipe.dimensions), _json(recipe.container_details),
        _json(recipe.pricing_summary), _json(recipe.raw_header),
        recipe.visual_reference_count,
    )
    # Replace components wholesale so a re-run cannot duplicate or orphan lines.
    await conn.execute("DELETE FROM historical_recipe_components WHERE recipe_id=$1", recipe_id)
    await conn.executemany(COMPONENT_SQL, [
        (recipe_id, c.line_order, c.component_label, c.vendor, c.supplier_sku,
         c.description, _num(c.quantity), _num(c.first_cost), _num(c.landed_cost),
         _num(c.retail), _num(c.extended_total), _json(c.formulas), _json(c.raw_row))
        for c in recipe.components
    ])
    return recipe_id


async def write_source_file(conn, *, relative_path: str, path: Path, file_kind: str,
                            sha256: str, status: str, item_code: Optional[str],
                            linked_item_code: Optional[str], error: Optional[str],
                            metadata: dict[str, Any]) -> int:
    return await conn.fetchval(
        SOURCE_FILE_SQL,
        f"{PATH_PREFIX}/{relative_path}", relative_path, path.name,
        path.suffix.lstrip(".").lower(), file_kind, sha256, path.stat().st_size,
        status, item_code, linked_item_code, ri.PARSER_VERSION, error,
        _json(metadata),
    )


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true", help="write to the database")
    ap.add_argument("--format", default="all",
                    help="format family to load: all (default), "
                         + ", ".join(ri.SUPPORTED_FORMATS))
    ap.add_argument("--dir", default=str(RECIPES_DIR), help="worksheet root")
    ap.add_argument("--limit", type=int, help="stop after N parsed recipes (smoke test)")
    ap.add_argument("--verbose", action="store_true", help="one line per file")
    args = ap.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        print(f"recipe directory not found: {root}", file=sys.stderr)
        return 2

    wanted = None if args.format == "all" else {args.format}
    if wanted and not wanted <= set(ri.SUPPORTED_FORMATS) | {ri.FORMAT_PRICE_SHEET, ri.FORMAT_UNKNOWN}:
        print(f"unknown --format {args.format!r}", file=sys.stderr)
        return 2

    files = discover(root)
    print(f"{'COMMIT' if args.commit else 'DRY RUN'} — {len(files)} xlsx under {root}")
    print(f"format filter: {args.format}\n")

    # ── pass 1: hash + sniff, then pick one canonical copy per content hash ───
    by_hash: dict[str, list[str]] = defaultdict(list)
    meta: dict[str, dict[str, Any]] = {}
    for path, rel in files:
        digest = ri.sha256_file(path)
        family, a1 = ri.sniff_format(path)
        by_hash[digest].append(rel)
        meta[rel] = {"path": path, "sha256": digest, "family": family, "a1": a1}
    canonical = {min(rels, key=_canonical_rank) for rels in by_hash.values()}
    print(f"deduplicated: {len(files)} files -> {len(canonical)} unique by content hash\n")

    # ── pass 2: parse + load ─────────────────────────────────────────────────
    stats = Counter()
    skips: Counter = Counter()
    families = Counter()
    build_types = Counter()
    parsed_total = 0
    component_total = 0
    anomaly_total = 0

    conn = None
    if args.commit:
        conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)

    try:
        for path, rel in files:
            info = meta[rel]
            family = info["family"]
            families[family] += 1

            if wanted and family not in wanted:
                stats["filtered"] += 1
                continue

            duplicate_of = None
            if rel not in canonical:
                duplicate_of = min(by_hash[info["sha256"]], key=_canonical_rank)

            recipe: Optional[ri.ParsedRecipe] = None
            status = "imported"
            error: Optional[str] = None

            if duplicate_of is not None:
                status, error = "duplicate", None
                skips[f"duplicate of {Path(duplicate_of).name}"] += 0  # counted below
                skips["duplicate content (mirrored PRICING folder)"] += 1
            elif family not in ri.SUPPORTED_FORMATS:
                status = "unsupported"
                error = f"no adapter for {ri.FORMAT_LABELS.get(family, family)}"
                skips[f"unsupported format: {info['a1'] or '(blank A1)'}"] += 1
            elif args.limit is not None and parsed_total >= args.limit:
                stats["filtered"] += 1
                continue
            else:
                try:
                    recipe = ri.parse_recipe_xlsx(path, format_family=family)
                except ri.RecipeParseError as exc:
                    status, error = "skipped", str(exc)
                    skips[str(exc)] += 1
                except Exception as exc:  # a malformed workbook must not stop the run
                    status, error = "error", f"{type(exc).__name__}: {exc}"
                    skips[f"error: {type(exc).__name__}"] += 1

            collection = ri.source_collection(rel)
            metadata: dict[str, Any] = {
                "a1": info["a1"],
                "format_family": family,
                "source_collection": collection,
                "duplicate_paths": sorted(r for r in by_hash[info["sha256"]] if r != rel),
            }
            if duplicate_of is not None:
                metadata["duplicate_of"] = f"{PATH_PREFIX}/{duplicate_of}"
            if recipe is not None:
                parsed_total += 1
                component_total += len(recipe.components)
                anomaly_total += recipe.anomaly_count
                build_types[recipe.build_type or "(none)"] += 1
                metadata.update({
                    "components": len(recipe.components),
                    "anomalies": recipe.anomaly_count,
                    "unpriced_lines": len(recipe.raw_header.get("unpriced_lines") or []),
                })
            stats[status] += 1

            if args.verbose:
                detail = (f"{len(recipe.components)} comp, {recipe.anomaly_count} anom, "
                          f"{recipe.build_type}" if recipe else (error or ""))
                print(f"  {status:11s} {family:24s} {rel[:56]:56s} {detail}")

            if conn is not None:
                async with conn.transaction():
                    source_file_id = await write_source_file(
                        conn, relative_path=rel, path=path,
                        file_kind=family, sha256=info["sha256"], status=status,
                        item_code=recipe.item_code if recipe else None,
                        linked_item_code=recipe.customer_item_code if recipe else None,
                        error=error, metadata=metadata,
                    )
                    if recipe is not None:
                        await write_recipe(conn, source_file_id, recipe, collection)
                    else:
                        # a file that no longer parses must not keep a stale recipe
                        await conn.execute(
                            "DELETE FROM historical_recipes WHERE source_file_id=$1",
                            source_file_id)

        # ── summary ──────────────────────────────────────────────────────────
        print("\n" + "=" * 72)
        print(f"{'COMMITTED' if args.commit else 'DRY RUN'} — no rows written" if not args.commit
              else "COMMITTED")
        print(f"  files seen        {len(files)}")
        print(f"  unique by hash    {len(canonical)}")
        print(f"  recipes parsed    {parsed_total}")
        print(f"  components        {component_total}")
        print(f"  flagged anomalies {anomaly_total}")

        print("\n  status:")
        for key, count in stats.most_common():
            print(f"    {key:14s} {count:5d}")

        print("\n  formats seen:")
        for key, count in families.most_common():
            mark = "ok " if key in ri.SUPPORTED_FORMATS else "-- "
            print(f"    {mark}{key:26s} {count:5d}  {ri.FORMAT_LABELS.get(key, '')}")

        if skips:
            print("\n  skipped, by reason:")
            for reason, count in skips.most_common():
                if count:
                    print(f"    {count:5d}  {reason[:80]}")

        if build_types:
            print("\n  build types derived:")
            for key, count in build_types.most_common():
                print(f"    {count:5d}  {key}")

        if conn is not None:
            for table in ("recipe_source_files", "historical_recipes",
                          "historical_recipe_components"):
                total = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"\n  {table:30s} {total:6d} rows")
    finally:
        if conn is not None:
            await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
