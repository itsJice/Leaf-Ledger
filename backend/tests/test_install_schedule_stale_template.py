"""The Install Schedule's stale-template guard (GET /page stamp, PUT /state check).

11/1/2026, 4:09 PM CT: a tab opened before the 10/31 10:31 PM publish saved
with a current base (it kept loading the state, so the stale-tab guard let it
through), but its older page didn't know the newer keys and dropped
hoursOverride and every team's driverId. Now the served page carries its
publish stamp and a save from any other publish is refused.
"""

import asyncio
import json
from datetime import datetime, timezone

from app.apis import install_schedule as sched
from test_install_schedule_stale_guard import ADMIN, Row, body_of

PUBLISHED = datetime(2026, 11, 1, 3, 31, 0, 123456, tzinfo=timezone.utc)   # 10/31 10:31 PM CT
EARLIER = datetime(2026, 10, 31, 1, 0, 0, tzinfo=timezone.utc)
SAVED = datetime(2026, 11, 1, 20, 0, 0, tzinfo=timezone.utc)

NEW_PAGE = '<html><head><meta charset="utf-8"><script>meta[name="tbdg-page-rev"]</script>'
OLD_PAGE = '<html><head><meta charset="utf-8"><script>no guard here</script>'


def run(coro):
    return asyncio.run(coro)


def live_state():
    return {"season": "2026", "placement": {"7": ["2026-11-20|Crew 1|0"]},
            "hoursOverride": {"7": 4},
            "teams": [{"id": "t1", "name": "Team Ana", "season": 2026, "leadId": "p1",
                       "members": ["p1", "p2"], "driverId": "p2"}]}


def stale_tab_doc():
    """What the 11/1 tab sent: no hoursOverride, no driverId."""
    st = live_state()
    del st["hoursOverride"]
    del st["teams"][0]["driverId"]
    return st


def published(fake_db, html=NEW_PAGE, at=PUBLISHED):
    sched._PAGE_SENDS_REV.clear()
    fake_db.on("SELECT updated_at FROM ll_app.install_schedule_pages",
               lambda sql, *a: {"updated_at": at}, method="fetchrow")
    fake_db.on("SELECT strpos(html, $2) > 0", lambda sql, s, mark: mark in html, method="fetchval")


def put(fake_request, state, **extra):
    body = {"version": "build-1", "state": state, "baseUpdatedAt": SAVED.isoformat(), **extra}
    return run(sched.put_state(fake_request("user-a"), body, role=ADMIN))


def test_the_11_1_tab_is_refused_and_nothing_is_written(fake_db, fake_request):
    row = Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    status, out = body_of(put(fake_request, stale_tab_doc()))       # sends no pageRev
    assert status == 409 and out["staleTemplate"] is True and out["conflict"] is True
    assert out["detail"] == "This schedule was updated. Reload to keep saving."
    assert out["pageRev"] == PUBLISHED.isoformat()
    # No state to merge: a page from before the guard stops and offers a reload.
    assert "state" not in out
    assert row.state == live_state() and row.at == SAVED and row.history == []
    assert not fake_db.seen("UPDATE ll_app.install_schedule_state")


def test_a_page_from_an_earlier_publish_is_refused(fake_db, fake_request):
    row = Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    status, out = body_of(put(fake_request, stale_tab_doc(), pageRev=EARLIER.isoformat()))
    assert status == 409 and out["staleTemplate"] is True
    assert row.state == live_state()


def test_the_current_publish_saves(fake_db, fake_request):
    row = Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    st = live_state()
    st["approved"] = ["7"]
    out = put(fake_request, st, pageRev=PUBLISHED.isoformat())
    assert out["ok"] and row.state["approved"] == ["7"] and len(row.history) == 1


def test_a_page_with_no_stamp_is_not_checked(fake_db, fake_request):
    # A local preview is served from a file, so it has no stamp to send.
    Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    assert put(fake_request, live_state(), pageRev=None)["ok"]


def test_a_garbled_stamp_is_refused(fake_db, fake_request):
    Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    assert put(fake_request, live_state(), pageRev="yesterday").status_code == 409


def test_not_enforced_until_the_guarded_page_is_published(fake_db, fake_request):
    # The backend deploys before the page is republished: every open tab is
    # then from before the guard, and they must keep saving.
    Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db, html=OLD_PAGE)
    assert put(fake_request, stale_tab_doc())["ok"]


def test_no_published_page_or_season_is_not_checked(fake_db, fake_request):
    Row(fake_db, live_state(), SAVED, "user-b")
    first = put(fake_request, live_state())                         # no page row
    assert first["ok"]
    published(fake_db)
    st = live_state()
    del st["season"]
    assert put(fake_request, st, baseUpdatedAt=first["updatedAt"])["ok"]


def test_the_check_is_cached_per_publish(fake_db, fake_request):
    Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    base = SAVED.isoformat()
    for _ in range(3):
        base = put(fake_request, live_state(), pageRev=PUBLISHED.isoformat(), baseUpdatedAt=base)["updatedAt"]
    assert len(fake_db.calls("SELECT strpos(html")) == 1


def test_get_state_says_which_publish_is_current(fake_db):
    Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db)
    assert run(sched.get_state("build-1", "2026", role=ADMIN))["pageRev"] == PUBLISHED.isoformat()


def test_get_state_says_nothing_before_the_guarded_page(fake_db):
    Row(fake_db, live_state(), SAVED, "user-b")
    published(fake_db, html=OLD_PAGE)
    assert "pageRev" not in run(sched.get_state("build-1", "2026", role=ADMIN))


def test_page_is_served_with_its_stamp(fake_db):
    fake_db.on_fetchval("SELECT season FROM ll_app.install_schedule_pages", "2026")
    fake_db.on_fetchrow("SELECT html, updated_at FROM ll_app.install_schedule_pages",
                        {"html": NEW_PAGE, "updated_at": PUBLISHED})
    html = run(sched.get_install_schedule_page(file="index.html"))
    assert html.startswith(f'<html><head><meta name="tbdg-page-rev" content="{PUBLISHED.isoformat()}">')
    assert html.endswith(NEW_PAGE[len("<html><head>"):])


def test_stamp_without_a_head_or_a_time():
    assert sched.stamp_page_rev("<p>x</p>", PUBLISHED).endswith("<p>x</p>")
    assert sched.stamp_page_rev("<html><head></head>", None) == "<html><head></head>"


def test_stamp_round_trips_through_the_check():
    meta = sched.stamp_page_rev("<head>", PUBLISHED)
    sent = json.loads(json.dumps(meta.split('content="')[1].split('"')[0]))
    assert not sched.is_stale_page({"pageRev": sent}, (PUBLISHED, True))
