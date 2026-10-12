"""Clients spreadsheet import (Comment #11): the template, parsing CSV and
.xlsx, Odoo header aliases, per-row validation, duplicates (against saved
clients and within the file), that the dry run writes nothing, that commit
creates only new rows through the New Client INSERT, and who may do it."""

import asyncio
import base64
import io
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.apis import clients
from app.apis.clients import ClientImportIn
from app.libs import client_import as ci
from app.libs import roles

T0 = datetime(2026, 10, 12, 12, 0, 0)


def run(coro):
    return asyncio.run(coro)


def b64(text: str, encoding: str = "utf-8") -> str:
    return base64.b64encode(text.encode(encoding)).decode()


def upload(text: str, filename: str = "clients.csv", encoding: str = "utf-8") -> ClientImportIn:
    return ClientImportIn(filename=filename, content_base64=b64(text, encoding))


def csv_text(*rows) -> str:
    return "\r\n".join(",".join(r) for r in rows) + "\r\n"


HEADER = ",".join(ci.TEMPLATE_HEADERS)


def by_row(result):
    return {r["row"]: r for r in result["rows"]}


# ─── the template ───────────────────────────────────────────────────────────


def test_template_headers_are_the_new_client_form_labels_in_order():
    assert ci.TEMPLATE_HEADERS == (
        "First name", "Last name", "Business name", "Location", "Email", "Phone",
        "Street address", "City", "State", "ZIP", "Install time preference",
        "Additional contact label", "Additional contact phone", "Additional contact email",
        "General notes",
    )


def test_example_csv_round_trips_as_three_new_clients():
    rows = ci.read_rows("example.csv", ci.template_csv(with_examples=True).encode())
    assert rows[0] == list(ci.TEMPLATE_HEADERS)
    result = ci.validate(rows, {})
    assert result["counts"] == {"create": 3, "duplicate": 0, "error": 0, "total": 3}
    assert [r["name"] for r in result["rows"]] == [
        "Rivera, Jamie",                               # a person
        "Pine Hollow Dental",                          # a business (Dana Lee is the contact)
        "Lakeside Country Club | North Clubhouse",     # a business with a location
    ]
    assert result["ignored_columns"] == []


def test_template_csv_is_headers_only():
    assert ci.template_csv() == HEADER + "\r\n"


def test_template_endpoint(fake_db, fake_request):
    out = run(clients.import_template(fake_request()))
    assert out["headers"] == list(ci.TEMPLATE_HEADERS)
    assert len(out["example_rows"]) == 3 and all(len(r) == len(ci.TEMPLATE_HEADERS) for r in out["example_rows"])
    assert ["Street2", "added to Street address"] in out["odoo_aliases"]
    assert fake_db.executed == []


# ─── reading files ──────────────────────────────────────────────────────────


def test_reads_bom_semicolons_tabs_and_windows_encoding():
    assert ci.read_rows("a.csv", ("\ufeff" + HEADER + "\r\nA,B\r\n").encode())[0][0] == "First name"
    assert ci.read_rows("a.csv", b"First name;Last name\r\nAna;Diaz\r\n")[1] == ["Ana", "Diaz"]
    assert ci.read_rows("a.txt", b"First name\tLast name\nAna\tDiaz\n")[1] == ["Ana", "Diaz"]
    assert ci.read_rows("a.csv", "First name\nJosé\n".encode("cp1252"))[1] == ["José"]


def test_reads_quoted_commas_and_newlines():
    rows = ci.read_rows("a.csv", b'First name,General notes\r\nAna,"Gate, side door\nDog"\r\n')
    assert rows[1] == ["Ana", "Gate, side door\nDog"]


def test_reads_xlsx():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Zip", "Phone"])
    ws.append(["Jamie Rivera", 77380, 2815550142])
    buf = io.BytesIO()
    wb.save(buf)
    rows = ci.read_rows("odoo.xlsx", buf.getvalue())
    assert rows == [["Name", "Zip", "Phone"], ["Jamie Rivera", "77380", "2815550142"]]


