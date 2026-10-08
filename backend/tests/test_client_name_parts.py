"""A client's name as parts (migrations/021): first name, last name, business
name and location, whichever apply. Covers composing the canonical name, the
backfill parser (and that it round-trips), saving by parts through the
rename-everywhere path, the 409 on a duplicate and who may do it."""

import asyncio
import importlib
import re
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
NONE4 = dict.fromkeys(client_names.PART_FIELDS)


def run(coro):
    return asyncio.run(coro)


def row(**values):
    keys = [c.strip() for c in clients.CLIENT_COLUMNS.split(",")]
    out = dict.fromkeys(keys)
    out.update({"former_names": [], "secondary_contacts": [], "created_at": T0, "updated_at": T0})
    out.update(values)
    return out


def P(first=None, last=None, company=None, site=None):
    return {"first_name": first, "last_name": last, "company": company, "site": site}


# ─── compose ────────────────────────────────────────────────────────────────

COMPOSE = [
    (P("Nataliya", "Scheib"), "Scheib, Nataliya"),
    (P("  Nataliya ", " Scheib  "), "Scheib, Nataliya"),
    (P(last="Hellums"), "Hellums"),
    (P("Cher"), "Cher"),
    (P("Kerri", "Byler", site="House"), "Byler, Kerri - House"),
    (P("Kerri", "Byler", site="Store Buck Ferguson"), "Byler, Kerri - Store Buck Ferguson"),
    (P(company="Hilton Garden Inn"), "Hilton Garden Inn"),
    (P(company="The Club at Carlton Woods", site="Nicklaus Clubhouse"),
     "The Club at Carlton Woods | Nicklaus Clubhouse"),
    (P(company="A Hug Away", site="Daycare"), "A Hug Away | Daycare"),
    (P(company="Capital Bank - Baytown"), "Capital Bank - Baytown"),
    (P("Marissa", "Frazier", company="A Hug Away"), "A Hug Away | Frazier, Marissa"),
    (P("Marissa", "Frazier", company="A Hug Away", site="Residence"), "A Hug Away | Frazier, Marissa - Residence"),
    (P(site="Daycare"), ""),  # a location alone isn't a name
]


@pytest.mark.parametrize("parts, expected", COMPOSE)
def test_compose_name(parts, expected):
    assert compose_name(**parts) == expected


@pytest.mark.parametrize("parts, expected", [c for c in COMPOSE if c[1]])
def test_every_composed_name_parses_back_to_its_parts(parts, expected):
    """The parser is the inverse: what the form saves is what a re-derive reads."""
    back, _ = split_name(expected)
    assert compose_name(**back) == expected
    if "," in expected or "|" in expected:
        assert {k: v for k, v in back.items() if v} == {k: v.strip() for k, v in parts.items() if v and v.strip()}
    # A lone word ("Hellums") reads the same as a person or a business; the
    # parser calls it a business and flags it -- saved parts keep the choice.


def test_clean_parts_validates():
    assert clean_parts(" Nataliya ", "Scheib", "", None) == P("Nataliya", "Scheib")
    assert clean_parts(None, None, "A Hug Away", " Daycare ") == P(company="A Hug Away", site="Daycare")
    for bad in [("", " ", None, "Daycare"), ("A, B", "C", None, None),
                (None, None, "A | B", None), ("Kerri", "Byler", None, "x|y")]:
        with pytest.raises(client_names.NamePartsError):
            clean_parts(*bad)


# ─── the parser (backfill + on-the-fly) ─────────────────────────────────────


@pytest.mark.parametrize("name, fields, unsure", [
    ("Scheib, Nataliya", P("Nataliya", "Scheib"), False),
    ("Byler, Kerri - House", P("Kerri", "Byler", site="House"), False),
    ("Byler, Kerri - Office", P("Kerri", "Byler", site="Office"), False),
    ("The Club at Carlton Woods | Nicklaus Clubhouse",
     P(company="The Club at Carlton Woods", site="Nicklaus Clubhouse"), False),
    ("A Hug Away | Daycare", P(company="A Hug Away", site="Daycare"), False),
    ("Hilton Garden Inn", P(company="Hilton Garden Inn"), False),
    # existing styles are never re-punctuated: a business dash stays put
    ("Capital Bank - Baytown", P(company="Capital Bank - Baytown"), True),
    ("Capital Bank-Baytown", P(company="Capital Bank-Baytown"), True),
    ("A Hug Away | Frazier, Marissa Residence",
     P("Marissa Residence", "Frazier", company="A Hug Away"), True),
    ("Bergstrom, Debbie and Steve", P("Debbie and Steve", "Bergstrom"), True),
    ("Mattix, Margaret & Rick", P("Margaret & Rick", "Mattix"), True),
    ("Junious, Carvis Dr.", P("Carvis Dr.", "Junious"), True),
    ("O'Brien, Pamela (Hope)", P("Pamela (Hope)", "O'Brien"), True),
    ("Smith Family", P(company="Smith Family"), True),
    ("Smith, Joe, Jr", P(company="Smith, Joe, Jr"), True),
    ("Serenity Retreat, Tiffany Pardue", P(company="Serenity Retreat, Tiffany Pardue"), True),
    ("REPAIR Ecklund, Michol", P(company="REPAIR Ecklund, Michol"), True),
    ("Amy Allen", P(company="Amy Allen"), True),
    ("Hellums", P(company="Hellums"), True),
    # parts that would re-spell the name are flagged, never silently accepted
    ("Bourgeois , Cheryl", P("Cheryl", "Bourgeois"), True),
    ("Dollens,Peggy", P("Peggy", "Dollens"), True),
    ("", NONE4, True),
])
def test_split_name(name, fields, unsure):
    parts, reasons = split_name(name)
    assert parts == fields
    assert bool(reasons) is unsure, reasons
    if not reasons:
        assert compose_name(**parts) == name  # a sure split reads back exactly


