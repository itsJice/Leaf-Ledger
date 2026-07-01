#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from catalog_extraction.exporter import write_export
from catalog_extraction.seleniumbase_runner import run_selector_extraction


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a supplier catalog extraction.")
    parser.add_argument("--config", required=True, help="Path to supplier JSON config.")
    parser.add_argument("--limit", type=int, default=None, help="Optional product limit for smoke runs.")
    parser.add_argument("--headed", action="store_true", help="Show browser window while running.")
    parser.add_argument("--output-root", default=str(ROOT / "outputs"), help="Output root directory.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    config = json.loads(config_path.read_text(encoding="utf-8"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_root) / config["supplier_key"] / run_id

    result = run_selector_extraction(config, limit=args.limit, headed=args.headed)
    result.report["run_id"] = run_id
    result.report["config_path"] = str(config_path)

    paths = write_export(result.rows, output_dir, result.report)
    print(json.dumps({"outputs": paths, "report": result.report}, indent=2))
    return 0 if result.rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