@pytest.mark.parametrize("filename, data, message", [
    ("a.csv", b"", "empty"),
    ("a.xls", b"\xd0\xcf\x11\xe0junk", "Old .xls"),
    ("a.xlsx", b"PKnot really a zip", "Couldn't open"),
    ("a.csv", b"x" * (ci.MAX_BYTES + 1), "too big"),
])
def test_unreadable_files(filename, data, message):
    with pytest.raises(ci.ImportFileError, match=message):
        ci.read_rows(filename, data)


def test_needs_a_name_column_and_a_header_row():
    with pytest.raises(ci.ImportFileError, match="name column"):
        ci.validate([["Email", "Phone"], ["a@b.co", "2815550100"]], {})
    with pytest.raises(ci.ImportFileError, match="headers"):
        ci.validate([["", ""], ["x", "y"]], {})


def test_row_limit():
    rows = [["First name"]] + [[f"P{i}"] for i in range(ci.MAX_ROWS + 1)]
    with pytest.raises(ci.ImportFileError, match="at most"):
        ci.validate(rows, {})


# ─── headers and Odoo aliases ───────────────────────────────────────────────


def test_headers_match_ignoring_case_spacing_and_punctuation():
    mapping, ignored = ci.map_headers([" first NAME ", "last_name", "E-mail", "ZIP code", "Country", "Tags"])
    assert mapping == {0: "first_name", 1: "last_name", 2: "email", 3: "zip"}
    assert ignored == ["Country", "Tags"]


def test_odoo_company_column_is_not_the_business_name():
    """Odoo's "Company" is the company that owns the record (ours)."""
    mapping, ignored = ci.map_headers(["Name", "Company", "Company Name"])
    assert mapping == {0: "name", 2: "company"}
    assert ignored == ["Company"]


ODOO_HEADER = ["Name", "Is a Company", "Company Name", "Street", "Street2", "City", "State",
               "Zip", "Country", "Email", "Phone", "Mobile", "Internal Notes"]


def odoo(*rows):
    return ci.validate([ODOO_HEADER, *[list(r) for r in rows]], {})


def test_odoo_person_row():
    result = odoo(["Jamie Rivera", "False", "", "123 Maple Ln", "Apt 4", "The Woodlands", "Texas (US)",
                   "77380", "United States", "jamie@example.com", "(281) 555-0142", "281-555-0199",
                   "Dog in yard"])
    r = ci.public_row(result["rows"][0])
    assert r["status"] == "create" and r["name"] == "Rivera, Jamie"
    assert (r["first_name"], r["last_name"], r["company"]) == ("Jamie", "Rivera", None)
    assert r["street"] == "123 Maple Ln, Apt 4"
    assert (r["city"], r["state"], r["zip"]) == ("The Woodlands", "TX", "77380")
    assert r["phone"] == "(281) 555-0142"
    assert r["secondary_contacts"] == [{"label": "Mobile", "phone": "281-555-0199", "email": None}]
    assert r["notes_text"] == "Dog in yard"
    assert r["notes"] == ['Split "Jamie Rivera" into First "Jamie", Last "Rivera"']
    assert result["ignored_columns"] == ["Country"]
    assert result["columns"]["Street2"] == "Street address (line 2)"


def test_odoo_company_rows_and_contacts():
    result = odoo(
        ["Pine Hollow Dental", "True", "", "", "", "", "", "", "", "", "", "", ""],
        ["Pine Hollow Dental, Dana Lee", "False", "Pine Hollow Dental", "", "", "", "", "", "", "", "", "", ""],
        ["Hilton Garden Inn", "", "", "", "", "", "", "", "", "", "", "", ""],
        ["Rivera, Jamie", "", "", "", "", "", "", "", "", "", "", "2815550142", ""],
    )
    rows = by_row(result)
    assert (rows[2]["name"], rows[2]["status"]) == ("Pine Hollow Dental", "create")
    # Odoo's "Business, Person" display name: Dana Lee is the contact person
    assert rows[3]["fields"]["parts"] == {"first_name": "Dana", "last_name": "Lee",
                                          "company": "Pine Hollow Dental", "site": None}
    assert rows[3]["notes"] == ["Dana Lee is saved as the contact person"]
    assert (rows[3]["status"], rows[3]["message"]) == ("duplicate", "Same name as row 2 in this file")
    # a business word, no Is a Company column value: read as a business
    assert rows[4]["fields"]["parts"]["company"] == "Hilton Garden Inn"
    assert 'Read "Hilton Garden Inn" as a business name' in rows[4]["notes"]
    # "Last, First" and Mobile with no Phone
    assert rows[5]["name"] == "Rivera, Jamie" and rows[5]["fields"]["phone"] == "2815550142"
    assert rows[5]["fields"]["secondary_contacts"] == []


