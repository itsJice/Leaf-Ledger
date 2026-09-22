"""Characterisation tests for the shared purchase-order API (`app.apis.orders`).

Pins the API's behaviour, including the `_money` / `_esc` helpers that
`jobs/export.py` and `orders/export.py` both import from `app.libs.export_format`.
"""

import asyncio
import io
from datetime import datetime, timezone
from decimal import Decimal

import openpyxl
import pytest
from fastapi import HTTPException

from app.apis import orders
from app.apis.jobs import export as jobs_export
from app.apis.orders import export as orders_export

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def order_row(**over):
    row = {"id": 60, "name": "Fall PO", "notes": None, "status": "draft", "created_by": "ana",
           "created_at": T0, "updated_at": T0}
    row.update(over)
    return row


def item_rows():
    # Keys follow build_order_view's SELECT column list.
    return [
        {"item_id": 1, "product_id": 555, "quantity": 3, "variant_note": "gold",
         "unit_price": Decimal("4.50"), "name": "Cone", "sku": "PC-20", "supplier_id": 7,
         "supplier_name": "Vickerman", "supplier_login_url": "http://v", "image_urls": ["http://img/1"],
         "photo_url": None, "raw_data": '{"normalized": {"size_in": 6}, "detail_url": "http://v/p"}',
         "height_in": None, "width_in": None, "diameter_in": None, "length_in": None},
        {"item_id": 2, "product_id": -9, "quantity": 2, "variant_note": None, "unit_price": None,
         "name": "Hand typed", "sku": None, "supplier_id": None, "supplier_name": None,
         "supplier_login_url": None, "image_urls": None, "photo_url": None, "raw_data": None,
         "height_in": 12.0, "width_in": 8.5, "diameter_in": None, "length_in": None},
    ]


def test_ensure_schema_runs_once(fake_db):
    run(orders.list_orders())
    assert fake_db.ddl_runs == 1
    run(orders.list_orders())
    assert fake_db.ddl_runs == 1


def test_list_without_jobs_tables_uses_null_columns(fake_db):
    fake_db.on_fetch("FROM ll_app.orders o", [{**order_row(), "supplier_name": None, "job_names": None,
                                              "item_count": 0, "total_qty": 0, "vendor_count": 0,
                                              "total_cost": None}])
    out = run(orders.list_orders())
    (sql, _), = fake_db.calls("FROM ll_app.orders o")
    assert "NULL::text AS supplier_name, NULL::text AS job_names," in sql
    assert "LEFT JOIN suppliers s" not in sql
    assert "GROUP BY o.id\n" in sql
    assert out[0]["name"] == "Fall PO"


def test_list_with_jobs_tables_joins_supplier(fake_db):
    fake_db.on_fetchval("information_schema.tables", 1)
    run(orders.list_orders())
    (sql, _), = fake_db.calls("FROM ll_app.orders o")
    assert "string_agg(DISTINCT j.name, ', ')" in sql
    assert "LEFT JOIN suppliers s ON s.id = o.supplier_id" in sql
    assert "GROUP BY o.id, s.name" in sql


def test_create_defaults_name_and_zero_counts(fake_db):
    fake_db.on_fetchrow("INSERT INTO ll_app.orders", order_row(name="Untitled order"))
    out = run(orders.create_order(orders.OrderCreate(name="  ", created_by="ana")))
    assert [a for _, a in fake_db.calls("INSERT INTO ll_app.orders")] == [("Untitled order", None, "ana")]
    assert out == {**order_row(name="Untitled order"), "item_count": 0, "total_qty": 0,
                   "vendor_count": 0, "total_cost": None}


