"""Several titles per roster person (Comments #36, 2026-11-16), and Leads who
also work as General Installers (Comments #32/#33). `titles` is every title,
primary first; `title` stays the primary, and roles and pay read only that.
FAKE people only."""
import inspect

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
    # Al is first on D1 but works as a general there: Les leads.
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


def test_crew_lead_skips_a_lead_working_as_general():
    b = board()
    assert [p["id"] for p in b.crew_leads("2026-11-14|Crew 1|0")] == ["p2"]
    assert b.lead_of("2026-11-14|Crew 1|0")["id"] == "p2"
    assert b.lead_of("2026-11-14|Crew 2|0")["id"] == "p1"          # alone, still the lead
    assert b.lead_of("2026-11-15|Crew 1|0") is None
    assert [d["id"] for d in b.days_led_by("p1")] == ["2026-11-14|Crew 2|0"]
    line = install_calendar._crew_line(b, "2026-11-14|Crew 1|0")
    assert "Les Lead (lead)" in line and "Al Both (lead)" not in line


def test_role_and_pay_follow_the_primary_title_only():
    # Role: the primary title decides (Lead -> lead, anything else -> crew).
    src = inspect.getsource(roles)
    assert 'person.get("title") == "Lead"' in src
    # Pay class: the primary title, never an extra one.
    gen_with_lead = {"id": "x", "title": "General Installer", "titles": ["General Installer", "Lead"]}
    assert install_costs.TITLE_CLASS.get(gen_with_lead["title"]) == "general"
    assert "TITLE_CLASS.get(person.get(\"title\")" in inspect.getsource(install_costs)


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


def test_lead_shift_payload_lists_lead_ids():
    from app.apis import lead
    b = board()
    out = lead._day_out(b, b.days["2026-11-14|Crew 1|0"], [], [])
    assert out["leadIds"] == ["p2"]
    assert out["lead"]["id"] == "p2"
