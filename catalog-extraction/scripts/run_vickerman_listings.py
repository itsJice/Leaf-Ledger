#!/usr/bin/env python3
"""Crawl all Vickerman header listings for coverage verification."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from catalog_extraction.vickerman_listings import crawl_all_headers

OUT = ROOT / "outputs" / "vickerman-full" / "listings.json"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    results = crawl_all_headers(OUT, log=log)
    total_rows = sum(
        sub.get("total_available", 0)
        for header in results["headers"]
        for sub in header["subcategories"]
    )
    unique = {
        sku
        for header in results["headers"]
        for sub in header["subcategories"]
        for sku in sub["skus"]
    }
    log(f"listing rows (available filter): {total_rows}")
    log(f"unique SKUs across all headers: {len(unique)}")
