"""A client's name as parts (migrations/021): composing the canonical name,
the backfill parser, saving by parts through the rename-everywhere path,
the 409 on a duplicate and who may do it."""

import asyncio
import importlib
import sys
from datetime import datetime
from pathlib import Path

import asyncpg
import pytest
from fastapi import HTTPException

from app.apis import clients
from app.apis.clients import ClientCreate, ClientUpdate
from app.libs import client_names
from app.libs.client_names import clean_parts, compose_name, name_parts, split_name

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
split_script = importlib.import_module("split_client_names")

T0 = datetime(2026, 10, 8, 12, 0, 0)


def run(coro):
    return asyncio.run(coro)


def row(**values):
    keys = [c.strip() for c in clients.CLIENT_COLUMNS.split(",")]
    out = dict.fromkeys(keys)
    out.update({"former_names": [], "secondary_contacts": [], "created_at": T0, "updated_at": T0})
    out.update(values)
    return out


# ─── compose ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("parts, expected", [
    (("person", "Nataliya", "Scheib", None, None), "Scheib, Nataliya"),
    (("person", "  Nataliya ", " Scheib  ", None, None), "Scheib, Nataliya"),
    (("person", "", "Hellums", None, None), "Hellums"),
    (("person", "Cher", "", None, None), "Cher"),
    (("business", None, None, "The Club at Carlton Woods", "Nicklaus Clubhouse"),
     "The Club at Carlton Woods | Nicklaus Clubhouse"),
    (("business", None, None, "A Hug Away", "Daycare"), "A Hug Away | Daycare"),
    (("business", None, None, "Capital Bank - Baytown", None), "Capital Bank - Baytown"),
    (("business", None, None, "Capital Bank - Baytown", "  "), "Capital Bank - Baytown"),
    ((None, "a", "b", "c", "d"), ""),
])
def test_compose_name(parts, expected):
    assert compose_name(*parts) == expected


def test_clean_parts_keeps_only_the_types_fields_and_validates():
    assert clean_parts("Person", " Nataliya ", "Scheib", "left over", "x") == {
        "client_type": "person", "first_name": "Nataliya", "last_name": "Scheib",
        "company": None, "site": None}
    assert clean_parts("business", "stale", "stale", "A Hug Away", "") == {
        "client_type": "business", "first_name": None, "last_name": None,
        "company": "A Hug Away", "site": None}
    for bad in [("robot", "a", "b", None, None), ("person", "", " ", None, None),
                ("business", None, None, "", "Daycare"), ("person", "A, B", "C", None, None),
                ("business", None, None, "A | B", None)]:
        with pytest.raises(client_names.NamePartsError):
            clean_parts(*bad)


# ─── the parser (backfill + on-the-fly) ─────────────────────────────────────


