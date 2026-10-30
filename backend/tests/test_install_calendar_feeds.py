"""Dallas / Houston and install / takedown subscription feeds: the same
office feed narrowed by ``region`` and ``kind`` query parameters."""

import asyncio

import pytest
from fastapi import HTTPException

from app.apis import install_calendar as feed_api
from app.libs import install_calendar as cal
from app.libs import schedule_board

NOW = __import__("datetime").datetime(2026, 10, 30, 12, 0)

HOU_IN = "2026-11-10|Crew 1|0"      # Houston day: install + an event teardown
DAL_IN = "2026-11-03|Crew 1|0"      # built Mi Cocina night
DAL_OFFICE = "2026-11-02|Crew 3|0"  # M Crowd office, daytime (cat M Crowd)
HOU_TD = "2027-01-08|Crew 1|0"      # Houston takedown day, one stop marked Install
DAL_TD = "2027-01-03|Crew 2|0"      # Dallas takedown night staff added (dallasNights)

PAYLOAD = {
    "depot": {"lat": 29.7, "lon": -95.4},
    "node": {},
    "durs": [],
    "spec": {
        "version": "v1",
        "const": {"NIGHT": 450, "LUNCH": 40, "DAY_CAP": 600},
        "calendar": [{"date": "2026-11-03", "kind": "dallas_night"}],
        "dayMeta": {
            HOU_IN: {"cat": "Standard", "anchored": True, "stacked": 1, "win": 600},
            DAL_IN: {"cat": "M Crowd", "anchored": False, "stacked": 1, "win": 450},
            DAL_OFFICE: {"cat": "M Crowd", "anchored": False, "stacked": 1, "win": 480},
            HOU_TD: {"cat": "Standard", "anchored": True, "stacked": 1, "win": 600},
        },
    },
    "clients": {
        "1": {"name": "River Oaks Home", "city": "Houston", "h26": 2.0, "lat": 29.75, "lon": -95.42},
        "2": {"name": "NRG Teardown", "city": "Houston", "h26": 1.0, "visitType": "Takedown",
              "lat": 29.68, "lon": -95.41},
        "3": {"name": "M Crowd Lakewood", "city": "Dallas", "h26": 3.0},
        "4": {"name": "M Crowd Corporate Office", "city": "Dallas", "h26": 1.0},
        "5": {"name": "Katy Home", "city": "Katy", "h26": 1.5, "lat": 29.78, "lon": -95.82},
        "6": {"name": "Late Install Co", "city": "Houston", "h26": 1.0, "visitType": "Install",
              "lat": 29.76, "lon": -95.37},
        "7": {"name": "M Crowd Plano", "city": "Plano", "h26": 2.0, "visitType": "Takedown"},
    },
    "days": [
        {"id": HOU_IN, "date": "2026-11-10", "crew": "Crew 1", "stops": [1, 2]},
        {"id": DAL_IN, "date": "2026-11-03", "crew": "Crew 1", "stops": [3]},
        {"id": DAL_OFFICE, "date": "2026-11-02", "crew": "Crew 3", "stops": [4]},
        {"id": HOU_TD, "date": "2027-01-08", "crew": "Crew 1", "stops": [5, 6]},
        {"id": DAL_TD, "date": "2027-01-03", "crew": "Crew 2", "stops": [7]},
    ],
}
STATE = {"dallasNights": ["2027-01-03"]}


def board():
    return schedule_board.resolve("2026", PAYLOAD, STATE)


def ics(**kw):
    return cal.build_ics(board(), now=NOW, **kw)


def stops_in(text):
    """The client names with an install event in a feed."""
    names = [c["name"] for c in PAYLOAD["clients"].values()]
    lines = text.replace("\r\n ", "").split("\r\n")
    return sorted(n for n in names
                  if any(l.startswith("SUMMARY:") and f"· {n} (" in l for l in lines))


def test_region_follows_the_tools_m_crowd_day_rule():
    b = board()
    got = {did: cal.day_region(b, d) for did, d in b.days.items()}
    assert got == {HOU_IN: "houston", DAL_IN: "dallas", DAL_OFFICE: "dallas",
                   HOU_TD: "houston", DAL_TD: "dallas"}


def test_kind_is_the_tools_visit_kind():
    b = board()
    kinds = {r: cal.stop_kind(b, d, r) for d in b.days.values() for r in d["stops"]}
    # Nov stop marked Takedown is a takedown; Jan stop marked Install is an install.
    assert kinds == {1: "install", 2: "takedown", 3: "install", 4: "install",
                     5: "takedown", 6: "install", 7: "takedown"}