def test_get_groups_items_by_vendor(fake_db):
    fake_db.on_fetchrow("SELECT * FROM ll_app.orders WHERE id = $1", order_row())
    fake_db.on_fetch("FROM ll_app.order_items i LEFT JOIN products p", item_rows())
    view = run(orders.get_order(60))
    assert view == {
        "id": 60, "name": "Fall PO", "notes": None, "status": "draft", "created_by": "ana",
        "created_at": T0, "updated_at": T0,
        "vendors": [
            {"supplier_id": None, "supplier_name": "Unknown supplier", "supplier_login_url": None,
             "items": [{"item_id": 2, "product_id": -9, "name": "Hand typed", "sku": None,
                        "size": '12×8.5"', "quantity": 2, "variant_note": None, "unit_price": None,
                        "line_total": None, "product_url": None, "image_url": None}],
             "subtotal": 0.0, "subtotal_qty": 2},
            {"supplier_id": 7, "supplier_name": "Vickerman", "supplier_login_url": "http://v",
             "items": [{"item_id": 1, "product_id": 555, "name": "Cone", "sku": "PC-20", "size": '6"',
                        "quantity": 3, "variant_note": "gold", "unit_price": 4.5, "line_total": 13.5,
                        "product_url": "http://v/p", "image_url": "http://img/1"}],
             "subtotal": 13.5, "subtotal_qty": 3},
        ],
        "total_cost": 13.5, "total_qty": 5, "item_count": 2, "vendor_count": 2,
    }


