"""sync_clients.py -- which season each sheet column is filed under.

No database and no workbook: the extraction is fed a synthetic pipeline
cache shaped like prep.py's output (every name invented), and the merge
rules are exercised through the shared app.libs.client_season module.
"""
import json
import os

import pytest

import sync_clients as S


@pytest.mark.parametrize("raw,expected", [
    ("YES", (True, None)),
    ("No", (False, None)),
    ("", (None, None)),
    (None, (None, None)),
    ("Ask", (None, "Ask")),
    ("?", (None, "?")),
    ("NO — client now stores at her own house", (False, "NO — client now stores at her own house")),
    (12, (None, "12")),  # a box count typed into the yes/no column
])
def test_storing_from_sheet(raw, expected):
    assert S.storing_from_sheet(raw) == expected


def _cache(tmp_path, clients, days):
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps({"all_clients": clients, "days": days}))
    return str(path)


def test_extract_current_season_files_prior_columns_on_prior_seasons(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "CACHE", _cache(tmp_path, [
        {
            "row": 2, "name": "Test Client A", "street": "1 Elm", "city": "Testville", "st": "TX",
            "zip": "77001", "phone": "555", "email": "a@x.test",
            "storage": "YES", "box_count": 9, "box_verified": True,
            "est_hours": 2.0, "role_need": {"leads": 1, "specialty": 0, "designer": 0, "general": 3},
            "people_needed": 4, "specialty_needed": "SN", "confirmation_notes": "Confirmed",
            "pickup_delivery_total": None, "ideal_total": 1500,
            "install_fee_2026": 400, "takedown_fee_2026": 150, "storage_fee": 90,
            "install_2026_no_install": False,
            # about LAST season (2025)
            "real_hours": 2.5, "prior_real_start": "09:45", "prior_real_end": "12:15",
            "crew_2025": "Crew B (6)", "crew_size_2025": 6, "invoice_2025_total": 1065,
            "production_notes": "relight garland",
            "prior_takedown_date": "2026-01-08", "prior_takedown_order": 4,
            "prior_takedown_est_hours": 1.25, "prior_takedown_est_note": None,
            "prior_takedown_real_hours": None, "prior_takedown_real_note": "Arrive 2:20 Depart 5:40",
            "prior_takedown_real_start": "14:20", "prior_takedown_real_end": "17:40",
            "prior_takedown_on_calendar": None, "prior_takedown_called": None,
            # about TWO seasons back (2024)
            "date_2024": "2024-12-04", "prior2_takedown_date": "2025-01-10",
        },
        {"row": 3, "name": "Test Client Dropped", "install_2026_no_install": True},
    ], days=[{"date": "2026-11-12", "stops": [{"row": 2}]}]))

    (rec,) = S.extract_current_season("2026")

    assert rec["name"] == "Test Client A"
    # this season's own record
    assert rec["install_date"] == "2026-11-12"
    assert (rec["storing"], rec["storage_note"], rec["boxes"], rec["boxes_verified"]) == (True, None, 9, True)
    assert (rec["install_fee"], rec["takedown_fee"], rec["storage_fee"]) == (400.0, 150.0, 90.0)
    assert rec["total"] is None and rec["ideal_total"] == 1500.0
    assert rec["specialty"] == "SN" and rec["confirmation_notes"] == "Confirmed"
    assert rec["role_need"]["general"] == 3 and rec["people_needed"] == 4
    assert "production_notes" not in rec and "notes" not in rec  # last season's notes are not this season's
    # last season's columns go on last season's row
    assert rec["supplements"]["2025"] == {
        "real_hours": 2.5, "real_start": "09:45", "real_end": "12:15",
        "crew": "Crew B (6)", "crew_size": 6, "invoice_total": 1065.0,
        "production_notes": "relight garland",
        "takedown_date": "2026-01-08", "takedown_order": 4,
        "takedown_est_hours": 1.25, "takedown_est_note": None,
        "takedown_real_hours": None, "takedown_real_note": "Arrive 2:20 Depart 5:40",
        "takedown_real_start": "14:20", "takedown_real_end": "17:40",
        "takedown_on_calendar": None, "takedown_called": None,
    }
    assert rec["supplements"]["2024"] == {"install_date": "2024-12-04", "takedown_date": "2025-01-10"}
    assert S.summarize("2026", rec) == "Scheduled 11/12/2026 · $640"


def test_extract_current_season_labels_prior_seasons_from_the_label(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "CACHE", _cache(tmp_path, [
        {"row": 2, "name": "Test Client A", "install_2027_no_install": False, "crew_2025": "Crew A"},
    ], days=[]))
    (rec,) = S.extract_current_season("2027")
    assert set(rec["supplements"]) == {"2026", "2025"}
    assert rec["supplements"]["2026"]["crew"] == "Crew A"
    assert rec["install_date"] is None