def test_split_columns_win_over_name():
    result = ci.validate([["Name", "First name", "Last name"], ["Whatever Co", "Ana", "Diaz"]], {})
    assert result["rows"][0]["name"] == "Diaz, Ana"


def test_lowercase_names_are_capitalized_and_others_left_as_typed():
    result = ci.validate([["First name", "Last name"], ["jamie", "de la rosa"], ["Dr. Ann", "McNeil"]], {})
    rows = by_row(result)
    assert rows[2]["name"] == "De La Rosa, Jamie" and "Capitalized the first/last name" in rows[2]["notes"]
    assert rows[3]["name"] == "McNeil, Dr. Ann" and rows[3]["notes"] == []


@pytest.mark.parametrize("raw, expected", [
    ("Texas (US)", "TX"), ("texas", "TX"), ("tx", "TX"), ("New Mexico", "NM"), ("Ontario (CA)", "Ontario"),
])
def test_state(raw, expected):
    assert ci.clean_state(raw) == expected


@pytest.mark.parametrize("raw, expected", [("77380.0", "77380"), ("7730", "07730"), ("77380-1234", "77380-1234")])
def test_zip(raw, expected):
    assert ci.clean_zip(raw) == expected


# ─── per-row validation ─────────────────────────────────────────────────────


def test_row_errors():
    rows = [list(ci.TEMPLATE_HEADERS),
            ["", "", "", "House", "", "", "", "", "", "", "", "", "", "", ""],           # no name
            ["Ana", "Diaz", "", "", "ana@", "", "", "", "", "", "", "", "", "", ""],      # bad email
            ["Ben", "Ito", "", "", "", "555-12", "", "", "", "", "", "", "", "", ""],    # short phone
            ["Cy", "Oz", "", "", "", "call me", "", "", "", "", "", "", "", "", ""],     # letters
            ["Di", "Ma", "", "", "", "", "", "", "", "", "dawn", "", "", "", ""],        # time pref
            ["Ed", "Ng", "", "", "", "", "", "", "", "", "", "Wife", "12", "x@", ""],   # contact
            ["Fa", "Lu", "A|B", "", "", "", "", "", "", "", "", "", "", "", ""],         # bar
            ["Gi", "Wu", "", "", "", "(281) 555-0100 x12", "", "", "", "", "Early morning", "", "", "", ""],
            ]
    rows = by_row(ci.validate(rows, {}))
    assert rows[2]["message"] == "Enter a first or last name, or a business name"
    assert rows[3]["message"] == 'email "ana@" doesn\'t look like an email address'
    assert rows[4]["message"] == 'phone "555-12" doesn\'t look like a phone number'
    assert rows[5]["status"] == "error"
    assert "Install time preference \"dawn\"" in rows[6]["message"]
    assert rows[7]["message"] == ('additional contact phone "12" doesn\'t look like a phone number; '
                                  'additional contact email "x@" doesn\'t look like an email address')
    assert rows[8]["message"] == "Names can't contain |"
    assert {r["status"] for n, r in rows.items() if n < 9} == {"error"}
    assert rows[9]["status"] == "create" and rows[9]["fields"]["time_preference"] == "morning"


def test_blank_rows_are_skipped_and_rows_numbered_like_the_spreadsheet():
    result = ci.validate([["First name"], ["", ], ["Ana"], [" "], ["Ben"]], {})
    assert [r["row"] for r in result["rows"]] == [3, 5]


# ─── duplicates ─────────────────────────────────────────────────────────────

EXISTING = ci.existing_name_index([
    {"name": "Rivera, Jamie", "former_names": []},
    {"name": "Byler, Kerri", "former_names": ["Byers, Kerri"]},
    {"name": "Pine Hollow Dental", "former_names": None},
])