def test_get_404(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(orders.get_order(1))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found"


def test_export_xlsx_single_vendor(fake_db):
    fake_db.on_fetchrow("SELECT * FROM ll_app.orders WHERE id = $1", order_row())
    rows = item_rows()
    rows[0]["image_urls"] = None  # keep _thumb off the network
    fake_db.on_fetch("FROM ll_app.order_items i LEFT JOIN products p", rows)
    resp = run(orders.export_order(60, format="XLSX", supplier_id=7))
    assert resp.headers["content-disposition"] == 'attachment; filename="Fall_PO_Vickerman.xlsx"'
    wb = openpyxl.load_workbook(io.BytesIO(resp.body))
    assert wb.sheetnames == ["Vickerman"]
    got = list(wb["Vickerman"].iter_rows(values_only=True))
    assert got[0][0] == "Fall PO"
    assert got[1][0] == "Vickerman  ·  Sep 01, 2026"
    assert got[3] == ("Image", "Product", "SKU", "Size", "Qty", "Unit", "Line Total", "Link")
    assert got[4] == (None, "Cone", "PC-20", '6"', 3, 4.5, 13.5, "View on site")


def test_export_rejects_bad_format_before_connecting(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(orders.export_order(60, format="csv"))
    assert exc.value.detail == "format must be pdf, docx or xlsx"
    assert fake_db.executed == []


def test_patch_without_fields_is_a_noop(fake_db):
    assert run(orders.update_order(60, orders.OrderUpdate())) == {"ok": True}
    assert not fake_db.seen("UPDATE")


def test_patch_sets_only_non_null_fields(fake_db):
    run(orders.update_order(60, orders.OrderUpdate(name="Renamed", status="placed")))
    (sql, args), = fake_db.calls("UPDATE ll_app.orders SET")
    assert sql == "UPDATE ll_app.orders SET name = $1, status = $2, updated_at = now() WHERE id = $3"
    assert args == ("Renamed", "placed", 60)


def test_add_item_404s(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(orders.add_item(60, orders.AddItem(product_id=555)))
    assert exc.value.detail == "Order not found"
    fake_db.on_fetchval("SELECT 1 FROM ll_app.orders WHERE id = $1", 1)
    with pytest.raises(HTTPException) as exc:
        run(orders.add_item(60, orders.AddItem(product_id=555)))
    assert exc.value.detail == "Product not found"


def test_add_item_upserts_with_snapshot_and_clamped_qty(fake_db):
    fake_db.on_fetchval("SELECT 1 FROM ll_app.orders WHERE id = $1", 1)
    fake_db.on_fetchrow("FROM products p LEFT JOIN suppliers s", {
        "name": "Cone", "supplier_sku": "PC-20", "current_price": Decimal("4.50"), "supplier_name": "Vickerman"})
    assert run(orders.add_item(60, orders.AddItem(product_id=555, quantity=0, added_by="ana"))) == {"ok": True}
    (sql, args), = fake_db.calls("INSERT INTO ll_app.order_items")
    assert "ON CONFLICT (order_id, product_id) DO UPDATE" in sql
    assert args == (60, 555, 1, None, Decimal("4.50"), "Cone", "PC-20", "Vickerman", "ana")
    assert [a for _, a in fake_db.calls("UPDATE ll_app.orders SET updated_at")] == [(60,)]


def test_update_item_zero_qty_deletes_and_stops(fake_db):
    fake_db.on_fetchrow("SELECT order_id FROM ll_app.order_items WHERE id = $1", {"order_id": 60})
    assert run(orders.update_item(5, orders.UpdateItem(quantity=0, variant_note="x"))) == {"ok": True}
    assert fake_db.executed[1] == ("SELECT order_id FROM ll_app.order_items WHERE id = $1", (5,))
    assert fake_db.executed[2:] == [
        ("DELETE FROM ll_app.order_items WHERE id = $1", (5,)),
        ("UPDATE ll_app.orders SET updated_at = now() WHERE id = $1", (60,)),
    ]
    assert not fake_db.seen("UPDATE ll_app.order_items")


def test_update_item_qty_and_note(fake_db):
    fake_db.on_fetchrow("SELECT order_id FROM ll_app.order_items WHERE id = $1", {"order_id": 60})
    assert run(orders.update_item(5, orders.UpdateItem(quantity=4, variant_note="x"))) == {"ok": True}
    assert fake_db.executed[2:] == [
        ("UPDATE ll_app.order_items SET quantity = $2 WHERE id = $1", (5, 4)),
        ("UPDATE ll_app.order_items SET variant_note = $2 WHERE id = $1", (5, "x")),
        ("UPDATE ll_app.orders SET updated_at = now() WHERE id = $1", (60,)),
    ]


def test_update_item_404(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(orders.update_item(5, orders.UpdateItem(quantity=2)))
    assert exc.value.detail == "Item not found"


def test_delete_item_404_when_missing(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(orders.delete_item(5))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Item not found"
    assert not fake_db.seen("UPDATE ll_app.orders")


def test_delete_item_touches_order(fake_db):
    fake_db.on_fetchrow("DELETE FROM ll_app.order_items", {"order_id": 60})
    assert run(orders.delete_item(5)) == {"ok": True}
    assert [a for _, a in fake_db.calls("UPDATE ll_app.orders SET updated_at")] == [(60,)]


# ─── export helpers: orders vs jobs ──────────────────────────────────────────

HELPER_INPUTS = [0, 1234.5, 1234.567, None, "abc", -5, '<a href="x">&</a>']


def _outcome(fn, value):
    try:
        return ("ok", fn(value))
    except Exception as exc:  # noqa: BLE001
        return ("raises", type(exc).__name__)


@pytest.mark.parametrize(
    "value,expected",
    [(0, ("ok", "$0.00")), (1234.5, ("ok", "$1,234.50")), (1234.567, ("ok", "$1,234.57")),
     (None, ("ok", "")), ("abc", ("ok", "")), (-5, ("ok", "$-5.00")),
     ('<a href="x">&</a>', ("ok", "")), (Decimal("4.5"), ("ok", "$4.50"))],
)
def test_money(value, expected):
    assert _outcome(orders_export._money, value) == expected


@pytest.mark.parametrize("value", HELPER_INPUTS)
def test_money_matches_jobs_export(value):
    assert _outcome(orders_export._money, value) == _outcome(jobs_export._money, value)


@pytest.mark.parametrize("value", HELPER_INPUTS)
def test_esc_matches_jobs_export(value):
    # Reported to diverge; as of this commit the two implementations agree on every input.
    assert _outcome(orders_export._esc, value) == _outcome(jobs_export._esc, value)


def test_esc_concrete_output():
    assert orders_export._esc('Tom & "Jerry" <b>') == "Tom &amp; &quot;Jerry&quot; &lt;b&gt;"
    assert orders_export._esc(0) == "0"
    assert orders_export._esc(None) == ""
    assert jobs_export._esc('Tom & "Jerry" <b>') == "Tom &amp; &quot;Jerry&quot; &lt;b&gt;"


def test_pdf_link_with_quotes_and_ampersands_renders():
    # A quote in product_url used to close href="..." early; truncating after
    # escaping could also cut an entity in half. Both break reportlab's parser.
    url = 'http://v/p?a=1&b="x"' + "&" * 40
    view = {"name": 'Fall "PO"', "created_at": T0, "total_cost": 0.0, "total_qty": 0,
            "vendors": [{"supplier_name": "V & Co", "subtotal": 0.0, "subtotal_qty": 0, "items": [
                {"name": "Cone", "sku": None, "size": None, "quantity": 0, "unit_price": None,
                 "line_total": None, "product_url": url, "image_url": None}]}]}
    body, media, ext = orders_export.render(view, "pdf")
    assert (media, ext) == ("application/pdf", "pdf") and body.startswith(b"%PDF")
