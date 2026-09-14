"""Characterisation tests for ``app.apis.arrangements``.

These pin TODAY's behaviour (response shapes, the SQL issued and its bound
arguments) so a later refactor of the module can be verified against them.
They are snapshots, not a spec: where current behaviour looks wrong it is pinned
as-is and called out in a comment.

The DB is the shared ``fake_db`` harness from ``conftest.py``. The JSON sidecar
file (``ITEM_META_PATH``) is redirected into ``tmp_path`` for every test so the
real ``container_item_meta.local.json`` next to the module is never touched.
"""

import asyncio
import json
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.apis import arrangements
from app.apis.arrangements import (
    ArrangementCreate,
    ArrangementUpdate,
    ContainerIn,
    ContainerItemIn,
    ContainerUpdate,
    ItemStatusUpdate,
    RoomIn,
    encode_scope_label,
    parse_scope_label,
)

T0 = datetime(2026, 1, 2, 3, 4, 5)
T1 = datetime(2026, 2, 3, 4, 5, 6)

# SELECT * FROM arrangements
ARR_ROW = {
    "id": 9,
    "name": "Smith Lobby",
    "client_name": "Smith",
    "notes": None,
    "created_by": "local-dev-user",
    "created_at": T0,
    "updated_at": T1,
}

FULL_CONTAINER_COLUMNS = [
    "id", "arrangement_id", "container_product_id", "label", "sort_order", "created_at",
    "room_id", "bucket_type", "requested_quantity", "scope_notes",
    "build_type", "status", "hero_image_url",
]
LEGACY_CONTAINER_COLUMNS = ["id", "arrangement_id", "container_product_id", "label", "sort_order", "created_at"]
FULL_ITEM_COLUMNS = ["id", "container_id", "product_id", "quantity", "status", "part_key", "part_label", "part_order"]
LEGACY_ITEM_COLUMNS = ["id", "container_id", "product_id", "quantity"]


@pytest.fixture(autouse=True)
def sidecar_path(tmp_path, monkeypatch):
    path = tmp_path / "container_item_meta.local.json"
    monkeypatch.setattr(arrangements, "ITEM_META_PATH", str(path))
    return path


def run(coro):
    return asyncio.run(coro)


def args_of(fake_db, pattern):
    return [args for _, args in fake_db.calls(pattern)]


def wire(
    fake_db,
    *,
    rooms_table=False,
    status_col=True,
    item_columns=FULL_ITEM_COLUMNS,
    container_columns=FULL_CONTAINER_COLUMNS,
    arr=ARR_ROW,
    markup=None,
    containers=(),
    items=(),
    rooms=(),
    meta_table=True,
):
    """Register the SQL every ``fetch_arrangement_full`` call path needs."""
    fake_db.on_fetchval("SELECT to_regclass('public.project_rooms') IS NOT NULL", rooms_table)
    fake_db.on_fetchval("column_name = 'status'", status_col)
    fake_db.on_fetch("table_name = 'container_items'", [{"column_name": c} for c in item_columns])
    fake_db.on_fetch("table_name = 'arrangement_containers'", [{"column_name": c} for c in container_columns])
    fake_db.on_fetchrow("SELECT * FROM arrangements WHERE id = $1", arr)
    fake_db.on_fetchval("SELECT markup_percentage FROM markup_settings", markup)
    fake_db.on_fetch("FROM arrangement_containers ac LEFT JOIN products p", list(containers))
    fake_db.on_fetch("SELECT * FROM project_rooms WHERE arrangement_id = $1", list(rooms))
    fake_db.on_fetchval("SELECT to_regclass('public.container_item_meta') IS NOT NULL", meta_table)
    fake_db.on_fetchval("SELECT 1 FROM container_item_meta LIMIT 1", 1)
    fake_db.on_fetch("FROM container_items ci", list(items))


def empty_full(arr=ARR_ROW):
    return {**arr, "rooms": [], "containers": [], "total_cost": 0.0, "total_with_markup": 0.0}


# ─── Pure helpers ────────────────────────────────────────────────────────────


def _scope(label="Scope", room_id=None, bucket_type=None, requested_quantity=1, scope_notes=None):
    return {
        "label": label,
        "room_id": room_id,
        "bucket_type": bucket_type,
        "requested_quantity": requested_quantity,
        "scope_notes": scope_notes,
    }


