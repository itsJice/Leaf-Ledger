#!/usr/bin/env python3
"""Batch-load all 23 THE FINDINGS spreadsheets into products.

Dry-run by default; pass --commit to write. Reuses the single-supplier
importer (findings_intake) + upsert SQL (load_findings). Each file is mapped to
its supplier by id for robustness.

    python scripts/load_all_findings.py [--commit]
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import dotenv

dotenv.load_dotenv(BACKEND / ".env")
dotenv.load_dotenv(BACKEND / ".env.dev", override=True)

import asyncpg  # noqa: E402

from app.libs.findings_intake import parse_findings_xlsx  # noqa: E402
from load_findings import UPSERT_SQL, _values  # noqa: E402

FINDINGS = Path("/Users/justice/Documents/From Selenium To Leaf & Ledger/THE FINDINGS")

# (supplier_id, filename)
MAPPING = [
    (15, "AccentDecor_Catalog_2026.xlsx"),
    (7,  "AmazingGreen_Catalog_2026.xlsx"),
    (4,  "AmericanBest_Catalog_2026.xlsx"),
    (5,  "AutographFoliages_Catalog_2026.xlsx"),
    (8,  "Craftex_Catalog_2026.xlsx"),
    (22, "HRCasabella_Catalog_2026.xlsx"),
    (23, "JacksonPottery_Catalog_2026.xlsx"),
    (21, "PMJC_Catalog_2026.xlsx"),
    (25, "RockWarehouse_Catalog_2026.xlsx"),
    (2,  "SelectArtificials_Catalog_2026.xlsx"),
    (14, "SuperMoss_Catalog_2026.xlsx"),
    (9,  "Vickerman_Catalog_2026.xlsx"),
    (6,  "Winward_Catalog_2026.xlsx"),
    (1,  "allstate_products.xlsx"),
    (18, "athome_selected_categories.xlsx"),
    (19, "dfw_vases_products.xlsx"),
    (11, "forestline_products.xlsx"),
    (20, "jayscotts_products.xlsx"),
    (3,  "regency_products.xlsx"),
    (10, "schusters_products.xlsx"),
    (13, "second_flor_products.xlsx"),
    (16, "unlimited_container_products.xlsx"),
    (17, "wgv_products.xlsx"),
]


async def main() -> int:
    commit = "--commit" in sys.argv
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    total = 0
    missing = []
    print(f"{'sid':>3}  {'supplier':24s} {'file':38s} {'rows':>7}")
    try:
        for sid, fname in MAPPING:
            path = FINDINGS / fname
            sup = await c.fetchval("SELECT name FROM suppliers WHERE id=$1", sid)
            if not path.exists():
                missing.append(fname)
                print(f"{sid:>3}  {str(sup)[:24]:24s} {fname[:38]:38s}  MISSING FILE")
                continue
            if sup is None:
                print(f"{sid:>3}  {'???':24s} {fname[:38]:38s}  MISSING SUPPLIER")
                continue
            rows, rep = parse_findings_xlsx(str(path))
            if commit:
                values = [_values(sid, p) for p in rows]
                CH = 1000
                async with c.transaction():
                    for i in range(0, len(values), CH):
                        await c.executemany(UPSERT_SQL, values[i:i + CH])
            total += len(rows)
            print(f"{sid:>3}  {sup[:24]:24s} {fname[:38]:38s} {rep['rows_ok']:>7}")
        print(f"\n{'COMMITTED' if commit else 'DRY RUN'} — total rows: {total}")
        if missing:
            print("MISSING FILES:", missing)
        if commit:
            gt = await c.fetchval("SELECT COUNT(*) FROM products")
            print(f"products in DB now: {gt}")
        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
