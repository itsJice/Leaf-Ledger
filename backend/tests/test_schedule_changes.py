"""The Install Schedule "Changes" list (Comment #19).

Covers the diff from two saved states to readable lines (one test per kind of
change), the feed across history rows, paging and filters, follow / last
seen, who-saved-it names (never emails), and which roles may use it.
"""
import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.apis import schedule_changes as api
from app.libs import roles, schedule_board
from app.libs import schedule_changes as sc

from tests.conftest import FakeRequest

# ─── A small board ───────────────────────────────────────────────────────────

D1 = "2026-11-07|Crew 1|0"   # Sat 11/7
D2 = "2026-11-13|Crew 1|0"   # Fri 11/13
D2b = "2026-11-13|Crew 2|0"
D3 = "2026-12-02|Crew 3|0"   # Wed 12/2 (the only crew that day, so "Crew 1")
D4 = "2026-11-02|Crew 2|0"   # Mon 11/2
D4a = "2026-11-02|Crew 1|0"

PAYLOAD = {
    "clients": {
        "1": {"name": "Jinks, Amy"},
        "2": {"name": "Scheib, Natalia"},
        "3": {"name": "M Crowd Monkey Bar on 9"},
        "4": {"name": "Hanover Corporate"},
        "5": {"name": "Lewis, Holly"},
    },
    "days": [
        {"id": D1, "date": "2026-11-07", "crew": "Crew 1", "stops": [1]},
        {"id": D2, "date": "2026-11-13", "crew": "Crew 1", "stops": [4, 5]},
        {"id": D2b, "date": "2026-11-13", "crew": "Crew 2", "stops": []},
        {"id": D4a, "date": "2026-11-02", "crew": "Crew 1", "stops": [3]},
        {"id": D4, "date": "2026-11-02", "crew": "Crew 2", "stops": []},
        {"id": D3, "date": "2026-12-02", "crew": "Crew 3", "stops": []},
    ],
    "spec": {"version": "v1"},
}
ROSTER = [
    {"id": "p1", "first": "Alberto", "last": "Ortiz", "title": "Lead", "email": "alberto@example.com"},
    {"id": "p2", "first": "Lesly", "last": "Ruiz", "email": "lesly@example.com"},
    {"id": "p3", "name": "Office Person", "email": "office@example.com"},
]
BASE = {
    "placement": {"1": [D1], "3": [D4a], "4": [D2], "5": [D2]},
    "roster": ROSTER,
    "staffing": {},
    "approved": [], "confirmed": [], "hold": [], "notInstalling": [],
    "stopPin": {}, "newDates": [], "trainingDays": [], "manualOrder": {},
}


def ctx() -> sc.Context:
    board = schedule_board.resolve("2026", PAYLOAD, BASE)
    return api.context_for(board)


def after(**changes) -> dict:
    s = copy.deepcopy(BASE)
    s.update(changes)
    return s


def texts(prev, cur):
    return [e["text"] for e in sc.diff(prev, cur, ctx())]


def kinds(prev, cur):
    return [(e["kind"], e["type"]) for e in sc.diff(prev, cur, ctx())]


# ─── Diff: one test per kind ─────────────────────────────────────────────────

def test_no_change_no_events():
    assert sc.diff(BASE, copy.deepcopy(BASE), ctx()) == []


def test_move_to_another_date_same_crew_number():
    cur = after(placement={**BASE["placement"], "1": [D2]})
    assert texts(BASE, cur) == ["Jinks, Amy moved Sat 11/7 → Fri 11/13 (Crew 1)"]
    assert kinds(BASE, cur) == [("moved", "moves")]
    ev = sc.diff(BASE, cur, ctx())[0]
    assert ev["clients"] == ["Jinks, Amy"]
    assert ev["dates"] == ["2026-11-07", "2026-11-13"]


def test_move_shows_both_crews_when_they_differ():
    cur = after(placement={**BASE["placement"], "1": [D2b]})
    assert texts(BASE, cur) == ["Jinks, Amy moved Sat 11/7 (Crew 1) → Fri 11/13 (Crew 2)"]