@pytest.mark.parametrize(
    "label, expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("Front urn", None),
        # prefix is case-sensitive and must start at position 0
        ('ll_scope:{"label":"Tree"}', None),
        (' LL_SCOPE:{"label":"Tree"}', None),
        # undecodable JSON -> None
        ("LL_SCOPE:", None),
        ("LL_SCOPE:not json", None),
        # empty object -> fully defaulted
        ("LL_SCOPE:{}", _scope()),
        # label trimmed; blank label falls back to the trimmed bucket_type
        ('LL_SCOPE:{"label":"  ","bucket_type":" Garland "}', _scope(label="Garland", bucket_type="Garland")),
        # mixed case preserved, room_id NOT coerced, numeric-string quantity parsed, notes trimmed
        (
            'LL_SCOPE:{"label":" Mixed Case Tree ","room_id":"7","requested_quantity":"12","scope_notes":" tall "}',
            _scope(label="Mixed Case Tree", room_id="7", requested_quantity=12, scope_notes="tall"),
        ),
        # quantity: junk -> 1, negative -> 1, float truncated
        ('LL_SCOPE:{"requested_quantity":"abc"}', _scope()),
        ('LL_SCOPE:{"requested_quantity":-5}', _scope()),
        ('LL_SCOPE:{"requested_quantity":3.9,"room_id":0}', _scope(requested_quantity=3, room_id=0)),
        # other prefix family is not a scope
        ('LL_ROOM:{"name":"Foyer"}', None),
    ],
)
def test_parse_scope_label_snapshot(label, expected):
    assert parse_scope_label(label) == expected


@pytest.mark.parametrize("label", ["LL_SCOPE:null", "LL_SCOPE:[]", 'LL_SCOPE:{"label":5}'])
def test_parse_scope_label_raises_attribute_error_on_non_dict_or_non_str(label):
    # Suspected bug, pinned: the except tuple (TypeError, ValueError,
    # JSONDecodeError) does not cover AttributeError from ``None.get`` /
    # ``list.get`` / ``int.strip``.
    with pytest.raises(AttributeError):
        parse_scope_label(label)


def test_encode_scope_label_round_trips_through_parse():
    encoded = encode_scope_label(" Mantel ", 30, " garland ", 0, "  ")
    assert encoded == 'LL_SCOPE:{"label":"Mantel","room_id":30,"bucket_type":"garland","requested_quantity":1,"scope_notes":null}'
    assert parse_scope_label(encoded) == _scope(label="Mantel", room_id=30, bucket_type="garland")


@pytest.mark.parametrize("value, expected", [(True, True), (1, True), (False, False), (None, False)])
def test_has_item_status_column(fake_db, value, expected):
    fake_db.on_fetchval("information_schema.columns", value)
    conn = run(arrangements.get_conn())
    assert run(arrangements.has_item_status_column(conn)) is expected
    ((sql, args),) = fake_db.executed
    assert "table_name = 'container_items'" in sql and "column_name = 'status'" in sql
    assert args == ()


def test_load_item_meta_sidecar(sidecar_path):
    assert arrangements.load_item_meta_sidecar() == {}  # missing file
    sidecar_path.write_text('{"101": {"status": "candidate"}}')
    assert arrangements.load_item_meta_sidecar() == {"101": {"status": "candidate"}}
    assert arrangements.get_item_meta_sidecar(101) == {"status": "candidate"}
    assert arrangements.get_item_meta_sidecar(102) == {}
    sidecar_path.write_text("[1, 2]")  # valid JSON, not a dict
    assert arrangements.load_item_meta_sidecar() == {}
    sidecar_path.write_text("{not json")
    assert arrangements.load_item_meta_sidecar() == {}


# ─── ensure_project_schema ───────────────────────────────────────────────────


def test_ensure_project_schema_first_then_second_call(fake_db):
    conn = run(arrangements.get_conn())

    run(arrangements.ensure_project_schema(conn))
    # cold: DO $$ block + CREATE TABLE container_item_meta, no introspection
    assert fake_db.ddl_runs == 2
    assert len(fake_db.executed) == 2
    assert fake_db.executed[0][0].lstrip().startswith("DO $$")
    assert "CREATE TABLE IF NOT EXISTS container_item_meta" in fake_db.executed[1][0]
    assert arrangements._PROJECT_SCHEMA_CHECKED is True

    # warm, project_rooms exists: one to_regclass probe, no DDL
    fake_db.on_fetchval("to_regclass('public.project_rooms')", True)
    run(arrangements.ensure_project_schema(conn))
    assert fake_db.ddl_runs == 2
    assert len(fake_db.executed) == 3
    assert "to_regclass('public.project_rooms')" in fake_db.executed[2][0]

    # warm, but project_rooms missing: probe, then the full DDL again
    fake_db.on_fetchval("to_regclass('public.project_rooms')", False)
    run(arrangements.ensure_project_schema(conn))
    assert fake_db.ddl_runs == 4
    assert len(fake_db.executed) == 6


