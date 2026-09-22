#!/usr/bin/env python3
"""
TBDG — interactive team-review page (review.html) for one Christmas season.

The season is derived (see SEASON below), never hard-coded: every year-shaped
string in the generated page comes from it.

Single self-contained HTML file (Leaflet from CDN, OSM tiles) with:
  - date strip -> day-by-day navigation, crew-by-crew cards
  - exact, name-labeled pins colored by crew; routes drawn depot->stops->depot
  - per-card: people needed, last season's real hours, storage/boxes, legs, 10h bar
  - approve toggle per crew-day
  - drag-and-drop (or Move dialog) to move a stop to another crew/day;
    routes + times recompute instantly from the embedded OSRM matrix
  - changes persist in localStorage; Export JSON/CSV of decisions
"""
import hashlib
import json
import os

import rules
import schedule as S
import season as season_lib

# ---------------------------------------------------------------------------
# Which season this build is for.
#
# Nothing about the page is allowed to hard-code a year: the same source
# builds every autumn's tool, and a baked "2026" is silently wrong from 1
# February onward. Everything year-shaped below (the title, the takedown
# cutoff, the month chips, the January picker, export filenames, the
# localStorage key) is derived from this one number and substituted into the
# HTML/JS template through the __SEASON__ family of tokens.
#
# Read the same way schedule.py reads it -- its value if it exposes one,
# otherwise TBDG_SEASON, otherwise the calendar rule -- so a build of an
# out-of-cycle season (TBDG_SEASON=2027 ./build_review.py) agrees end to end
# rather than pairing next year's calendar with this year's labels.
SEASON = getattr(S, "SEASON", None)
if not isinstance(SEASON, int):
    SEASON = int(os.environ.get("TBDG_SEASON") or season_lib.season_for())
SEASON_NEXT = SEASON + 1          # January's calendar year
SEASON_PREV = SEASON - 1          # last season -- the invoice/hours comparison year
SPAN_START, SPAN_END = season_lib.season_span(SEASON)
TAKEDOWN_CUTOFF = season_lib.takedown_cutoff(SEASON)
MONTH_YEAR = {m: season_lib.year_of_month(SEASON, m) for m in (10, 11, 12, 1)}

#: Literal -> value substitutions applied to the HTML template at write time
#: (before __DATA__, so nothing in the client payload is ever rescanned).
SUBS = {
    "__SEASON__": str(SEASON),
    "__SEASON_NEXT__": str(SEASON_NEXT),
    "__SEASON_PREV__": str(SEASON_PREV),
    "__SPAN_START__": SPAN_START.isoformat(),
    "__SPAN_END__": SPAN_END.isoformat(),
    "__CUTOFF__": TAKEDOWN_CUTOFF.isoformat(),
    "__Y_OCT__": str(MONTH_YEAR[10]),
    "__Y_NOV__": str(MONTH_YEAR[11]),
    "__Y_DEC__": str(MONTH_YEAR[12]),
    "__Y_JAN__": str(MONTH_YEAR[1]),
}

# Clients installed at no charge (donations). Kept in client_config.json with
# every other named-client rule so no name is hard-coded here.
NO_CHARGE = S.CLIENT_CONFIG.get("no_charge", {})

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "review.html")

# Real installers (names + personal phone numbers) -- same PII rule as
# client_config.json, gitignored, loaded defensively so a fresh checkout
# without the file still builds. Applied client-side as the roster's
# starting point only when nobody has saved a real roster yet (see the
# `rosterSeed` / normRoster wiring below) -- never overwrites an edit.
try:
    with open(os.path.join(HERE, "roster_seed.json")) as f:
        ROSTER_SEED = json.load(f)
except FileNotFoundError:
    ROSTER_SEED = []
# normRoster() (build_review.py's JS, further down) drops any record with no
# `id` -- assign the same "p<n>" ids the tool itself hands out, so the file
# on disk can stay plain names/phones.
for _i, _p in enumerate(ROSTER_SEED, 1):
    _p["id"] = f"p{_i}"

sched = json.load(open(os.path.join(CACHE, "schedule.json")))
mat = json.load(open(os.path.join(CACHE, "matrix.json")))

# node index per client row (depot = 0)
node = {}
for i, rid in enumerate(mat["node_ids"]):
    if rid is not None:
        node[rid] = i
durs = [[(int(v) if v is not None else 0) for v in row] for row in mat["durations"]]

# Clients added in the review tool (or replayed from the notebook) have no
# entry in the real OSRM matrix -- matrix.json is prep.py's cache of the
# spreadsheet-only clients and never gets rewritten. Extend durs/node with
# the same haversine-estimate synthetic node schedule.py used to route
# their frozen day, so the browser's own radius/slot-finder math (which
# rebuilds N/D from THIS payload, not from schedule.json) sees them too.
node_latlon = {0: (sched["depot"]["lat"], sched["depot"]["lon"])}
for c in sched["all_clients"]:
    if c.get("lat") is not None and c["row"] in node:
        node_latlon[node[c["row"]]] = (c["lat"], c["lon"])