def test_several_stops_moving_together_read_as_one_line():
    cur = after(placement={**BASE["placement"], "4": [D3], "5": [D3]})
    assert texts(BASE, cur) == [
        "Moved 2 stops Fri 11/13 → Wed 12/2 (Crew 1): Hanover Corporate; Lewis, Holly"
    ]


def test_crew_switch_on_the_same_date():
    cur = after(placement={**BASE["placement"], "4": [D2b]})
    assert texts(BASE, cur) == ["Hanover Corporate switched crews on Fri 11/13: Crew 1 → Crew 2"]
    assert kinds(BASE, cur) == [("crew", "moves")]


def test_crew_renumbering_alone_is_not_news():
    # Same card, stored under another crew name; nothing else on that date,
    # so it is still "Crew 1" -- staff saw no change.
    payload = copy.deepcopy(PAYLOAD)
    payload["days"] = [d for d in payload["days"] if not d["id"].startswith("2026-11-07")]
    c = api.context_for(schedule_board.resolve("2026", payload, BASE))
    cur = after(placement={**BASE["placement"], "1": ["2026-11-07|Crew 3|0"]})
    assert sc.diff(BASE, cur, c) == []


def test_added_and_removed():
    cur = after(placement={**BASE["placement"], "2": [D3]})
    assert texts(BASE, cur) == ["Added Scheib, Natalia to Wed 12/2, Crew 1"]
    assert kinds(BASE, cur)[0] == ("added", "adds")
    gone = {k: v for k, v in BASE["placement"].items() if k != "5"}
    assert texts(BASE, after(placement=gone)) == ["Removed Lewis, Holly from Fri 11/13, Crew 1"]