# ─── list ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status_col, cost_sql",
    [
        (True, "COALESCE(SUM(CASE WHEN ci.status = 'selected' THEN ci.quantity * p.current_price ELSE 0 END), 0) as total_cost"),
        (False, "COALESCE(SUM(ci.quantity * p.current_price), 0) as total_cost"),
    ],
)
def test_list_arrangements(fake_db, fake_request, status_col, cost_sql):
    wire(fake_db, status_col=status_col)
    row = {**ARR_ROW, "container_count": 2, "total_cost": 13.5}
    fake_db.on_fetch("FROM arrangements a LEFT JOIN arrangement_containers ac", [row])

    out = run(arrangements.list_arrangements(fake_request()))

    assert out == [row]
    assert fake_db.ddl_runs == 2
    assert fake_db.seen(cost_sql)
    assert fake_db.seen("ac.label NOT LIKE 'LL_ROOM:%' THEN ac.id END) as container_count")
    assert fake_db.seen("GROUP BY a.id ORDER BY a.updated_at DESC")
    assert not fake_db.seen("created_by =")  # team-owned: no creator filter


# ─── get ─────────────────────────────────────────────────────────────────────


def test_get_arrangement_404(fake_db, fake_request):
    wire(fake_db, arr=None)
    with pytest.raises(HTTPException) as exc:
        run(arrangements.get_arrangement(404, fake_request()))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Arrangement not found"
    assert args_of(fake_db, "SELECT * FROM arrangements WHERE id = $1") == [(404,)]
    assert not fake_db.seen("markup_percentage")


ITEM_KEYS = [
    "id", "container_id", "product_id", "quantity", "status", "part_key", "part_label", "part_order",
    "product_name", "product_category", "unit", "current_price", "supplier_sku", "photo_url", "supplier_name",
]


def item_row(**values):
    row = dict.fromkeys(ITEM_KEYS)
    row.update(values)
    return row


def test_get_arrangement_native_columns(fake_db, fake_request):
    room_placeholder = {
        **dict.fromkeys(FULL_CONTAINER_COLUMNS),
        "id": 30, "arrangement_id": 9, "label": 'LL_ROOM:{"name":"Lobby","notes":null}',
        "sort_order": 0, "container_name": None,
    }
    container = {
        **dict.fromkeys(FULL_CONTAINER_COLUMNS),
        "id": 31, "arrangement_id": 9, "container_product_id": 500, "container_name": "Urn",
        "label": "Front urn", "sort_order": 1, "created_at": T0, "room_id": 4, "bucket_type": "urn",
        "requested_quantity": 2, "scope_notes": "tall",
    }
    items = [
        item_row(id=101, container_id=31, product_id=7, quantity=3, status="selected", part_key="base",
                 part_label="Base", part_order=1, product_name="Moss", product_category="floral",
                 unit="bag", current_price=4.5, supplier_sku="M-1", supplier_name="Acme"),
        item_row(id=102, container_id=31, product_id=8, quantity=2, status="candidate",
                 product_name="Ribbon", product_category="ribbon", unit="roll",
                 photo_url="http://x/r.jpg"),
    ]
    wire(fake_db, markup=25, containers=[room_placeholder, container], items=items)

    out = run(arrangements.get_arrangement(9, fake_request()))

    assert out == {
        **ARR_ROW,
        "rooms": [{
            "id": 30, "arrangement_id": 9, "name": "Lobby", "notes": None, "sort_order": 0,
            "created_at": T0, "updated_at": T0,  # placeholder had no created_at -> arrangement's
        }],
        "containers": [{
            "id": 31, "arrangement_id": 9, "container_product_id": 500, "container_name": "Urn",
            "label": "Front urn", "room_id": 4, "bucket_type": "urn", "build_type": "urn",
            "status": "draft", "hero_image_url": None, "requested_quantity": 2, "scope_notes": "tall",
            "sort_order": 1,
            "items": [
                {"id": 101, "product_id": 7, "product_name": "Moss", "product_category": "floral",
                 "unit": "bag", "current_price": 4.5, "supplier_name": "Acme", "supplier_sku": "M-1",
                 "photo_url": None, "quantity": 3, "line_total": 13.5, "status": "selected",
                 "part_key": "base", "part_label": "Base", "part_order": 1},
                {"id": 102, "product_id": 8, "product_name": "Ribbon", "product_category": "ribbon",
                 "unit": "roll", "current_price": None, "supplier_name": None, "supplier_sku": None,
                 "photo_url": "http://x/r.jpg", "quantity": 2, "line_total": 0.0, "status": "candidate",
                 "part_key": None, "part_label": None, "part_order": 0},
            ],
            "subtotal": 13.5,
        }],
        "total_cost": 13.5,
        "total_with_markup": 16.88,
    }
    # items fetched once (the LL_ROOM placeholder is skipped), with native columns + meta table
    ((items_sql, items_args),) = fake_db.calls("FROM container_items ci")
    assert items_args == (31,)
    assert "COALESCE(cim.status, ci.status, 'selected')::text AS status" in items_sql
    assert "COALESCE(cim.part_order, ci.part_order, 0)::integer AS part_order" in items_sql
    assert "LEFT JOIN container_item_meta cim ON cim.item_id = ci.id" in items_sql
    # project_rooms absent: neither the rooms SELECT nor the migration ran
    assert not fake_db.seen("SELECT * FROM project_rooms")
    assert not fake_db.seen("label LIKE $2")


