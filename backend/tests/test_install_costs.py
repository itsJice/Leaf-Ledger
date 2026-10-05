"""The install cost card: season inheritance, pay by class, crew-day cost."""

import pytest

from app.libs import install_costs as ic


def row(season, key, amount, label=None):
    return {"season": season, "key": key, "amount": amount, "label": label}


def card_2026():
    return [
        row("2026", "pay:lead", 18, "Lead"), row("2026", "pay:lead_assist", 17, "Lead Assist"),
        row("2026", "pay:general", 15, "General Installer"), row("2026", "pay:junior", 12, "Junior Installer"),
        row("2026", "pay:designer", 16.5, "Designer"),
        row("2026", "van_day", 225), row("2026", "trailer_day", 125),
        row("2026", "vans_per_crew", 1), row("2026", "trailers_per_crew", 1),
        row("2026", "mpg", 10), row("2026", "gas_per_gallon", 4), row("2026", "ancillary_day", 20),
        row("2026", "load_min_per_box", 2), row("2026", "overhead_pct", 19.4), row("2026", "target_profit_pct", 16),
    ]


def test_resolve_card_orders_classes_and_reports_nothing_missing():
    card = ic.resolve_card(card_2026(), "2026")
    assert [c["slug"] for c in card["classes"]] == ["lead", "lead_assist", "general", "junior", "designer"]
    assert card["costs"]["van_day"] == 225
    assert card["missing"] == []


def test_resolve_card_inherits_and_honours_removals():
    rows = card_2026() + [
        row("2027", "pay:junior", None),                 # dropped in 2027
        row("2027", "pay:trainee", None, "Trainee"),     # added, no rate yet
        row("2027", "van_day", None),                    # cleared -> needs input
        row("2027", "gas_per_gallon", 3.5),
    ]
    card = ic.resolve_card(rows, "2027")
    slugs = [c["slug"] for c in card["classes"]]
    assert "junior" not in slugs and slugs[-1] == "trainee"
    assert card["costs"]["gas_per_gallon"] == 3.5 and "van_day" not in card["costs"]
    assert set(card["missing"]) == {"van_day", "pay:trainee"}
    # 2026 is untouched by 2027's rows
    assert ic.resolve_card(rows, "2026")["missing"] == []


def test_empty_card_needs_the_required_keys():
    card = ic.resolve_card([], "2026")
    assert set(card["missing"]) == {k for k, m in ic.COST_KEYS.items() if m["required"]}
    assert ic.derived(card) == {"gas_per_mile": None, "break_even_pct": None, "target_spend_pct": None}


def test_derived_numbers():
    d = ic.derived(ic.resolve_card(card_2026(), "2026"))
    assert d == {"gas_per_mile": 0.4, "break_even_pct": 80.6, "target_spend_pct": 64.6}


def test_person_rate_class_title_and_override():
    card = ic.resolve_card(card_2026(), "2026")
    lead = {"id": "p1", "title": "Lead"}
    assert ic.person_rate(lead, None, card) == {"pay_class": "lead", "label": "Lead", "rate": 18, "source": "title"}
    assert ic.person_rate({"id": "p2", "title": "General Installer"}, {"pay_class": "junior"}, card)["rate"] == 12
    over = ic.person_rate(lead, {"pay_class": "lead", "rate_override": "19.50"}, card)
    assert over["rate"] == 19.5 and over["source"] == "override"
    # a class that no longer exists falls back to the title
    assert ic.person_rate(lead, {"pay_class": "gone"}, card)["source"] == "title"
    # the roster's Designer title is paid as the Designer class
    assert ic.person_rate({"id": "p3", "title": "Designer"}, None, card) == {
        "pay_class": "designer", "label": "Designer", "rate": 16.5, "source": "title"}


def test_person_rate_missing_when_class_has_no_rate():
    card = ic.resolve_card([row("2026", "pay:lead", None, "Lead")], "2026")
    assert ic.person_rate({"title": "Lead"}, None, card) == {
        "pay_class": "lead", "label": "Lead", "rate": None, "source": "missing"}


def test_crew_day_cost_at_the_2026_card():
    card = ic.resolve_card(card_2026(), "2026")
    # one lead + four general, 10-hour shift, 60 route miles
    out = ic.crew_day_cost([18, 15, 15, 15, 15], 10, 60, card)
    assert out["labor"] == 780
    assert (out["van"], out["trailer"], out["gas"], out["ancillary"]) == (225, 125, 24, 20)
    assert out["total"] == 1174 and out["missing"] == []


def test_crew_day_cost_names_what_is_missing():
    card = ic.resolve_card([row("2026", "mpg", 10)], "2026")
    out = ic.crew_day_cost([18, None], 8, 40, card)
    assert out["labor"] == 144
    assert set(out["missing"]) == {"pay rate", "van_day", "trailer_day", "gas"}


@pytest.mark.parametrize("label,slug", [("Trainee", "trainee"), ("Night Lead!", "night_lead"), ("  ", "")])
def test_slugify(label, slug):
    assert ic.slugify(label) == slug


def test_valid_key():
    assert ic.valid_key("van_day") and ic.valid_key("pay:night_lead")
    assert not ic.valid_key("pay:") and not ic.valid_key("pay:Bad Slug") and not ic.valid_key("tip")
