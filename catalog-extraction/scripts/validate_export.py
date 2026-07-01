#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"supplier_key", "supplier_name", "sku", "name", "source_url"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a catalog export before Leaf & Ledger import.")
    parser.add_argument("path", help="CSV/XLSX export path.")
    args = parser.parse_args()

    path = Path(args.path)
    frame = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)

    missing_columns = sorted(REQUIRED_COLUMNS - set(frame.columns))
    missing_required_rows = {}
    for column in sorted(REQUIRED_COLUMNS & set(frame.columns)):
        missing_required_rows[column] = int(frame[column].fillna("").astype(str).str.strip().eq("").sum())

    duplicate_skus = 0
    if {"supplier_key", "sku"}.issubset(frame.columns):
        duplicate_skus = int(frame.duplicated(subset=["supplier_key", "sku"], keep=False).sum())

    report = {
        "path": str(path),
        "rows": int(len(frame)),
        "missing_columns": missing_columns,
        "missing_required_rows": missing_required_rows,
        "duplicate_supplier_skus": duplicate_skus,
        "ok": not missing_columns and not any(missing_required_rows.values()) and duplicate_skus == 0,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