def test_get_arrangement_legacy_labels_and_sidecar(fake_db, fake_request, sidecar_path):
    sidecar_path.write_text(json.dumps({"201": {"status": "candidate", "part_key": "k", "part_label": "L", "part_order": 2}}))
    container = {
        **dict.fromkeys(LEGACY_CONTAINER_COLUMNS),
        "id": 40, "arrangement_id": 9, "container_name": None, "sort_order": 1,
        "label": 'LL_SCOPE:{"label":" Mantel ","room_id":30,"bucket_type":"garland","requested_quantity":"3","scope_notes":""}',
        # stale native values are ignored because the columns are not reported
        "room_id": 99, "bucket_type": "IGNORED",
    }
    items = [item_row(id=201, container_id=40, product_id=7, quantity=5, status="selected",
                      product_name="Garland", product_category="greenery", unit="ft", current_price=2.0)]
    wire(fake_db, status_col=False, item_columns=LEGACY_ITEM_COLUMNS, container_columns=LEGACY_CONTAINER_COLUMNS,
         containers=[container], items=items, meta_table=False)

    out = run(arrangements.get_arrangement(9, fake_request()))

    assert out == {
        **ARR_ROW,
        "rooms": [],
        "containers": [{
            "id": 40, "arrangement_id": 9, "container_product_id": None, "container_name": None,
            "label": "Mantel", "room_id": 30, "bucket_type": "garland", "build_type": "garland",
            "status": "draft", "hero_image_url": None, "requested_quantity": 3, "scope_notes": None,
            "sort_order": 1,
            "items": [{
                "id": 201, "product_id": 7, "product_name": "Garland", "product_category": "greenery",
                "unit": "ft", "current_price": 2.0, "supplier_name": None, "supplier_sku": None,
                "photo_url": None, "quantity": 5, "line_total": 0.0, "status": "candidate",
                "part_key": "k", "part_label": "L", "part_order": 2,
            }],
            "subtotal": 0.0,
        }],
        "total_cost": 0.0,
        "total_with_markup": 0.0,
    }
    ((items_sql, _),) = fake_db.calls("FROM container_items ci")
    assert "COALESCE(cim.status, NULL::text, 'selected')::text AS status" in items_sql
    assert "NULL::integer AS part_order) cim ON false" in items_sql


# ─── create / update / delete ────────────────────────────────────────────────