for c in sched["all_clients"]:
    if c.get("lat") is None or c["row"] in node:
        continue
    node[c["row"]] = S.add_synthetic_node(durs, node_latlon, c["lat"], c["lon"])

clients = {}
for c in sched["all_clients"]:
    if c.get("lat") is None:
        continue
    clients[c["row"]] = {
        "row": c["row"], "name": c["name"], "street": c["street"],
        "city": c["city"], "st": c.get("st", "TX"), "zip": c["zip"],
        "phone": c.get("phone", ""),
        "email": c.get("email", ""), "storage": c.get("storage", ""),
        "boxes": c.get("box_count") or "", "d24": c.get("date_2024", ""),
        "d25": c.get("prior_install_date", ""),
        "real25": c.get("real_hours"), "crew25": c.get("crew_2025", ""),
        "size25": c.get("crew_size_2025"), "people": c.get("people_needed"),
        # Per-role staffing ask, so a crew-day can be judged on whether it has
        # a LEAD -- not merely enough bodies. See prep.py.
        "roleNeed": c.get("role_need") or {},
        "h26": c.get("cal_hours"), "basis": c.get("hours_basis", ""),
        "zone": c["zone"], "area": c["area"], "cat": c["category"],
        "bus": c["business"], "lat": c["lat"], "lon": c["lon"],
        "geo": c.get("geo_source", ""),
        # Deposited date + free-text note from the "2026 Install Date"
        # column. Both were already parsed by prep.py and never used.
        "locked": c.get("install_2026_confirmed", "") or "",
        "advice": c.get("install_2026_note", "") or "",
        # Billing export fields (see prep.py) -- storageFee is a real,
        # working column; install/takedownFee are None until the broken
        # spreadsheet formulas are fixed (2026-08-10: not yet).
        "storageFee": c.get("storage_fee"),
        "installFee": c.get("install_fee_2026"),
        "takedownFee": c.get("takedown_fee_2026"),
        "invoice25": c.get("invoice_2025_total"),
        "noCharge": NO_CHARGE.get(c["name"], ""),
        "repairNotes": c.get("production_notes", "") or "",
        "install24": c.get("install_fee_2024"), "storage24": c.get("storage_fee_2024"),
        "install25": c.get("install_fee_2025"), "storage25": c.get("storage_fee_2025"),
    }

# Day ids must survive a pipeline re-run, or saved accommodations silently
# reattach to the wrong day. The old id embedded the day's index in the
# global array, so inserting one day shifted every later id. Key on the
# occurrence within (date, crew) instead -- stable unless that specific
# pair gains or loses a day.
_occ = {}
days = []
for d in sched["days"]:
    k = (d["date"], d["crew"])
    _occ[k] = _occ.get(k, -1) + 1
    days.append({
        "id": f'{d["date"]}|{d["crew"]}|{_occ[k]}',
        "date": d["date"], "dow": d["dow"], "crew": d["crew"],
        "stops": [s["row"] for s in d["stops"]],
        # Real road-following path + actual mileage from route_geometry.py
        # (OSRM /route -- distinct from the /table durations used to plan
        # the stop order). Goes stale the moment the day is edited; the
        # client re-fetches live in that case (see liveRoute() in the JS).
        "geom": d.get("geometry"), "mi": d.get("distance_mi"),
        "legMi": d.get("leg_mi"),
    })

# Day METADATA lives in a side map keyed by day id, not on the day itself.
# Emptying a day used to delete it outright, so refilling that slot rebuilt
# a bare day defaulting to a 600-minute window -- silently discarding
# negotiated client exceptions (Capital Bank 960, Lewis/LTS 960, ...) and
# showing a false OVER flag. Metadata now outlives its day.
dayMeta = {}
for d, dd in zip(sched["days"], days):
    dayMeta[dd["id"]] = {
        "cat": d["category"], "anchored": d["depot_anchored"],
        "stacked": d["stacked_crews"], "note": d["note"],
        "win": d.get("window_min", S.DAY_CAP), "lunchMin": d.get("lunch", S.LUNCH),
        "half": d.get("half_rows", []), "joint": d.get("joint_with", ""),
        "startRow": d.get("start_row"),
        "winReason": rules.window_reason(d),
        "flags": d.get("flags", []), "zones": d.get("zones", []),
    }

# ---- static eligibility, precomputed -------------------------------------
# Every (client x date) answer, computed once here by the same predicates
# validate.py uses. The browser looks the answer up rather than
# re-implementing the rules, so there is no second copy to drift.
#
# Stored as interned blocker-sets referenced by index: 2005 non-empty cells
# collapse to ~42 distinct sets, which takes the table from ~193KB to ~13KB.
# The crew dimension is omitted because no static rule depends on the crew
# (R2, the one crew rule, is a per-DAY coverage check -- see club_crew_ok);
# it is asserted below rather than assumed.
cal = rules.calendar()
_by_name = {c["name"]: c for c in sched["all_clients"]}
elig_dates = [ci["date"] for ci in cal]
_sets, _set_idx = [[]], {"[]": 0}
by_row = {}
for row in sorted(clients):
    c = _by_name[clients[row]["name"]]
    seq = []
    for ci in cal:
        per_crew = [rules.static_blockers(c, ci["date"], crew, ci["dow"], ci["kind"])
                    for crew in S.CREWS]
        assert all(b == per_crew[0] for b in per_crew), (
            f"static rule became crew-dependent for {c['name']} on {ci['date']} "
            f"-- the eligibility table's crew collapse is no longer valid")
        key = json.dumps(per_crew[0])
        if key not in _set_idx:
            _set_idx[key] = len(_sets)
            _sets.append(per_crew[0])
        seq.append(_set_idx[key])
    if any(seq):
        by_row[str(row)] = seq
