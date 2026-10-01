"""The Product Purchase Request Form: seed, validation, the Sheet-compatible
CSV export, and the parsing the response import relies on."""
import csv
import datetime as dt
import io

from app.libs import forms as F
from scripts.import_form_responses import parse_rows


def questions():
    out, qid = [], 0
    for sid, sec in enumerate(F.PRODUCT_REQUEST_FORM["sections"], 1):
        for key, label, helper, qtype, required, options, export_pos in sec["questions"]:
            qid += 1
            out.append({"id": qid, "section_id": sid, "key": key, "label": label, "helper_text": helper,
                        "type": qtype, "required": required, "options": options, "export_position": export_pos})
    return out


def good_answers():
    return {
        "requestor": "Reyna", "client_name": "Sims, Darcy", "project_name": "Home Christmas 26",
        "location_item": "Trees", "product_description": "8 Inch Shiny Silver Mercury Glass Finish Onion",
        "most_important_quality": '8" onion, silver shiney', "match_existing": F.MATCH_OPTIONS[2],
        "preferred_vendor": "Vickerman", "style_number_color": None, "catalog_page": None,
        "quantity_needed": "17", "install_date": "2026-09-18", "samples_pictures": [F.SAMPLES_OPTIONS[2]],
    }


# ── the seed is the Google Form ──────────────────────────────────────────────


def test_seed_matches_the_google_form():
    qs = questions()
    assert [q["key"] for q in qs] == [
        "requestor", "client_name", "project_name", "location_item", "product_description",
        "most_important_quality", "match_existing", "preferred_vendor", "style_number_color",
        "catalog_page", "quantity_needed", "install_date", "samples_pictures"]
    assert [q["section_id"] for q in qs] == [1] * 4 + [2] * 9
    optional = {q["key"] for q in qs if not q["required"]}
    assert optional == {"preferred_vendor", "style_number_color", "catalog_page"}
    assert next(q for q in qs if q["key"] == "quantity_needed")["type"] == "short_text"  # "7 rolls (70 yards)"
    assert F.PRODUCT_REQUEST_FORM["description"].startswith("Please fill out one form per item.")


# ── validation ───────────────────────────────────────────────────────────────


def test_valid_submission_has_no_errors():
    assert F.validate(questions(), good_answers()) == {}


def test_required_fields_by_section():
    qs = questions()
    a = good_answers() | {"client_name": "  ", "product_description": None}
    a = {q["key"]: F.clean_value(q, a.get(q["key"])) for q in qs}
    # Next on section 1 checks only section 1
    assert F.validate(qs, a, section_id=1) == {"client_name": F.REQUIRED_MESSAGE}
    assert F.validate(qs, a, section_id=2) == {"product_description": F.REQUIRED_MESSAGE}
    assert set(F.validate(qs, a)) == {"client_name", "product_description"}


def test_optional_fields_may_be_blank_and_choices_must_be_options():
    qs = questions()
    assert F.validate(qs, good_answers() | {"preferred_vendor": None, "catalog_page": None}) == {}
    assert F.validate(qs, good_answers() | {"requestor": "Bob"}) == {"requestor": "Choose one of the options"}
    assert F.validate(qs, good_answers() | {"samples_pictures": ["something else"]}) == {
        "samples_pictures": "Choose from the options"}
    assert F.validate(qs, good_answers() | {"samples_pictures": []}) == {"samples_pictures": F.REQUIRED_MESSAGE}
    assert F.validate(qs, good_answers() | {"install_date": "next week"}) == {"install_date": "Enter a date"}


def test_clean_value_trims_and_dedupes():
    qs = {q["key"]: q for q in questions()}
    assert F.clean_value(qs["client_name"], "  Sims,   Darcy ") == "Sims, Darcy"
    assert F.clean_value(qs["client_name"], "   ") is None
    assert F.clean_value(qs["samples_pictures"], [F.SAMPLES_OPTIONS[0], F.SAMPLES_OPTIONS[0], " "]) == [F.SAMPLES_OPTIONS[0]]


