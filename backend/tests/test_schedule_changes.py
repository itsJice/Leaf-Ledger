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
    # 60 stops (one line) plus the 20 new crews they landed on: one line in all.
    assert [e["kind"] for e in out2] == ["bulk"]
    assert out2[0]["text"] == "Large update: 80 changes at once (a restore or bulk edit)"


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
    store = Store([{**r, "version": "v1"} for r in history()])
    follows = Follows()
    fake_db.on("SELECT max(id) FROM ll_app.install_schedule_history", store.hist_max, method="fetchval")
    fake_db.on("SELECT max(id) FROM ll_app.install_schedule_history_archive", store.arch_max, method="fetchval")
    fake_db.on("FROM ll_app.install_schedule_history", store.history, method="fetch")
    fake_db.on("FROM ll_app.install_schedule_history_archive", store.archive, method="fetch")
    fake_db.on_fetch("FROM auth.users", [
        {"id": "uid-a", "email": "office@example.com", "full_name": None},
        {"id": "uid-b", "email": "pat.smith@example.com", "full_name": None},
    ])
    fake_db.on("SELECT following, last_seen_at FROM ll_app.schedule_change_follows", follows.get, method="fetchrow")
    fake_db.on("ON CONFLICT (user_id) DO UPDATE SET following", follows.follow, method="fetchrow")
    fake_db.on("GREATEST(ll_app.schedule_change_follows.last_seen_at", follows.seen, method="fetchrow")
    monkeypatch.setattr(sc, "is_login_id", lambda w: str(w).startswith("uid-"))
    wired_store["store"] = store
    return fake_db, follows


wired_store: dict = {}


class Store:
    """history + archive rows, answering the router's queries."""

    def __init__(self, hist, arch=()):
        self.hist, self.arch = list(hist), list(arch)

    def hist_max(self, _sql):
        return max((r["id"] for r in self.hist), default=0)

    def arch_max(self, _sql):
        return max((r["id"] for r in self.arch), default=0)

    def history(self, _sql, season, after_id):
        rows = [r for r in self.hist if r["id"] > after_id]
        return [{**r, "state": json.dumps(r["state"])} for r in sorted(rows, key=lambda r: (r["created_at"], r["id"]))]

    def archive(self, _sql, season):
        return [{**r, "state": json.dumps(r["state"])} for r in sorted(self.arch, key=lambda r: r["created_at"])]


def call(coro):
    return asyncio.run(coro)


def lc(req, role="staff", **kw):
    args = dict(limit=50, before=None, q="", start=None, end=None, type=None, tests=False, role=role)
    args.update(kw)
    return call(api.list_changes(req, **args))


def test_api_lists_changes_with_names_not_emails(wired):
    out = lc(FakeRequest("uid-z"))
    assert out["total"] == 3
    assert [e["by"] for e in out["events"]] == ["Pat Smith", "Claude (import)", "Office Person"]
    blob = json.dumps(out)
    assert "@" not in blob and "uid-a" not in blob and "writer" not in out["events"][0]
    assert out["following"] is False and out["unseen"] == 0
    assert not any(e["isNew"] for e in out["events"])


def test_api_paging_and_filters(wired):
    page1 = lc(FakeRequest("uid-z"), limit=2)
    assert len(page1["events"]) == 2 and page1["next"] == "h12-0"
    page2 = lc(FakeRequest("uid-z"), limit=2, before=page1["next"])
    assert [e["id"] for e in page2["events"]] == ["h11-0"] and page2["next"] is None
    holds = lc(FakeRequest("uid-z"), type="holds")
    assert [e["kind"] for e in holds["events"]] == ["hold"]
    with pytest.raises(Exception):
        lc(FakeRequest("uid-z"), type="ratings")
    with pytest.raises(Exception):
        lc(FakeRequest("uid-z"), start="11/2")


