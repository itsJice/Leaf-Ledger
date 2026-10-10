"""The Install Schedule's stale-tab guard (PUT /install-schedule/state).

10/8/2026: a server-side 1099 import (updated_by 'claude-1099-import', 8:29 PM
CT) added 23 roster people and contractor fields. A tab opened before it saved
its whole state at 9:03 PM while sending mass texts and silently erased all of
it. These run put_state/get_state against a small in-memory stand-in for the
state row, so the import, the stale save and the retry happen in order.
"""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.apis import install_schedule as sched

T_LOAD = datetime(2026, 10, 9, 0, 0, 5, 123456, tzinfo=timezone.utc)      # tab opened
T_IMPORT = datetime(2026, 10, 9, 1, 29, 0, 654321, tzinfo=timezone.utc)   # 8:29 PM CT


def run(coro):
    return asyncio.run(coro)


def person(pid, first, **kw):
    return {"id": pid, "first": first, "last": "Test", "name": f"{first} Test",
            "title": "General Installer", "active": True, "texts": [], **kw}


def before_import():
    return {"season": "2026", "placement": {"1": ["2026-11-13|A|0"], "2": ["2026-11-18|B|0"]},
            "roster": [person("p1", "Ana", active=False), person("p2", "Luis")],
            "staffing": {}}


def after_import():
    st = before_import()
    st["roster"][0].update(active=True, legalName="Ana Q Test", street="1 Main St",
                           city="Houston", state="TX", zip="77002", tax1099=True)
    st["roster"][1].update(legalName="Luis R Test", directDeposit=True)
    st["roster"] += [person(f"p{i}", f"New{i}", legalName=f"New{i} Legal", tax1099=True)
                     for i in range(3, 26)]                                  # 23 people
    return st


TEXT = {"at": "2026-10-09T02:03:00.000Z", "lang": "en", "body": "Can you work Oct 26?"}


class Row:
    """One ll_app.install_schedule_state row, plus the history it appends."""

    def __init__(self, fake_db, state=None, at=None, by=None):
        self.state, self.at, self.by = state, at, by
        self.history = []
        fake_db.on("SELECT state, updated_by, updated_at FROM ll_app.install_schedule_state",
                   self._select, method="fetchrow")
        fake_db.on("INSERT INTO ll_app.install_schedule_state", self._insert, method="execute")
        fake_db.on("RETURNING updated_at", self._update, method="fetchval")
        fake_db.on("INSERT INTO ll_app.install_schedule_history", self._hist, method="execute")

    def _select(self, sql, *args):
        if self.state is None:
            return None
        return {"state": json.dumps(self.state), "updated_by": self.by, "updated_at": self.at}

    def _insert(self, sql, *args):
        if self.state is None:
            self.state, self.at, self.by = {}, datetime(2026, 10, 1, tzinfo=timezone.utc), args[2]
        return "INSERT 0 1"

    def _update(self, sql, version, encoded, by, season):
        self.state, self.by = json.loads(encoded), by
        self.at = self.at + timedelta(minutes=1)
        return self.at

    def _hist(self, sql, *args):
        self.history.append(args)
        return "INSERT 0 1"

    def script_write(self, state, at, by):
        """A server-side script: FOR UPDATE + its own updated_at guard, then a
        write that bumps updated_at (the import did exactly this)."""
        self.state, self.at, self.by = copy.deepcopy(state), at, by


ADMIN = "super_admin"


def put(fake_request, state, *, base="omit", role=ADMIN, who="user-a"):
    body = {"version": "build-1", "state": state}
    if base != "omit":
        body["baseUpdatedAt"] = base
    return run(sched.put_state(fake_request(who), body, role=role))


def body_of(resp):
    return resp.status_code, json.loads(resp.body)


def test_the_10_8_scenario_import_then_stale_tab_texting(fake_db, fake_request):
    row = Row(fake_db, before_import(), T_LOAD, "user-a")
    # 1. The tab loads (its base is the stamp it was handed).
    loaded = run(sched.get_state("build-1", "2026", role=ADMIN))
    assert loaded["updatedAt"] == T_LOAD.isoformat()
    # 2. The import lands while that tab stays open.
    row.script_write(after_import(), T_IMPORT, "claude-1099-import")
    # 3. The stale tab texts Luis and saves the only roster it knows.
    stale = copy.deepcopy(loaded["state"])
    stale["roster"][1]["texts"] = [TEXT]
    status, conflict = body_of(put(fake_request, stale, base=loaded["updatedAt"]))
    # Refused, with the current state to merge onto; nothing was written.
    assert status == 409 and conflict["conflict"] is True
    assert conflict["updatedBy"] == "claude-1099-import"
    assert conflict["updatedAt"] == T_IMPORT.isoformat()
    assert len(conflict["state"]["roster"]) == 25
    assert row.state == after_import() and row.at == T_IMPORT and row.history == []
    # 4. The page merges its one change (the text) onto that and retries on
    #    the new base. (The merge itself is mergeShared() in the page --
    #    scheduler/tests/test_stale_tab_merge.py runs it on this same scenario.)
    merged = copy.deepcopy(conflict["state"])
    merged["roster"][1]["texts"] = [TEXT]
    out = put(fake_request, merged, base=conflict["updatedAt"])
    assert out["ok"] and out["updatedAt"] == row.at.isoformat() and row.at > T_IMPORT
    # The import is intact and the text is applied.
    assert len(row.state["roster"]) == 25
    assert row.state["roster"][0]["legalName"] == "Ana Q Test" and row.state["roster"][0]["active"]
    assert row.state["roster"][1]["texts"] == [TEXT]
    assert row.state["roster"][1]["legalName"] == "Luis R Test"
    assert len(row.history) == 1
    # 5. Its next save builds on what it was just handed: no conflict.
    merged["roster"][0]["notes"] = "Prefers nights"
    assert put(fake_request, merged, base=out["updatedAt"])["ok"]