# ── CSV export: the Sheet's exact columns ────────────────────────────────────


def test_export_column_order_and_headers_match_the_sheet():
    headers = F.export_headers(questions())
    assert len(headers) == 14  # A..N
    assert headers[0] == "Timestamp"
    assert headers[1] == "Client Name/Nombre del Cliente (Por ejemplo: Smith, John)"
    assert headers[2] == "Project Name/Título del Proyecto (Por ejemplo: Outdoor)"
    assert headers[3].startswith("Location and Item / Lugar y Artículo (Por ejemplo:")
    assert headers[4].startswith("Product Description / Describa el producto.")
    assert headers[5].startswith("What is the most important quality")
    assert headers[6] == "Does this need to match an existing product?"
    assert headers[7] == "Preferred Vendor / Proveedor Recomendado"
    assert headers[8] == "Style Number and color / Número de modelo y color"
    assert headers[9] == "Catalog Page Number / Página del catálogo"
    assert headers[10].startswith("Quantity Needed:")
    assert headers[11].startswith("Install Date:")
    assert headers[12].startswith("Samples & Pictures:")
    assert headers[13] == "Requestor"  # asked first, but the sheet's last column


def test_export_rows_format_like_the_sheet():
    qs = questions()
    ts = dt.datetime(2026, 9, 15, 0, 4, 29, tzinfo=dt.timezone.utc)  # 19:04:29 Central on 9/14
    later = ts + dt.timedelta(days=1)
    rows = list(csv.reader(io.StringIO(F.export_csv(qs, [
        {"submitted_at": later, "answers": good_answers() | {"client_name": "Second"}},
        {"submitted_at": ts, "answers": good_answers() | {"samples_pictures": F.SAMPLES_OPTIONS[:2],
                                                           "requestor": None}},
    ]))))
    assert rows[1][0] == "9/14/2026 19:04:29"
    assert rows[1][1] == "Sims, Darcy" and rows[2][1] == "Second"  # oldest first
    assert rows[1][11] == "9/18/2026"
    assert rows[1][12] == ", ".join(F.SAMPLES_OPTIONS[:2])
    assert rows[1][13] == "" and rows[2][13] == "Reyna"


# ── import parsing ────────────────────────────────────────────────────────────


def test_checkbox_cells_split_on_known_options_not_commas():
    two = ", ".join([F.SAMPLES_OPTIONS[3], F.SAMPLES_OPTIONS[0]])
    assert F.parse_checkboxes(two, F.SAMPLES_OPTIONS) == [F.SAMPLES_OPTIONS[3], F.SAMPLES_OPTIONS[0]]
    assert F.parse_checkboxes(F.SAMPLES_OPTIONS[2], F.SAMPLES_OPTIONS) == [F.SAMPLES_OPTIONS[2]]
    assert F.parse_checkboxes("", F.SAMPLES_OPTIONS) == []
    # a radio answer is matched even though it contains commas
    assert F.parse_choice(F.MATCH_OPTIONS[1], F.MATCH_OPTIONS) == F.MATCH_OPTIONS[1]


def test_export_then_import_round_trips():
    qs = questions()
    ts = dt.datetime(2026, 9, 28, 21, 20, 25, tzinfo=F.TZ)
    a = good_answers() | {
        "client_name": "The Woodlands", "project_name": "Ballroom Foyer",
        "catalog_page": "https://www.vickerman.com/p/g1255g?opt=9%27%20x%2024%22",
        "quantity_needed": "127 yards of Garland - see measurements", "match_existing": F.MATCH_OPTIONS[0],
        "samples_pictures": [F.SAMPLES_OPTIONS[3], F.SAMPLES_OPTIONS[1]], "requestor": None}
    text = F.export_csv(qs, [{"submitted_at": ts, "answers": a}])
    (row,), unknown = parse_rows(text, qs)
    assert unknown == []
    assert row["submitted_at"] == ts
    got = {k: v for k, v in row["answers"].items()}
    expect = {k: v for k, v in a.items() if v not in (None, "", [])}
    assert got == expect
