"""scripts/migrate_client_notes.py -- the pure parts, and that applying
goes through the same writers as the API. No database."""
import asyncio

import pytest

from scripts import migrate_client_notes as M

SHEET = [
    {"name": "Beaver, Austin", "install_2026_note": "1/3 same day as Hug Away", "production_notes": "relight garland"},
    {"name": "Old Name Co", "install_2026_note": "", "production_notes": ""},
]


def run(coro):
    return asyncio.run(coro)


def test_match_sheet_by_sheet_name_name_or_former_name():
    idx = M.index_sheet(SHEET)
    assert M.match_sheet({"name": "Beaver Austin"}, idx)["name"] == "Beaver, Austin"
    assert M.match_sheet({"name": "New Co", "former_names": ["old name co."]}, idx)["name"] == "Old Name Co"
    assert M.match_sheet({"name": "x", "sheet_name": "BEAVER,  austin"}, idx)["name"] == "Beaver, Austin"
    assert M.match_sheet({"name": "Nobody"}, idx) is None


def test_build_export_and_report():
    clients = [
        {"id": 1, "name": "Beaver Austin", "notes": "Gate code 12. Relight garland", "staff_alert": None},
        {"id": 2, "name": "Quiet Client", "notes": None, "staff_alert": None},
    ]
    seasons = {1: {
        "2025": {"production_notes": "relight garland", "app_edits": {"production_notes": "x"}},
        "2024": {"crew": "A"},  # no notes: left out
    }}
    export = M.build_export(clients, seasons, M.index_sheet(SHEET), "2026")
    beaver = export[0]
    assert beaver == {
        "client_id": 1, "name": "Beaver Austin", "general_notes": "Gate code 12. Relight garland",
        "staff_alert": None,
        "seasons": {"2025": {"notes": None, "production_notes": "relight garland",
                             "app_edited": ["production_notes"]}},
        "sheet": {"name": "Beaver, Austin", "install_note": "1/3 same day as Hug Away",
                  "install_note_season": "2026", "production_notes": "relight garland",
                  "production_notes_season": "2025"},
    }
    flags = M.flags_for(beaver)
    assert "sheet install note not on 2026" in flags
    assert not any("production notes not on" in f for f in flags)
    rows = M.report_rows(export)
    assert [(r["client_id"], r["season"]) for r in rows] == [(1, "2025")]  # client 2 has nothing
    assert set(rows[0]) == set(M.REPORT_COLUMNS)


def test_validate_edits_normalises_and_reports_every_problem():
    ok = M.validate_edits([{"client_id": 1, "general_notes": "  hi ", "staff_alert": "",
                            "seasons": {"2026": {"notes": "after 2pm", "production_notes": None}}}])
    assert ok == [{"client_id": 1, "general_notes": "hi", "staff_alert": None,
                   "seasons": {"2026": {"notes": "after 2pm", "production_notes": None}}}]
    with pytest.raises(M.EditError) as exc:
        M.validate_edits([
            {"client_id": "1"},
            {"client_id": 2, "seasons": {"26": {"notes": "x"}}},
            {"client_id": 3, "seasons": {"2026": {"crew": "A"}}},
            {"client_id": 4, "staff_alert": "x" * 501},
            {"client_id": 5},
            {"client_id": 6, "general_notes": "a", "colour": "red"},
        ])
    msg = str(exc.value)
    for bit in ("edit 1: client_id", "'26' is not a year", "not crew", "over 500", "client 5): nothing",
                "unknown key(s) colour"):
        assert bit in msg
    with pytest.raises(M.EditError):
        M.validate_edits({"client_id": 1})


def test_plan_changes_only_lists_real_changes():
    current = {"general_notes": "same", "staff_alert": None,
               "seasons": {"2026": {"notes": "old", "production_notes": None}}}
    edit = {"client_id": 1, "general_notes": "same", "staff_alert": "Dog",
            "seasons": {"2026": {"notes": "new", "production_notes": None}, "2025": {"notes": "x"}}}
    assert M.plan_changes(edit, current) == [
        ("staff_alert", None, "Dog"), ("2026.notes", "old", "new"), ("2025.notes", None, "x")]


def test_apply_uses_the_api_writers(fake_db):
    from app.apis import clients

    fake_db.on_fetchval("information_schema.columns", 3)
    conn = run(clients.get_conn())
    run(M.apply_edits(conn, [
        {"client_id": 1, "general_notes": "Gate code 12", "staff_alert": "Dog",
         "seasons": {"2026": {"notes": "after 2pm"}}},
        {"client_id": 2, "staff_alert": None},
    ]))
    (notes_args,) = [a for _, a in fake_db.calls("UPDATE clients SET notes")]
    assert notes_args == (1, "Gate code 12")
    ((sql, args),) = fake_db.calls("INSERT INTO client_activity")
    assert args[:3] == (1, "2026", "No date recorded")
    assert '"app_edits": {"notes"' in args[3] and '"notes": "after 2pm"' in args[3]
    alerts = [a for _, a in fake_db.calls("UPDATE clients SET staff_alert")]
    assert alerts == [(1, "Dog", M.ALERT_BY), (2, None, None)]