def test_new_client_added_in_the_tool_is_named():
    cur = after(placement={**BASE["placement"], "900001": [D3]},
                newClients=[{"row": 900001, "name": "Crane Solutions"}])
    feed = sc.build_feed(
        [{"id": 1, "state": BASE, "updated_by": "x", "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc)},
         {"id": 2, "state": cur, "updated_by": "x", "created_at": datetime(2026, 10, 1, 1, tzinfo=timezone.utc)}],
        ctx(), {})
    assert feed[0]["text"] == "Added Crane Solutions to Wed 12/2, Crew 1"


def test_hold_and_off_hold():
    cur = after(hold=[3])
    assert texts(BASE, cur) == ["M Crowd Monkey Bar on 9 put on hold (Mon 11/2, Crew 1)"]
    assert kinds(BASE, cur) == [("hold", "holds")]
    assert texts(cur, BASE) == ["M Crowd Monkey Bar on 9 taken off hold (Mon 11/2, Crew 1)"]


def test_not_installing_replaces_the_removal_line():
    gone = {k: v for k, v in BASE["placement"].items() if k != "4"}
    cur = after(placement=gone, notInstalling=[4])
    assert texts(BASE, cur) == ["Not installing: Hanover Corporate (was Fri 11/13, Crew 1)"]
    assert kinds(BASE, cur) == [("not_installing", "holds")]
    assert texts(cur, BASE) == ["Back on the schedule: Hanover Corporate, Fri 11/13, Crew 1"]


def test_approval_added_and_removed():
    cur = after(approved=[D4a])
    assert texts(BASE, cur) == ["Crew 1 approved for Mon 11/2"]
    assert kinds(BASE, cur) == [("approved", "approvals")]
    assert texts(cur, BASE) == ["Crew 1 approval removed for Mon 11/2"]


def test_approval_cleared_by_a_move_is_not_a_second_line():
    prev = after(approved=[D2])
    cur = after(placement={**BASE["placement"], "5": [D1]}, approved=[])
    assert texts(prev, cur) == ["Lewis, Holly moved Fri 11/13 → Sat 11/7 (Crew 1)"]


def test_date_confirmed_with_client():
    cur = after(confirmed=[1])
    assert texts(BASE, cur) == ["Date confirmed with client: Jinks, Amy on Sat 11/7, Crew 1"]
    assert texts(cur, BASE) == ["Date no longer confirmed: Jinks, Amy on Sat 11/7, Crew 1"]


def test_position_locks():
    cur = after(stopPin={"4": "first"})
    assert texts(BASE, cur) == ["Locked First: Hanover Corporate"]
    assert kinds(BASE, cur) == [("lock", "locks")]
    assert texts(cur, after(stopPin={"4": "last"})) == ["Locked Last: Hanover Corporate (was First)"]
    assert texts(cur, BASE) == ["Position unlocked: Hanover Corporate (was First)"]


def test_staffing_add_and_remove():
    cur = after(staffing={D4a: ["p1"]})
    assert texts(BASE, cur) == ["Alberto Ortiz added to Mon 11/2 (Crew 1)"]
    assert kinds(BASE, cur) == [("staff_add", "staffing")]
    assert texts(cur, BASE) == ["Alberto Ortiz taken off Mon 11/2 (Crew 1)"]


def test_staffing_collapses_many_days_and_many_people():
    days = [D1, D2, D2b, D4a]
    many_days = after(staffing={d: ["p1"] for d in days})
    assert texts(BASE, many_days) == ["Alberto Ortiz added to 4 crew days (Mon 11/2 to Fri 11/13)"]
    roster = ROSTER + [{"id": f"x{i}", "name": f"Helper {i}"} for i in range(4)]
    crowd = after(roster=roster, staffing={D4a: [f"x{i}" for i in range(4)]})
    c = api.context_for(schedule_board.resolve("2026", PAYLOAD, after(roster=roster)))
    assert [e["text"] for e in sc.diff(after(roster=roster), crowd, c)] == [
        "4 people added to Mon 11/2 (Crew 1): Helper 0, Helper 1, Helper 2, Helper 3"
    ]


def test_dates_training_days_and_crews():
    cur = after(newDates=["2026-12-12"], trainingDays=["2026-10-21"])
    assert texts(BASE, cur) == ["New date added: Sat 12/12", "Training day set: Wed 10/21"]
    assert {t for _, t in kinds(BASE, cur)} == {"dates"}
    takedown = [(datetime(2026, 12, 26) + timedelta(days=i)).date().isoformat() for i in range(5)]
    assert texts(BASE, after(newDates=takedown)) == ["5 new dates added (Sat 12/26 to Wed 12/30)"]
    new_crew = after(placement={**BASE["placement"], "2": ["2026-11-07|Crew 2|1"]})
    assert texts(BASE, new_crew) == [
        "Added Scheib, Natalia to Sat 11/7, Crew 2",
        "New crew on Sat 11/7 (Crew 2)",
    ]


def test_stop_order_and_arrival_times():
    prev = after(manualOrder={D2: [4, 5]},
                 timeline={D2: {"stops": [{"row": 4, "start": 510}, {"row": 5, "start": 650}]}})
    cur = after(manualOrder={D2: [5, 4]},
                timeline={D2: {"stops": [{"row": 5, "start": 510}, {"row": 4, "start": 655}]}})
    assert texts(prev, cur) == [
        "Stop order changed on Fri 11/13 (Crew 1): 1. Lewis, Holly 2. Hanover Corporate",
    ]
    # Times on a day whose order didn't change, past the 30-minute threshold.
    t0 = after(timeline={D2: {"stops": [{"row": 4, "start": 510}, {"row": 5, "start": 650}]}})
    t1 = after(timeline={D2: {"stops": [{"row": 4, "start": 520}, {"row": 5, "start": 700}]}})
    assert texts(t0, t1) == ["Arrival times changed on Fri 11/13 (Crew 1): Lewis, Holly 10:50 AM → 11:40 AM"]


def test_noise_is_left_out():
    roster = copy.deepcopy(ROSTER)
    roster[0]["rating"] = 5
    roster[0]["dates"] = ["2026-11-02"]
    cur = after(roster=roster, comments={"1": [{"text": "hi"}]}, moves=[{"row": 1}], savedAt=123,
                view="cal")
    assert sc.diff(BASE, cur, ctx()) == []


def test_bulk_update_is_one_line():
    payload_clients = {str(i): {"name": f"Client {i:02d}"} for i in range(100, 160)}
    payload = {**PAYLOAD, "clients": {**PAYLOAD["clients"], **payload_clients}}
    c = api.context_for(schedule_board.resolve("2026", payload, BASE))
    prev = after(placement={**BASE["placement"], **{str(i): [D1] for i in range(100, 160)}})
    cur = after(placement={**BASE["placement"], **{str(i): [D3] if i % 2 else [D4] for i in range(100, 160)}})
    out = sc.diff(prev, cur, c)
    assert [e["kind"] for e in out] == ["moved", "moved"]  # grouped by from/to: 2 lines
    cur2 = after(placement={**BASE["placement"], **{str(i): [f"2026-12-{(i % 20) + 1:02d}|Crew 1|0"] for i in range(100, 160)}})
    out2 = sc.diff(prev, cur2, c)
    assert out2[0]["kind"] == "bulk" and out2[0]["text"].startswith("Large update: 60 stops changed")


# ─── Formatting and names ────────────────────────────────────────────────────

def test_twelve_hour_central_time():
    at = datetime(2026, 10, 12, 21, 2, tzinfo=timezone.utc)   # 4:02 PM CDT
    assert sc.fmt_time_ct(at) == "4:02 PM"
    assert sc.fmt_clock(1380) == "11:00 PM" and sc.fmt_clock(1500) == "1:00 AM"
    assert sc.fmt_day("2026-11-07") == "Sat 11/7"


@pytest.mark.parametrize("writer,name", [
    ("claude-1099-import", "Claude (import)"),
    ("claude:takedown", "Claude"),
    ("claude:scheib-to-dec2", "Claude"),
    ("claude-roster-merge", "Claude"),
    ("claude (requested by Justice): Erica+Reyna Designer", "Claude (for Justice)"),
    ("roster-import", "Import"),
    ("restore-from-2b1ff23c96ad", "Restore"),
    ("roster-phone-swap", "Script"),
    ("local-dev-user", "Local test"),
    ("b1923bde-c399-4371-a424-eca8173ccd26", None),
])
def test_script_writer_names(writer, name):
    assert sc.script_writer_name(writer) == name


def test_login_names_never_show_an_email():
    assert sc.login_display_name("justice@example.com", None, "Justice Wenz") == "Justice Wenz"
    assert sc.login_display_name("amy.jones@example.com", None, None) == "Amy Jones"
    assert sc.login_display_name("x@example.com", "Pat Office", None) == "Pat Office"
    assert "@" not in sc.login_display_name("someone@example.com", None, None)


# ─── Feed, paging, filters, unseen ───────────────────────────────────────────

T0 = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)


