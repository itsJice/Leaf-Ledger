#!/usr/bin/env python3
"""
TBDG -- ROUTE GEOMETRY stage.

The scheduler already orders every crew-day's stops to minimize REAL drive
TIME (route_exact in schedule.py -- exhaustive permutation against the true
asymmetric OSRM duration matrix, verified optimal). This stage adds the
other half of "real roads": it fetches each day's actual road-following
polyline and real driving mileage from OSRM's /route service (distinct
from the /table service used for scheduling, which only returns durations
between points, not the path between them or the distance).

Runs after schedule.py. Fully cached by stop sequence, so re-running the
pipeline after a small edit only fetches the days that actually changed.

Adds to every day in cache/schedule.json:
  geometry     -- [[lat,lon], ...] the real road path (depot->stops->depot
                  for Houston days; stop-to-stop for Dallas out-of-town nights)
  distance_mi  -- total real driving miles for the day
  leg_mi       -- per-leg miles, aligned with the existing `legs` (minutes)
"""
import hashlib
import json
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
GEOM_CACHE = os.path.join(CACHE, "route_geometries.json")
MI_PER_M = 1 / 1609.344


def seq_key(coords):
    raw = ";".join(f"{lo:.6f},{la:.6f}" for lo, la in coords)
    return hashlib.sha1(raw.encode()).hexdigest()


def fetch_route(coords):
    """coords: [(lon, lat), ...]. Returns (geometry, distance_mi, leg_mi) or None."""
    if len(coords) < 2:
        return None
    coord_str = ";".join(f"{lo},{la}" for lo, la in coords)
    url = f"https://router.project-osrm.org/route/v1/driving/{coord_str}"
    for attempt in range(4):
        try:
            r = requests.get(url, params={"overview": "simplified", "geometries": "geojson",
                                          "annotations": "distance"}, timeout=30)
            j = r.json()
            if j.get("code") == "Ok":
                route = j["routes"][0]
                # 5 decimal places ~= 1.1m -- plenty for a route line, and it
                # keeps the embedded payload small (this ships inside the
                # self-contained review.html on every load).
                geom = [[round(la, 5), round(lo, 5)]
                        for lo, la in route["geometry"]["coordinates"]]
                leg_mi = [round(leg["distance"] * MI_PER_M, 2) for leg in route["legs"]]
                return geom, round(route["distance"] * MI_PER_M, 2), leg_mi
            print("  OSRM route code:", j.get("code"), j.get("message"))
        except Exception as e:
            print("  route retry:", e)
        time.sleep(2)
    return None


def main():
    sched_path = os.path.join(CACHE, "schedule.json")
    sched = json.load(open(sched_path))
    depot = sched["depot"]
    days = sched["days"]

    cache = {}
    if os.path.exists(GEOM_CACHE):
        cache = json.load(open(GEOM_CACHE))

    fetched = reused = skipped = 0
    for d in days:
        stops = d["stops"]
        pts = [(s["lon"], s["lat"]) for s in stops if s.get("lat") is not None]
        if len(pts) != len(stops) or not pts:
            skipped += 1
            continue
        if d["depot_anchored"]:
            coords = [(depot["lon"], depot["lat"])] + pts + [(depot["lon"], depot["lat"])]
        else:
            coords = pts
        if len(coords) < 2:
            skipped += 1
            continue

        key = seq_key(coords)
        if key in cache:
            geom, mi, leg_mi = cache[key]
            reused += 1
        else:
            result = fetch_route(coords)
            if result is None:
                skipped += 1
                continue
            geom, mi, leg_mi = result
            cache[key] = [geom, mi, leg_mi]
            fetched += 1
            time.sleep(0.25)  # be polite to the public demo server

        d["geometry"] = geom
        d["distance_mi"] = mi
        d["leg_mi"] = leg_mi

    with open(GEOM_CACHE, "w") as f:
        json.dump(cache, f)
    with open(sched_path, "w") as f:
        json.dump(sched, f, indent=2, default=str)
    print(f"Route geometry: {fetched} fetched, {reused} cached, {skipped} skipped "
          f"({len(days)} crew-days)")


if __name__ == "__main__":
    main()