def test_name_parts_prefers_saved_parts_and_derives_otherwise():
    saved = name_parts({"name": "Bourgeois , Cheryl", "first_name": "Cheryl", "last_name": "Bourgeois"})
    assert saved == {**P("Cheryl", "Bourgeois"), "name_parts_saved": True}
    derived = name_parts({"name": "Byler, Kerri - House", **NONE4})
    assert derived == {**P("Kerri", "Byler", site="House"), "name_parts_saved": False}


# ─── the backfill script ────────────────────────────────────────────────────


def test_backfill_report_counts_and_plan():
    live = [
        {"id": 1, "name": "Scheib, Nataliya", **NONE4},
        {"id": 2, "name": "A Hug Away | Daycare", **NONE4},
        {"id": 3, "name": "Bergstrom, Debbie and Steve", **NONE4},
        {"id": 4, "name": "Hilton Garden Inn", **NONE4, "company": "Hilton Garden Inn"},  # saved
        {"id": 5, "name": "Byler, Kerri - House", **NONE4},
    ]
    report = split_script.propose(live)
    c = split_script.counts(report)
    assert (c["clients"], c["person"], c["business"], c["unsure"], c["saved_already"], c["with_location"]) == \
        (5, 3, 2, 1, 1, 2)

    sure = [r for r in report if not r["unsure"]]
    writes, skipped = split_script.plan_writes(live, sure)
    assert writes == [(1, "Nataliya", "Scheib", None, None),
                      (2, None, None, "A Hug Away", "Daycare"),
                      (5, "Kerri", "Byler", None, "House")]
    assert any("already has saved parts" in s for s in skipped)


def test_backfill_from_a_reviewed_csv_never_respells_or_races_a_rename():
    live = [{"id": 3, "name": "Bergstrom, Debbie and Steve", **NONE4},
            {"id": 5, "name": "Bourgeois , Cheryl", **NONE4},
            {"id": 6, "name": "Amy Allen Now", **NONE4}]
    reviewed = [
        # a human decided: first name "Debbie and Steve"
        {"id": "3", "name": "Bergstrom, Debbie and Steve",
         "first_name": "Debbie and Steve", "last_name": "Bergstrom", "company": "", "site": ""},
        # would read "Bourgeois, Cheryl" -- not this script's job to rename
        {"id": "5", "name": "Bourgeois , Cheryl",
         "first_name": "Cheryl", "last_name": "Bourgeois", "company": "", "site": ""},
        # renamed in the app since the report was made
        {"id": "6", "name": "Amy Allen", "company": "Amy Allen"},
    ]
    writes, skipped = split_script.plan_writes(live, reviewed)
    assert writes == [(3, "Debbie and Steve", "Bergstrom", None, None)]
    assert len(skipped) == 2
    assert "rename it in the app" in skipped[0] and "renamed since the report" in skipped[1]


def test_backfill_script_never_updates_the_name():
    src = Path(split_script.__file__).read_text()
    assert not re.search(r"(?<![_a-z])name\s*=", src.split("async def main")[1])
    assert "AND company IS NULL AND site IS NULL" in src


# ─── the API: create / update by parts ──────────────────────────────────────


def test_create_by_parts_composes_the_name_and_saves_the_parts(fake_db, fake_request):
    fake_db.on("INSERT INTO clients", lambda sql, *a: row(
        id=9, name=a[0], first_name=a[11], last_name=a[12], company=a[13], site=a[14]),
        method="fetchrow")
    body = ClientCreate(name="ignored", first_name=" Kerri", last_name="Byler ", site="House")
    out = run(clients.create_client(body, fake_request()))
    (args,) = [a for _, a in fake_db.calls("INSERT INTO clients")]
    assert args[0] == "Byler, Kerri - House"
    assert args[11:] == ("Kerri", "Byler", None, "House")
    assert (out["name"], out["site"], out["name_parts_saved"]) == ("Byler, Kerri - House", "House", True)


def test_create_with_only_a_location_is_a_400(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.create_client(ClientCreate(site="Daycare"), fake_request()))
    assert exc.value.status_code == 400 and "business name" in exc.value.detail
    assert fake_db.executed == []


