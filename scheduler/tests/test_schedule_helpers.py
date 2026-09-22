"""Pure helpers in schedule.py, on synthetic matrices and coordinates."""
import pytest

import schedule as S

# Synthetic ASYMMETRIC drive-time matrix, seconds. D[a][b] = a -> b.
D3 = [
    [0,    600, 1200],
    [900,    0,  300],
    [1500, 420,    0],
]
# Open paths over nodes {0,1,2} (sum of the two legs):
#   0-1-2  600+300  =  900   <- best
#   0-2-1 1200+420  = 1620
#   1-0-2  900+1200 = 2100
#   1-2-0  300+1500 = 1800
#   2-0-1 1500+600  = 2100
#   2-1-0  420+900  = 1320


def stop(midx, hours, name):
    return {"row": 100 + midx, "midx": midx, "cal_hours": hours,
            "name": name, "zone": "Test Zone"}


def test_constants_match_rules_md():
    assert (S.WINDOW, S.DAY_CAP, S.DAY_MIN, S.LUNCH) == (720, 600, 450, 40)
    assert (S.NIGHT, S.NIGHT_MIN, S.NIGHT_MAX, S.RADIUS_S) == (450, 390, 540, 1800)


def test_day_totals_hand_computed():
    # 2.0 + 1.5 + 3.25 = 6.75h install = 405 min; 15 min drive; 40 min lunch
    assert S.day_totals(6.75, 15.0) == 460.0
    assert S.day_totals(0, 0) == S.LUNCH


def test_route_exact_three_stops_open():
    order, drive_min = S.route_exact(D3, [0, 1, 2], depot_anchored=False)
    assert order == [0, 1, 2]
    assert drive_min == 15.0


def test_build_day_three_stops_totals():
    stops = [stop(2, 3.25, "Test Client C"), stop(0, 2.0, "Test Client A"),
             stop(1, 1.5, "Test Client B")]
    by_idx = {s["midx"]: s for s in stops}
    day = S.build_day(D3, "Crew 1", "2026-11-17", stops, by_idx, "Standard",
                      depot_anchored=False)
    assert day["order_idx"] == [0, 1, 2]
    assert [s["name"] for s in day["stops"]] == ["Test Client A", "Test Client B",
                                                 "Test Client C"]
    assert day["install_h"] == 6.75
    assert day["drive_min"] == 15.0
    assert day["legs"] == [10.0, 5.0]
    assert day["total_min"] == S.day_totals(6.75, 15.0) == 460.0
    assert day["dow"] == "Tue"
    assert day["flags"] == []            # 460 min: above the 7.5h min, under cap


def test_tour_len_and_two_opt_respect_asymmetry():
    assert S.tour_len(D3, [0, 1, 2, 0]) == 600 + 300 + 1500
    assert S.tour_len(D3, [0, 2, 1, 0]) == 1200 + 420 + 900
    assert S.two_opt(D3, [0, 2, 1, 0]) == [0, 1, 2, 0]


def test_leg_treats_missing_duration_as_zero():
    assert S.leg([[0, None], [5, 0]], 0, 1) == 0.0
    assert S.leg([[0, None], [5, 0]], 1, 0) == 5


# --- haversine / travel-time estimate -------------------------------------------
NYC = (40.7128, -74.0060)
LA = (34.0522, -118.2437)


def test_haversine_new_york_to_los_angeles():
    mi = S.haversine_mi(NYC, LA)
    assert mi == pytest.approx(2445, abs=5)
    assert S.haversine_mi(LA, NYC) == pytest.approx(mi)


def test_haversine_one_degree_of_latitude_and_zero():
    # arc length of 1 degree on R = 3958.8 mi: 3958.8 * pi / 180 = 69.094 mi
    assert S.haversine_mi((29.0, -95.0), (30.0, -95.0)) == pytest.approx(69.094, abs=0.01)
    assert S.haversine_mi((29.76, -95.37), (29.76, -95.37)) == 0.0


def test_est_seconds_uses_road_fudge_and_average_speed():
    a, b = (29.0, -95.0), (30.0, -95.0)
    # 69.094 mi * 1.35 road fudge / 27 mph * 3600 s/h = 12436.9 -> 12437
    assert S.est_seconds(a, b) == 12437
    assert S.est_seconds(a, a) == 0


# --- radius rules ---------------------------------------------------------------
def _pool(D, hours=2.0):
    stops = [stop(i, hours, f"Test Client {chr(64 + i)}") for i in range(1, len(D))]
    return stops, {s["midx"]: s for s in stops}


@pytest.mark.parametrize("ab,linked", [(1800, True), (1801, False)])
def test_pack_bins_links_only_within_30_min_radius(ab, linked):
    # depot 0; A=1 and B=2 are `ab` seconds apart; C=3 is 2500s from both
    D = [
        [0,    900,  900,  900],
        [900,    0,   ab, 2500],
        [900,   ab,    0, 2500],
        [900, 2500, 2500,    0],
    ]
    pool, by_idx = _pool(D)
    bins = S.pack_bins(D, pool, by_idx)
    names = sorted(sorted(s["name"] for s in b) for b in bins)
    if linked:
        assert names == [["Test Client A", "Test Client B"], ["Test Client C"]]
    else:
        assert names == [["Test Client A"], ["Test Client B"], ["Test Client C"]]


@pytest.mark.parametrize("depot_leg,merged", [
    (3000, True),    # rural (> 2700s from depot): wider 45-min radius applies
    (2700, False),   # exactly 2700 is still urban: 30-min radius
])
def test_merge_singletons_rural_radius(depot_leg, merged):
    # two lone stops 2000s apart: outside 1800 (urban) but inside 2700 (rural)
    D = [
        [0,         depot_leg, depot_leg],
        [depot_leg, 0,         2000],
        [depot_leg, 2000,      0],
    ]
    pool, _ = _pool(D, hours=1.0)
    bins = S.merge_singletons(D, [[s] for s in pool])
    assert len(bins) == (1 if merged else 2)