def test_duplicates_against_saved_clients_and_former_names():
    result = ci.validate([["First name", "Last name", "Business name", "Location"],
                          ["jamie", " RIVERA ", "", ""],
                          ["Kerri", "Byers", "", ""],
                          ["Dana", "Lee", "Pine Hollow Dental", ""],
                          ["", "", "Pine Hollow Dental", "Office"]], EXISTING)
    rows = by_row(result)
    assert (rows[2]["status"], rows[2]["message"]) == ("duplicate", 'Already a client: "Rivera, Jamie"')
    assert rows[3]["message"] == 'Already a client (renamed to "Byler, Kerri")'
    assert rows[4]["message"] == 'Already a client: "Pine Hollow Dental". If this is another site, add a Location.'
    assert "Dana Lee is saved as the contact person" in rows[4]["notes"]
    assert rows[5]["status"] == "create"
    assert result["counts"] == {"create": 1, "duplicate": 3, "error": 0, "total": 4}


def test_duplicates_within_the_file_keep_the_first():
    result = ci.validate([["First name", "Last name"], ["Ana", "Diaz"], ["Ben", "Ito"], ["ana", "diaz"]], {})
    rows = by_row(result)
    assert rows[2]["status"] == rows[3]["status"] == "create"
    assert (rows[4]["status"], rows[4]["message"]) == ("duplicate", "Same name as row 2 in this file")


def test_an_error_row_does_not_claim_a_name():
    result = ci.validate([["First name", "Last name", "Email"], ["Ana", "Diaz", "bad"], ["Ana", "Diaz", ""]], {})
    rows = by_row(result)
    assert rows[2]["status"] == "error" and rows[3]["status"] == "create"


# ─── the API ────────────────────────────────────────────────────────────────

FILE = csv_text(
    ["First name", "Last name", "Business name", "Location", "Email", "Phone", "Install time preference",
     "Additional contact label", "Additional contact phone"],
    ["Ana", "Diaz", "", "", "ana@example.com", "2815550100", "Late", "Wife", "2815550101"],
    ["Jamie", "Rivera", "", "", "", "", "", "", ""],
    ["", "", "Lakeside Country Club", "North Clubhouse", "", "", "", "", ""],
    ["Bad", "Row", "", "", "nope", "", "", "", ""],
    ["Ana", "Diaz", "", "", "", "", "", "", ""],
)


def saved_clients(fake_db):
    fake_db.on_fetch("SELECT name, former_names FROM clients", [
        {"name": "Rivera, Jamie", "former_names": []},
    ])


def inserted_row(sql, *args):
    keys = [c.strip() for c in clients.CLIENT_COLUMNS.split(",")]
    out = dict.fromkeys(keys)
    out.update(id=100 + len(args[0]), name=args[0], email=args[1], phone=args[2], notes=args[3],
               secondary_contacts=args[8], time_preference=args[10],
               first_name=args[11], last_name=args[12], company=args[13], site=args[14],
               former_names=[], created_at=T0, updated_at=T0)
    return out


def test_validate_is_a_dry_run(fake_db, fake_request):
    saved_clients(fake_db)
    out = run(clients.validate_client_import(upload(FILE), fake_request()))
    assert out["dry_run"] is True
    assert out["counts"] == {"create": 2, "duplicate": 2, "error": 1, "total": 5}
    assert [(r["row"], r["status"]) for r in out["rows"]] == [
        (2, "create"), (3, "duplicate"), (4, "create"), (5, "error"), (6, "duplicate")]
    assert out["rows"][2]["name"] == "Lakeside Country Club | North Clubhouse"
    assert "fields" not in out["rows"][0]
    # nothing written: no INSERT/UPDATE/DELETE of any kind
    writes = [sql for sql, _ in fake_db.executed
              if sql.lstrip().split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]
    assert writes == []
    assert not fake_db.seen("INSERT INTO clients")