@pytest.mark.parametrize("name, kind, fields, unsure", [
    ("Scheib, Nataliya", "person", {"last_name": "Scheib", "first_name": "Nataliya"}, False),
    ("The Club at Carlton Woods | Nicklaus Clubhouse", "business",
     {"company": "The Club at Carlton Woods", "site": "Nicklaus Clubhouse"}, False),
    ("A Hug Away | Daycare", "business", {"company": "A Hug Away", "site": "Daycare"}, False),
    ("Hilton Garden Inn", "business", {"company": "Hilton Garden Inn", "site": None}, False),
    # existing styles are never re-punctuated: a dash stays in the company
    ("Capital Bank - Baytown", "business", {"company": "Capital Bank - Baytown", "site": None}, True),
    ("Capital Bank-Baytown", "business", {"company": "Capital Bank-Baytown", "site": None}, True),
    ("Woodlands CC-Legacy", "business", {"company": "Woodlands CC-Legacy"}, True),
    ("Bergstrom, Debbie and Steve", "person", {"last_name": "Bergstrom"}, True),
    ("Mattix, Margaret & Rick", "person", {"first_name": "Margaret & Rick"}, True),
    ("Junious, Carvis Dr.", "person", {"last_name": "Junious"}, True),
    ("O'Brien, Pamela (Hope)", "person", {"last_name": "O'Brien"}, True),
    ("Byler, Kerri - House", "person", {"first_name": "Kerri - House"}, True),
    ("Smith Family", "business", {"company": "Smith Family"}, True),
    ("Smith, Joe, Jr", "business", {"company": "Smith, Joe, Jr"}, True),
    ("Serenity Retreat, Tiffany Pardue", "business", {"company": "Serenity Retreat, Tiffany Pardue"}, True),
    ("REPAIR Ecklund, Michol", "business", {"company": "REPAIR Ecklund, Michol"}, True),
    ("Amy Allen", "business", {"company": "Amy Allen"}, True),
    ("Hellums", "business", {"company": "Hellums"}, True),
    ("A Hug Away | Frazier, Marissa Residence", "business", {"site": "Frazier, Marissa Residence"}, True),
    # parts that would re-spell the name are flagged, never silently accepted
    ("Bourgeois , Cheryl", "person", {"last_name": "Bourgeois", "first_name": "Cheryl"}, True),
    ("Dollens,Peggy", "person", {"last_name": "Dollens"}, True),
    ("", "business", {}, True),
])
def test_split_name(name, kind, fields, unsure):
    parts, reasons = split_name(name)
    assert parts["client_type"] == kind
    for k, v in fields.items():
        assert parts[k] == v, k
    assert bool(reasons) is unsure, reasons
    if not reasons:
        assert compose_name(**parts) == name  # a sure split reads back exactly


def test_name_parts_prefers_saved_parts_and_derives_otherwise():
    saved = name_parts({"name": "Bourgeois , Cheryl", "client_type": "person",
                        "first_name": "Cheryl", "last_name": "Bourgeois"})
    assert saved == {"client_type": "person", "first_name": "Cheryl", "last_name": "Bourgeois",
                     "company": None, "site": None, "name_parts_saved": True}
    derived = name_parts({"name": "Scheib, Nataliya", "client_type": None})
    assert derived["client_type"] == "person" and derived["last_name"] == "Scheib"
    assert derived["name_parts_saved"] is False


# ─── the backfill script ────────────────────────────────────────────────────


def test_backfill_report_counts_and_plan():
    live = [
        {"id": 1, "name": "Scheib, Nataliya", "client_type": None},
        {"id": 2, "name": "A Hug Away | Daycare", "client_type": None},
        {"id": 3, "name": "Bergstrom, Debbie and Steve", "client_type": None},
        {"id": 4, "name": "Hilton Garden Inn", "client_type": "business"},  # already saved
    ]
    report = split_script.propose(live)
    c = split_script.counts(report)
    assert (c["clients"], c["person"], c["business"], c["unsure"], c["saved_already"]) == (4, 2, 2, 1, 1)

    sure = [r for r in report if not r["unsure"]]
    writes, skipped = split_script.plan_writes(live, sure)
    assert writes == [(1, "person", "Nataliya", "Scheib", None, None),
                      (2, "business", None, None, "A Hug Away", "Daycare")]
    assert any("already has saved parts" in s for s in skipped)


def test_backfill_from_a_reviewed_csv_never_respells_or_races_a_rename():
    live = [{"id": 3, "name": "Bergstrom, Debbie and Steve", "client_type": None},
            {"id": 5, "name": "Bourgeois , Cheryl", "client_type": None},
            {"id": 6, "name": "Amy Allen Now", "client_type": None}]
    reviewed = [
        # a human decided: person, first name "Debbie and Steve"
        {"id": "3", "name": "Bergstrom, Debbie and Steve", "client_type": "person",
         "first_name": "Debbie and Steve", "last_name": "Bergstrom", "company": "", "site": ""},
        # would read "Bourgeois, Cheryl" -- not this script's job to rename
        {"id": "5", "name": "Bourgeois , Cheryl", "client_type": "person",
         "first_name": "Cheryl", "last_name": "Bourgeois", "company": "", "site": ""},
        # renamed in the app since the report was made
        {"id": "6", "name": "Amy Allen", "client_type": "business", "company": "Amy Allen"},
    ]
    writes, skipped = split_script.plan_writes(live, reviewed)
    assert writes == [(3, "person", "Debbie and Steve", "Bergstrom", None, None)]
    assert len(skipped) == 2
    assert "rename it in the app" in skipped[0] and "renamed since the report" in skipped[1]


