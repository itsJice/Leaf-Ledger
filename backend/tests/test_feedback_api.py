"""Characterisation tests for the feedback inbox API (`app.apis.feedback`).

Note: there is no delete route today; the inbox supports submit, list,
status update (PUT /{id}), replying to a Claude review (PUT /{id}/reply)
and screenshot fetch.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.apis import feedback

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def feedback_row(**over):
    # Keys follow the SELECT column list in list_feedback / update_feedback_status.
    row = {"id": 42, "message": "Add a dark mode", "has_screenshot": True, "page_path": "/jobs",
           "submitted_name": "crew", "status": "new", "created_at": T0}
    row.update(over)
    return row


def test_ensure_schema_runs_once(fake_db):
    run(feedback.list_feedback())
    assert fake_db.ddl_runs == 1
    run(feedback.list_feedback())
    assert fake_db.ddl_runs == 1


def test_submit_inserts_trimmed_fields(fake_db, fake_request, fake_user):
    fake_db.on_fetchrow("INSERT INTO ll_app.feature_requests", {"id": 42})
    req = fake_request()
    req.headers["user-agent"] = "Mozilla/Test"
    body = feedback.FeedbackIn(message="  Add a dark mode  ", screenshot="data:image/png;base64,AAA",
                               page_path="/jobs" + "x" * 600)
    out = run(feedback.submit_feedback(body, req, fake_user))
    assert out == feedback.FeedbackOut(id=42, ok=True)
    (_, args), = fake_db.calls("INSERT INTO ll_app.feature_requests")
    assert args == ("Add a dark mode", "data:image/png;base64,AAA", ("/jobs" + "x" * 600)[:500],
                    "Mozilla/Test", "user-1", "crew")


@pytest.mark.parametrize(
    "body,status,detail",
    [
        ({"message": "   "}, 400, "Message is required"),
        ({"message": "x" * 4001}, 413, "Message is too long"),
        ({"message": "hi", "screenshot": "x" * 3_000_001}, 413, "Screenshot is too large"),
        ({"message": "hi", "screenshot": "http://img"}, 400, "Screenshot must be a data: image URL"),
    ],
)
def test_submit_validation(fake_db, fake_request, fake_user, body, status, detail):
    with pytest.raises(HTTPException) as exc:
        run(feedback.submit_feedback(feedback.FeedbackIn(**body), fake_request(), fake_user))
    assert (exc.value.status_code, exc.value.detail) == (status, detail)
    assert fake_db.executed == []


def test_list_clamps_limit_and_maps_rows(fake_db):
    fake_db.on_fetch("FROM ll_app.feature_requests ORDER BY created_at DESC", [feedback_row()])
    out = run(feedback.list_feedback(limit=10_000))
    assert out == [feedback.FeedbackRow(id=42, message="Add a dark mode", has_screenshot=True,
                                        page_path="/jobs", submitted_name="crew", status="new",
                                        created_at="2026-09-01T12:00:00+00:00")]
    run(feedback.list_feedback(limit=-3))
    assert [a for _, a in fake_db.calls("FROM ll_app.feature_requests ORDER BY")] == [(500,), (1,)]


def test_list_degrades_to_empty_on_outage(monkeypatch):
    async def broken():
        raise RuntimeError("no database")

    monkeypatch.setattr(feedback, "get_conn", broken)
    assert run(feedback.list_feedback()) == []


def test_update_status(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(feedback.update_feedback_status(42, feedback.StatusIn(status="archived")))
    assert (exc.value.status_code, exc.value.detail) == (400, "status must be one of ['done', 'new']")
    with pytest.raises(HTTPException) as exc:
        run(feedback.update_feedback_status(42, feedback.StatusIn(status="done")))
    assert (exc.value.status_code, exc.value.detail) == (404, "No submission with that id")
    fake_db.on_fetchrow("UPDATE ll_app.feature_requests SET status", feedback_row(status="done"))
    out = run(feedback.update_feedback_status(42, feedback.StatusIn(status="done")))
    assert out.status == "done" and out.created_at == "2026-09-01T12:00:00+00:00"
    assert [a for _, a in fake_db.calls("UPDATE ll_app.feature_requests")] == [(42, "done"), (42, "done")]


def test_screenshot(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(feedback.get_feedback_screenshot(42))
    assert (exc.value.status_code, exc.value.detail) == (404, "No screenshot for this submission")
    fake_db.on_fetchrow("SELECT screenshot FROM ll_app.feature_requests", {"screenshot": ""})
    with pytest.raises(HTTPException):
        run(feedback.get_feedback_screenshot(42))
    fake_db.on_fetchrow("SELECT screenshot FROM ll_app.feature_requests", {"screenshot": "data:image/png;base64,AAA"})
    assert run(feedback.get_feedback_screenshot(42)) == {"screenshot": "data:image/png;base64,AAA"}


def test_list_includes_claude_review(fake_db):
    fake_db.on_fetch("FROM ll_app.feature_requests ORDER BY created_at DESC", [feedback_row(
        claude_status="needs_approval", claude_note="Plan: add a toggle", claude_link=None,
        claude_reviewed_at=T0, reply=None, reply_name=None, replied_at=None,
    )])
    (out,) = run(feedback.list_feedback())
    assert (out.claude_status, out.claude_note, out.claude_reviewed_at) == (
        "needs_approval", "Plan: add a toggle", "2026-09-01T12:00:00+00:00")


def test_reply_validation(fake_db, fake_user):
    with pytest.raises(HTTPException) as exc:
        run(feedback.reply_to_claude(42, feedback.ReplyIn(reply="  "), fake_user))
    assert (exc.value.status_code, exc.value.detail) == (400, "Write a reply or approve the plan")
    with pytest.raises(HTTPException) as exc:
        run(feedback.reply_to_claude(42, feedback.ReplyIn(reply="ok", approve=True), fake_user))
    assert exc.value.status_code == 404


def test_reply_queues_for_claude(fake_db, fake_user):
    fake_db.on_fetchrow("UPDATE ll_app.feature_requests SET claude_status", feedback_row(claude_status="approved"))
    out = run(feedback.reply_to_claude(42, feedback.ReplyIn(approve=True), fake_user))
    assert out.claude_status == "approved"
    run(feedback.reply_to_claude(42, feedback.ReplyIn(reply=" It's the Jobs page "), fake_user))
    args = [a for _, a in fake_db.calls("UPDATE ll_app.feature_requests SET claude_status")]
    assert args == [(42, "approved", None, "crew"), (42, "replied", "It's the Jobs page", "crew")]