def _rename_db(fake_db, old_name):
    state = {"name": old_name, "parts": dict(NONE4)}
    fake_db.on("SELECT name FROM clients WHERE id = $1", lambda sql, *a: state["name"], method="fetchval")

    def update(sql, *a):
        mode, values = a[13], a[14:18]
        if a[1]:
            state["name"] = a[1].strip()
        if mode == "set":
            state["parts"] = dict(zip(client_names.PART_FIELDS, values))
        elif mode == "clear":
            state["parts"] = dict(NONE4)
        return row(id=196, name=state["name"], **state["parts"])
    fake_db.on("UPDATE clients SET", update, method="fetchrow")
    for table in ("UPDATE arrangements", "UPDATE ll_app.jobs", "UPDATE ll_app.product_requests",
                  "UPDATE ll_app.shift_notes", "UPDATE ll_app.shift_time_entries"):
        fake_db.on_execute(table, "UPDATE 1")
    return state


def test_update_by_parts_renames_everywhere(fake_db, fake_request):
    _rename_db(fake_db, "Scheib, Nataliya")
    body = ClientUpdate(first_name="Natalia", last_name="Scheib", company="", site="", name="ignored")
    out = run(clients.update_client(196, body, fake_request()))

    assert out["name"] == "Scheib, Natalia"
    assert (out["first_name"], out["last_name"], out["company"]) == ("Natalia", "Scheib", None)
    assert out["renamed"]["from"] == "Scheib, Nataliya" and out["renamed"]["to"] == "Scheib, Natalia"
    (args,) = [a for _, a in fake_db.calls("UPDATE clients SET")]
    assert args[1] == "Scheib, Natalia" and args[11:14] == (True, "Scheib, Nataliya", "set")
    for table in ("UPDATE arrangements", "UPDATE ll_app.jobs", "UPDATE ll_app.product_requests",
                  "UPDATE ll_app.shift_notes", "UPDATE ll_app.shift_time_entries"):
        assert [a for _, a in fake_db.calls(table)] == [("Scheib, Natalia", "Scheib, Nataliya", 196)], table


def test_adding_a_location_to_a_person(fake_db, fake_request):
    _rename_db(fake_db, "Byler, Kerri")
    out = run(clients.update_client(196, ClientUpdate(
        first_name="Kerri", last_name="Byler", company="", site="House"), fake_request()))
    assert out["name"] == "Byler, Kerri - House" and out["site"] == "House"
    assert out["renamed"]["to"] == "Byler, Kerri - House"


def test_business_with_a_location(fake_db, fake_request):
    _rename_db(fake_db, "Club at Carlton Woods Nicklaus")
    out = run(clients.update_client(196, ClientUpdate(
        first_name="", last_name="", company="The Club at Carlton Woods", site="Nicklaus Clubhouse"),
        fake_request()))
    assert out["name"] == "The Club at Carlton Woods | Nicklaus Clubhouse"
    assert (out["company"], out["site"], out["first_name"]) == (
        "The Club at Carlton Woods", "Nicklaus Clubhouse", None)
    assert out["renamed"] is not None


def test_same_parts_same_name_saves_parts_without_a_rename(fake_db, fake_request):
    _rename_db(fake_db, "Scheib, Nataliya")
    out = run(clients.update_client(196, ClientUpdate(first_name="Nataliya", last_name="Scheib"), fake_request()))
    assert out["renamed"] is None and out["name_parts_saved"] is True
    assert not fake_db.seen("UPDATE arrangements")
    (args,) = [a for _, a in fake_db.calls("UPDATE clients SET")]
    assert args[11:14] == (False, "Scheib, Nataliya", "set")


def test_plain_name_rename_clears_saved_parts(fake_db, fake_request):
    """An older caller (or the published schedule page) renames with just
    `name`: the saved parts would be stale, so they're dropped and derived."""
    state = _rename_db(fake_db, "Scheib, Nataliya")
    state["parts"] = P("Nataliya", "Scheib")
    out = run(clients.update_client(196, ClientUpdate(name="Scheib Family"), fake_request()))
    assert out["name"] == "Scheib Family" and out["name_parts_saved"] is False
    assert out["company"] == "Scheib Family" and out["first_name"] is None


def test_contact_only_save_keeps_name_and_parts(fake_db, fake_request):
    _rename_db(fake_db, "Scheib, Nataliya")
    run(clients.update_client(196, ClientUpdate(phone="555"), fake_request()))
    (args,) = [a for _, a in fake_db.calls("UPDATE clients SET")]
    assert args[1] is None and args[11:] == (False, "Scheib, Nataliya", "keep", None, None, None, None)
    assert not fake_db.seen("UPDATE arrangements")


def test_parts_that_collide_with_another_client_are_a_409(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1", "Scheib, Nataliya")

    async def dup(sql, *args):
        raise asyncpg.UniqueViolationError("duplicate key")
    fake_db.on("UPDATE clients SET", dup, method="fetchrow")
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client(196, ClientUpdate(company="Schieb"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (409, "Another client already has that name")
    assert not fake_db.seen("UPDATE arrangements")


def test_bad_parts_on_update_are_a_400_before_any_write(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client(196, ClientUpdate(first_name="", site="House"), fake_request()))
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