def test_api_follow_marks_new_and_mark_all_seen(wired):
    _db, follows = wired
    me = FakeRequest("uid-z")
    out = call(api.set_follow(api.FollowIn(following=True), me))
    assert out["following"] is True
    # Pretend they last looked an hour after the first change.
    follows.rows["uid-z"]["last_seen_at"] = T0 + timedelta(hours=1)
    feed = lc(me)
    assert [e["isNew"] for e in feed["events"]] == [True, True, False]
    assert feed["unseen"] == 2
    assert call(api.change_status(me))["unseen"] == 2
    # Mark all seen up to the newest change shown.
    call(api.mark_seen(api.SeenIn(upTo=datetime.fromisoformat(feed["newest"])), me))
    assert call(api.change_status(me))["unseen"] == 0
    after_seen = lc(me)
    assert not any(e["isNew"] for e in after_seen["events"])
    # last seen never moves backwards
    call(api.mark_seen(api.SeenIn(upTo=T0), me))
    assert follows.rows["uid-z"]["last_seen_at"] > T0 + timedelta(days=1)


def test_api_own_changes_are_never_new(wired):
    _db, follows = wired
    follows.rows["uid-b"] = {"following": True, "last_seen_at": T0 + timedelta(hours=1)}
    feed = lc(FakeRequest("uid-b"))
    assert [e["isNew"] for e in feed["events"]] == [False, True, False]
    assert feed["events"][0]["mine"] is True
    assert feed["unseen"] == 1


def test_api_not_following_has_no_badge(wired):
    _db, follows = wired
    follows.rows["uid-z"] = {"following": False, "last_seen_at": T0}
    assert call(api.change_status(FakeRequest("uid-z"))) == {
        "following": False, "unseen": 0, "lastSeenAt": T0.isoformat()}


def test_api_hides_test_saves_unless_a_super_admin_asks(wired):
    store = wired_store["store"]
    test_state = after(placement=history()[-1]["state"]["placement"], hold=[3], staffing={D4a: ["p1"]},
                       stopPin={"4": "first"})
    store.hist.append({"id": 14, "version": "v1", "state": test_state, "updated_by": "local-dev-user",
                       "created_at": T0 + timedelta(days=2)})
    assert [e["kind"] for e in lc(FakeRequest("uid-z"))["events"]][0] == "staff_add"
    assert lc(FakeRequest("uid-z"), tests=True)["events"][0]["kind"] == "staff_add"  # staff can't ask
    shown = lc(FakeRequest("uid-z"), role="super_admin", tests=True)
    assert shown["events"][0]["text"] == "Locked First: Hanover Corporate" and shown["events"][0]["test"] is True
    assert shown["canShowTests"] is True and lc(FakeRequest("uid-z"))["canShowTests"] is False
    _db, follows = wired
    follows.rows["uid-z"] = {"following": True, "last_seen_at": T0 + timedelta(days=1, minutes=30)}
    assert call(api.change_status(FakeRequest("uid-z")))["unseen"] == 0  # a test save is never NEW


def test_api_reads_new_saves_without_rebuilding(wired):
    store = wired_store["store"]
    assert lc(FakeRequest("uid-z"))["total"] == 3
    s4 = after(placement=history()[-1]["state"]["placement"], hold=[3], staffing={D4a: ["p1"]}, approved=[D4a])
    store.hist.append({"id": 15, "version": "v1", "state": s4, "updated_by": "uid-a",
                       "created_at": T0 + timedelta(days=3)})
    out = lc(FakeRequest("uid-z"))
    assert out["total"] == 4 and out["events"][0]["text"] == "Crew 1 approved for Mon 11/2"
    assert out["events"][0]["id"] == "h15-0" and out["events"][0]["by"] == "Office Person"


def test_api_merges_the_backfill_archive(wired):
    store = wired_store["store"]
    plan = {"placement": {"1": [D1], "4": [D2]}, "planClients": {"1": "Jinks, Amy", "4": "Hanover Corporate"},
            "planDays": [{"id": D1, "date": "2026-11-07", "crew": "Crew 1", "stops": [1]}]}
    store.arch += [
        {"id": 1, "kind": "plan", "version": "old-plan", "state": plan, "updated_by": "schedule-build",
         "created_at": T0 - timedelta(days=30), "source": "git-plan"},
        # A backfilled save that duplicates a history row is dropped.
        {"id": 2, "kind": "save", "version": "v1", "state": BASE, "updated_by": "uid-a",
         "created_at": T0, "source": "db-dump"},
    ]
    out = lc(FakeRequest("uid-z"))
    texts_ = [e["text"] for e in out["events"]]
    assert texts_[-2:] == ["Schedule rebuilt: 4 clients on 3 crew days", "First plan built: 2 clients on 2 crew days"]
    assert out["events"][-1]["by"] == "Schedule build (from backup)" and out["events"][-1]["fromBackup"] is True
    assert out["total"] == 5


