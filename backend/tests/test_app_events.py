"""The error log (app.apis.app_events), the server's own 500/slow logging
(app.libs.request_log), and the scrubbing they share (app.libs.redact)."""

import asyncio
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.apis import app_events
from app.libs import redact, request_log, roles


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fresh_limits():
    app_events.reset_limits()
    yield
    app_events.reset_limits()


@pytest.fixture
def as_role(monkeypatch):
    def set_role(role):
        async def fixed(email, roster_lookup=None):
            return role
        monkeypatch.setattr(roles, "resolve_role", fixed)
    set_role("staff")
    return set_role


JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVl"


# ─── redact ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("/clients?client=Allums,Mary", "/clients"),
    ("/install-schedule#token=abc", "/install-schedule"),
    ("/set-password#access_token=xyz&type=recovery", "/set-password"),
    ("/api/share/AbCdEf123/view", "/api/share/[hidden]/view"),
    (None, ""),
])
def test_path_only_drops_query_hash_and_share_tokens(raw, expected):
    assert redact.path_only(raw) == expected


def test_scrub_masks_tokens_secrets_and_urls():
    text = (f"Bearer {JWT} failed; token={JWT}; password: hunter2 "
            "GET https://x.onrender.com/api/install-calendar/feed.ics?token=s3cret ok "
            "on /clients?client=Allums")
    out = redact.scrub(text)
    assert JWT not in out and "hunter2" not in out and "s3cret" not in out and "Allums" not in out
    assert "/api/install-calendar/feed.ics" in out and "/clients" in out
    assert "Bearer [hidden]" in out


def test_scrub_tree_drops_secret_keys_and_bodies():
    out = redact.scrub_tree({"status": 401, "Authorization": "Bearer x", "body": {"price": 5},
                             "nested": [{"msg": f"tok {JWT}"}]})
    assert out == {"status": 401, "Authorization": "[hidden]", "body": "[hidden]",
                   "nested": [{"msg": "tok [hidden]"}]}


def test_scrub_never_raises():
    class Bad:
        def __str__(self):
            raise RuntimeError("boom")
    assert redact.scrub(Bad()) == ""
    assert redact.path_only(Bad()) == ""


# ─── who may report and read ────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["crew", "viewer", "lead", "staff", "admin", "super_admin"])
def test_every_ladder_role_and_viewer_may_report(role):
    assert roles.allowed(role, app_events.MIN_ROLE, "POST", False, "/api/app-events")


def test_production_may_report_but_not_read():
    assert roles.allowed("production", app_events.MIN_ROLE, "POST", False, "/api/app-events")
    assert not roles.allowed("production", app_events.MIN_ROLE, "GET", False, "/api/app-events")
    assert not roles.allowed("production", app_events.MIN_ROLE, "GET", False, "/api/app-events/summary")


@pytest.mark.parametrize("role", ["crew", "viewer", "production", "lead", "staff", "admin"])
def test_only_super_admin_reads(fake_db, fake_user, as_role, role):
    as_role(role)
    for call in (app_events.list_events(fake_user, 50, None, None, None, None, None),
                 app_events.summarize_events(fake_user, 7)):
        with pytest.raises(HTTPException) as exc:
            run(call)
        assert exc.value.status_code == 403
    assert not fake_db.seen("FROM ll_app.app_events")


# ─── reporting ──────────────────────────────────────────────────────────────

def test_report_scrubs_and_saves(fake_db, fake_request, fake_user, as_role):
    as_role("crew")
    req = fake_request()
    req.headers["user-agent"] = "Safari/iOS"
    body = app_events.EventsIn(events=[app_events.EventIn(
        kind="request_failed", source="schedule", page="/clients?client=Allums",
        message=f"PUT /api/install-schedule/state 401 with {JWT}",
        detail={"status": 401, "route": "/api/install-schedule/state", "Authorization": "Bearer x"},
        trail=[{"t": "2026-11-16T21:00:00Z", "type": "click", "label": "Save"}],
        occurred_at="2026-11-16T21:00:05Z",
    )])
    fake_db.on_fetchval("INSERT INTO ll_app.app_events", 77)
    out = run(app_events.report_events(body, req, fake_user))
    assert out == app_events.EventsOut(saved=1, dropped=0, ids=[77])
    (_, args), = fake_db.calls("INSERT INTO ll_app.app_events")
    occurred, kind, source, sub, name, role, page, message, detail, trail, ua = args
    assert (kind, source, sub, name, role, page, ua) == (
        "request_failed", "schedule", "user-1", "crew", "crew", "/clients", "Safari/iOS")
    assert occurred.isoformat() == "2026-11-16T21:00:05+00:00"
    assert JWT not in message and "[hidden]" in message
    assert json.loads(detail) == {"status": 401, "route": "/api/install-schedule/state",
                                  "Authorization": "[hidden]"}
    assert json.loads(trail)[0]["label"] == "Save"
    assert fake_db.ddl_runs == 1


