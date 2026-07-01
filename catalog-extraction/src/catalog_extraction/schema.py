from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProductExportRow:
    supplier_key: str
    supplier_name: str
    season: str
    sku: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    price: str = ""
    uom: str = ""
    moq: str = ""
    box_qty: str = ""
    case_qty: str = ""
    availability: str = ""
    dimensions: str = ""
    image_url: str = ""
    source_url: str = ""
    source_category_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        raw = record.pop("raw", {}) or {}
        record["raw_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        return record


EXPORT_COLUMNS = [
    "supplier_key",
    "supplier_name",
    "season",
    "sku",
    "name",
    "description",
    "category",
    "price",
    "uom",
    "moq",
    "box_qty",
    "case_qty",
    "availability",
    "dimensions",
    "image_url",
    "source_url",
    "source_category_url",
    "raw_json",
]