# ─── Builds, backups, restores ───────────────────────────────────────────────

def snap(key, version, state, at, by="uid-a", **kw):
    return {"key": key, "version": version, "state": state, "updated_by": by, "created_at": at, **kw}


def test_a_new_build_is_one_line_not_a_flood_of_moves():
    # v2 re-planned: every row sits somewhere else.
    replanned = after(placement={"1": [D3], "3": [D2], "4": [D1], "5": [D4a]})
    rows = [snap("h1", "v1", BASE, T0), snap("h2", "v2", replanned, T0 + timedelta(hours=1)),
            snap("h3", "v2", after(placement=replanned["placement"], hold=[3]), T0 + timedelta(hours=2))]
    feed = sc.build_feed(rows, ctx(), {"uid-a": "Pat"}, current_version="v2")
    assert [e["text"] for e in feed] == [
        "M Crowd Monkey Bar on 9 put on hold (Fri 11/13, Crew 1)",
        "Schedule rebuilt: 4 clients on 4 crew days",
    ]
    assert feed[1]["by"] == "Schedule build"


def test_a_build_that_kept_the_placement_is_diffed_normally():
    rows = [snap("h1", "v1", BASE, T0), snap("h2", "v2", after(confirmed=[1]), T0 + timedelta(hours=1))]
    feed = sc.build_feed(rows, ctx(), {"uid-a": "Pat"}, current_version="v2")
    assert [e["text"] for e in feed] == ["Date confirmed with client: Jinks, Amy on Sat 11/7, Crew 1"]


def test_plans_collapse_per_day_and_old_builds_are_named_from_rows():
    def plan(n):
        return {"placement": {str(r): [D1] for r in range(1, n + 1)}, "planClients": {"2": "Scheib, Natalia"},
                "planDays": []}
    day = datetime(2026, 7, 30, 21, 0, tzinfo=timezone.utc)
    rows = [snap("a1", "p1", plan(2), day, kind="plan", from_backup=True),
            snap("a2", "p2", plan(3), day + timedelta(hours=1), kind="plan", from_backup=True),
            snap("a3", "p3", plan(4), day + timedelta(hours=2), kind="plan", from_backup=True),
            snap("a4", "p4", plan(5), day + timedelta(days=1), kind="plan", from_backup=True)]
    feed = sc.build_feed(rows, ctx(), {})
    assert [e["text"] for e in feed] == [
        "Schedule re-planned: 5 clients on 1 crew days",
        "Schedule re-planned 2 times; latest: 4 clients on 1 crew days",
        "First plan built: 2 clients on 1 crew days",
    ]


def test_a_restore_is_one_line():
    moved = after(placement={**BASE["placement"], "1": [D2], "3": [D2b]}, hold=[4], confirmed=[5])
    rows = [snap("h1", "v1", BASE, T0), snap("h2", "v1", moved, T0 + timedelta(hours=1), by="restore-from-abc")]
    feed = sc.build_feed(rows, ctx(), {})
    assert [e["text"] for e in feed] == ["Restored an earlier version of the schedule (4 changes)"]
    assert feed[0]["by"] == "Restore"


def test_a_huge_save_is_one_line():
    roster = ROSTER + [{"id": f"x{i}", "name": f"Helper {i}"} for i in range(14)]
    prev = after(roster=roster)
    cur = after(roster=roster, staffing={D1: ["x0"], D2: ["x1"], D2b: ["x2"], D3: ["x3"], D4: ["x4"], D4a: ["x5"]},
                newDates=["2026-12-12"], trainingDays=["2026-10-21", "2026-10-23"], stopPin={"1": "first", "4": "last"},
                confirmed=[1, 4, 5], hold=[3])
    c = api.context_for(schedule_board.resolve("2026", PAYLOAD, prev))
    out = sc.diff(prev, cur, c)
    assert [e["kind"] for e in out] == ["bulk"] and out[0]["text"].startswith("Large update: 15 changes")


