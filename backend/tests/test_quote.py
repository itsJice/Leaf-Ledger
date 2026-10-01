"""Quote calculator: per-trip cost, profit levels, the room a price leaves.

Numbers are worked by hand at a simple card: lead $18, general $15, designer
$16.50, van $225 + trailer $125 + ancillary $20 a day, 10 mpg at $4 (40c a
mile), 2 min a box to load, overhead 20%, target profit 16%.
"""

import asyncio

import pytest
from pydantic import ValidationError

from app.apis import install_quote as api
from app.libs import install_costs as ic
from app.libs import quote as q
from app.libs.schedule_board import Board


def card(**over):
    rows = [
        ("pay:lead", 18, "Lead"), ("pay:general", 15, "General Installer"), ("pay:designer", 16.5, "Designer"),
        ("van_day", 225, None), ("trailer_day", 125, None), ("mpg", 10, None), ("gas_per_gallon", 4, None),
        ("ancillary_day", 20, None), ("load_min_per_box", 2, None),
        ("overhead_pct", 20, None), ("target_profit_pct", 16, None),
    ]
    rows = [(k, over.get(k, a), label) for k, a, label in rows]
    rows += [(k, v, None) for k, v in over.items() if k not in {r[0] for r in rows}]
    return ic.resolve_card([{"season": "2026", "key": k, "amount": a, "label": label} for k, a, label in rows], "2026")


# 1 lead + 3 general = $63/h; 4 h on site, 20 boxes, 30 min each way. Lunch
# is left out here so the hand-worked numbers stay simple; it has its own test.
BASE = {"crew": {"lead": 1, "general": 3}, "install_onsite_h": 4, "boxes": 20, "drive_min_each_way": 30,
        "lunch_min": 0}


def level(out, p):
    return next(lv for lv in out["levels"] if lv["profit_pct"] == p)


def test_trips_with_the_default_takedown_factor():
    out = q.quote(card(), BASE)
    assert out["crew_rate"] == 63 and out["crew_size"] == 4
    inst, td = out["trips"]
    # 40 min loading (20 boxes x 2 > 30 min arrival) + 60 min driving + 240 on site = 5 h 40
    assert inst["pretrip_min"] == 40 and inst["paid_h"] == 5.667
    assert inst["crew_pay"] == 357.0                        # 63 x 5.667
    assert (inst["van"], inst["trailer"], inst["ancillary"]) == (127.5, 70.83, 11.33)  # 56.7% of the day
    # miles default from 30 min at 27 mph = 13.5 each way; 27 mi x 40c
    assert out["inputs"]["miles_each_way"] == 13.5 and inst["gas"] == 10.8
    assert inst["total"] == 577.47
    # takedown on site = 4 h x 0.6 = 2.4 h -> paid (40 + 60 + 144) / 60
    assert td["onsite_h"] == 2.4 and td["paid_h"] == 4.067 and td["crew_pay"] == 256.2 and td["total"] == 417.47
    assert out["crew_hours"] == 9.73
    assert out["job_cost"] == 994.93


def test_takedown_can_be_overridden_or_left_out():
    out = q.quote(card(), {**BASE, "takedown_onsite_h": 1})
    assert out["trips"][1]["onsite_h"] == 1 and out["inputs"]["takedown_auto"] is False
    only = q.quote(card(), {**BASE, "include_takedown": False})
    assert [t["trip"] for t in only["trips"]] == ["install"] and only["job_cost"] == 577.47
    # the card's own factor wins over 0.6
    assert q.quote(card(takedown_time_factor=0.5), BASE)["trips"][1]["onsite_h"] == 2


def test_levels_break_even_and_target_price_needed():
    out = q.quote(card(), BASE)
    assert [lv["profit_pct"] for lv in out["levels"]] == [0, 10, 15, 16, 20, 25, 30, 35, 40, 50]
    be, tgt = level(out, 0), level(out, 16)
    assert be["break_even"] and not be["target"] and tgt["target"]
    assert be["price_needed"] == 1243.67                     # 994.93 / 0.80
    assert level(out, 10)["price_needed"] == 1421.33         # / 0.70
    assert tgt["price_needed"] == 1554.58                    # / 0.64
    assert level(out, 50)["price_needed"] == 3316.44         # / 0.30
    assert "max_job_cost" not in be and out["profit_pct"] is None


