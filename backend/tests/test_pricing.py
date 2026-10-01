"""app.libs.pricing -- the ideal price of a job and the discount off it."""

import pytest

from app.libs import pricing

RATES_2026 = {
    "crew_lead": 100.0, "specialty": 135.0, "designer": 150.0, "general": 75.0,
    "storage_box": 75.0,
    "van_crew_rate": 150.0, "handling_min_per_box": 2.0, "drive_min_default": 30.0,
}


def rows(**by_season):
    return [{"season": s, "key": k, "amount": a}
            for s, rates in by_season.items() for k, a in rates.items()]


def test_resolve_rates_inherits_from_latest_earlier_season():
    r = rows(**{"2025": {"crew_lead": 90, "general": 70},
                "2026": {"crew_lead": 100},
                "2028": {"crew_lead": 999}})
    assert pricing.resolve_rates(r, "2026") == {"crew_lead": 100.0, "general": 70.0}
    assert pricing.resolve_rates(r, "2027") == {"crew_lead": 100.0, "general": 70.0}   # nothing of its own
    assert pricing.resolve_rates(r, "2025") == {"crew_lead": 90.0, "general": 70.0}
    assert pricing.resolve_rates(r, "2024") == {}                                       # before any card
    assert pricing.resolve_rates([{"season": "2026", "key": "x", "amount": "1,000"}], "2026") == {"x": 1000.0}


def card(**over):
    d = {"role_need": {"leads": 1, "general": 4}, "est_hours": 3, "boxes": 10, "storing": True,
         "drive_min_out": 25, "drive_min_back": 30}
    d.update(over)
    return d


def test_ideal_full_card():
    out = pricing.ideal(card(), RATES_2026)
    # (1x100 + 4x75) x 3h = 1200 install, same again takedown
    # storage 10 x 75 = 750
    # pickup & delivery: loading 2x10x2 = 40 min, driving 2x(25+30) = 110 min -> 150/60 x 150 = 375
    assert out == {"install": 1200.0, "takedown": 1200.0, "storage": 750.0,
                   "pickup_delivery": 375.0, "total": 3525.0, "missing": []}


@pytest.mark.parametrize("boxes,storing,fee", [
    (0, False, 275.0),   # boxes stay at the client: driving only
    (10, True, 375.0),
    (30, True, 575.0),
    (65, True, 925.0),
])
def test_pickup_delivery_scales_with_boxes(boxes, storing, fee):
    out = pricing.ideal(card(boxes=boxes, storing=storing), RATES_2026)
    assert out["pickup_delivery"] == fee
    assert out["storage"] == (boxes * 75.0 if storing else 0.0)


def test_pickup_delivery_falls_back_to_default_drive_time():
    out = pricing.ideal(card(drive_min_out=None, drive_min_back=None), RATES_2026)
    # 40 min loading + 2 x (30 + 30) = 160 min -> 160/60 x 150
    assert out["pickup_delivery"] == 400.0
    out = pricing.ideal(card(drive_min_back=None), RATES_2026)
    assert out["pickup_delivery"] == 375.0 + (2 * 0 / 60) * 150   # 25 out, 30 default back = same as card()


def test_ideal_reports_what_is_missing():
    out = pricing.ideal({}, RATES_2026)
    assert out["total"] is None and out["install"] is None
    assert out["missing"] == ["est_hours", "role_need"]
    # pickup & delivery still prices (default legs, no boxes) so the card is
    # never entirely blank once rates exist
    assert out["pickup_delivery"] == 300.0
    out = pricing.ideal(card(), {"crew_lead": 100})
    assert "rate:general" in out["missing"] and "rate:storage_box" in out["missing"]
    assert out["total"] is None
    # role_need with only zeros is no crew at all
    assert "role_need" in pricing.ideal(card(role_need={"leads": 0}), RATES_2026)["missing"]


def test_ideal_specialty_and_designer_rates():
    out = pricing.ideal(card(role_need={"leads": 2, "specialty": 1, "designer": 1, "general": 6},
                             est_hours=8), RATES_2026)
    assert out["install"] == (200 + 135 + 150 + 450) * 8


def test_charged_is_invoice_then_total_never_a_fee_sum():
    assert pricing.charged({"invoice_total": "1,065.50", "total": 900}) == 1065.5
    assert pricing.charged({"total": 900}) == 900.0
    assert pricing.charged({"install_fee": 400, "takedown_fee": 400, "storage_fee": 75}) is None
    assert pricing.charged({"storage_fee": 75}) is None
    assert pricing.charged({}) is None


def test_price_view():
    v = pricing.price_view(card(total=2820, price_basis="2026 export"), RATES_2026)
    assert v["ideal"]["total"] == 3525.0
    assert v["charged"] == 2820.0 and v["charged_source"] == "total"
    assert v["discount_pct"] == 20.0
    assert v["basis"] == "2026 export"
    v = pricing.price_view(card(invoice_total=3525), RATES_2026)
    assert v["discount_pct"] == 0.0 and v["charged_source"] == "invoice"
    # a premium is a negative discount, not an error
    v = pricing.price_view(card(total=4230), RATES_2026)
    assert v["discount_pct"] == -20.0
    # nothing charged yet: no discount, no crash
    v = pricing.price_view(card(), RATES_2026)
    assert v["charged"] is None and v["discount_pct"] is None and v["charged_source"] is None
    # no ideal (blank card): charged still shows, discount does not
    v = pricing.price_view({"total": 500}, {})
    assert v["charged"] == 500.0 and v["discount_pct"] is None and v["ideal"]["total"] is None