def history():
    s1 = after(placement={**BASE["placement"], "1": [D2]})
    s2 = after(placement=s1["placement"], hold=[3])
    s3 = after(placement=s1["placement"], hold=[3], staffing={D4a: ["p1"]})
    return [
        {"id": 10, "state": BASE, "updated_by": "uid-a", "created_at": T0},
        {"id": 11, "state": s1, "updated_by": "uid-a", "created_at": T0 + timedelta(minutes=5)},
        {"id": 12, "state": s2, "updated_by": "claude-1099-import", "created_at": T0 + timedelta(days=1)},
        {"id": 13, "state": s3, "updated_by": "uid-b", "created_at": T0 + timedelta(days=1, minutes=1)},
    ]


def test_feed_is_newest_first_with_who_and_when():
    feed = sc.build_feed(history(), ctx(), {"uid-a": "Justice Wenz", "uid-b": "Pat"})
    assert [e["text"] for e in feed] == [
        "Alberto Ortiz added to Mon 11/2 (Crew 1)",
        "M Crowd Monkey Bar on 9 put on hold (Mon 11/2, Crew 1)",
        "Jinks, Amy moved Sat 11/7 → Fri 11/13 (Crew 1)",
    ]
    assert [e["by"] for e in feed] == ["Pat", "Claude (import)", "Justice Wenz"]
    assert feed[-1]["day"] == "2026-09-01" and feed[-1]["time"] == "9:05 AM"
    assert feed[0]["id"] == "13-0"


def test_paging_with_a_cursor():
    feed = sc.build_feed(history(), ctx(), {})
    first, nxt = sc.page(feed, limit=2)
    assert [e["id"] for e in first] == ["13-0", "12-0"] and nxt == "12-0"
    second, nxt2 = sc.page(feed, limit=2, before=nxt)
    assert [e["id"] for e in second] == ["11-0"] and nxt2 is None
    assert sc.page(feed, limit=2, before="nope")[0] == []