elig = {"dates": elig_dates, "sets": _sets, "byRow": by_row}

groups = []
for g in rules.SAME_DAY_GROUPS:
    rws = [c["row"] for c in sched["all_clients"] if c["name"] in g["names"]]
    rws = [r for r in rws if r in clients]
    if len(rws) < 2:
        continue
    first = next((c["row"] for c in sched["all_clients"]
                  if c["name"] == g["first"]), None) if g["first"] else None
    groups.append({"id": g["id"], "label": g["label"], "rows": rws,
                   "first": first, "minCrews": g["min_crews"], "why": g["why"]})

force_first = {}
for nm, why in rules.FORCE_FIRST.items():
    c = _by_name.get(nm)
    if c and c["row"] in clients:
        force_first[str(c["row"])] = why

spec = {
    "const": {
        "DAY_CAP": S.DAY_CAP, "DAY_MIN": S.DAY_MIN, "WINDOW": S.WINDOW,
        "LUNCH": S.LUNCH, "NIGHT": S.NIGHT, "NIGHT_MIN": S.NIGHT_MIN,
        "NIGHT_MAX": S.NIGHT_MAX, "RADIUS_S": S.RADIUS_S,
        "RADIUS_RURAL_S": 2700, "CREWS": list(S.CREWS),
    },
    "calendar": cal,
    "dayMeta": dayMeta,
    "groups": groups,
    "forceFirst": force_first,
    "eligibility": elig,
    "codes": {k: {"rule": v[0], "msg": v[1], "soft": v[2]}
              for k, v in rules.CODES.items()},
    "rosterSeed": ROSTER_SEED,
}

def _with_place(rows):
    """Attach the address/coords a dropped client already has.

    schedule.py emits these as {name, reason} only -- they never entered the
    router, so they carried no geometry. But they ARE geocoded (they sit in
    all_clients), and staff want them as pins on the not-installing map
    (user, 2026-08-31). Joined here rather than upstream so this needs no
    optimizer re-run: the build version hashes `days` and `clients`, which
    this doesn't touch, so saved reschedule state stays valid.

    A client with no address (the whole reason some are flagged) simply
    comes back without lat/lon and the map skips it -- the panel says so.
    """
    out = []
    for r in rows:
        c = _by_name.get(r["name"]) or {}
        out.append({**r,
                    "lat": c.get("lat"), "lon": c.get("lon"),
                    "street": c.get("street", ""), "city": c.get("city", ""),
                    "zip": c.get("zip", ""), "phone": c.get("phone", ""),
                    "zone": c.get("zone", "")})
    return out


payload_obj = {
    "depot": {"lat": sched["depot"]["lat"], "lon": sched["depot"]["lon"]},
    "clients": clients, "days": days, "node": node, "durs": durs,
    "noaddr": _with_place(sched.get("flagged_noaddr", [])),
    "dropped": _with_place(sched.get("dropped", [])),
    "spec": spec,
}
# Version stamps the inputs, so saved state from before a regeneration is
# caught and reconciled rather than silently misapplied to shifted days.
spec["version"] = hashlib.sha256(
    json.dumps({"d": days, "c": clients}, sort_keys=True).encode()
).hexdigest()[:12]

payload = json.dumps(payload_obj, separators=(",", ":"))

# The full HTML/CSS/JS page markup lives in review_template.html; tokens
# such as __DATA__ and __SEASON__ below are substituted into it at build time.
HTML = open(os.path.join(HERE, "review_template.html"), encoding="utf-8", newline="").read()

# A token that no longer appears in the template is a rename that silently
# left a hard-coded year behind -- exactly the failure this whole mechanism
# exists to prevent, so fail the build rather than ship it.
_unused = [t for t in SUBS if t not in HTML]
if _unused:
    raise SystemExit(f"season token(s) no longer used in the template: {_unused}")
html = HTML
for _tok, _val in SUBS.items():
    html = html.replace(_tok, _val)
# __DATA__ last, so a client name that happened to contain a token spelling
# can't be rewritten by the pass above.
html = html.replace("__DATA__", payload)

with open(OUT, "w") as f:
    f.write(html)
print("Wrote", OUT, f"({os.path.getsize(OUT)//1024} KB)")
print("Run publish_pages.py to push this to the deployed tool "
      "(it's served from Postgres now, not a file -- see RULES.md \xa712).")