def test_backfill_script_never_updates_the_name():
    src = Path(split_script.__file__).read_text()
    import re
    assert not re.search(r"(?<![_a-z])name\s*=", src.split("async def main")[1])
    assert "WHERE id = $1 AND client_type IS NULL" in src


# ─── the API: create / update by parts ──────────────────────────────────────


def test_create_by_parts_composes_the_name_and_saves_the_parts(fake_db, fake_request):
    fake_db.on("INSERT INTO clients", lambda sql, *a: row(
        id=9, name=a[0], client_type=a[11], first_name=a[12], last_name=a[13], company=a[14], site=a[15]),
        method="fetchrow")
    body = ClientCreate(name="ignored", client_type="person", first_name=" Nataliya", last_name="Scheib ")
    out = run(clients.create_client(body, fake_request()))
    (args,) = [a for _, a in fake_db.calls("INSERT INTO clients")]
    assert args[0] == "Scheib, Nataliya"
    assert args[11:] == ("person", "Nataliya", "Scheib", None, None)
    assert (out["name"], out["client_type"], out["name_parts_saved"]) == ("Scheib, Nataliya", "person", True)


def test_create_business_without_a_company_is_a_400(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.create_client(ClientCreate(client_type="business", site="Daycare"), fake_request()))
    assert exc.value.status_code == 400 and "company" in exc.value.detail
    assert fake_db.executed == []


def _rename_db(fake_db, old_name):
    state = {"name": old_name, "parts": dict.fromkeys(client_names.NAME_PART_COLUMNS)}
    fake_db.on("SELECT name FROM clients WHERE id = $1", lambda sql, *a: state["name"], method="fetchval")

    def update(sql, *a):
        mode, values = a[13], a[14:19]
        if a[1]:
            state["name"] = a[1].strip()
        if mode == "set":
            state["parts"] = dict(zip(client_names.NAME_PART_COLUMNS, values))
        elif mode == "clear":
            state["parts"] = dict.fromkeys(client_names.NAME_PART_COLUMNS)
        return row(id=196, name=state["name"], **state["parts"])
    fake_db.on("UPDATE clients SET", update, method="fetchrow")
    for table in ("UPDATE arrangements", "UPDATE ll_app.jobs", "UPDATE ll_app.product_requests",
                  "UPDATE ll_app.shift_notes", "UPDATE ll_app.shift_time_entries"):
        fake_db.on_execute(table, "UPDATE 1")
    return state


def test_update_by_parts_renames_everywhere(fake_db, fake_request):
    _rename_db(fake_db, "Scheib, Nataliya")
    body = ClientUpdate(client_type="person", first_name="Natalia", last_name="Scheib", name="ignored")
    out = run(clients.update_client(196, body, fake_request()))

    assert out["name"] == "Scheib, Natalia"
    assert (out["client_type"], out["first_name"], out["last_name"]) == ("person", "Natalia", "Scheib")
    assert out["renamed"]["from"] == "Scheib, Nataliya" and out["renamed"]["to"] == "Scheib, Natalia"
    (args,) = [a for _, a in fake_db.calls("UPDATE clients SET")]
    assert args[1] == "Scheib, Natalia" and args[11:14] == (True, "Scheib, Nataliya", "set")
    for table in ("UPDATE arrangements", "UPDATE ll_app.jobs", "UPDATE ll_app.product_requests",
                  "UPDATE ll_app.shift_notes", "UPDATE ll_app.shift_time_entries"):
        assert [a for _, a in fake_db.calls(table)] == [("Scheib, Natalia", "Scheib, Nataliya", 196)], table


