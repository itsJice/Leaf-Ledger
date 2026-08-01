#!/usr/bin/env python3
"""
One-off audit (2026-08-01): sanity-check every client's geocoded lat/lon
against their own stated ZIP code's centroid. Catches the Keffer-style bug
(a street mis-parse sent Nominatim a garbage query, which happily returned
SOME coordinate -- just the wrong one) that a "did geocoding succeed"
check alone can't see, since Nominatim returned a confident, non-empty
result both times.

Not part of the regular pipeline -- run by hand, reads cache/clients.json,
writes nothing. Flags anything more than FLAG_MILES from its ZIP centroid
for a human to look at.
"""
import csv
import json
import math
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
UA = {"User-Agent": "TBDG-christmas-scheduler/1.0 (justice@wenzdays.com)"}
FLAG_MILES = 12.0


def haversine_mi(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    clients = json.load(open(os.path.join(CACHE, "clients.json")))["clients"]

    cache_path = os.path.join(CACHE, "geocoded.csv")
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, newline="") as f:
            for row in csv.DictReader(f):
                cache[row["query"]] = (row["lat"], row["lon"])

    def zip_centroid(zip_code, st="TX"):
        key = f"{zip_code}, {st}"
        if key in cache:
            la, lo = cache[key]
            return (float(la), float(lo)) if la else None
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": key, "format": "json",
                                     "countrycodes": "us", "limit": 1},
                             headers=UA, timeout=25)
            time.sleep(1.1)
            if r.status_code == 200 and r.json():
                j = r.json()[0]
                cache[key] = (j["lat"], j["lon"])
                return float(j["lat"]), float(j["lon"])
        except Exception as e:
            print(f"  !! zip geocode failed for {zip_code}: {e}")
        cache[key] = ("", "")
        return None

    flagged = []
    checked = 0
    for c in clients:
        if c.get("lat") is None or not c.get("zip"):
            continue
        zc = str(c["zip"]).strip()
        if not zc or zc == "None":
            continue
        cen = zip_centroid(zc, c.get("st") or "TX")
        if cen is None:
            print(f"  ?? no ZIP centroid for {c['name']} ({zc})")
            continue
        checked += 1
        d = haversine_mi(c["lat"], c["lon"], cen[0], cen[1])
        if d > FLAG_MILES:
            flagged.append((c["name"], d, c["street"], c["zip"],
                            c["lat"], c["lon"], c.get("geo_source") or c.get("geo")))

    with open(cache_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query", "lat", "lon", "display"])
        for q, (la, lo) in cache.items():
            w.writerow([q, la, lo, ""])

    print(f"\nChecked {checked} clients against their ZIP centroid "
          f"(flag threshold {FLAG_MILES} mi)")
    print(f"Flagged: {len(flagged)}\n")
    flagged.sort(key=lambda x: -x[1])
    for name, d, street, zc, lat, lon, src in flagged:
        print(f"  {d:6.1f} mi  {name!r}")
        print(f"            street={street!r} zip={zc!r} geo_source={src}")
        print(f"            lat={lat} lon={lon}")


if __name__ == "__main__":
    main()