def test_create_arrangement(fake_db, fake_request):
    wire(fake_db)
    fake_db.on_fetchrow("INSERT INTO arrangements", {**ARR_ROW, "created_by": "user-7"})
    fake_db.on_fetchrow("INSERT INTO arrangement_containers", {"id": 31})
    fake_db.on_fetchrow("SELECT * FROM arrangements WHERE id = $1", {**ARR_ROW, "created_by": "user-7"})
    body = ArrangementCreate(
        name="Smith Lobby",
        client_name="Smith",
        containers=[ContainerIn(
            label="  Front urn ", room_id=4, bucket_type="urn", requested_quantity=0, scope_notes="  ",
            items=[ContainerItemIn(product_id=7, quantity=3, status=" Candidate ", part_key=" base ", part_label="", part_order=2)],
        )],
    )

    out = run(arrangements.create_arrangement(body, fake_request("user-7")))

    assert out == empty_full({**ARR_ROW, "created_by": "user-7"})
    assert args_of(fake_db, "INSERT INTO arrangements") == [("Smith Lobby", "Smith", None, "user-7")]
    assert args_of(fake_db, "INSERT INTO arrangement_containers") == [(9, None, "Front urn", 4, "urn", 1, None, 0)]
    assert fake_db.seen("(arrangement_id, container_product_id, label, room_id, bucket_type, requested_quantity, scope_notes, sort_order)")
    assert args_of(fake_db, "SET build_type = COALESCE($1, build_type, bucket_type)") == [("urn", 31)]
    assert args_of(fake_db, "INSERT INTO container_items") == [(31, 7, 3, "candidate", "base", None, 2)]
    assert fake_db.seen("INSERT INTO container_items (container_id, product_id, quantity, status, part_key, part_label, part_order)")


