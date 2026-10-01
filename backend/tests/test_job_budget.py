"""Job budgets: jobs grouped across crew-days, takedown estimate, hour budget."""

import pytest

from app.libs import crew_day_profit as cdp
from app.libs import job_budget as jb
from app.libs.schedule_board import Board
from app.libs import install_costs as ic
from tests.test_crew_day_profit import PRICES, board
from tests.test_crew_day_profit import card as base_card


def card(**over):
    """The crew-day tests' card, plus any key it doesn't carry (the takedown factor)."""
    c = base_card(**over)
    extra = {k: v for k, v in over.items() if k not in c["costs"] and k in ic.COST_KEYS}
    return {**c, "costs": {**c["costs"], **extra}}


def budgets(b, c=None, prices=PRICES):
    c = c or card()
    return jb.job_budgets(cdp.crew_days(b, prices, c, {}), prices, b, c)


def job(out, row):
    return next(j for j in out["jobs"] if j["row"] == row)


def test_a_job_split_over_two_days_is_one_job():
    b = board(stops2=[1, 3])
    days = cdp.crew_days(b, PRICES, card(), {})
    out = jb.job_budgets(days, PRICES, b, card())
    assert out["summary"]["jobs"] == 3
    ann = job(out, 1)
    assert [d["date"] for d in ann["days"]] == ["2026-11-02", "2026-11-03"]
    stops = [s for d in days["days"] for s in d["stops"] if s["row"] == 1]
    assert ann["install"]["onsite_h"] == pytest.approx(sum(s["onsite_h"] for s in stops))
    assert ann["install"]["paid_h"] == pytest.approx(sum(s["paid_h"] for s in stops), abs=0.01)
    assert ann["install"]["labor_cost"] == pytest.approx(sum(s["labor_cost"] for s in stops), abs=0.01)
    assert ann["install"]["other_cost"] == pytest.approx(sum(s["other_cost"] for s in stops), abs=0.01)
    # 6 people on day one (Club House needs 1 + 5), 4 on day two: the most sets the size
    assert ann["install"]["crew_size"] == 6
    # the crew rate is the two days' rates weighted by the job's paid hours on each
    (s1, d1), (s2, d2) = [(s, d) for d in days["days"] for s in d["stops"] if s["row"] == 1]
    want = (d1["crew_rate"] * s1["paid_h"] + d2["crew_rate"] * s2["paid_h"]) / (s1["paid_h"] + s2["paid_h"])
    assert ann["install"]["crew_rate"] == pytest.approx(want, abs=0.01)
    assert ann["install"]["crew_basis"] == "role needs"


def test_takedown_is_install_time_times_the_factor_and_the_same_trip():
    out = budgets(board(), card(takedown_time_factor=0.5))
    ann = job(out, 1)
    assert out["takedown_time_factor"] == 0.5
    assert ann["takedown"]["paid_h"] == pytest.approx(ann["install"]["paid_h"] * 0.5, abs=0.01)
    assert ann["takedown"]["labor_cost"] == pytest.approx(ann["install"]["labor_cost"] * 0.5, abs=0.01)
    assert ann["takedown"]["other_cost"] == ann["install"]["other_cost"]
    # default factor when the card says nothing
    assert budgets(board())["takedown_time_factor"] == 0.6


def test_price_total_net_and_hour_budget():
    out = budgets(board())
    ann = job(out, 1)
    assert ann["price"] == {"total": 5250, "install": 1500, "takedown": 1500, "storage": 2250,
                            "price_source": "clients", "basis": None}
    i, t, bud = ann["install"], ann["takedown"], ann["budget"]
    cost = i["labor_cost"] + i["other_cost"] + t["labor_cost"] + t["other_cost"]
    assert ann["job_cost"] == pytest.approx(cost, abs=0.02)
    assert ann["overhead"] == 1050  # 20% of 5250
    assert ann["net"] == pytest.approx(5250 - cost - 1050, abs=0.02)
    assert ann["net_pct"] == pytest.approx(ann["net"] / 5250 * 100, abs=0.05)
    assert ann["materials"] is None
    # budgets: (price x (1 - 20% - 20%) - vehicles) / crew rate, and at 80% for break-even
    vehicle = i["other_cost"] + t["other_cost"]
    assert bud["vehicle"] == pytest.approx(vehicle, abs=0.02)
    assert bud["budget_target_h"] == pytest.approx((5250 * 0.6 - vehicle) / i["crew_rate"], abs=0.1)
    assert bud["budget_breakeven_h"] == pytest.approx((5250 * 0.8 - vehicle) / i["crew_rate"], abs=0.1)
    assert bud["planned_h"] == pytest.approx(i["paid_h"] + t["paid_h"], abs=0.1)
    assert bud["over_target_h"] == pytest.approx(bud["planned_h"] - bud["budget_target_h"], abs=0.15)


