"""Value pins for app.libs.install_estimate (spec: install_estimate.md)."""

import pytest

from app.libs import install_estimate as E

RATES = {"setup": 30, "tree_small": 20, "tree_medium": 40, "tree_large": 60, "tree_xl": 90, "wreath": 10,
         "garland_ft": 1.5, "spray": 8, "swag": 6, "other": 5, "box": 2,
         "factor_night": 1.2, "factor_commercial": 1.1, "factor_first_year": 1.25}


@pytest.mark.parametrize("size,want", [
    ("12 ft", 12), ("7.5'", 7.5), ("9ft", 9), ("12", 12), ("36 in", 3), ("6' 6\"", 6.5), ("", None), ("tall", None),
])
def test_feet(size, want):
    assert E.feet(size) == want


@pytest.mark.parametrize("ft,band", [(7.5, "tree_small"), (8, "tree_medium"), (10, "tree_medium"),
                                     (12, "tree_large"), (14, "tree_large"), (15, "tree_xl")])
def test_tree_bands(ft, band):
    assert E.tree_band(ft) == band


def test_item_minutes():
    inv = [{"type": "tree", "size": "9 ft", "qty": 2}, {"type": "garland", "size": "25 ft", "qty": 2},
           {"type": "wreath", "qty": 3}]
    # 30 setup + 2*40 + 50 ft*1.5 + 3*10 + 10 boxes*2
    assert E.item_minutes(inv, 10, RATES) == (235.0, [])
    assert E.item_minutes([{"type": "tree", "qty": 1}], None, RATES) == (None, ["tree size"])
    assert E.item_minutes(inv, None, {**RATES, "garland_ft": None}) == (None, ["garland_ft"])


def test_last_real_time_wins_and_is_high_confidence_when_inventory_matches():
    inv = [{"type": "tree", "size": "9 ft", "qty": 1}]
    out = E.estimate(inventory=inv, boxes=8, rates={}, history=[
        {"season": "2024", "hours": 4.0, "inventory": inv},
        {"season": "2025", "hours": 2.6, "inventory": inv, "source": "install_times"},
    ])
    assert (out["hours"], out["basis"], out["confidence"]) == (2.5, "last_real", "high")
    assert out["basisText"] == "2025 real 2.6 h"


def test_inventory_change_scales_the_real_time():
    then = [{"type": "tree", "size": "9 ft", "qty": 1}]
    now = [{"type": "tree", "size": "9 ft", "qty": 2}]
    out = E.estimate(inventory=now, boxes=None, rates=RATES,
                     history=[{"season": "2025", "hours": 2.0, "inventory": then}])
    # (30 + 80) / (30 + 40) = 1.571 -> 3.14 h -> 3.25
    assert (out["hours"], out["basis"], out["confidence"]) == (3.25, "last_real_scaled", "medium")
    assert out["detail"]["scale"] == 1.571


def test_inventory_change_without_rates_stays_unscaled_and_says_why():
    out = E.estimate(inventory=[{"type": "wreath", "qty": 2}], boxes=None, rates={},
                     history=[{"season": "2025", "hours": 2.0, "inventory": [{"type": "wreath", "qty": 1}]}])
    assert (out["hours"], out["basis"], out["confidence"]) == (2.0, "last_real", "medium")
    assert "not scaled" in out["basisText"] and out["needsInput"] == ["setup", "wreath"]


def test_no_inventory_on_both_cards_is_medium():
    out = E.estimate(inventory=None, boxes=None, rates={}, history=[{"season": "2025", "hours": 3.1}])
    assert (out["hours"], out["confidence"]) == (3.0, "medium")


def test_per_item_with_factors_for_a_first_year_commercial_night_job():
    inv = [{"type": "tree", "size": "12 ft", "qty": 1}]
    out = E.estimate(inventory=inv, boxes=5, rates=RATES, history=[], night=True, commercial=True)
    # (30 + 60 + 10) * 1.2 * 1.1 * 1.25 = 165 min = 2.75 h
    assert (out["hours"], out["basis"], out["confidence"]) == (2.75, "per_item", "low")


def test_needs_input_never_invents_hours():
    out = E.estimate(inventory=None, boxes=10, rates=RATES, history=[{"season": "2025", "hours": None}])
    assert out["hours"] is None and out["basis"] == "needs_input" and "inventory" in out["needsInput"]
    out = E.estimate(inventory=[{"type": "spray", "qty": 2}], boxes=None, rates={"setup": 30},
                     history=[{"season": "2025", "hours": None}], commercial=True)
    assert out["needsInput"] == ["factor_commercial", "spray"]
    assert out["basisText"].startswith("NEEDS INPUT")


def test_fit_rates_recovers_known_minutes_and_leaves_thin_keys_blank():
    truth = {"setup": 30, "box": 3}
    jobs = [{"boxes": b, "hours": (truth["setup"] + truth["box"] * b) / 60} for b in (5, 10, 15, 20, 30)]
    jobs.append({"inventory": [{"type": "wreath", "qty": 1}], "boxes": 4, "hours": 42 / 60})
    out = E.fit_rates(jobs)
    assert out["jobs"] == 6
    assert abs(out["rates"]["setup"] - 30) < 1 and abs(out["rates"]["box"] - 3) < 0.1
    assert out["rates"]["wreath"] is None  # one job is not enough
    assert out["rates"]["tree_large"] is None


def test_fit_rates_with_no_usable_jobs():
    assert E.fit_rates([{"hours": None}])["rates"]["setup"] is None