def test_validate_bad_file_is_a_400(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.validate_client_import(upload("Email\r\nx@y.co\r\n"), fake_request()))
    assert exc.value.status_code == 400 and "name column" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        run(clients.validate_client_import(ClientImportIn(filename="a.csv", content_base64=""), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "That file is empty.")
    assert not fake_db.seen("INSERT")


def test_commit_creates_only_new_valid_rows_through_the_form_insert(fake_db, fake_request):
    saved_clients(fake_db)
    fake_db.on("INSERT INTO clients", inserted_row, method="fetchrow")
    out = run(clients.commit_client_import(upload(FILE), fake_request()))

    inserts = fake_db.calls("INSERT INTO clients")
    assert [sql for sql, _ in inserts] == [clients.INSERT_CLIENT_SQL] * 2
    assert [args for _, args in inserts] == [
        ("Diaz, Ana", "ana@example.com", "2815550100", None, None, None, None, None,
         '[{"label": "Wife", "phone": "2815550101", "email": null}]', None, "late",
         "Ana", "Diaz", None, None),
        ("Lakeside Country Club | North Clubhouse", None, None, None, None, None, None, None,
         "[]", None, None, None, None, "Lakeside Country Club", "North Clubhouse"),
    ]
    assert not fake_db.seen("UPDATE clients")
    assert out["dry_run"] is False
    assert out["counts"] == {"create": 2, "duplicate": 2, "error": 1, "total": 5}
    assert [c["name"] for c in out["created"]] == ["Diaz, Ana", "Lakeside Country Club | North Clubhouse"]
    assert out["created"][0]["secondary_contacts"] == [{"label": "Wife", "phone": "2815550101", "email": None}]
    assert [r["client_id"] for r in out["rows"]] == [109, None, 139, None, None]


def test_commit_skips_a_name_taken_since_the_preview(fake_db, fake_request):
    saved_clients(fake_db)

    def insert(sql, *args):
        return None if args[0] == "Diaz, Ana" else inserted_row(sql, *args)

    fake_db.on("INSERT INTO clients", insert, method="fetchrow")
    out = run(clients.commit_client_import(upload(FILE), fake_request()))
    rows = {r["row"]: r for r in out["rows"]}
    assert (rows[2]["status"], rows[2]["message"]) == ("duplicate", 'Already a client: "Diaz, Ana"')
    assert out["counts"]["create"] == 1 and len(out["created"]) == 1


def test_commit_with_nothing_new_writes_nothing(fake_db, fake_request):
    saved_clients(fake_db)
    out = run(clients.commit_client_import(upload(csv_text(["First name", "Last name"], ["Jamie", "Rivera"])),
                                           fake_request()))
    assert out["created"] == [] and out["counts"]["duplicate"] == 1
    assert not fake_db.seen("INSERT INTO clients")


def test_create_client_still_uses_the_shared_insert(fake_db, fake_request):
    fake_db.on("INSERT INTO clients", inserted_row, method="fetchrow")
    out = run(clients.create_client(clients.ClientCreate(first_name="Ana", last_name="Diaz"), fake_request()))
    assert out["name"] == "Diaz, Ana"
    assert [sql for sql, _ in fake_db.calls("INSERT INTO clients")] == [clients.INSERT_CLIENT_SQL]


# ─── who may import ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("role, ok", [
    ("crew", False), ("viewer", False), ("production", False), ("lead", False),
    ("staff", True), ("admin", True), ("super_admin", True),
])
def test_import_has_the_same_gate_as_new_client(role, ok):
    assert getattr(clients, "MIN_ROLE", "staff") == "staff"
    assert not getattr(clients, "VIEWER_READ", False)
    for path in ("/api/clients/import/validate", "/api/clients/import/commit"):
        assert roles.allowed(role, "staff", "POST", False, path) is ok
        assert roles.allowed(role, "staff", "POST", False, path) is roles.allowed(
            role, "staff", "POST", False, "/api/clients/create")


def test_odoo_contact_that_is_not_a_person_is_left_out_of_the_name():
    result = ci.validate([["Name", "Related Company"], ["Front Desk LLC", "Pine Hollow Dental"]], {})
    r = result["rows"][0]
    assert r["fields"]["parts"] == {"first_name": None, "last_name": None, "company": "Pine Hollow Dental", "site": None}
    assert r["notes"] == ["Left \"Front Desk LLC\" out (not a person's name)"]
