from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from catalog_extraction.schema import EXPORT_COLUMNS, ProductExportRow


def write_export(rows: list[ProductExportRow], output_dir: Path, report: dict) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [row.to_record() for row in rows]
    frame = pd.DataFrame(records, columns=EXPORT_COLUMNS)

    csv_path = output_dir / "products.csv"
    json_path = output_dir / "products.json"
    report_path = output_dir / "run_report.json"

    frame.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "csv": str(csv_path),
        "json": str(json_path),
        "report": str(report_path),
    }
