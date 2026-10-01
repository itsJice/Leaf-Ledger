"""Net profit per crew-day: revenue split, crew fill-in, paid time, status."""

from app.libs import crew_day_profit as cdp
from app.libs import install_costs as ic
from app.libs.schedule_board import Board


def card(**over):
    rows = [
        ("pay:lead", 18, "Lead"), ("pay:lead_assist", 17, "Lead Assist"), ("pay:general", 15, "General Installer"),
        ("pay:designer", 16.5, "Designer"), ("van_day", 225, None), ("trailer_day", 125, None),
        ("mpg", 10, None), ("gas_per_gallon", 4, None), ("ancillary_day", 20, None),
        ("load_min_per_box", 2, None), ("overhead_pct", 20, None), ("target_profit_pct", 20, None),
    ]
    rows = [(k, over.get(k, a), label) for k, a, label in rows]
    return ic.resolve_card([{"season": "2026", "key": k, "amount": a, "label": label} for k, a, label in rows], "2026")


def board(staffing=None, stops2=None):
    clients = {
        1: {"name": "Smith, Ann", "h26": 4, "boxes": 30, "roleNeed": {"leads": 1, "general": 3}, "lat": 29.8, "lon": -95.5},
        2: {"name": "Club House", "h26": 2, "boxes": 0, "roleNeed": {"leads": 1, "general": 5},
            "installFee": 900, "lat": 29.9, "lon": -95.5},
        3: {"name": "Free Job", "h26": 2, "noCharge": True, "roleNeed": {}, "lat": 29.9, "lon": -95.4},
    }
    days = {"2026-11-02|Crew 1|0": {"id": "2026-11-02|Crew 1|0", "date": "2026-11-02", "crew": "Crew 1", "stops": [1, 2]}}
    if stops2:
        days["2026-11-03|Crew 1|0"] = {"id": "2026-11-03|Crew 1|0", "date": "2026-11-03", "crew": "Crew 1", "stops": stops2}
    return Board(
        season="2026", version="v", clients=clients, days=days,
        roster=[{"id": "p1", "name": "Ana", "title": "Lead"}], staffing=staffing or {},
        depot={"lat": 29.81, "lon": -95.47}, const={"LUNCH": 40},
        # A saved timeline: 8:30 roll-out, 20 min out, 4 h + 15 min + 2 h, 20 min back.
        timeline={"2026-11-02|Crew 1|0": {"start": 510, "stops": [
            {"row": 1, "start": 530, "end": 770}, {"row": 2, "start": 785, "end": 905}], "back": 20}},
    )


PRICES = cdp.price_index([
    {"id": 7, "name": "Ann Smith", "sheet_name": "Smith, Ann", "former_names": [],
     "activity": [{"kind": "christmas_install", "season": "2026",
                   "detail": {"install_fee": 1500, "takedown_fee": 1500, "storage_fee": 2250, "total": 5250}}]},
], "2026")


def test_norm_name_matches_the_tool():
    assert cdp.norm_name("  Smith,  Ann. ") == "smith ann"


def test_prices_come_from_clients_then_schedule_then_no_charge():
    b = board()
    assert cdp.install_price(b.clients[1], PRICES.get("smith ann"))[:2] == (1500, "clients")
    assert cdp.install_price(b.clients[2], None)[:2] == (900, "schedule")
    assert cdp.install_price(b.clients[3], None)[:2] == (0.0, "no_charge")
    assert cdp.install_price({"name": "x"}, None)[:2] == (None, "unpriced")


def test_unstaffed_day_is_costed_from_role_needs():
    out = cdp.crew_days(board(), PRICES, card(), {})
    d = out["days"][0]
    # most any one stop needs: 1 lead + 5 general
    assert [c["pay_class"] for c in d["crew_people"]] == ["lead"] + ["general"] * 5
    assert d["staffed_count"] == 0 and d["estimated_count"] == 6
    # paid: max(30, 30 boxes x 2 min = 60) before + 510->925 on the road + 40 lunch
    assert d["pretrip_min"] == 60 and d["paid_hours"] == round((60 + 415 + 40) / 60, 2)
    assert d["revenue"] == 2400
    assert d["cost"]["labor"] == round((18 + 5 * 15) * (515 / 60), 2)


def test_staffed_people_fill_their_own_seat():
    d = cdp.crew_days(board(staffing={"2026-11-02|Crew 1|0": ["p1"]}), PRICES, card(),
                      {"p1": {"pay_class": "lead", "rate_override": 20}})["days"][0]
    assert d["staffed_count"] == 1 and d["estimated_count"] == 5
    assert d["crew_people"][0] == {"name": "Ana", "pay_class": "lead", "label": "Lead", "rate": 20}


def test_net_and_status_follow_the_card():
    out = cdp.crew_days(board(), PRICES, card(), {})
    d = out["days"][0]
    assert d["overhead"] == 480
    assert d["net"] == round(2400 - d["cost"]["total"] - 480, 2)
    assert d["status"] == ("healthy" if d["net_pct"] >= 20 else "tight" if d["net_pct"] >= 0 else "losing")
    # A higher overhead on the card moves the same day's net
    worse = cdp.crew_days(board(), PRICES, card(overhead_pct=40), {})["days"][0]
    assert worse["net"] == round(d["net"] - 480, 2)


def test_a_no_charge_day_is_losing():
    d = cdp.crew_days(board(stops2=[3]), PRICES, card(), {})["days"][1]
    assert d["revenue"] == 0 and d["net_pct"] is None and d["status"] == "losing"


def test_a_crewless_day_is_flagged():
    d = cdp.crew_days(board(stops2=[3]), PRICES, card(), {})["days"][1]
    assert d["crew_people"] == [] and "crew" in d["cost"]["missing"]


def test_last_years_crew_beats_role_needs():
    b = board()
    b.clients[1]["size25"] = 6
    b.clients[2]["size25"] = "4"
    d = cdp.crew_days(b, PRICES, card(), {})["days"][0]
    # largest 2025 crew on the day: 6 = one lead + five general
    assert [c["pay_class"] for c in d["crew_people"]] == ["lead"] + ["general"] * 5
    assert d["crew_basis"] == "2025 crew"


def test_role_needs_are_the_fallback():
    d = cdp.crew_days(board(), PRICES, card(), {})["days"][0]
    assert d["crew_basis"] == "role needs"


def test_the_biggest_stop_sets_the_whole_days_crew():
    # 5, then 8, then 5 people: eight ride out and are paid for every stop.
    b = board(stops2=[1, 2, 3])
    b.clients[1]["roleNeed"] = {"leads": 1, "general": 4}
    b.clients[2]["roleNeed"] = {"leads": 1, "specialty": 1, "general": 6}
    b.clients[3]["roleNeed"] = {"leads": 2, "general": 3}
    d = cdp.crew_days(b, PRICES, card(), {})["days"][1]
    assert [c["pay_class"] for c in d["crew_people"]] == ["lead", "lead_assist"] + ["general"] * 6
    rates = 18 + 17 + 6 * 15
    # every one of the eight is paid for the whole shift, all three stops
    assert abs(d["cost"]["labor"] - rates * d["paid_hours"]) < rates * 0.01


def test_the_biggest_2025_crew_sets_the_whole_days_crew():
    b = board(stops2=[1, 2, 3])
    for r, n in ((1, 5), (2, 8), (3, 5)):
        b.clients[r]["size25"] = n
    d = cdp.crew_days(b, PRICES, card(), {})["days"][1]
    assert len(d["crew_people"]) == 8 and d["crew_basis"] == "2025 crew"