def test_report_drops_unknown_kinds_and_server_kinds(fake_db, fake_request, fake_user, as_role):
    body = app_events.EventsIn(events=[app_events.EventIn(kind="server_error"),
                                       app_events.EventIn(kind="nonsense"),
                                       app_events.EventIn(kind="crash", message="x")])
    out = run(app_events.report_events(body, fake_request(), fake_user))
    assert out == app_events.EventsOut(saved=1, dropped=2)


def test_report_caps_batch_and_rate(fake_db, fake_request, fake_user, as_role, monkeypatch):
    monkeypatch.setattr(app_events, "RATE_LIMIT", 25)
    many = app_events.EventsIn(events=[app_events.EventIn(kind="error", message=str(i)) for i in range(30)])
    first = run(app_events.report_events(many, fake_request(), fake_user))
    assert first == app_events.EventsOut(saved=20, dropped=10)
    second = run(app_events.report_events(many, fake_request(), fake_user))
    assert second == app_events.EventsOut(saved=5, dropped=25)
    third = run(app_events.report_events(many, fake_request(), fake_user))
    assert third == app_events.EventsOut(saved=0, dropped=30)
    assert len(fake_db.calls("INSERT INTO ll_app.app_events")) == 25


def test_report_runs_cleanup_at_most_once_per_window(fake_db, fake_request, fake_user, as_role):
    body = app_events.EventsIn(events=[app_events.EventIn(kind="error")])
    run(app_events.report_events(body, fake_request(), fake_user))
    run(app_events.report_events(body, fake_request(), fake_user))
    deletes = fake_db.calls("DELETE FROM ll_app.app_events")
    assert len(deletes) == 1 and "90 days" in deletes[0][0]


def test_big_detail_and_trail_are_trimmed():
    detail = app_events.clean_detail({"status": 500, "stack": "at fn (a.js:1) " * 2_000, "big": "y " * 3_000})
    assert detail["status"] == 500 and len(detail["stack"]) == 3000 and detail["trimmed"]
    assert app_events.redact.json_size(detail) < app_events.MAX_DETAIL_BYTES
    trail = app_events.clean_trail([{"n": i, "pad": "z" * 900} for i in range(40)])
    assert trail[-1]["n"] == 39 and app_events.redact.json_size(trail) <= app_events.MAX_TRAIL_BYTES


def test_server_event_swallows_db_failure(monkeypatch):
    async def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(app_events, "get_conn", broken)
    run(app_events.record_server_event(kind="server_error", page="/api/x", message="m", detail={}))


def test_server_event_ignores_client_kinds(fake_db):
    run(app_events.record_server_event(kind="crash", page="/x", message="m", detail={}))
    assert not fake_db.seen("INSERT INTO ll_app.app_events")


# ─── reading ────────────────────────────────────────────────────────────────

def _row(**over):
    from datetime import datetime, timezone
    row = {"id": 9, "created_at": datetime(2026, 11, 16, 21, tzinfo=timezone.utc), "occurred_at": None,
           "kind": "crash", "source": "app", "user_name": "nicole", "role": "staff",
           "page": "/install-schedule", "message": "boom", "detail": '{"status": 500}',
           "trail": '[{"type": "page"}]', "user_agent": "Safari"}
    row.update(over)
    return row


