"""rules.static_blockers / club_crew_ok on synthetic clients (season 2026).

2026 calendar facts used below (all derived by schedule.py/season.py):
Dallas nights Mon-Fri Nov 2-6 (week span Sun Nov 1 - Sat Nov 7),
Thanksgiving Thu Nov 26, bank Friday Nov 27, Rotary Sunday Nov 29.
"""
import pytest

import rules
import schedule as S


def client(**kw):
    base = {"name": "Test Client X", "category": "Standard",
            "business": "Residence", "prior_install_date": "",
            "install_2026_confirmed": "", "install_2026_no_install": False}
    base.update(kw)
    return base


def test_derived_calendar_for_2026():
    assert rules.THANKSGIVING == "2026-11-26"
    assert S.BANK_FRIDAY == "2026-11-27"
    assert S.ROTARY_SUNDAY == "2026-11-29"
    assert S.DALLAS_DAYS == ["2026-11-02", "2026-11-03", "2026-11-04",
                             "2026-11-05", "2026-11-06"]
    assert S.DALLAS_WEEK_SPAN == ("2026-11-01", "2026-11-07")
    assert S.DOW["2026-11-14"] == "Sat"


# --- Saturday eligibility (RULES.md §5: prior-year install ALSO a Saturday) --
def test_saturday_ok_when_prior_install_was_saturday():
    c = client(prior_install_date="2025-11-15")          # a Saturday
    assert rules.static_blockers(c, "2026-11-14", "Crew 1") == []


def test_saturday_flagged_when_prior_install_was_a_weekday():
    c = client(prior_install_date="2025-11-14")          # a Friday
    assert rules.static_blockers(c, "2026-11-14", "Crew 1") == ["SAT_HIST"]


@pytest.mark.parametrize("prior", ["", "2025-11", "not-a-date-at-all"])
def test_saturday_flagged_without_usable_history(prior):
    c = client(prior_install_date=prior)
    assert rules.static_blockers(c, "2026-11-14", "Crew 1") == ["SAT_HIST"]


def test_saturday_eligibility_is_a_ceiling_not_a_floor():
    c = client(prior_install_date="2025-11-15")
    assert rules.static_blockers(c, "2026-11-17", "Crew 1") == []   # Tue


def test_business_on_saturday_flagged_but_country_club_exempt():
    biz = client(business="Business")
    club = client(business="Business", category="Country Club")
    assert rules.static_blockers(biz, "2026-11-14", "Crew 1") == ["BIZ_SAT"]
    assert rules.static_blockers(club, "2026-11-14", "Crew 1") == []


@pytest.mark.parametrize("iso,expected", [
    ("2025-11-15", True), ("2025-11-15T09:00:00", True),
    ("2025-11-14", False), ("", False), (None, False), ("2025-13-45", False),
])
def test_was_saturday(iso, expected):
    assert rules.was_saturday(iso) is expected


# --- client-pinned (deposited) dates -------------------------------------------
def test_pinned_client_on_its_date_is_clear():
    c = client(install_2026_confirmed="2026-11-17")
    assert rules.static_blockers(c, "2026-11-17", "Crew 2") == []


def test_pinned_client_on_another_date_is_locked():
    c = client(install_2026_confirmed="2026-11-17")
    assert rules.static_blockers(c, "2026-11-18", "Crew 2") == ["LOCKED"]


def test_pin_does_not_waive_saturday_history_but_both_are_soft():
    c = client(install_2026_confirmed="2026-11-28")       # Sat, no history
    got = rules.static_blockers(c, "2026-11-28", "Crew 1")
    assert got == ["SAT_HIST"]
    assert {"SAT_HIST", "LOCKED"} <= rules.SOFT_CODES


# --- category / calendar rules -------------------------------------------------
def test_sunday_is_off_except_rotary_on_its_sunday():
    assert rules.static_blockers(client(), "2026-11-15", "Crew 1") == ["SUNDAY"]
    rotary = client(category="Rotary House", business="Business")
    assert rules.static_blockers(rotary, "2026-11-29", "Crew 3") == []
    assert rules.static_blockers(rotary, "2026-11-17", "Crew 3") == ["ROTARY"]


def test_dallas_week_is_closed_both_directions():
    mc = client(category="M Crowd", business="Business")
    assert rules.static_blockers(mc, "2026-11-03", "Crew 1") == []
    assert rules.static_blockers(mc, "2026-11-17", "Crew 1") == ["MC_DATE"]
    assert rules.static_blockers(client(), "2026-11-03", "Crew 1") == ["MC_ONLY", "NOT_MC"]


def test_banks_only_on_bank_friday():
    bank = client(category="Capital Bank", business="Business")
    assert rules.static_blockers(bank, "2026-11-27", "Crew 2") == []
    assert rules.static_blockers(bank, "2026-11-24", "Crew 2") == ["BANK_DATE"]


def test_thanksgiving_dropped_and_unknown_date():
    assert rules.static_blockers(client(), "2026-11-26", "Crew 1") == ["THANKS"]
    dropped = client(install_2026_no_install=True)
    assert rules.static_blockers(dropped, "2026-11-17", "Crew 1") == ["DROPPED"]
    assert rules.static_blockers(client(), "2027-03-01", "Crew 1") == ["NO_DATE"]


# --- R2 club coverage ------------------------------------------------------------
@pytest.mark.parametrize("category,crews,expected", [
    ("Standard", [], True),                                  # rule only covers clubs
    ("Country Club", ["Crew 1"], True),
    ("Country Club", ["Crew 2", "Crew 1"], True),            # joint day, two cards
    ("Country Club", ["Crew 1 + Crew 2 (joint)"], True),
    ("Country Club", ["Crew 2", "Crew 3"], False),
    ("Country Club", [], False),
])
def test_club_crew_ok(category, crews, expected):
    assert rules.club_crew_ok(category, crews) is expected


def test_client_rule_tables_come_from_synthetic_config():
    assert rules.PINS == {"Test Client C": "2026-11-17"}
    assert rules.NO_INSTALL == ["Test Client Dropped"]
    assert not hasattr(rules, "code_msg") and not hasattr(rules, "is_soft")
