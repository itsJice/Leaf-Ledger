"""The calendar subscribe button's link: office staff only, since it carries the feed's secret."""

import asyncio

import pytest
from fastapi import HTTPException

from app.apis import install_schedule
from app.libs import roles

PATH = "/api/install-schedule/calendar-link"


@pytest.mark.parametrize("role,ok", [
    ("staff", True), ("admin", True), ("super_admin", True),
    ("lead", False), ("crew", False), ("viewer", False), ("production", False),
])
def test_only_office_staff_and_up_get_the_link(role, ok):
    # The endpoint's own dependency: require_role("staff"), no viewer_read.
    assert roles.allowed(role, "staff", "GET", False, PATH) is ok


def test_router_level_check_alone_would_let_viewer_and_production_in():
    # Why the endpoint carries its own check: the router is VIEWER_READ and on
    # production's read allowlist -- except for this path.
    assert roles.allowed("viewer", "staff", "GET", True, PATH)
    assert not roles.production_may("GET", PATH)
    assert roles.production_may("GET", "/api/install-schedule/page")


def test_endpoint_has_the_staff_dependency():
    route = next(r for r in install_schedule.router.routes if r.path.endswith("/calendar-link"))
    assert route.dependencies, "calendar-link must not rely on the router-level check alone"


def test_link_is_404_until_the_feed_is_configured(monkeypatch):
    monkeypatch.delenv("INSTALL_CALENDAR_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e:
        asyncio.run(install_schedule.calendar_link())
    assert e.value.status_code == 404

    monkeypatch.setenv("INSTALL_CALENDAR_TOKEN", "s3cret")
    assert asyncio.run(install_schedule.calendar_link()) == {
        "path": "/api/install-calendar/feed.ics?token=s3cret"}