def test_list_pages_and_filters(fake_db, fake_user, as_role):
    as_role("super_admin")
    fake_db.on_fetch("FROM ll_app.app_events", [_row()])
    out = run(app_events.list_events(fake_user, 50, 100, "crash", "nicole", None, None))
    assert out[0].detail == {"status": 500} and out[0].trail == [{"type": "page"}]
    (sql, args), = fake_db.calls("FROM ll_app.app_events")
    assert "id < $1" in sql and "kind = $2" in sql and "user_name = $3" in sql and "LIMIT $4" in sql
    assert args == (100, "crash", "nicole", 50)


def test_list_by_ids(fake_db, fake_user, as_role):
    as_role("super_admin")
    run(app_events.list_events(fake_user, 50, None, None, None, None, "3,x,7"))
    (sql, args), = fake_db.calls("FROM ll_app.app_events")
    assert "id = ANY($1::bigint[])" in sql and args[0] == [3, 7]


def test_summary_is_one_bounded_query(fake_db, fake_user, as_role):
    from datetime import datetime, timezone
    as_role("super_admin")
    t = datetime(2026, 11, 16, tzinfo=timezone.utc)
    fake_db.on_fetch("GROUP BY kind, message", [{"kind": "crash", "message": "boom", "count": 3,
                                                 "people": ["nicole"], "pages": ["/x"],
                                                 "first_at": t, "last_at": t}])
    out = run(app_events.summarize_events(fake_user, 7))
    assert out[0].count == 3 and out[0].people == ["nicole"]
    (sql, _), = fake_db.calls("GROUP BY kind, message")
    assert "LIMIT 50" in sql


# ─── request_log middleware ─────────────────────────────────────────────────

@pytest.fixture
def recorded(monkeypatch):
    calls = []

    async def fake_record(**kw):
        calls.append(kw)
    monkeypatch.setattr(app_events, "record_server_event", fake_record)
    return calls


def _app(monkeypatch):
    app = FastAPI()

    @app.get("/api/ok")
    async def ok():
        return {"ok": True}

    @app.get("/api/boom/{client_id}")
    async def boom(client_id: str):
        raise RuntimeError(f"bad thing for {client_id} token={JWT}")

    @app.get("/api/slow")
    async def slow():
        return {"ok": True}

    @app.get("/api/refused")
    async def refused():
        raise HTTPException(status_code=403, detail="no")

    app.add_middleware(request_log.RequestLogMiddleware)
    return app


def test_middleware_records_500_with_route_template(monkeypatch, recorded):
    client = TestClient(_app(monkeypatch), raise_server_exceptions=False)
    assert client.get("/api/boom/Allums?x=1").status_code == 500
    assert len(recorded) == 1
    ev = recorded[0]
    assert ev["kind"] == "server_error" and ev["page"] == "/api/boom/{client_id}"
    assert ev["detail"]["route"] == "/api/boom/{client_id}" and ev["detail"]["status"] == 500
    assert ev["detail"]["error_type"] == "RuntimeError"
    assert JWT not in ev["message"]


def test_middleware_ignores_ok_and_4xx(monkeypatch, recorded):
    client = TestClient(_app(monkeypatch))
    assert client.get("/api/ok").status_code == 200
    assert client.get("/api/refused").status_code == 403
    assert recorded == []


def test_middleware_records_slow(monkeypatch, recorded):
    monkeypatch.setattr(request_log, "SLOW_MS", 0)
    client = TestClient(_app(monkeypatch))
    client.get("/api/slow")
    assert [e["kind"] for e in recorded] == ["slow_request"]


def test_middleware_skips_the_log_itself(monkeypatch, recorded):
    monkeypatch.setattr(request_log, "SLOW_MS", 0)
    app = _app(monkeypatch)

    @app.post("/api/app-events")
    async def events():
        return {}
    TestClient(app).post("/api/app-events")
    assert recorded == []


def test_schedule_kinds_are_accepted(fake_db, fake_request, fake_user, as_role):
    body = app_events.EventsIn(events=[app_events.EventIn(kind="save_blocked", source="schedule", message="m"),
                                       app_events.EventIn(kind="save_conflict", source="schedule", message="m"),
                                       app_events.EventIn(kind="blank", source="schedule", message="m")])
    out = run(app_events.report_events(body, fake_request(), fake_user))
    assert out.saved == 3 and out.dropped == 0