@pytest.mark.parametrize("region,kind,names", [
    ("dallas", "install", ["M Crowd Corporate Office", "M Crowd Lakewood"]),
    ("dallas", "takedown", ["M Crowd Plano"]),
    ("houston", "install", ["Late Install Co", "River Oaks Home"]),
    ("houston", "takedown", ["Katy Home", "NRG Teardown"]),
    ("dallas", None, ["M Crowd Corporate Office", "M Crowd Lakewood", "M Crowd Plano"]),
    ("houston", None, ["Katy Home", "Late Install Co", "NRG Teardown", "River Oaks Home"]),
    (None, "install", ["Late Install Co", "M Crowd Corporate Office", "M Crowd Lakewood",
                       "River Oaks Home"]),
])
def test_each_feed_has_exactly_its_stops(region, kind, names):
    assert stops_in(ics(region=region, kind=kind)) == names


def test_dallas_plus_houston_is_everything():
    every = stops_in(ics())
    both = stops_in(ics(region="dallas")) + stops_in(ics(region="houston"))
    assert sorted(both) == every
    n = lambda **kw: ics(**kw).count("BEGIN:VEVENT")
    assert n(region="dallas") + n(region="houston") == n()


def test_the_four_split_feeds_add_up_to_all():
    every = stops_in(ics())
    parts = [stops_in(ics(region=r, kind=k)) for r in cal.REGIONS for k in cal.KINDS]
    assert sorted(n for p in parts for n in p) == every
    assert len(every) == 7


def test_a_mixed_day_keeps_its_drives_but_only_its_own_stops():
    b = board()
    hou = b.days[HOU_IN]
    all_ev = [e["summary"] for e in cal.feed_events(b, hou)]
    inst = [e["summary"] for e in cal.feed_events(b, hou, kind="install")]
    td = [e["summary"] for e in cal.feed_events(b, hou, kind="takedown")]
    assert any("Arrive at branch" in s for s in inst) and any("Arrive at branch" in s for s in td)
    assert any("· River Oaks Home (" in s for s in inst) and not any("· NRG Teardown (" in s for s in inst)
    assert any("· NRG Teardown (" in s for s in td) and not any("· River Oaks Home (" in s for s in td)
    assert len(inst) < len(all_ev) and len(td) < len(all_ev)


def test_unfiltered_feed_is_unchanged():
    b = board()
    assert cal.build_ics(b, now=NOW) == cal.build_ics(b, now=NOW, region=None, kind=None)
    text = ics()
    assert "X-WR-CALNAME:TBDG Xmas Schedule\r\n" in text
    assert text.count("BEGIN:VEVENT") == sum(len(cal.day_events(b, d)) for d in b.days.values())


@pytest.mark.parametrize("region,kind,name", [
    ("dallas", "install", "TBDG Dallas Installs"),
    ("dallas", "takedown", "TBDG Dallas Takedowns"),
    ("houston", "install", "TBDG Houston Installs"),
    ("houston", "takedown", "TBDG Houston Takedowns"),
    ("dallas", None, "TBDG Dallas"),
    ("houston", None, "TBDG Houston"),
    (None, "takedown", "TBDG Takedowns"),
    (None, None, "TBDG Xmas Schedule"),
])
def test_each_feed_has_its_own_calendar_name(region, kind, name):
    text = ics(region=region, kind=kind)
    assert f"X-WR-CALNAME:{name}\r\n" in text
    assert f"\r\nNAME:{name}\r\n" in text


@pytest.fixture
def api(monkeypatch):
    b = board()

    async def fake_load(*_, **__):
        return b

    async def nothing(_board):
        return set(), {}

    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    monkeypatch.setattr(feed_api, "client_lookup", nothing)
    monkeypatch.setenv("INSTALL_CALENDAR_TOKEN", "s3cret")
    return lambda **kw: asyncio.run(feed_api.calendar_feed(**kw))


def test_endpoint_filters_by_query_params(api):
    body = api(token="s3cret", region="Dallas", kind="takedown").body.decode()
    assert stops_in(body) == ["M Crowd Plano"]
    assert "X-WR-CALNAME:TBDG Dallas Takedowns" in body
    assert api(token="s3cret").body.decode().count("BEGIN:VEVENT") == ics().count("BEGIN:VEVENT")


@pytest.mark.parametrize("kw", [{"region": "austin"}, {"kind": "both"}, {"region": "dallas", "kind": "x"}])
def test_endpoint_rejects_unknown_values(api, kw):
    with pytest.raises(HTTPException) as e:
        api(token="s3cret", **kw)
    assert e.value.status_code == 400


def test_bad_token_still_404s_before_params_are_checked(api):
    with pytest.raises(HTTPException) as e:
        api(token="wrong", region="austin")
    assert e.value.status_code == 404