def test_unknown_writer_from_a_backup():
    rows = [snap("h1", "v1", BASE, T0), snap("a1", "v1", after(hold=[3]), T0 + timedelta(hours=1), by=None,
                                            from_backup=True)]
    assert sc.build_feed(rows, ctx(), {})[0]["by"] == "Unknown (from backup)"


def test_merge_snapshots_orders_and_dedupes():
    h = [{"id": 5, "version": "v1", "state": {}, "updated_by": "u", "created_at": T0}]
    a = [{"id": 1, "kind": "save", "version": "v1", "state": {}, "updated_by": "u", "created_at": T0},
         {"id": 2, "kind": "save", "version": "v1", "state": {}, "updated_by": "u", "created_at": T0 - timedelta(days=1)},
         {"id": 3, "kind": "plan", "version": "p", "state": {}, "updated_by": "b", "created_at": T0 - timedelta(days=9)}]
    assert [r["key"] for r in api.merge_snapshots(h, a)] == ["a3", "a2", "h5"]


# ─── The backfill importer ───────────────────────────────────────────────────

def _importer():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_schedule_history.py"
    spec = importlib.util.spec_from_file_location("backfill_schedule_history", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_importer_keeps_only_whats_missing():
    bf = _importer()
    s1, s2 = {"placement": {"1": ["d"]}}, {"placement": {"1": ["e"]}}
    live_at = {("v1", T0)}
    live_hash = {("v1", bf.canon(s1))}
    cands = [
        bf.candidate(kind="save", version="v1", state=s1, created_at=T0 + timedelta(hours=1),
                     updated_by=None, source="json-backup", source_ref="x.json"),  # same state as live
        bf.candidate(kind="save", version="v1", state=s2, created_at=T0, updated_by="u",
                     source="db-dump", source_ref="d#1"),  # same moment as live
        bf.candidate(kind="save", version="v1", state=s2, created_at=T0 - timedelta(days=1), updated_by="u",
                     source="db-dump", source_ref="d#2"),  # missing: kept
        bf.candidate(kind="save", version="v1", state=s2, created_at=T0 - timedelta(days=1), updated_by=None,
                     source="json-backup", source_ref="y.json"),  # same again from another source
        bf.candidate(kind="plan", version="p", state={"placement": {"1": ["a"]}}, created_at=T0 - timedelta(days=40),
                     updated_by="schedule-build", source="git-plan", source_ref="abc"),
    ]
    keep = bf.choose(cands, live_at, live_hash)
    assert [(k["source"], k["source_ref"]) for k in keep] == [("git-plan", "abc"), ("db-dump", "d#2")]
    assert len({k["dedupe_key"] for k in keep}) == 2


def test_importer_helpers():
    bf = _importer()
    assert bf.copy_field("\\N") is None
    assert bf.copy_field('{"a": "x\\\\ty"}') == '{"a": "x\\ty"}'
    st = bf.plan_state({"clients": {"1": {"name": "A"}}, "days": [{"id": "d1", "date": "2026-11-02", "crew": "Crew 1",
                                                                  "stops": [1], "geom": [[1, 2]]}]})
    assert st == {"placement": {"1": ["d1"]}, "planClients": {"1": "A"},
                  "planDays": [{"id": "d1", "date": "2026-11-02", "crew": "Crew 1", "stops": [1]}]}
    at = bf.stamp_from_name("roster-replies-20261010-141844.json")
    assert sc.fmt_time_ct(at) == "2:18 PM" and at.date().isoformat() == "2026-10-10"
    assert bf.as_dt(1791824532162).year == 2026


def test_saves_are_never_trimmed():
    import inspect

    from app.apis import install_schedule
    assert "DELETE FROM ll_app.install_schedule_history" not in inspect.getsource(install_schedule)


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
