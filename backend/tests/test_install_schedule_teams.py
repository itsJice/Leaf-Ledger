"""Teams (saved groups of roster people, by year) on the Install Schedule
state document: they carry over to a rebuilt schedule like the roster does,
and a save from a page published before teams can't erase them."""
from app.apis import install_schedule as sched


def test_teams_carry_forward_with_the_roster():
    assert "teams" in sched.CARRY_FORWARD_KEYS
    assert {"roster", "staffing"} <= set(sched.CARRY_FORWARD_KEYS)


TEAMS = [{"id": "t1", "name": "Team A", "season": 2026, "leadId": "p1", "members": ["p1", "p2"]}]


def test_a_save_without_the_teams_key_keeps_the_stored_teams():
    out = sched.keep_stored_teams({"roster": []}, {"roster": [], "teams": TEAMS})
    assert out == {"roster": [], "teams": TEAMS}


def test_a_page_that_knows_teams_can_delete_them():
    assert sched.keep_stored_teams({"teams": []}, {"teams": TEAMS}) == {"teams": []}
    assert sched.keep_stored_teams({"teams": TEAMS[:0] + [{"id": "t2"}]}, {"teams": TEAMS}) == {"teams": [{"id": "t2"}]}


def test_nothing_stored_means_nothing_added():
    assert sched.keep_stored_teams({"a": 1}, None) == {"a": 1}
    assert sched.keep_stored_teams({"a": 1}, {"teams": []}) == {"a": 1}
    assert sched.keep_stored_teams({"a": 1}, {"teams": "junk"}) == {"a": 1}


# seasonRoles: the season's Box Truck Driver (2026-10-31), kept the same way.
ROLES = {"2026": {"boxTruckId": "p1"}}


def test_season_roles_carry_forward_and_survive_an_older_page():
    assert "seasonRoles" in sched.CARRY_FORWARD_KEYS
    out = sched.keep_stored_teams({"teams": TEAMS}, {"teams": TEAMS, "seasonRoles": ROLES})
    assert out == {"teams": TEAMS, "seasonRoles": ROLES}
    # an older page that knows neither key keeps both
    assert sched.keep_stored_teams({}, {"teams": TEAMS, "seasonRoles": ROLES}) == {"teams": TEAMS, "seasonRoles": ROLES}


def test_a_page_that_knows_season_roles_can_clear_them():
    assert sched.keep_stored_teams({"seasonRoles": {}}, {"seasonRoles": ROLES}) == {"seasonRoles": {}}
    assert sched.keep_stored_teams({"a": 1}, {"seasonRoles": "junk"}) == {"a": 1}
    assert sched.keep_stored_teams({"a": 1}, {"seasonRoles": {}}) == {"a": 1}