def test_stale_save_never_writes_card_dates(fake_db, fake_request, monkeypatch):
    monkeypatch.setattr(sched, "season_for", lambda: 2026)
    Row(fake_db, after_import(), T_IMPORT, "user-b")
    st = before_import()
    st["dateMoves"] = [{"id": 41, "name": "Amy Jinks", "kind": "install",
                        "date": "2026-11-13", "from": "2026-11-16"}]
    status, _ = body_of(put(fake_request, st, base=T_LOAD.isoformat()))
    assert status == 409
    assert not fake_db.seen("client_activity")


def test_conflict_strips_contractor_info_below_admin(fake_db, fake_request):
    Row(fake_db, after_import(), T_IMPORT, "claude-1099-import")
    status, conflict = body_of(put(fake_request, before_import(), base=T_LOAD.isoformat(), role="staff"))
    assert status == 409
    assert not any(k in p for p in conflict["state"]["roster"] for k in sched.SENSITIVE_ROSTER_FIELDS)


def test_a_page_that_saw_nothing_is_stale_once_someone_saved(fake_db, fake_request):
    Row(fake_db, after_import(), T_IMPORT, "user-b")
    status, _ = body_of(put(fake_request, before_import(), base=None))
    assert status == 409


def test_first_save_of_a_new_build_goes_through(fake_db, fake_request):
    row = Row(fake_db)                           # no row at all yet
    assert put(fake_request, before_import(), base=None)["ok"]
    assert row.state == before_import()


def test_any_write_since_the_base_counts_whatever_the_clocks_did(fake_db, fake_request):
    # The stored stamp is OLDER than the page's base (clock skew between a
    # script and the database): still not the version the page saw.
    Row(fake_db, after_import(), T_LOAD - timedelta(hours=1), "script")
    status, _ = body_of(put(fake_request, before_import(), base=T_LOAD.isoformat()))
    assert status == 409


def test_bad_base_is_a_400(fake_db, fake_request):
    Row(fake_db, after_import(), T_IMPORT, "x")
    with pytest.raises(HTTPException) as exc:
        put(fake_request, before_import(), base="yesterday")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("base", ["2026-10-09T01:29:00.654321+00:00", "2026-10-09T01:29:00.654321Z"])
def test_base_round_trips_exactly(fake_db, fake_request, base):
    Row(fake_db, after_import(), T_IMPORT, "x")
    assert put(fake_request, after_import(), base=base)["ok"]


# ─── pages published before the guard (no baseUpdatedAt) ────────────────────


def test_old_page_save_is_accepted_but_cannot_drop_people_or_contractor_info(fake_db, fake_request, capsys):
    row = Row(fake_db, after_import(), T_IMPORT, "claude-1099-import")
    stale = before_import()                          # what the 9:03 PM tab held
    stale["roster"][1]["texts"] = [TEXT]
    stale["roster"][1]["phone"] = "(713) 555-0100"   # a real edit still lands
    assert put(fake_request, stale)["ok"]
    roster = {p["id"]: p for p in row.state["roster"]}
    assert len(roster) == 25                                         # nobody dropped
    assert roster["p2"]["texts"] == [TEXT] and roster["p2"]["phone"] == "(713) 555-0100"
    assert roster["p2"]["legalName"] == "Luis R Test"                # kept from storage
    assert roster["p1"]["legalName"] == "Ana Q Test"
    assert roster["p25"]["legalName"] == "New25 Legal"
    log = capsys.readouterr().out
    assert "without baseUpdatedAt" in log and "kept 23 people" in log


def test_old_page_admin_clearing_one_field_still_works(fake_db, fake_request):
    """Only a person sent with NO contractor fields at all is topped up; an
    old page that knows the fields sends the ones it kept."""
    row = Row(fake_db, after_import(), T_IMPORT, "x")
    st = after_import()
    del st["roster"][0]["street"]
    assert put(fake_request, st)["ok"]
    assert "street" not in row.state["roster"][0] and row.state["roster"][0]["city"] == "Houston"


def test_old_pages_can_be_refused_once_republished(fake_db, fake_request, monkeypatch):
    Row(fake_db, after_import(), T_IMPORT, "x")
    monkeypatch.setenv(sched.REQUIRE_BASE_ENV, "true")
    with pytest.raises(HTTPException) as exc:
        put(fake_request, before_import())
    assert exc.value.status_code == 428
    # a guarded save is unaffected
    assert put(fake_request, after_import(), base=T_IMPORT.isoformat())["ok"]