def test_filters():
    feed = sc.build_feed(history(), ctx(), {})
    assert [e["kind"] for e in feed if sc.matches(e, q="jinks")] == ["moved"]
    assert [e["kind"] for e in feed if sc.matches(e, q="alberto")] == ["staff_add"]
    assert [e["kind"] for e in feed if sc.matches(e, types={"holds", "staffing"})] == ["staff_add", "hold"]
    assert [e["kind"] for e in feed if sc.matches(e, start="2026-09-02")] == ["staff_add", "hold"]
    assert [e["kind"] for e in feed if sc.matches(e, end="2026-09-01")] == ["moved"]


def test_unseen_skips_your_own_changes():
    feed = sc.build_feed(history(), ctx(), {})
    seen = T0 + timedelta(hours=1)
    assert sc.unseen_count(feed, seen, None) == 2
    assert sc.unseen_count(feed, seen, "uid-b") == 1
    assert sc.unseen_count(feed, None, "uid-b") == 0


# ─── The API ─────────────────────────────────────────────────────────────────

class Follows:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def get(self, _sql, uid):
        return self.rows.get(uid)

    def follow(self, _sql, uid, following):
        row = self.rows.setdefault(uid, {"following": following, "last_seen_at": None})
        row["following"] = following
        if following and row["last_seen_at"] is None:
            row["last_seen_at"] = datetime.now(timezone.utc)
        return dict(row)

    def seen(self, _sql, uid, up_to):
        row = self.rows.setdefault(uid, {"following": False, "last_seen_at": None})
        row["last_seen_at"] = max(x for x in (row["last_seen_at"], up_to) if x)
        return dict(row)


@pytest.fixture
def wired(fake_db, monkeypatch):
    api.clear_cache()
    board = schedule_board.resolve("2026", PAYLOAD, BASE)

    async def fake_board(*_, **__):
        return board

    monkeypatch.setattr(schedule_board, "load_board", fake_board)
    rows = history()
    follows = Follows()
    fake_db.on_fetchval("SELECT max(id) FROM ll_app.install_schedule_history", 13)
    fake_db.on_fetch("FROM ll_app.install_schedule_history", [
        {**r, "state": json.dumps(r["state"])} for r in rows
    ])
    fake_db.on_fetch("FROM auth.users", [
        {"id": "uid-a", "email": "office@example.com", "full_name": None},
        {"id": "uid-b", "email": "pat.smith@example.com", "full_name": None},
    ])
    fake_db.on("SELECT following, last_seen_at FROM ll_app.schedule_change_follows", follows.get, method="fetchrow")
    fake_db.on("ON CONFLICT (user_id) DO UPDATE SET following", follows.follow, method="fetchrow")
    fake_db.on("GREATEST(ll_app.schedule_change_follows.last_seen_at", follows.seen, method="fetchrow")
    monkeypatch.setattr(sc, "is_login_id", lambda w: str(w).startswith("uid-"))
    return fake_db, follows


def call(coro):
    return asyncio.run(coro)


def test_api_lists_changes_with_names_not_emails(wired):
    out = call(api.list_changes(FakeRequest("uid-z"), limit=50, before=None, q="", start=None, end=None, type=None))
    assert out["total"] == 3
    assert [e["by"] for e in out["events"]] == ["Pat Smith", "Claude (import)", "Office Person"]
    blob = json.dumps(out)
    assert "@" not in blob and "uid-a" not in blob and "writer" not in out["events"][0]
    assert out["following"] is False and out["unseen"] == 0
    assert not any(e["isNew"] for e in out["events"])