def test_switching_to_business_with_a_site(fake_db, fake_request):
    _rename_db(fake_db, "Club at Carlton Woods Nicklaus")
    out = run(clients.update_client(196, ClientUpdate(
        client_type="business", company="The Club at Carlton Woods", site="Nicklaus Clubhouse",
        first_name="stale"), fake_request()))
    assert out["name"] == "The Club at Carlton Woods | Nicklaus Clubhouse"
    assert (out["company"], out["site"], out["first_name"]) == (
        "The Club at Carlton Woods", "Nicklaus Clubhouse", None)
    assert out["renamed"] is not None


def test_same_parts_same_name_saves_parts_without_a_rename(fake_db, fake_request):
    _rename_db(fake_db, "Scheib, Nataliya")
    out = run(clients.update_client(196, ClientUpdate(
        client_type="person", first_name="Nataliya", last_name="Scheib"), fake_request()))
    assert out["renamed"] is None and out["name_parts_saved"] is True
    assert not fake_db.seen("UPDATE arrangements")
    (args,) = [a for _, a in fake_db.calls("UPDATE clients SET")]
    assert args[11:14] == (False, "Scheib, Nataliya", "set")


def test_plain_name_rename_clears_saved_parts(fake_db, fake_request):
    """An older caller (or the published schedule page) renames with just
    `name`: the saved parts would be stale, so they're dropped and derived."""
    state = _rename_db(fake_db, "Scheib, Nataliya")
    state["parts"] = {"client_type": "person", "first_name": "Nataliya", "last_name": "Scheib",
                      "company": None, "site": None}
    out = run(clients.update_client(196, ClientUpdate(name="Scheib Family"), fake_request()))
    assert out["name"] == "Scheib Family" and out["name_parts_saved"] is False
    assert out["client_type"] == "business" and out["company"] == "Scheib Family"


def test_contact_only_save_keeps_name_and_parts(fake_db, fake_request):
    _rename_db(fake_db, "Scheib, Nataliya")
    run(clients.update_client(196, ClientUpdate(phone="555"), fake_request()))
    (args,) = [a for _, a in fake_db.calls("UPDATE clients SET")]
    assert args[1] is None and args[11:] == (False, "Scheib, Nataliya", "keep", None, None, None, None, None)
    assert not fake_db.seen("UPDATE arrangements")


def test_parts_that_collide_with_another_client_are_a_409(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1", "Scheib, Nataliya")

    async def dup(sql, *args):
        raise asyncpg.UniqueViolationError("duplicate key")
    fake_db.on("UPDATE clients SET", dup, method="fetchrow")
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client(196, ClientUpdate(client_type="business", company="Schieb"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (409, "Another client already has that name")
    assert not fake_db.seen("UPDATE arrangements")


def test_bad_parts_on_update_are_a_400_before_any_write(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client(196, ClientUpdate(client_type="person"), fake_request()))
    assert exc.value.status_code == 400
    assert fake_db.executed == []


@pytest.mark.parametrize("role, ok", [
    ("crew", False), ("viewer", False), ("production", False), ("lead", False),
    ("staff", True), ("admin", True), ("super_admin", True),
])
def test_renaming_by_parts_needs_staff(role, ok):
    """Same route, same gate as PR #68: the parts ride on PUT /clients/update."""
    from app.libs import roles

    assert getattr(clients, "MIN_ROLE", "staff") == "staff"
    assert roles.allowed(role, "staff", "PUT", False, "/api/clients/update/{client_id}") is ok
    assert roles.allowed(role, "staff", "POST", False, "/api/clients/create") is ok