def test_price_needed_is_none_when_overhead_and_profit_reach_100():
    out = q.quote(card(overhead_pct=60), BASE)
    assert level(out, 40)["price_needed"] is None and level(out, 50)["price_needed"] is None
    assert level(out, 35)["price_needed"] == 19898.67       # 994.93 / 0.05


def test_max_fields_at_a_price():
    out = q.quote(card(), {**BASE, "price": 3000})
    # 3000 - 994.93 - 600 overhead = 1405.07 -> 46.8%
    assert out["overhead"] == 600 and out["profit"] == 1405.07 and out["profit_pct"] == 46.8
    tgt = level(out, 16)
    assert tgt["max_job_cost"] == 1920 and tgt["headroom"] == 925.07
    # (1920 - 381.73 vans/gas/extras) / $63 an hour of this crew
    assert tgt["max_crew_hours"] == 24.42
    assert tgt["max_materials"] == 925.07
    assert tgt["max_designer_hours"] == 56.06               # 925.07 / 16.50
    be = level(out, 0)
    assert be["max_job_cost"] == 2400 and be["headroom"] == 1405.07


def test_designer_and_materials_count_in_the_job_cost():
    out = q.quote(card(), {**BASE, "designer_hours": 2, "materials": 100, "price": 3000})
    assert out["designer"] == {"hours": 2, "rate": 16.5, "cost": 33}
    assert out["job_cost"] == 1127.93
    tgt = level(out, 16)
    # materials may grow by the headroom: 1920 - (1127.93 - 100)
    assert tgt["max_materials"] == 892.07
    # designer hours: (1920 - (1127.93 - 33)) / 16.50
    assert tgt["max_designer_hours"] == 50.0                 # 825.07 / 16.50
    assert tgt["max_crew_hours"] == round((1920 - 381.7333 - 33 - 100) / 63, 2)


def test_a_missing_class_rate_is_named_not_zeroed_silently():
    c = card(**{"pay:trainee": None})
    c["classes"].append({"slug": "trainee", "label": "Trainee", "rate": None})
    out = q.quote(c, {**BASE, "crew": {"lead": 1, "trainee": 2, "ghost": 1}})
    assert out["crew_rate"] == 18 and out["crew_size"] == 4
    assert set(out["missing"]) == {"pay:trainee", "pay:ghost"}


def test_not_stored_with_us_skips_the_loading():
    out = q.quote(card(), {**BASE, "stored_with_us": False})
    assert out["trips"][0]["pretrip_min"] == 30 and out["trips"][0]["paid_h"] == 5.5
    # a few boxes still take the 30-minute arrival
    assert q.quote(card(), {**BASE, "boxes": 5})["trips"][0]["pretrip_min"] == 30


def test_zero_crew_rate_and_zero_price_are_guarded():
    out = q.quote(card(), {"install_onsite_h": 2, "price": 0})
    assert out["crew_rate"] == 0 and out["trips"][0]["crew_pay"] == 0
    assert all(lv["max_crew_hours"] is None for lv in out["levels"])
    assert out["profit_pct"] is None
    # no designer rate on the card: designer hours affordable is None, not a crash
    c = card()
    c["classes"] = [x for x in c["classes"] if x["slug"] != "designer"]
    out = q.quote(c, {**BASE, "price": 3000, "designer_hours": 1})
    assert level(out, 16)["max_designer_hours"] is None and "pay:designer" in out["missing"]


