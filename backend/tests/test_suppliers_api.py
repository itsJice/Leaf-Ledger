"""Characterisation tests for the LIVE supplier routes (`app.apis.suppliers`).

Only list / create / update / delete / credentials are covered; the catalog
import / filter / discover routes are dead (see wt/dead-routes.md).
`db.storage` (the databutton shim) is replaced with an in-memory dict so no
test can touch the filesystem-backed store.
"""

import asyncio
import types
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.apis import suppliers

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


class _MemText:
    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value


@pytest.fixture
def storage(monkeypatch):
    mem = types.SimpleNamespace(text=_MemText(), json=_MemText(), binary=_MemText())
    monkeypatch.setattr(suppliers, "db", types.SimpleNamespace(storage=mem))
    monkeypatch.setattr(suppliers, "_SUPPLIER_COUNT_CACHE", {"ts": 0.0, "counts": None})
    return mem


def run(coro):
    return asyncio.run(coro)


def supplier_row(**over):
    row = {"id": 7, "name": "Vickerman", "scraper_key": "vickerman", "scraper_enabled": True,
           "login_url": "http://v", "login_username": "old", "login_password": "pw",
           "credential_status": "ok", "contact_name": None, "contact_email": None, "contact_phone": None,
           "notes": None, "categories": ["Trees"], "shipping_speed": None, "shipping_notes": None,
           "net_terms": "Net 30", "credit_limit": Decimal("1000"), "payment_process": None,
           "secondary_contacts": '[{"label": "AP", "name": "Jo", "phone": null, "email": null}]',
           "created_at": T0, "updated_at": T0, "last_price_synced_at": None, "last_full_sync_at": None}
    row.update(over)
    return row


def test_list_decodes_contacts_and_caches_counts(fake_db, storage):
    fake_db.on_fetch("FROM suppliers s ORDER BY s.name", [
        {**supplier_row(), "has_credentials": True},
        {**supplier_row(id=8, name="Accent", secondary_contacts=None), "has_credentials": False},
    ])
    fake_db.on_fetch("FROM products WHERE is_active = TRUE GROUP BY supplier_id", [{"supplier_id": 7, "n": 1500}])
    out = run(suppliers.list_suppliers())
    assert [(r["id"], r["product_count"], r["secondary_contacts"]) for r in out] == [
        (7, 1500, [{"label": "AP", "name": "Jo", "phone": None, "email": None}]),
        (8, 0, []),
    ]
    # Second call inside the TTL reuses the module-level cache.
    run(suppliers.list_suppliers())
    assert len(fake_db.calls("GROUP BY supplier_id")) == 1
    assert len(fake_db.calls("FROM suppliers s ORDER BY s.name")) == 2
    assert suppliers._SUPPLIER_COUNT_CACHE["counts"] == {7: 1500}
    assert storage.text.data == {} and storage.binary.data == {}


def test_create_infers_scraper_key_and_serialises_contacts(fake_db, storage):
    fake_db.on_fetchrow("INSERT INTO suppliers", {**supplier_row(), "product_count": 0, "has_credentials": False})
    body = suppliers.SupplierCreate(name="Vickerman Co",
                                    secondary_contacts=[suppliers.SupplierContact(label="AP", name="Jo")])
    out = run(suppliers.create_supplier(body))
    (sql, args), = fake_db.calls("INSERT INTO suppliers")
    assert "RETURNING *, 0 as product_count" in sql
    assert args == ("Vickerman Co", "vickerman", True, None, None, None, None, None, [], None, None, None,
                    None, None, '[{"label": "AP", "name": "Jo", "phone": null, "email": null}]',
                    None, None, "missing")
    assert out["secondary_contacts"] == [{"label": "AP", "name": "Jo", "phone": None, "email": None}]
    assert out["has_credentials"] is False


def test_create_saves_login_typed_into_the_add_form(fake_db, storage):
    # Comment #12: a login entered while adding a supplier was silently dropped.
    fake_db.on_fetchrow("INSERT INTO suppliers", {**supplier_row(login_username="buyer", login_password="zip77",
                                                                 credential_status="untested"), "product_count": 0})
    body = suppliers.SupplierCreate(name="Vickerman Co", login_username="  buyer ", login_password="zip77")
    out = run(suppliers.create_supplier(body))
    (sql, args), = fake_db.calls("INSERT INTO suppliers")
    assert args[-3:] == ("buyer", "zip77", "untested")
    assert out["has_credentials"] is True


