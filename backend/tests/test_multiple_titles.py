"""Several titles per roster person (Comments #36, 2026-11-16), and Leads who
also work as General Installers (Comments #32/#33). `titles` is every title,
primary first; `title` stays the primary.

Option 1 (the user, 2026-11-17): extra titles never change who leads a crew,
who gets lead pages or the lead login role, or pay -- all of those read the
primary title exactly as before. FAKE people only."""
import asyncio

from test_install_costs import card_2026

from app.apis import install_schedule as sched
from app.libs import install_calendar, install_costs, roles, schedule_board

PAYLOAD = {
    "spec": {"version": "v1", "dayMeta": {}},
    "clients": {"10": {"name": "Smith Home", "street": "1 Oak St", "city": "Dallas", "st": "TX", "zip": "75201"}},
    "days": [
        {"id": "2026-11-14|Crew 1|0", "date": "2026-11-14", "crew": "Crew 1", "stops": [10]},
        {"id": "2026-11-14|Crew 2|0", "date": "2026-11-14", "crew": "Crew 2", "stops": [10]},
        {"id": "2026-11-15|Crew 1|0", "date": "2026-11-15", "crew": "Crew 1", "stops": [10]},
    ],
}
STATE = {
    "roster": [
        {"id": "p1", "first": "Al", "last": "Both", "title": "Lead", "titles": ["Lead", "General Installer"]},
        {"id": "p2", "first": "Les", "last": "Lead", "title": "Lead"},
        {"id": "p3", "first": "Gen", "last": "Eral", "title": "General Installer",
         "titles": ["General Installer", "Designer", "Boss"]},
        {"id": "p4", "first": "Old", "last": "Rec", "title": "Designer"},
    ],
    # Al (Lead + General) is first on D1, so he leads it, as before.
    "staffing": {"2026-11-14|Crew 1|0": ["p1", "p2", "p3"], "2026-11-14|Crew 2|0": ["p1", "p3"], "2026-11-15|Crew 1|0": ["p3"]},
}


def board():
    return schedule_board.resolve("2026", PAYLOAD, STATE)


def test_norm_person_carries_titles_primary_first():
    b = board()
    assert b.person("p1")["titles"] == ["Lead", "General Installer"]
    assert b.person("p3")["titles"] == ["General Installer", "Designer"]   # unknown dropped
    assert b.person("p4")["titles"] == ["Designer"]                        # derived when absent
    assert b.person("p1")["title"] == "Lead"


def test_crew_lead_is_the_first_primary_lead_as_before():
    """Al (Lead + General) is first on D1 and leads it, exactly as on main:
    an extra General title doesn't hand the crew to Les."""
    b = board()
    assert b.lead_of("2026-11-14|Crew 1|0")["id"] == "p1"
    assert b.lead_of("2026-11-14|Crew 2|0")["id"] == "p1"
    assert b.lead_of("2026-11-15|Crew 1|0") is None      # Gen's extra Designer isn't Lead
    assert [d["id"] for d in b.days_led_by("p1")] == ["2026-11-14|Crew 1|0", "2026-11-14|Crew 2|0"]
    assert b.days_led_by("p2") == []
    assert not hasattr(b, "crew_leads") and not hasattr(b, "can_lead_page")
    # Calendar crew line tags every primary Lead "(lead)", as before.
    line = install_calendar._crew_line(b, "2026-11-14|Crew 1|0")
    assert "Al Both (lead)" in line and "Les Lead (lead)" in line and "Gen Eral (lead)" not in line


def test_an_extra_lead_title_never_makes_a_lead():
    state = {"roster": [{"id": "g", "first": "Gen", "last": "Plus", "title": "General Installer",
                         "titles": ["General Installer", "Lead"]}],
             "staffing": {"2026-11-14|Crew 1|0": ["g"]}}
    b = schedule_board.resolve("2026", PAYLOAD, state)
    assert b.person("g")["titles"] == ["General Installer", "Lead"]
    assert b.lead_of("2026-11-14|Crew 1|0") is None
    assert b.days_led_by("g") == []


def _role(person):
    async def lookup(_email):
        return person
    roles.clear_cache()
    return asyncio.run(roles.resolve_role("multi-title@example.com", roster_lookup=lookup))


def test_login_role_follows_the_primary_title_only(fake_db):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    assert _role({"title": "Lead", "titles": ["Lead", "General Installer"]}) == "lead"
    assert _role({"title": "General Installer", "titles": ["General Installer", "Lead"]}) == "crew"
    assert _role({"title": "Designer", "titles": ["Designer", "Lead"]}) == "crew"
    roles.clear_cache()


def test_pay_class_follows_the_primary_title_only():
    card = install_costs.resolve_card(card_2026(), "2026")
    gen_plus_lead = {"id": "x", "title": "General Installer", "titles": ["General Installer", "Lead"]}
    lead_plus_gen = {"id": "y", "title": "Lead", "titles": ["Lead", "General Installer"]}
    assert install_costs.person_rate(gen_plus_lead, None, card)["rate"] == 15
    assert install_costs.person_rate(lead_plus_gen, None, card)["rate"] == 18
    # A pay assignment still wins over the title.
    assert install_costs.person_rate(lead_plus_gen, {"pay_class": "general"}, card)["rate"] == 15


STORED = {"roster": [
    {"id": "p1", "name": "Al Both", "title": "Lead", "titles": ["Lead", "General Installer"]},
    {"id": "p2", "name": "Les Lead", "title": "Lead", "titles": ["Lead"]},
]}


def test_save_without_titles_keeps_the_stored_extras():
    out = sched.keep_stored_person_fields(
        {"roster": [{"id": "p1", "name": "Al Both", "title": "Lead"},
                    {"id": "p2", "name": "Les Lead", "title": "Lead"}]}, STORED)
    assert out["roster"][0]["titles"] == ["Lead", "General Installer"]
    assert "titles" not in out["roster"][1]       # one title: nothing to keep


def test_save_without_titles_that_changed_the_primary_drops_the_old_one():
    out = sched.keep_stored_person_fields(
        {"roster": [{"id": "p1", "name": "Al Both", "title": "Designer"}]}, STORED)
    assert out["roster"][0]["titles"] == ["Designer", "General Installer"]
    out = sched.keep_stored_person_fields(
        {"roster": [{"id": "p1", "name": "Al Both", "title": "General Installer"}]}, STORED)
    assert out["roster"][0]["titles"] == ["General Installer"]


def test_save_with_titles_is_taken_as_sent():
    sent = {"roster": [{"id": "p1", "name": "Al Both", "title": "Lead", "titles": ["Lead"]}]}
    assert sched.keep_stored_person_fields(sent, STORED) == sent


def test_titles_survive_a_non_admin_save():
    """Only contractor fields are stripped for non-admins; titles pass."""
    sent = {"roster": [{"id": "p1", "title": "Lead", "titles": ["Lead", "General Installer"],
                        "legalName": "x"}]}
    out = sched.keep_stored_contractor_info(sent, STORED)
    assert out["roster"][0]["titles"] == ["Lead", "General Installer"]
    assert "legalName" not in out["roster"][0]
    assert "titles" not in sched.SENSITIVE_ROSTER_FIELDS


def test_lead_shift_payload_names_the_primary_lead():
    from app.apis import lead
    b = board()
    out = lead._day_out(b, b.days["2026-11-14|Crew 1|0"], [], [])
    assert out["lead"]["id"] == "p1"
    assert "leadIds" not in out