def test_api_paging_and_filters(wired):
    page1 = call(api.list_changes(FakeRequest("uid-z"), limit=2, before=None, q="", start=None, end=None, type=None))
    assert len(page1["events"]) == 2 and page1["next"] == "12-0"
    page2 = call(api.list_changes(FakeRequest("uid-z"), limit=2, before=page1["next"], q="", start=None, end=None, type=None))
    assert [e["id"] for e in page2["events"]] == ["11-0"] and page2["next"] is None
    holds = call(api.list_changes(FakeRequest("uid-z"), limit=50, before=None, q="", start=None, end=None, type="holds"))
    assert [e["kind"] for e in holds["events"]] == ["hold"]
    with pytest.raises(Exception):
        call(api.list_changes(FakeRequest("uid-z"), limit=50, before=None, q="", start=None, end=None, type="ratings"))
    with pytest.raises(Exception):
        call(api.list_changes(FakeRequest("uid-z"), limit=50, before=None, q="", start="11/2", end=None, type=None))


def test_api_follow_marks_new_and_mark_all_seen(wired):
    _db, follows = wired
    me = FakeRequest("uid-z")
    out = call(api.set_follow(api.FollowIn(following=True), me))
    assert out["following"] is True
    # Pretend they last looked an hour after the first change.
    follows.rows["uid-z"]["last_seen_at"] = T0 + timedelta(hours=1)
    feed = call(api.list_changes(me, limit=50, before=None, q="", start=None, end=None, type=None))
    assert [e["isNew"] for e in feed["events"]] == [True, True, False]
    assert feed["unseen"] == 2
    assert call(api.change_status(me))["unseen"] == 2
    # Mark all seen up to the newest change shown.
    call(api.mark_seen(api.SeenIn(upTo=datetime.fromisoformat(feed["newest"])), me))
    assert call(api.change_status(me))["unseen"] == 0
    after_seen = call(api.list_changes(me, limit=50, before=None, q="", start=None, end=None, type=None))
    assert not any(e["isNew"] for e in after_seen["events"])
    # last seen never moves backwards
    call(api.mark_seen(api.SeenIn(upTo=T0), me))
    assert follows.rows["uid-z"]["last_seen_at"] > T0 + timedelta(days=1)


def test_api_own_changes_are_never_new(wired):
    _db, follows = wired
    follows.rows["uid-b"] = {"following": True, "last_seen_at": T0 + timedelta(hours=1)}
    feed = call(api.list_changes(FakeRequest("uid-b"), limit=50, before=None, q="", start=None, end=None, type=None))
    assert [e["isNew"] for e in feed["events"]] == [False, True, False]
    assert feed["events"][0]["mine"] is True
    assert feed["unseen"] == 1


def test_api_not_following_has_no_badge(wired):
    _db, follows = wired
    follows.rows["uid-z"] = {"following": False, "last_seen_at": T0}
    assert call(api.change_status(FakeRequest("uid-z"))) == {
        "following": False, "unseen": 0, "lastSeenAt": T0.isoformat()}


# ─── Roles ───────────────────────────────────────────────────────────────────

def test_router_role_settings():
    assert api.MIN_ROLE == "staff" and api.VIEWER_READ is True


@pytest.mark.parametrize("role,method,path,ok", [
    ("staff", "GET", "/api/schedule-changes", True),
    ("staff", "POST", "/api/schedule-changes/seen", True),
    ("admin", "PUT", "/api/schedule-changes/follow", True),
    ("super_admin", "GET", "/api/schedule-changes/status", True),
    ("viewer", "GET", "/api/schedule-changes", True),
    ("viewer", "GET", "/api/schedule-changes/status", True),
    ("viewer", "POST", "/api/schedule-changes/seen", False),
    ("viewer", "PUT", "/api/schedule-changes/follow", False),
    ("production", "GET", "/api/schedule-changes", True),
    ("production", "GET", "/api/schedule-changes/status", True),
    ("production", "POST", "/api/schedule-changes/seen", True),
    ("production", "PUT", "/api/schedule-changes/follow", True),
    ("lead", "GET", "/api/schedule-changes", False),
    ("crew", "GET", "/api/schedule-changes", False),
    ("lead", "POST", "/api/schedule-changes/seen", False),
])
def test_who_may_use_it(role, method, path, ok):
    assert roles.allowed(role, api.MIN_ROLE, method, api.VIEWER_READ, path) is ok


def test_production_may_open_the_page():
    assert "/install-changes" in roles.PRODUCTION_PAGES