def test_update_writes_only_sent_columns(fake_db, storage):
    fake_db.on_fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_row())
    fake_db.on_fetchrow("UPDATE suppliers SET", supplier_row(login_password="new", net_terms=None))
    fake_db.on_fetchval("SELECT COUNT(*) FROM products WHERE supplier_id", 1500)
    body = suppliers.SupplierUpdate(login_password="new", net_terms=None, credit_limit=2500.5)
    out = run(suppliers.update_supplier(7, body))
    (sql, args), = fake_db.calls("UPDATE suppliers SET")
    assert sql == (
        "UPDATE suppliers SET login_password = $1::text, net_terms = $2::text, "
        "credit_limit = $3::numeric, scraper_key = $4::text, "
        "scraper_enabled = CASE WHEN $4::text IS NOT NULL THEN true ELSE scraper_enabled END, "
        "credential_status = $5::text, updated_at = NOW() WHERE id = $6 RETURNING *"
    )
    assert args == ("new", None, Decimal("2500.5"), "vickerman", "untested", 7)
    assert out["product_count"] == 1500
    assert out["has_credentials"] is True


def test_update_404(fake_db, storage):
    with pytest.raises(HTTPException) as exc:
        run(suppliers.update_supplier(7, suppliers.SupplierUpdate(name="x")))
    assert exc.value.status_code == 404


def test_blank_login_boxes_never_erase_saved_credentials(fake_db, storage):
    # Saved vendor logins took the team a long time to gather; an edit saved
    # with the username/password boxes empty must keep them, not wipe them.
    saved = supplier_row()
    assert saved["login_username"] and saved["login_password"]
    fake_db.on_fetchrow("SELECT * FROM suppliers WHERE id = $1", saved)
    fake_db.on_fetchrow("UPDATE suppliers SET", saved)
    fake_db.on_fetchval("SELECT COUNT(*) FROM products WHERE supplier_id", 10)
    out = run(suppliers.update_supplier(7, suppliers.SupplierUpdate(login_username="", login_password="  ", notes="hi")))
    (sql, args), = fake_db.calls("UPDATE suppliers SET")
    assert "login_username" not in sql and "login_password" not in sql
    assert "" not in args and "  " not in args
    assert out["has_credentials"] is True


def test_blank_login_on_a_supplier_without_one_marks_missing(fake_db, storage):
    fake_db.on_fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_row(login_username=None, login_password=None))
    fake_db.on_fetchrow("UPDATE suppliers SET", supplier_row(login_username="", login_password=None))
    run(suppliers.update_supplier(7, suppliers.SupplierUpdate(login_username="")))
    (sql, args), = fake_db.calls("UPDATE suppliers SET")
    assert args[-2:] == ("missing", 7)


def test_update_rejects_blank_name(fake_db, storage):
    fake_db.on_fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_row())
    for blank in ("", "   "):
        with pytest.raises(HTTPException) as exc:
            run(suppliers.update_supplier(7, suppliers.SupplierUpdate(name=blank)))
        assert (exc.value.status_code, exc.value.detail) == (400, "Supplier name cannot be blank")
    assert fake_db.executed == [
        ("SELECT * FROM suppliers WHERE id = $1", (7,)),
        ("SELECT * FROM suppliers WHERE id = $1", (7,)),
    ]


def test_delete_404_when_missing(fake_db, storage):
    with pytest.raises(HTTPException) as exc:
        run(suppliers.delete_supplier(7))
    assert (exc.value.status_code, exc.value.detail) == (404, "Supplier not found")
    assert not fake_db.seen("DELETE FROM suppliers")


def test_delete_supplier_without_products(fake_db, storage):
    fake_db.on_fetchrow("SELECT name FROM suppliers WHERE id = $1", {"name": "Old Vendor"})
    fake_db.on_fetchval("FROM products WHERE supplier_id = $1", 0)
    fake_db.on_execute("DELETE FROM suppliers", "DELETE 1")
    assert run(suppliers.delete_supplier(7)) == {"ok": True, "products_deleted": 0}


def test_delete_supplier_with_products_needs_its_name_typed(fake_db, storage):
    # Deleting a supplier cascades to every product it supplies -- one stray
    # click must not take 22,000 Vickerman products with it.
    fake_db.on_fetchrow("SELECT name FROM suppliers WHERE id = $1", {"name": "Vickerman"})
    fake_db.on_fetchval("FROM products WHERE supplier_id = $1", 22000)
    fake_db.on_execute("DELETE FROM suppliers", "DELETE 1")
    for typed in (None, "", "vickerman ", "Vickermann"):
        with pytest.raises(HTTPException) as exc:
            run(suppliers.delete_supplier(7, confirm_name=typed))
        assert exc.value.status_code == 409
        assert "22,000 products" in exc.value.detail
    assert not fake_db.seen("DELETE FROM suppliers")
    assert run(suppliers.delete_supplier(7, confirm_name=" Vickerman ")) == {"ok": True, "products_deleted": 22000}


def test_credentials(fake_db, storage):
    with pytest.raises(HTTPException) as exc:
        run(suppliers.get_supplier_credentials(7))
    assert exc.value.status_code == 404
    fake_db.on_fetchrow("SELECT login_username, login_password FROM suppliers",
                        {"login_username": "u", "login_password": "p"})
    assert run(suppliers.get_supplier_credentials(7)) == {"login_username": "u", "login_password": "p"}
    assert storage.text.data == {}