def test_create_arrangement_rejects_bad_item_status_after_inserting_arrangement(fake_db, fake_request):
    wire(fake_db)
    fake_db.on_fetchrow("INSERT INTO arrangements", ARR_ROW)
    fake_db.on_fetchrow("INSERT INTO arrangement_containers", {"id": 31})
    body = ArrangementCreate(name="X", containers=[ContainerIn(items=[ContainerItemIn(product_id=7, status="maybe")])])
    with pytest.raises(HTTPException) as exc:
        run(arrangements.create_arrangement(body, fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Item status must be candidate or selected")
    # Pinned: the arrangement + container rows were already written (no real
    # transaction around create), only the item insert is skipped.
    assert fake_db.seen("INSERT INTO arrangements")
    assert fake_db.seen("INSERT INTO arrangement_containers")
    assert not fake_db.seen("INSERT INTO container_items")


def test_update_arrangement(fake_db, fake_request):
    wire(fake_db)
    out = run(arrangements.update_arrangement(9, ArrangementUpdate(name="Renamed", notes="n"), fake_request()))
    assert out == empty_full()
    assert args_of(fake_db, "UPDATE arrangements SET name = COALESCE($1, name)") == [("Renamed", None, "n", 9)]
    assert fake_db.executed[0][0].strip().startswith("UPDATE arrangements SET")  # before any schema check


def test_delete_arrangement(fake_db, fake_request):
    out = run(arrangements.delete_arrangement(9, fake_request()))
    assert out == {"ok": True}
    assert [(sql.strip(), args) for sql, args in fake_db.executed] == [("DELETE FROM arrangements WHERE id = $1", (9,))]
    assert fake_db.ddl_runs == 0


# ─── containers ──────────────────────────────────────────────────────────────


def test_add_container_unknown_room_falls_back_to_scope_label(fake_db, fake_request):
    wire(fake_db, rooms_table=False)
    fake_db.on_fetchval("SELECT COALESCE(MAX(sort_order), -1) FROM arrangement_containers", 2)
    fake_db.on_fetchrow("INSERT INTO arrangement_containers", {"id": 55})
    body = ContainerIn(
        container_product_id=500, label="Porch pots", room_id=30, bucket_type=" pot ",
        requested_quantity=2, scope_notes="notes", build_type="planter",
        items=[ContainerItemIn(product_id=8)],
    )

    out = run(arrangements.add_container(9, body, fake_request()))

    assert out == empty_full()
    label = 'LL_SCOPE:{"label":"Porch pots","room_id":30,"bucket_type":"pot","requested_quantity":2,"scope_notes":"notes"}'
    assert args_of(fake_db, "INSERT INTO arrangement_containers") == [(9, 500, label, None, "pot", 2, "notes", 3)]
    assert args_of(fake_db, "SET build_type = COALESCE") == [("planter", 55)]
    assert args_of(fake_db, "INSERT INTO container_items") == [(55, 8, 1, "selected", None, None, 0)]
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]
    assert not fake_db.seen("SELECT EXISTS(SELECT 1 FROM project_rooms")


def test_update_container_404(fake_db, fake_request):
    wire(fake_db)
    with pytest.raises(HTTPException) as exc:
        run(arrangements.update_container(77, ContainerUpdate(label="x"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "Container not found")
    assert args_of(fake_db, "SELECT arrangement_id, label, room_id FROM arrangement_containers WHERE id = $1") == [(77,)]
    assert not fake_db.seen("UPDATE arrangement_containers")


def test_update_container_reencodes_legacy_scope_label(fake_db, fake_request):
    wire(fake_db)
    fake_db.on_fetchrow("SELECT arrangement_id, label, room_id FROM arrangement_containers", {
        "arrangement_id": 9,
        "label": 'LL_SCOPE:{"label":"Old","room_id":30,"bucket_type":"pot","requested_quantity":2,"scope_notes":"keep"}',
        "room_id": None,
    })

    out = run(arrangements.update_container(44, ContainerUpdate(label="New", requested_quantity=0), fake_request()))

    assert out == empty_full()
    new_label = 'LL_SCOPE:{"label":"New","room_id":30,"bucket_type":"pot","requested_quantity":1,"scope_notes":"keep"}'
    assert args_of(fake_db, "UPDATE arrangement_containers SET label = COALESCE($1, label), bucket_type") == [
        (new_label, None, 1, None, 44)
    ]
    assert args_of(fake_db, "SET build_type = COALESCE") == [(None, 44)]
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]


def test_remove_container(fake_db, fake_request, sidecar_path):
    sidecar_path.write_text(json.dumps({"101": {"status": "candidate"}, "999": {"status": "selected"}}))
    fake_db.on_fetchval("SELECT arrangement_id FROM arrangement_containers WHERE id = $1", 9)
    fake_db.on_fetchval("to_regclass('public.container_item_meta')", True)
    fake_db.on_fetch("SELECT id FROM container_items WHERE container_id = $1", [{"id": 101}])

    out = run(arrangements.remove_container(44, fake_request()))

    assert out == {"ok": True}
    assert args_of(fake_db, "DELETE FROM container_item_meta WHERE item_id IN") == [(44,)]
    assert args_of(fake_db, "DELETE FROM arrangement_containers WHERE id = $1") == [(44,)]
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]
    assert json.loads(sidecar_path.read_text()) == {"999": {"status": "selected"}}
    assert fake_db.ddl_runs == 0  # no ensure_project_schema on this route


# ─── items ───────────────────────────────────────────────────────────────────


def test_add_item_inserts_new_row_and_writes_sidecar(fake_db, fake_request, sidecar_path):
    wire(fake_db, meta_table=False)
    fake_db.on_fetchval("INSERT INTO container_items", 77)
    fake_db.on_fetchval("SELECT arrangement_id FROM arrangement_containers WHERE id = $1", 9)
    body = ContainerItemIn(product_id=7, quantity=4, status="CANDIDATE", part_key=" base ", part_label="Base", part_order=2)

    out = run(arrangements.add_item_to_container(44, body, fake_request()))

    assert out == {"ok": True}
    assert args_of(fake_db, "AND COALESCE(part_key, '') = COALESCE($4, '')") == [(44, 7, "candidate", "base")]
    assert args_of(fake_db, "INSERT INTO container_items") == [(44, 7, 4, "candidate", "base", "Base", 2)]
    assert not fake_db.seen("INSERT INTO container_item_meta")
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]
    sidecar = json.loads(sidecar_path.read_text())
    assert set(sidecar) == {"77"}
    assert {k: v for k, v in sidecar["77"].items() if k != "updated_at"} == {
        "status": "candidate", "part_key": "base", "part_label": "Base", "part_order": 2,
    }


def test_add_item_merges_into_existing_row_via_meta_table(fake_db, fake_request, sidecar_path):
    wire(fake_db, meta_table=True)
    fake_db.on_fetchrow("LEFT JOIN container_item_meta cim ON cim.item_id = ci.id", {"id": 101, "quantity": 3})
    body = ContainerItemIn(product_id=7, quantity=2)

    out = run(arrangements.add_item_to_container(44, body, fake_request()))

    assert out == {"ok": True}
    assert args_of(fake_db, "LEFT JOIN container_item_meta cim ON cim.item_id = ci.id") == [(44, 7, "selected", None)]
    assert args_of(fake_db, "UPDATE container_items SET quantity = quantity + $1 WHERE id = $2") == [(2, 101)]
    assert not fake_db.seen("INSERT INTO container_items")
    assert args_of(fake_db, "INSERT INTO container_item_meta") == [(101, "selected", None, None, 0)]
    # arr_id lookup returned None -> no updated_at bump
    assert not fake_db.seen("UPDATE arrangements")
    assert not sidecar_path.exists()