def test_paid_lunch_follows_the_share_of_the_day():
    base = {k: v for k, v in BASE.items() if k != "lunch_min"}
    inst = q.quote(card(), base)["trips"][0]
    # 5 h 40 of work is 56.7% of a 10-hour day -> 56.7% of the 40-minute lunch
    assert inst["paid_h"] == round(340 / 60 + 40 / 60 * (340 / 600), 3)
    assert q.quote(card(), {**base, "install_onsite_h": 12})["trips"][0]["paid_h"] == round((40 + 60 + 720 + 40) / 60, 3)


def test_a_long_job_carries_at_most_one_whole_day():
    out = q.quote(card(), {**BASE, "install_onsite_h": 12})
    assert out["trips"][0]["day_share"] == 1 and out["trips"][0]["van"] == 225


# ---- API ----

def test_router_is_admin_only():
    assert api.MIN_ROLE == "admin"


def test_calc_merges_card_and_quote_missing():
    rows = [{"season": "2026", "key": "pay:lead", "amount": 18, "label": "Lead"},
            {"season": "2026", "key": "mpg", "amount": 10, "label": None}]
    out = api._calc(rows, api.QuoteIn(season="2026", crew={"lead": 1, "general": 2}, install_onsite_h=3, price=2000))
    assert out["season"] == "2026" and out["classes"][0]["slug"] == "lead"
    assert {"van_day", "overhead_pct", "pay:general"} <= set(out["missing"])
    assert len(out["missing"]) == len(set(out["missing"]))


@pytest.mark.parametrize("bad", [
    {"install_onsite_h": -1}, {"boxes": 99999}, {"price": -5}, {"crew": {"Bad Slug": 1}}, {"crew": {"lead": -1}},
])
def test_quote_in_validates(bad):
    with pytest.raises(ValidationError):
        api.QuoteIn(**bad)


def test_post_calc_reads_the_card(fake_db):
    fake_db.on_fetch("FROM ll_app.install_cost_rates", [
        {"season": "2026", "key": "pay:lead", "amount": 18, "label": "Lead"},
        {"season": "2026", "key": "overhead_pct", "amount": 20, "label": None},
    ])
    out = asyncio.run(api.post_calc(api.QuoteIn(season="2026", crew={"lead": 1}, install_onsite_h=1)))
    assert out["overhead_pct"] == 20 and out["crew_rate"] == 18


def test_job_entries():
    board = Board(
        season="2026", version="v",
        clients={
            1: {"name": "Smith, Ann", "h26": 4, "boxes": 30, "size25": 5, "real25": 3.5,
                "roleNeed": {"leads": 1, "general": 9}, "lat": 29.9, "lon": -95.47},
            2: {"name": "Club House", "h26": 2, "boxes": 0, "roleNeed": {"leads": 1, "general": 2},
                "installFee": 900, "takedownFee": 900, "storage": "NO — client stores it"},
            3: {"name": "Not On A Day", "h26": 1, "storage": "YES"},
        },
        days={"d1": {"id": "d1", "date": "2026-11-02", "crew": "Crew 1", "stops": [2, 1]}},
        depot={"lat": 29.8, "lon": -95.47},
    )
    prices = {"smith ann": {"name": "Ann Smith", "install": 1500, "takedown": 1500, "storage": 2250, "total": 5250}}
    jobs = api.job_entries(board, prices)
    assert [j["name"] for j in jobs] == ["Ann Smith", "Club House"]
    ann, club = jobs
    assert ann["price"] == {"total": 5250, "install": 1500, "takedown": 1500, "storage": 2250, "source": "clients"}
    assert ann["crew"] == {"lead": 1, "general": 4} and ann["crew_basis"] == "2025 crew"
    # 0.1 deg of latitude ~ 6.91 mi x 1.35 road factor
    assert ann["miles_each_way"] == 9.3
    assert ann["drive_min_each_way"] == round(6.9093 * 1.35 / 27 * 60)
    assert club["price"]["total"] == 1800 and club["price"]["source"] == "schedule"
    assert club["crew"] == {"lead": 1, "general": 2} and club["crew_basis"] == "role needs"
    assert club["miles_each_way"] is None and club["stored_with_us"] is False