def test_total_falls_back_to_the_sum_of_the_fees():
    prices = cdp.price_index([
        {"id": 7, "name": "Smith, Ann", "activity": [{"kind": "christmas_install", "season": "2026",
                                                      "detail": {"install_fee": 1000, "takedown_fee": 1000}}]},
    ], "2026")
    ann = job(budgets(board(), prices=prices), 1)
    assert ann["price"]["total"] == 2000 and ann["price"]["storage"] is None


def test_schedule_fees_then_no_charge_then_unpriced():
    b = board(stops2=[3])
    b.clients[2]["takedownFee"] = 900
    out = budgets(b, prices={})
    club = job(out, 2)
    assert club["price"]["total"] == 1800 and club["price"]["price_source"] == "schedule"
    free = job(out, 3)
    assert free["price"]["total"] == 0 and free["price"]["price_source"] == "no_charge"
    assert free["status"] == "losing" and free["net_pct"] is None
    ann = job(out, 1)
    assert ann["status"] == "unpriced" and ann["price"]["total"] is None
    assert ann["net"] is None and ann["budget"]["budget_target_h"] is None
    # unpriced last; the $0 loser first
    assert out["jobs"][-1]["row"] == 1 and out["jobs"][0]["row"] == 3
    assert out["summary"]["priced_jobs"] == 2
    assert out["summary"]["unpriced_cost"] == ann["job_cost"]


def test_status_follows_the_card_and_sort_is_worst_first():
    out = budgets(board())
    for j in out["jobs"]:
        p = j["net_pct"]
        assert j["status"] == ("healthy" if p >= 20 else "tight" if p >= 0 else "losing")
    pcts = [j["net_pct"] for j in out["jobs"]]
    assert pcts == sorted(pcts)
    counts = out["summary"]["counts"]
    assert sum(counts.values()) == out["summary"]["jobs"]
    assert out["summary"]["over_budget"] == sum(1 for j in out["jobs"] if j["budget"]["over_target_h"] > 0)
    # 40 more points of overhead take 40 points off every priced job
    worse = budgets(board(), card(overhead_pct=60))
    for j in worse["jobs"]:
        assert j["net_pct"] == pytest.approx(job(out, j["row"])["net_pct"] - 40, abs=0.15)
    assert job(worse, 2)["status"] == "losing"


def test_last_year_hours_and_crew():
    b = board()
    b.clients[1]["real25"] = 5
    b.clients[1]["size25"] = 6
    out = budgets(b)
    ann = job(out, 1)
    assert ann["last_year"] == {"hours": 5, "crew_size": 6, "takedown_hours": None}
    assert ann["last_year_vs_plan"] == {"plan_onsite_h": 4.0, "real25_h": 5, "diff_h": -1.0, "ratio": 0.8}
    assert ann["install"]["crew_basis"] == "2025 crew"
    club = job(out, 2)
    assert club["last_year"] == {"hours": None, "crew_size": None, "takedown_hours": None} and club["last_year_vs_plan"] is None


def test_no_crew_rate_means_no_hour_budget():
    b = Board(season="2026", version="v", clients={
        3: {"name": "Free Job", "h26": 2, "installFee": 500, "roleNeed": {}, "lat": 29.9, "lon": -95.4}},
        days={"d": {"id": "d", "date": "2026-11-04", "crew": "Crew 2", "stops": [3]}},
        depot={"lat": 29.81, "lon": -95.47}, const={"LUNCH": 40})
    j = budgets(b, prices={})["jobs"][0]
    assert j["install"]["crew_size"] == 0 and j["install"]["crew_basis"] == "none"
    assert j["budget"]["budget_target_h"] is None and j["budget"]["over_target_h"] is None
    assert j["placeholder"] is True


def test_last_year_comes_from_the_clients_tab_when_the_schedule_has_none():
    clients = [{"name": "Ann Smith", "sheet_name": "Smith, Ann", "former_names": [], "activity": [
        {"kind": "christmas_install", "season": "2025",
         "detail": {"real_hours": 2.08, "crew_size": 6, "takedown_real_hours": 1.0}}]}]
    idx = jb.last_year_index(clients, "2026")
    assert idx["smith ann"] == {"hours": 2.08, "crew_size": 6, "takedown_hours": 1.0}
    b = board()
    out = jb.job_budgets(cdp.crew_days(b, PRICES, card(), {}), PRICES, b, card(), idx)
    ann = next(j for j in out["jobs"] if j["row"] == 1)
    assert ann["last_year"] == {"hours": 2.08, "crew_size": 6, "takedown_hours": 1.0}