def test_add_item_bad_status_400(fake_db, fake_request):
    wire(fake_db)
    with pytest.raises(HTTPException) as exc:
        run(arrangements.add_item_to_container(44, ContainerItemIn(product_id=7, status="maybe"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Item status must be candidate or selected")
    assert fake_db.ddl_runs == 2  # schema check ran before validation
    assert not fake_db.seen("container_items WHERE container_id")


def test_update_item_quantity(fake_db, fake_request):
    fake_db.on_fetchrow("SELECT ci.container_id, ac.arrangement_id", {"container_id": 44, "arrangement_id": 9})
    fake_db.on_fetchval("to_regclass('public.container_item_meta')", False)

    assert run(arrangements.update_item_quantity(101, 5, fake_request())) == {"ok": True}
    assert args_of(fake_db, "UPDATE container_items SET quantity = $1 WHERE id = $2") == [(5, 101)]
    assert not fake_db.seen("DELETE FROM container_items")

    fake_db.executed.clear()
    assert run(arrangements.update_item_quantity(101, 0, fake_request())) == {"ok": True}
    assert args_of(fake_db, "DELETE FROM container_items WHERE id = $1") == [(101,)]
    assert not fake_db.seen("DELETE FROM container_item_meta")
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]


def test_update_item_quantity_unknown_item_is_not_404(fake_db, fake_request):
    # Pinned: no existence check -- an unknown id still returns ok.
    assert run(arrangements.update_item_quantity(404, 3, fake_request())) == {"ok": True}
    assert args_of(fake_db, "UPDATE container_items SET quantity = $1") == [(3, 404)]
    assert not fake_db.seen("UPDATE arrangements")


def test_update_item_status_404(fake_db, fake_request):
    wire(fake_db)
    with pytest.raises(HTTPException) as exc:
        run(arrangements.update_item_status(404, ItemStatusUpdate(status="selected"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "Item not found")
    assert not fake_db.seen("UPDATE container_items")


def test_update_item_status_native_and_meta_table(fake_db, fake_request):
    wire(fake_db, status_col=True, meta_table=True)
    fake_db.on_fetchrow("SELECT ci.container_id, ac.arrangement_id", {"container_id": 44, "arrangement_id": 9})

    out = run(arrangements.update_item_status(101, ItemStatusUpdate(status=" Candidate "), fake_request()))

    assert out == {"ok": True, "status_supported": True}
    assert args_of(fake_db, "UPDATE container_items SET status = $1 WHERE id = $2") == [("candidate", 101)]
    assert args_of(fake_db, "INSERT INTO container_item_meta (item_id, status, updated_at)") == [(101, "candidate")]
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]


def test_update_item_status_sidecar_only(fake_db, fake_request, sidecar_path):
    sidecar_path.write_text(json.dumps({"101": {"status": "selected", "part_key": "k", "part_label": "L", "part_order": "3"}}))
    wire(fake_db, status_col=False, meta_table=False)
    fake_db.on_fetchrow("SELECT ci.container_id, ac.arrangement_id", {"container_id": 44, "arrangement_id": 9})

    out = run(arrangements.update_item_status(101, ItemStatusUpdate(status="candidate"), fake_request()))

    # status_supported is True only because the sidecar now has an entry
    assert out == {"ok": True, "status_supported": True}
    assert not fake_db.seen("UPDATE container_items")
    assert not fake_db.seen("INSERT INTO container_item_meta")
    entry = json.loads(sidecar_path.read_text())["101"]
    assert {k: v for k, v in entry.items() if k != "updated_at"} == {
        "status": "candidate", "part_key": "k", "part_label": "L", "part_order": 3,
    }


def test_remove_item(fake_db, fake_request):
    fake_db.on_fetchval("SELECT container_id FROM container_items WHERE id = $1", 44)
    fake_db.on_fetchval("to_regclass('public.container_item_meta')", True)
    fake_db.on_fetchval("SELECT arrangement_id FROM arrangement_containers WHERE id = $1", 9)

    assert run(arrangements.remove_item(101, fake_request())) == {"ok": True}

    assert [(sql.strip(), args) for sql, args in fake_db.executed] == [
        ("SELECT container_id FROM container_items WHERE id = $1", (101,)),
        ("SELECT to_regclass('public.container_item_meta') IS NOT NULL", ()),
        ("SELECT 1 FROM container_item_meta LIMIT 1", ()),
        ("DELETE FROM container_item_meta WHERE item_id = $1", (101,)),
        ("DELETE FROM container_items WHERE id = $1", (101,)),
        ("SELECT arrangement_id FROM arrangement_containers WHERE id = $1", (44,)),
        ("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", (9,)),
    ]


# ─── rooms ───────────────────────────────────────────────────────────────────


def test_add_room_blank_name_400(fake_db, fake_request):
    wire(fake_db)
    with pytest.raises(HTTPException) as exc:
        run(arrangements.add_room(9, RoomIn(name="   "), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Room name is required")
    assert not fake_db.seen("INSERT")


def test_add_room_into_project_rooms(fake_db, fake_request):
    room = {"id": 12, "arrangement_id": 9, "name": "Lobby", "notes": None, "sort_order": 2, "created_at": T0, "updated_at": T0}
    wire(fake_db, rooms_table=True, rooms=[room])
    fake_db.on_fetchval("SELECT COALESCE(MAX(sort_order), -1) FROM project_rooms", 1)

    out = run(arrangements.add_room(9, RoomIn(name=" Lobby ", notes="  "), fake_request()))

    assert out == {**empty_full(), "rooms": [room]}
    assert args_of(fake_db, "INSERT INTO project_rooms (arrangement_id, name, notes, sort_order)") == [(9, "Lobby", None, 2)]
    assert not fake_db.seen("INSERT INTO arrangement_containers")
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]
    # migration probe ran (and found no LL_ROOM rows)
    assert args_of(fake_db, "AND label LIKE $2") == [(9, "LL_ROOM:%")]
    assert fake_db.ddl_runs == 2


def test_add_room_fallback_to_room_label(fake_db, fake_request):
    wire(fake_db, rooms_table=False)
    fake_db.on_fetchval("SELECT COALESCE(MAX(sort_order), -1) FROM arrangement_containers", 0)

    out = run(arrangements.add_room(9, RoomIn(name="Lobby", notes=" by door "), fake_request()))

    assert out == empty_full()
    assert args_of(fake_db, "INSERT INTO arrangement_containers (arrangement_id, label, sort_order)") == [
        (9, 'LL_ROOM:{"name":"Lobby","notes":"by door"}', 1)
    ]


def test_update_room_fallback_label(fake_db, fake_request):
    wire(fake_db, rooms_table=False)
    fake_db.on_fetchrow("SELECT arrangement_id, label FROM arrangement_containers WHERE id = $1",
                        {"arrangement_id": 9, "label": 'LL_ROOM:{"name":"Lobby","notes":null}'})

    out = run(arrangements.update_room(30, RoomIn(name="Great Room"), fake_request()))

    assert out == empty_full()
    assert args_of(fake_db, "UPDATE arrangement_containers SET label = $1 WHERE id = $2") == [
        ('LL_ROOM:{"name":"Great Room","notes":null}', 30)
    ]
    assert not fake_db.seen("UPDATE project_rooms")


def test_update_room_404_when_label_is_not_a_room(fake_db, fake_request):
    wire(fake_db, rooms_table=False)
    fake_db.on_fetchrow("SELECT arrangement_id, label FROM arrangement_containers WHERE id = $1",
                        {"arrangement_id": 9, "label": "Front urn"})
    with pytest.raises(HTTPException) as exc:
        run(arrangements.update_room(31, RoomIn(name="X"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "Room/design package not found")


def test_delete_room(fake_db, fake_request):
    wire(fake_db, rooms_table=True)
    fake_db.on_fetchrow("SELECT arrangement_id FROM project_rooms WHERE id = $1", {"arrangement_id": 9})

    assert run(arrangements.delete_room(12, fake_request())) == {"ok": True}
    assert args_of(fake_db, "DELETE FROM project_rooms WHERE id = $1") == [(12,)]
    assert not fake_db.seen("DELETE FROM arrangement_containers")
    assert args_of(fake_db, "UPDATE arrangements SET updated_at = NOW()") == [(9,)]


def test_delete_room_404(fake_db, fake_request):
    wire(fake_db, rooms_table=True)
    with pytest.raises(HTTPException) as exc:
        run(arrangements.delete_room(12, fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "Room not found")
    assert args_of(fake_db, "SELECT arrangement_id, label FROM arrangement_containers WHERE id = $1") == [(12,)]
    assert not fake_db.seen("DELETE FROM")  # bare "DELETE" would match the DDL's ON DELETE CASCADE
