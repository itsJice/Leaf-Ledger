"""Stock fields on POST /api/products/ornament-match.

The matcher carries ``products.availability`` / ``availability_note`` through
its in-process ball index and exposes ``in_stock`` (integer pieces when
``availability`` is a bare non-negative integer, as the Vickerman scraper
writes it) so the calculator can warn when an order exceeds stock.
"""

import asyncio

import pytest

from app.apis import products


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("120", 120),
        (" 48 \n", 48),
        ("0", 0),
        ("in_stock", None),
        ("available", None),
        ("Out of Stock", None),
        ("-3", None),
        ("12.5", None),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_parse_in_stock(raw, expected):
    assert products._parse_in_stock(raw) == expected


def _row(pid, sku, availability, note, supplier="Vickerman"):
    return {
        "id": pid,
        "supplier": supplier,
        "name": f'4" Red Shiny Ball Ornament {sku}',
        "supplier_sku": sku,
        "color": "Red",
        "finish": "Shiny",
        "current_price": 24.5,
        "diameter_in": 4,
        "width_in": None,
        "height_in": None,
        "image_urls": [f"https://img.example/{sku}.jpg"],
        "case_qty": 6,
        "uom": "BX",
        "product_type": "Ball Ornament",
        "availability": availability,
        "availability_note": note,
        "norm": None,
    }


def test_ornament_match_returns_stock_fields(fake_db, monkeypatch):
    monkeypatch.setattr(products, "_BALL_CACHE", {"ts": 0.0, "rows": None})
    fake_db.on_fetch("FROM products p JOIN suppliers s ON s.id = p.supplier_id", [
        _row(1, "N590602", "120", "In stock: 120; future stock: 2026-11-01 (600)"),
        _row(2, "N590603", "0", "In stock: 0; future stock: none"),
        _row(3, "N590604", "in_stock", None),
        _row(4, "N590605", None, None),
    ])

    body = products.OrnamentMatchRequest(
        lines=[products.OrnamentMatchLine(size=4, quantity=30, color="red")],
        per_line=10,
    )
    out = asyncio.run(products.ornament_match(body))

    sql, _ = fake_db.calls("FROM products p JOIN suppliers s")[0]
    assert "p.availability, p.availability_note" in sql

    matches = {m["sku"]: m for m in out["lines"][0]["matches"]}
    assert set(matches) == {"N590602", "N590603", "N590604", "N590605"}

    assert matches["N590602"]["in_stock"] == 120
    assert matches["N590602"]["availability"] == "120"
    assert matches["N590602"]["availability_note"].startswith("In stock: 120")

    assert matches["N590603"]["in_stock"] == 0
    assert matches["N590603"]["availability"] == "0"

    assert matches["N590604"]["in_stock"] is None
    assert matches["N590604"]["availability"] == "in_stock"
    assert matches["N590604"]["availability_note"] is None

    assert matches["N590605"]["in_stock"] is None
    assert matches["N590605"]["availability"] is None
    assert matches["N590605"]["availability_note"] is None

    # Existing fields are untouched.
    m = matches["N590602"]
    assert m["case_qty"] == 6 and m["packs_needed"] == 5
    assert m["color_match"] is True and m["size_delta"] == 0.0
    assert m["price"] == 24.5 and m["size_in"] == 4.0
