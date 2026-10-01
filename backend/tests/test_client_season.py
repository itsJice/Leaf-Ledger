"""app.libs.client_season -- the per-season field rules every writer shares."""

import pytest

from app.libs import client_season as cs


def test_summarize_lines():
    assert cs.summarize(None) == "No date recorded"
    assert cs.summarize({"install_date": "2026-11-20"}) == "Scheduled 11/20/2026"
    assert cs.summarize({"install_date": "2026-11-20", "total": 1200}) == "Scheduled 11/20/2026 · $1,200"
    # fees summed when there is no total
    assert cs.summarize({"install_fee": 400, "takedown_fee": 200.5, "storage_fee": 0}) == "No date recorded · $600"
    assert cs.summarize({"cancelled": True}) == "Cancelled before install"
    assert cs.summarize({"not_installing": True}) == "Not installing"
    assert cs.summarize({"not_installing": True, "was_scheduled": "2026-11-25"}) == \
        "Not installing — previously scheduled 11/25/2026"
    assert cs.summarize({"not_installing": True, "install_date": "2026-11-25"}) == \
        "Not installing — previously scheduled 11/25/2026"
    assert cs.summarize({"hold": True, "install_date": "2026-11-20", "total": 900}) == \
        "On hold · Scheduled 11/20/2026 · $900"
    # a string total (older rows stored some as text) still formats
    assert cs.summarize({"total": "950.4"}) == "No date recorded · $950"


def test_merge_sheet_detail_keeps_app_edits_and_flags():
    prior = {"storing": True, "boxes": 12, "install_fee": 400, "hold": True,
             "app_edits": {"storing": "t1", "boxes": "t1"}}
    fresh = {"storing": False, "boxes": 4, "install_fee": 450, "crew": "B"}
    assert cs.merge_sheet_detail(prior, fresh) == {
        "storing": True, "boxes": 12,          # app-owned, kept
        "install_fee": 450, "crew": "B",       # sheet's to refresh
        "hold": True,                          # flag carried even unstamped
        "app_edits": {"storing": "t1", "boxes": "t1"},
    }
    assert cs.merge_sheet_detail(None, fresh) == fresh
    assert cs.merge_sheet_detail({"not_installing": True}, fresh) == {**fresh, "not_installing": True}


def test_supplement_detail_adds_without_clobbering():
    prior = {"install_fee": 400, "real_hours": 3.0, "app_edits": {"real_hours": "t"}}
    out = cs.supplement_detail(prior, {"real_hours": 2.5, "crew": "Crew B (6)", "invoice_total": None})
    assert out == {"install_fee": 400, "real_hours": 3.0, "crew": "Crew B (6)", "app_edits": {"real_hours": "t"}}
    assert cs.supplement_detail(None, {"takedown_date": "2026-01-08"}) == {"takedown_date": "2026-01-08"}


def test_apply_edits_coerces_stamps_and_clears(monkeypatch):
    monkeypatch.setattr(cs, "now_iso", lambda: "T")
    d = cs.apply_edits({"install_date": "2026-11-20"}, {"storing": "yes", "boxes": "12", "invoice_total": "$1,065.50"})
    assert d == {"install_date": "2026-11-20", "storing": True, "boxes": 12, "invoice_total": 1065.5,
                 "app_edits": {"storing": "T", "boxes": "T", "invoice_total": "T"}}
    # clearing a value drops it and its stamp
    d = cs.apply_edits(d, {"boxes": None, "invoice_total": ""})
    assert d == {"install_date": "2026-11-20", "storing": True, "app_edits": {"storing": "T"}}
    # storing=False is a real value, not a clear
    d = cs.apply_edits(d, {"storing": False})
    assert d["storing"] is False and "storing" in d["app_edits"]


def test_apply_edits_hold_and_not_installing_are_exclusive(monkeypatch):
    monkeypatch.setattr(cs, "now_iso", lambda: "T")
    d = cs.apply_edits({"install_date": "2026-11-20"}, {"hold": True})
    assert d == {"install_date": "2026-11-20", "hold": True, "app_edits": {"hold": "T"}}
    d = cs.apply_edits(d, {"not_installing": True})
    assert d == {"install_date": "2026-11-20", "not_installing": True, "was_scheduled": "2026-11-20",
                 "app_edits": {"not_installing": "T"}}
    d = cs.apply_edits(d, {"hold": True})
    assert d == {"install_date": "2026-11-20", "hold": True, "app_edits": {"hold": "T"}}
    d = cs.apply_edits(d, {"hold": False})
    assert d == {"install_date": "2026-11-20"}


@pytest.mark.parametrize("key,value", [
    ("colour", "red"), ("boxes", "lots"), ("boxes", "1.5"), ("storing", "maybe"),
    ("install_date", "Nov 20"), ("install_fee", "four hundred"),
    # the old sheet-fed ideal is no longer an app field
    ("ideal_total", "1500"),
    # inventory: a list of typed lines, nothing else
    ("inventory", "3 trees"), ("inventory", [{"type": "bush", "qty": 1}]),
    ("inventory", [{"type": "tree", "qty": 0}]), ("inventory", [{"type": "tree", "qty": "two"}]),
    ("inventory", ["tree"]),
    # role_need: the four known roles, whole numbers, zero or more
    ("role_need", 3), ("role_need", {"elves": 2}), ("role_need", {"leads": -1}),
    ("role_need", {"general": "4.5"}),
])
def test_coerce_field_rejects(key, value):
    with pytest.raises(cs.FieldError):
        cs.coerce_field(key, value)


def test_coerce_inventory_and_role_need():
    lines = cs.coerce_field("inventory", [
        {"type": "Tree", "size": " 12 ft ", "qty": "2", "note": ""},
        {"type": "wreath", "size": "36in", "qty": 4},
        {"type": "garland"},                      # qty defaults to 1, no size
    ])
    assert lines == [
        {"type": "tree", "qty": 2, "size": "12 ft"},
        {"type": "wreath", "qty": 4, "size": "36in"},
        {"type": "garland", "qty": 1},
    ]
    assert cs.coerce_field("inventory", []) is None          # empty list clears
    assert cs.coerce_field("role_need", {"leads": "1", "general": 4}) == {"leads": 1, "general": 4}
    assert cs.coerce_field("role_need", {"leads": 1, "designer": None}) == {"leads": 1}
    assert cs.coerce_field("role_need", {}) is None
    # and they ride through apply_edits like any other field, stamped
    d = cs.apply_edits({}, {"role_need": {"leads": 1, "general": 4}, "drive_min_out": "25.5"}, when="T")
    assert d == {"role_need": {"leads": 1, "general": 4}, "drive_min_out": 25.5,
                 "app_edits": {"role_need": "T", "drive_min_out": "T"}}
