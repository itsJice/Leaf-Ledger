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
    assert "RETURNING *, 0 as product_count, FALSE as has_credentials" in sql
    assert args == ("Vickerman Co", "vickerman", True, None, None, None, None, None, [], None, None, None,
                    None, None, '[{"label": "AP", "name": "Jo", "phone": null, "email": null}]')
    assert out["secondary_contacts"] == [{"label": "AP", "name": "Jo", "phone": None, "email": None}]


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


def test_update_blank_credentials_marks_missing_and_404(fake_db, storage):
    with pytest.raises(HTTPException) as exc:
        run(suppliers.update_supplier(7, suppliers.SupplierUpdate(name="x")))
    assert exc.value.status_code == 404
    fake_db.on_fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_row())
    fake_db.on_fetchrow("UPDATE suppliers SET", supplier_row(login_username=""))
    run(suppliers.update_supplier(7, suppliers.SupplierUpdate(name="", login_username="")))
    (sql, args), = fake_db.calls("UPDATE suppliers SET")
    assert not sql.startswith("UPDATE suppliers SET name")  # empty name is ignored, not written
    assert args == ("", "vickerman", "missing", 7)


def test_delete_404_on_zero_rows(fake_db, storage):
    fake_db.on_execute("DELETE FROM suppliers", "DELETE 0")
    with pytest.raises(HTTPException) as exc:
        run(suppliers.delete_supplier(7))
    assert exc.value.detail == "Supplier not found"
    fake_db.on_execute("DELETE FROM suppliers", "DELETE 1")
    assert run(suppliers.delete_supplier(7)) == {"ok": True}


def test_credentials(fake_db, storage):
    with pytest.raises(HTTPException) as exc:
        run(suppliers.get_supplier_credentials(7))
    assert exc.value.status_code == 404
    fake_db.on_fetchrow("SELECT login_username, login_password FROM suppliers",
                        {"login_username": "u", "login_password": "p"})
    assert run(suppliers.get_supplier_credentials(7)) == {"login_username": "u", "login_password": "p"}
    assert storage.text.data == {}
