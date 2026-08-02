#!/usr/bin/env python3
"""
TBDG 2026 Christmas install schedule -- SCHEDULE stage.

Loads the enriched clients + OSRM drive matrix from prep.py, applies every
non-negotiable rule, packs standard Houston clients into crew-days, routes
each crew-day with real OSRM drive time, validates the 8am-8pm window, and
writes the Excel workbook + interactive Leaflet map.
"""
import datetime
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

WINDOW = 720          # absolute 8:00am-8:00pm legal window (Houston days)
DAY_CAP = 600         # crews work 8-10 hrs/day -> hard cap 10h (incl. lunch)
DAY_MIN = 450         # teams LIKE to work: soft minimum 7.5h/day.
                      # Day shape: arrive depot 8:00, roll out 8:30 ->
                      # a 10h route day is back ~6:30pm, min day ~4pm.
LUNCH = 40            # Houston days include a 40-min lunch
NIGHT = 450           # Mi Cocina nights start 11pm: MAX 7.5h of work incl
                      # drive (user rule) -> done by 6:30am
NIGHT_MIN = 390       # ...and MIN 6.5h of work on every night EXCEPT the
                      # last, which stays light as the buffer (user rule)
NIGHT_MAX = 540       # absolute hard wall 8am; 6:30-8am is overrun buffer
RADIUS_S = 1800       # every stop must be within 30 min drive of its day-group
# Crews are named by their lead: Crew 1, Crew 2, Crew 3
CREWS = ["Crew 1", "Crew 2", "Crew 3"]

# 2026 November calendar (Thanksgiving = Thu Nov 26).
DALLAS_DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
CLUB_MONDAYS = ["2026-11-09", "2026-11-16"]
BANK_FRIDAY = "2026-11-27"
ROTARY_SUNDAY = "2026-11-29"
HOU_WEEKDAYS = ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
                "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20",
                "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-30"]
SATURDAYS = []   # no standard Saturday capacity -- see STD_WEEKDAYS note
# Round-1 Houston weekday slots (user, 2026-08-01): teams work consecutive
# Mon-Fri only, nothing on Saturday/Sunday except named exceptions (Rotary
# House's Sunday, one club's client-requested Saturday -- both pinned
# individually below, independent of this pool). The window runs forward
# from Thanksgiving through a deposited client's confirmed Dec 2 (this
# round's last date), and back from Thanksgiving only as far as needed to
# fit everyone -- that floor is Nov 12, one crew-day of slack short of
# exactly filling this round's Houston need (41 crew-days into 42 slots).
# The wider Nov 9-Dec 10 calendar the review tool shows (see DOW below)
# stays available for later manual reschedule accommodation; it's just no
# longer where the INITIAL round automatically lands people.
STD_WEEKDAYS = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17",
                "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23",
                "2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30",
                "2026-12-01", "2026-12-02"]
FORCE_START = set()          # no forced first day -- balance fills naturally
OVERFLOW_TAIL = set()        # no auto-assigned overflow tail this round
DOW = {  # for labels, and the full set of dates the review tool can show.
    # Sundays/Thanksgiving are included too (not workable -- see rules.py's
    # SUNDAY/THANKS blockers) so the date strip can show a real, explained
    # gray bubble instead of just not mentioning that day at all.
    "2026-11-01": "Sun", "2026-11-02": "Mon", "2026-11-03": "Tue",
    "2026-11-04": "Wed", "2026-11-05": "Thu", "2026-11-06": "Fri",
    "2026-11-07": "Sat", "2026-11-09": "Mon", "2026-11-10": "Tue",
    "2026-11-11": "Wed", "2026-11-12": "Thu", "2026-11-13": "Fri",
    "2026-11-14": "Sat", "2026-11-15": "Sun",
    "2026-11-16": "Mon", "2026-11-17": "Tue",
    "2026-11-18": "Wed", "2026-11-19": "Thu", "2026-11-20": "Fri",
    "2026-11-21": "Sat", "2026-11-22": "Sun",
    "2026-11-23": "Mon", "2026-11-24": "Tue",
    "2026-11-25": "Wed", "2026-11-26": "Thu",   # Thanksgiving
    "2026-11-27": "Fri", "2026-11-28": "Sat",
    "2026-11-29": "Sun", "2026-11-30": "Mon", "2026-12-01": "Tue",
    "2026-12-02": "Wed", "2026-12-03": "Thu", "2026-12-04": "Fri",
    "2026-12-05": "Sat", "2026-12-06": "Sun", "2026-12-07": "Mon",
    "2026-12-08": "Tue", "2026-12-09": "Wed", "2026-12-10": "Thu",
}


import client_config_loader
CLIENT_CONFIG = client_config_loader.load()

OVERRIDES = os.path.join(HERE, "overrides.json")


def load_new_clients():
    """Clients added in the review tool (anomaly jobs, callbacks) that
    aren't in the spreadsheet at all -- exported alongside the frozen days
    in overrides.json. Raw dicts; main() turns each into a full client
    record with its own synthetic matrix node."""
    if not os.path.exists(OVERRIDES):
        return []
    try:
        with open(OVERRIDES) as f:
            doc = json.load(f)
    except (ValueError, OSError):
        return []
    if doc.get("kind") != "tbdg-install-overrides":
        return []
    return [c for c in doc.get("new_clients", [])
            if c.get("name") and c.get("lat") is not None and c.get("lon") is not None]


# A client added in the browser gets REAL OSRM drive times captured once
# at creation (build_review.py live-fetches a /table lookup against every
# real client, both directions, and persists the result as out_row/in_col
# in the notebook) -- reused here verbatim so a from-scratch rebuild
# agrees with what the tool already showed. The straight-line estimate
# below is only a fallback: a client created before this existed, or one
# whose live fetch failed at the time.
ROAD_FUDGE = 1.35
EST_AVG_MPH = 27


def haversine_mi(a, b):
    import math
    R = 3958.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def est_seconds(a, b):
    return round(haversine_mi(a, b) * ROAD_FUDGE / EST_AVG_MPH * 3600)


def add_synthetic_node(D, node_latlon, lat, lon, out_row=None, in_col=None):
    """out_row/in_col are real OSRM durations vs the ORIGINAL (real-client)
    matrix nodes, indexed 0..len(out_row)-1 -- any node beyond that (an
    earlier synthetic addition) always falls back to the estimate, same
    as build_review.py's extendMatrix()."""
    idx = len(D)
    pt = (lat, lon)
    real_n = len(out_row) if out_row else 0
    for i, row in enumerate(D):
        row.append(in_col[i] if in_col and i < real_n else est_seconds(node_latlon[i], pt))
    new_row = [out_row[i] if out_row and i < real_n else est_seconds(pt, node_latlon[i])
               for i in range(len(D))]
    new_row.append(0)
    D.append(new_row)
    node_latlon[idx] = pt
    return idx


def load_overrides():
    """Days already promised to clients, exported from the review tool.

    Absent file = normal full re-plan. Present = those days are replayed
    verbatim and everything else schedules around them. Keyed by client
    NAME rather than spreadsheet row, because inserting a row into the
    sheet renumbers every row after it and would silently reattach dates
    to the wrong people.
    """
    if not os.path.exists(OVERRIDES):
        return []
    try:
        with open(OVERRIDES) as f:
            doc = json.load(f)
    except (ValueError, OSError) as e:
        print(f"  !! overrides.json unreadable ({e}) -- ignoring it")
        return []
    if doc.get("kind") != "tbdg-install-overrides":
        print("  !! overrides.json is not a TBDG notebook -- ignoring it")
        return []
    out = [d for d in doc.get("days", [])
           if d.get("date") and d.get("crew") and d.get("stops")]
    # Deterministic order so a rebuild is reproducible.
    out.sort(key=lambda d: (d["date"], d["crew"]))
    return out


def load():
    with open(os.path.join(CACHE, "clients.json")) as f:
        data = json.load(f)
    with open(os.path.join(CACHE, "matrix.json")) as f:
        mat = json.load(f)
    clients = data["clients"]
    depot = data["depot"]
    # row -> matrix index (0 = depot)
    row2idx = {}
    for i, rid in enumerate(mat["node_ids"]):
        if rid is not None:
            row2idx[rid] = i
    for c in clients:
        c["midx"] = row2idx.get(c["row"])
    by_row = {c["row"]: c for c in clients}
    return depot, clients, by_row, mat["durations"]


# ---------------------------------------------------------------------------
# Routing helpers (durations in seconds; returned drive in minutes)
# ---------------------------------------------------------------------------
def leg(D, a, b):
    v = D[a][b]
    return v if v is not None else 0.0


def route_loop(D, stops, depot=0):
    """Closed tour depot->stops->depot. NN seed + 2-opt. stops = matrix idx."""
    if not stops:
        return [], 0.0
    unv = stops[:]
    tour = [depot]
    cur = depot
    while unv:
        nxt = min(unv, key=lambda s: leg(D, cur, s))
        tour.append(nxt)
        unv.remove(nxt)
        cur = nxt
    tour.append(depot)
    tour = two_opt(D, tour, fixed_ends=True)
    drive = sum(leg(D, tour[i], tour[i + 1]) for i in range(len(tour) - 1))
    return tour[1:-1], drive / 60.0


def route_open(D, stops):
    """Open path among stops (no depot). NN seed + 2-opt. Returns order+drive."""
    if len(stops) <= 1:
        return stops[:], 0.0
    # seed from the stop with min total distance to others (central-ish)
    seed = min(stops, key=lambda s: sum(leg(D, s, t) for t in stops))
    unv = [s for s in stops if s != seed]
    path = [seed]
    cur = seed
    while unv:
        nxt = min(unv, key=lambda s: leg(D, cur, s))
        path.append(nxt)
        unv.remove(nxt)
        cur = nxt
    path = two_opt(D, path)
    drive = sum(leg(D, path[i], path[i + 1]) for i in range(len(path) - 1))
    return path, drive / 60.0


def tour_len(D, tour):
    return sum(leg(D, tour[i], tour[i + 1]) for i in range(len(tour) - 1))


def two_opt(D, tour, fixed_ends=True):
    """Interior 2-opt on a sequence whose first and last nodes stay fixed.

    OSRM driving durations are ASYMMETRIC (one-ways, ramps), so reversing a
    segment also flips its internal edges — the classic boundary-only delta
    can 'improve' while the true tour gets longer, and moves can cycle
    forever. We therefore accept a reversal only when the FULL recomputed
    tour length strictly decreases, which guarantees termination."""
    n = len(tour)
    if n <= 3:
        return tour
    best = tour_len(D, tour)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 2):
            for k in range(i + 1, n - 1):
                cand = tour[:i] + tour[i:k + 1][::-1] + tour[k + 1:]
                cl = tour_len(D, cand)
                if cl < best - 1e-6:
                    tour, best = cand, cl
                    improved = True
    return tour


def day_totals(install_h, drive_min):
    return install_h * 60 + drive_min + LUNCH


def route_exact(D, idxs, depot_anchored):
    """Exhaustive optimal ordering for small days (n <= 8): tries every
    permutation with the TRUE asymmetric durations. 8! = 40,320 orders —
    cheap as a one-time final pass, and provably optimal (no A->B == B->A
    assumption anywhere)."""
    import itertools
    best, best_p = None, None
    for p in itertools.permutations(idxs):
        if depot_anchored:
            seq = (0,) + p + (0,)
        else:
            seq = p
        d = sum(leg(D, seq[i], seq[i + 1]) for i in range(len(seq) - 1))
        if best is None or d < best:
            best, best_p = d, p
    return list(best_p), best / 60.0


def build_day(D, crew, date, stops, by_idx, category, depot_anchored=True,
              stacked_crews=1, note="", window=None, lunch=None,
              half_rows=None, start_row=None, joint_with="", allow_single=False):
    """Compute an ordered, validated crew-day dict. Final ordering is
    EXHAUSTIVELY optimal for days of <= 8 stops. `window`/`lunch` default
    to the Houston 10h day; Mi Cocina nights pass 420/0.

    JOINT JOBS: `half_rows` lists stops worked TOGETHER with another crew
    (each side carries half the install hours); `joint_with` names the
    partner crew; `start_row` pins that stop first in the route (both
    crews meet there at start of shift, then split to their own stops)."""
    window = DAY_CAP if window is None else window
    lunch = LUNCH if lunch is None else lunch
    half_rows = set(half_rows or ())
    idxs = [s["midx"] for s in stops]
    if start_row is not None and len(idxs) >= 2:
        start_idx = next(s["midx"] for s in stops if s["row"] == start_row)
        rest = [i for i in idxs if i != start_idx]
        import itertools as _it
        best, best_p = None, ()
        for p in _it.permutations(rest):
            seq = ((0,) if depot_anchored else ()) + (start_idx,) + p + \
                  ((0,) if depot_anchored else ())
            dd = sum(leg(D, seq[i], seq[i + 1]) for i in range(len(seq) - 1))
            if best is None or dd < best:
                best, best_p = dd, p
        order, drive = [start_idx] + list(best_p), best / 60.0
    elif 2 <= len(idxs) <= 8:
        order, drive = route_exact(D, idxs, depot_anchored)
    elif depot_anchored:
        order, drive = route_loop(D, idxs)
    else:
        order, drive = route_open(D, idxs)
    ordered = [by_idx[i] for i in order]

    def eff_h(s):
        return s["cal_hours"] / 2 if s["row"] in half_rows else s["cal_hours"]
    install = sum(eff_h(s) for s in stops) / stacked_crews
    total = install * 60 + drive + lunch
    legs = []
    seq = ([0] + order + [0]) if depot_anchored else order
    for i in range(len(seq) - 1):
        legs.append(round(leg(D, seq[i], seq[i + 1]) / 60.0, 1))
    flags = []
    if category == "M Crowd" and window == NIGHT and NIGHT < total <= NIGHT_MAX:
        flags.append(f"past 6:30am by {round(total - NIGHT)}min (within 8am hard limit)")
    elif total > window:
        flags.append(f"OVER {window // 60}h by {round(total - window)}min")
    elif total < DAY_MIN and category == "Standard":
        flags.append("light day (<7.5h)")
    if len(stops) < 2 and category not in ("Rotary House",) and \
            stacked_crews == 1 and not joint_with and not allow_single:
        flags.append("single-stop day")
    return {
        "date": date, "dow": DOW.get(date, "?"), "crew": crew,
        "category": category, "stops": ordered, "order_idx": order,
        "install_h": round(install, 2), "drive_min": round(drive, 1),
        "lunch": lunch, "total_min": round(total, 1), "legs": legs,
        "window_min": window,
        "depot_anchored": depot_anchored, "stacked_crews": stacked_crews,
        "half_rows": sorted(half_rows), "joint_with": joint_with,
        "note": note, "flags": flags,
        "zones": sorted({s["zone"] for s in stops}),
        # Forced-first stop (client ordering requirements -- see
        # client_config.json's force_first/lead_names -- plus every joint
        # mega-restaurant lead). Was computed above and thrown away -- the
        # review tool needs it or it re-routes these days wrongly the
        # first time anyone edits them.
        "start_row": start_row,
    }


# ---------------------------------------------------------------------------
# Packing standard clients into crew-days
# ---------------------------------------------------------------------------
def pack_bins(D, pool, by_idx):
    """Proximity-first day clustering, the plot-then-group way.

    1) Plot all points and link them into geographic super-clusters:
       connected components where every member is within RADIUS_S (30 min)
       of some other member. A far-out pocket (Bellville, Clear Lake)
       becomes its own component and never welds to a cross-town stop.
    2) Split each component into BALANCED days (~equal install hours),
       not fill-to-the-brim days — so no leftover crumbs. Every candidate
       day is verified: real install hrs + real drive + lunch <= 10h cap.
    """
    import math

    # ---- 1) connected components under 30-min linkage ----
    remaining = pool[:]
    comps = []
    while remaining:
        comp = [remaining.pop(0)]
        grew = True
        while grew:
            grew = False
            for c in remaining[:]:
                if min(leg(D, c["midx"], x["midx"]) for x in comp) <= RADIUS_S:
                    comp.append(c)
                    remaining.remove(c)
                    grew = True
        comps.append(comp)

    # ---- 2) balanced split of each component ----
    def nn_chain(comp):
        """Order component geographically: nearest-neighbor chain starting
        from its farthest-from-depot member (work the edge inward)."""
        start = max(comp, key=lambda c: leg(D, 0, c["midx"]))
        chain, unv = [start], [c for c in comp if c is not start]
        while unv:
            nxt = min(unv, key=lambda c: leg(D, chain[-1]["midx"], c["midx"]))
            chain.append(nxt)
            unv.remove(nxt)
        return chain

    def fits(day):
        order, drive = route_loop(D, [x["midx"] for x in day])
        return day_totals(sum(x["cal_hours"] for x in day), drive) <= DAY_CAP

    def balanced_split(comp, nd):
        """Slice the NN chain into nd contiguous runs of ~equal install hours.
        Cuts at cumulative-hour quantiles (k/nd of the total), so no run —
        including the tail — can silently absorb the overflow. Contiguity
        along the chain keeps each day geographically tight."""
        chain = nn_chain(comp)
        total = sum(c["cal_hours"] for c in comp)
        days, cur, acc = [], [], 0.0
        for c in chain:
            cur.append(c)
            acc += c["cal_hours"]
            if len(days) < nd - 1 and acc >= total * (len(days) + 1) / nd - 1e-9:
                days.append(cur)
                cur = []
        if cur:
            days.append(cur)
        return days

    def greedy_chain_pack(comp):
        """Fallback that is valid BY CONSTRUCTION: walk the NN chain and
        start a new day whenever adding the next stop would break the cap.
        Used for drive-heavy pockets where hour-quantiles can't balance."""
        days, cur = [], []
        for c in nn_chain(comp):
            trial = cur + [c]
            if not cur or fits(trial):
                cur = trial
            else:
                days.append(cur)
                cur = [c]
        if cur:
            days.append(cur)
        return days

    bins = []
    for comp in comps:
        total = sum(c["cal_hours"] for c in comp)
        split = None
        for nd in range(max(1, math.ceil(total / 7.5)), len(comp) + 1):
            cand = balanced_split(comp, nd)
            if all(fits(day) for day in cand):
                split = cand
                break
        if split is None:  # never emit an unverified day
            split = greedy_chain_pack(comp)
        bins.extend(split)
    return bins


# ---------------------------------------------------------------------------
# Email-driven overrides (client requests / confirmed appointments from the
# joybells Christmas account). These pin specific clients to fixed dates and
# override the generic clubs-on-Mondays rule where a client asked otherwise.
# ---------------------------------------------------------------------------
# Names, pin dates and reasons live in client_config.json -- see
# load_client_config() above.
DROP_CLIENTS = set(CLIENT_CONFIG["drop_clients"].keys())
CARLTON_NICKLAUS = CLIENT_CONFIG["clubs"]["nicklaus"]
CARLTON_OUTDOOR = CLIENT_CONFIG["clubs"]["outdoor"]
CARLTON_FAZIO = CLIENT_CONFIG["clubs"]["fazio"]
WCC_NOV30 = CLIENT_CONFIG["clubs"]["wcc_nov30"]
WCC_PLAYERS = CLIENT_CONFIG["clubs"]["wcc_players"]
ROYAL = CLIENT_CONFIG["clubs"]["royal"]


def main():
    depot, clients, by_row, D = load()
    by_idx = {c["midx"]: c for c in clients if c["midx"] is not None}
    by_name = {c["name"]: c for c in clients}

    routable = [c for c in clients if c["midx"] is not None]
    flagged_noaddr = [c for c in clients if c["no_address"]]

    days = []          # list of crew-day dicts
    assigned_rows = set()
    consumed = set()   # (date, base-crew) slots taken by special/pinned days

    def take(pred):
        got = [c for c in routable if pred(c) and c["row"] not in assigned_rows]
        for c in got:
            assigned_rows.add(c["row"])
        return got

    def names(nlist):
        return take(lambda c: c["name"] in set(nlist))

    # ---- DROP: manual list + anyone the "2026 Install Date" column marks
    #      "No Install" / "No 2026 Install" (client note, not scheduled --
    #      excluded from the map/schedule entirely). ----
    dropped = names(DROP_CLIENTS) + take(lambda c: c.get("install_2026_no_install"))

    # ---- New clients added in the review tool (not in the spreadsheet at
    #      all -- anomaly jobs, callbacks). Give each its own synthetic
    #      matrix node and fold it into the normal client pool so the
    #      freeze-replay below can find it by name like any other client.
    node_latlon = {0: (depot["lat"], depot["lon"])}
    for c in clients:
        if c.get("midx") is not None:
            node_latlon[c["midx"]] = (c["lat"], c["lon"])
    next_synth_row = 900001
    new_clients = load_new_clients()
    for nc in new_clients:
        row = nc.get("row") or next_synth_row
        next_synth_row = max(next_synth_row, row + 1)
        midx = add_synthetic_node(D, node_latlon, nc["lat"], nc["lon"],
                                   out_row=nc.get("outRow"), in_col=nc.get("inCol"))
        rec = {
            "row": row, "name": nc["name"], "street": nc.get("street", ""),
            "city": "", "st": "TX", "zip": "", "area": "", "zone": "",
            "box_count": None, "box_count_sheet": None, "box_verified": False,
            "phone": "", "email": "", "storage": "", "date_2024": "",
            "crew_2025": "", "crew_size_2025": None, "people_needed": None,
            "est_hours": None, "real_hours": None,
            "prior_install_date": "", "business": "Business",
            "category": "Standard", "no_address": False,
            "install_2026_confirmed": "", "install_2026_note": nc.get("notes", ""),
            "install_2026_no_install": False,
            "cal_hours": nc.get("hours") or 1,
            "hours_basis": "manual entry (review tool)",
            "lat": nc["lat"], "lon": nc["lon"],
            "geo_display": "manual (review tool)",
            "geo_source": "street" if nc.get("outRow") else "synthetic",
            "midx": midx,
        }
        clients.append(rec)
        by_row[row] = rec
        by_idx[midx] = rec
        routable.append(rec)
    if new_clients:
        print(f"  NEW CLIENTS (from review tool): {len(new_clients)} -- "
              f"{[c['name'] for c in new_clients]}")

    # ---- THE NOTEBOOK: replay days already promised to clients ----------
    # Applied FIRST, before any other rule, so those clients and their
    # calendar slots are claimed and nothing downstream can re-plan them.
    # This is a FROZEN ASSIGNMENT layer, not a set of constraints to
    # re-solve around: once dates have gone out, the right answer to an
    # updated spreadsheet is minimum perturbation, not a better schedule
    # that moves 30 people who were already told when to expect us.
    by_client_name = {c["name"]: c for c in routable}
    frozen_days, frozen_names, missing_names = [], set(), []
    # A joint job appears on BOTH crews' cards, so the same client is
    # legitimately named by two override days. Claim names only after every
    # override day has been read, or the second card comes out empty.
    claimed_here = set()
    for od in load_overrides():
        stops = []
        for nm in od.get("stops", []):
            c = by_client_name.get(nm)
            if c is None:
                missing_names.append(nm)
                continue
            # already taken by an EARLIER rule (e.g. dropped), or by a
            # previous non-joint override day -- skip
            if c["row"] in assigned_rows:
                continue
            if c["row"] in claimed_here and not od.get("joint"):
                continue
            stops.append(c)
        if not stops:
            continue
        for c in stops:
            claimed_here.add(c["row"])
            frozen_names.add(c["name"])
        half = {c["row"] for c in stops if c["name"] in set(od.get("half") or ())}
        start = next((c["row"] for c in stops if c["name"] == od.get("startRow")), None)
        frozen_days.append(build_day(
            D, od["crew"], od["date"], stops, by_idx,
            od.get("cat", "Standard"),
            depot_anchored=od.get("anchored", True),
            stacked_crews=od.get("stacked", 1),
            window=od.get("win"), lunch=od.get("lunch"),
            half_rows=half, start_row=start,
            joint_with=od.get("joint", "") or "",
            allow_single=True,
            note=od.get("note", "")))
        consumed.add((od["date"], od["crew"]))
    assigned_rows.update(claimed_here)
    days.extend(frozen_days)
    if frozen_days:
        print(f"  NOTEBOOK: froze {len(frozen_days)} crew-day(s), "
              f"{len(frozen_names)} client(s) held to their promised date")
        if missing_names:
            print(f"    !! {len(missing_names)} name(s) in the notebook are no "
                  f"longer in the spreadsheet: {sorted(set(missing_names))}")

    # ---- Rule 1: Mi Cocina / M Crowd — NIGHT SHIFTS 11pm-6am (7h incl drive),
    #      as few nights as possible, tight geographic groupings. ----
    dallas = take(lambda c: c["category"] == "M Crowd")

    def fits_night(stops, stacked=1):
        idxs = [s["midx"] for s in stops]
        if len(idxs) == 1:
            drive = 0.0
        elif len(idxs) <= 8:
            _, drive = route_exact(D, idxs, False)
        else:
            _, drive = route_open(D, idxs)
        return (sum(s["cal_hours"] for s in stops) / stacked) * 60 + drive <= NIGHT

    # PACE CALIBRATION from 2025 actuals: crews did 3-4 restaurants per
    # night (Nov 10/11/15 each had 4). The precisely-timed installs cluster
    # at ~2.2h; the uniform "3.0" entries are block estimates that would
    # make those observed nights impossible in a 7h window. Recalibrate the
    # flat 3.0s to the measured median so planning matches the crew's real
    # 3-per-night pace. Megas (Lake Highlands, Highland Park) stay as-is.
    import statistics as _st
    mega = [c for c in dallas if c["cal_hours"] * 60 > NIGHT]
    _precise = [c["real_hours"] for c in dallas
                if c not in mega and c.get("real_hours")
                and abs(c["real_hours"] - 3.0) > 0.01]
    _pace = round(_st.median(_precise), 2) if _precise else 2.17
    for c in dallas:
        if c in mega:
            continue
        if c.get("real_hours") and abs(c["real_hours"] - 3.0) <= 0.01:
            c["cal_hours"] = _pace
            c["hours_basis"] = "MiCo pace (3/night)"
    # M CROWD CORPORATE OFFICE: the ONE daytime install — client requires
    # normal business hours (start after 9am, done before 5pm). Arrival-day
    # plan: drive up Monday morning, install 9-5 window, hotel + sleep,
    # then the first night shift starts Monday 11pm.
    corp = [c for c in dallas if CLIENT_CONFIG["corp_name_substr"] in c["name"]]
    for c in corp:
        days.append(build_day(
            D, "Crew 3", DALLAS_DAYS[0], [c], by_idx, "M Crowd",
            depot_anchored=False, stacked_crews=1, window=480, lunch=0,
            allow_single=True,
            note="DAYTIME install — client requires business hours (9am-5pm). "
                 "Arrival day: drive up Monday morning, start after 9am, done "
                 "well before 5pm, then hotel before the first night shift."))
    dallas = [c for c in dallas if c not in corp]
    mega = [c for c in mega if c not in corp]
    normal = [c for c in dallas if c not in mega]

    # Mega restaurants need 2 crews stacked; each stacked bin may absorb
    # one nearby rider. Then split the rest into the FEWEST solo routes
    # that fit the 7h night; nights = ceil(total crew slots / 3 crews).
    night_bins = []  # (stops, stacked_crews)
    for mstop in sorted(mega, key=lambda c: -c["cal_hours"]):
        grp = [mstop]
        while True:  # absorb nearest riders while the stacked night fits
            added = False
            for c in sorted(normal, key=lambda c: min(
                    leg(D, c["midx"], x["midx"]) for x in grp)):
                if fits_night(grp + [c], 2):
                    grp.append(c)
                    normal.remove(c)
                    added = True
                    break
            if not added:
                break
        night_bins.append((grp, 2))

    # Remaining restaurants: geographic NN chain across DFW (west -> east),
    # sliced at cumulative-hour quantiles into EXACTLY solo_target balanced
    # routes, then a swap/size-repair pass for tight legs and no singles.
    def night_drive(stops):
        if len(stops) <= 1:
            return 0.0
        _, drv = route_exact(D, [s["midx"] for s in stops], False)
        return drv

    def um(stops):
        """Route is under the 6.5h night minimum."""
        return sum(c["cal_hours"] for c in stops) * 60 + \
            night_drive(stops) < NIGHT_MIN

    if normal:
        start = min(normal, key=lambda c: c["lon"])  # start Fort Worth side
        chain, unv = [start], [c for c in normal if c is not start]
        while unv:
            nxt = min(unv, key=lambda c: leg(D, chain[-1]["midx"], c["midx"]))
            chain.append(nxt)
            unv.remove(nxt)

        # DP over chain positions: FEWEST fitting routes, then fewest routes
        # under the 6.5h minimum (those must fit on the buffer night), then
        # least drive.
        n = len(chain)
        INF = (10 ** 9, 10 ** 9, 10 ** 9)
        dp = [INF] * (n + 1)
        dp[0] = (0, 0, 0.0)
        cut_at = [0] * (n + 1)
        for i in range(1, n + 1):
            for j in range(max(0, i - 6), i):
                run = chain[j:i]
                if not fits_night(run, 1):
                    continue
                drv = night_drive(run)
                rm = sum(c["cal_hours"] for c in run) * 60 + drv
                cand = (dp[j][0] + 1,
                        dp[j][1] + (1 if rm < NIGHT_MIN else 0),
                        dp[j][2] + drv)
                if cand < dp[i]:
                    dp[i] = cand
                    cut_at[i] = j
        runs, i = [], n
        while i > 0:
            j = cut_at[i]
            runs.append(chain[j:i])
            i = j
        solo_bins = runs[::-1]

        # size repair: pull the nearest stop out of a 3+ bin into any single
        changed = True
        while changed:
            changed = False
            for i, b in enumerate(solo_bins):
                if len(b) != 1:
                    continue
                best = None
                for j, ob in enumerate(solo_bins):
                    if j == i or len(ob) < 3:
                        continue
                    for c in ob:
                        dmin = min(leg(D, c["midx"], x["midx"]) for x in b)
                        if fits_night(b + [c], 1) and \
                           (best is None or dmin < best[0]):
                            best = (dmin, j, c)
                if best:
                    _, j, c = best
                    solo_bins[j].remove(c)
                    solo_bins[i].append(c)
                    changed = True

        # improvement pass: swaps always; moves only from 3+ bins (so the
        # fixed route count and no-singles property are preserved)
        improved = True
        while improved:
            improved = False
            for a in range(len(solo_bins)):
                for b in range(len(solo_bins)):
                    if a == b:
                        continue
                    A, B = solo_bins[a], solo_bins[b]
                    base = night_drive(A) + night_drive(B)
                    for x in list(A):
                        if len(A) <= 2:
                            break
                        A2, B2 = [s for s in A if s is not x], B + [x]
                        if fits_night(B2, 1) and \
                           um(A2) + um(B2) <= um(A) + um(B) and \
                           night_drive(A2) + night_drive(B2) < base - 0.5:
                            solo_bins[a], solo_bins[b] = A2, B2
                            improved = True
                            break
                    if improved:
                        break
                    for x in list(A):
                        for y in list(B):
                            A2 = [s for s in A if s is not x] + [y]
                            B2 = [s for s in B if s is not y] + [x]
                            if fits_night(A2, 1) and fits_night(B2, 1) and \
                               um(A2) + um(B2) <= um(A) + um(B) and \
                               night_drive(A2) + night_drive(B2) < base - 0.5:
                                solo_bins[a], solo_bins[b] = A2, B2
                                improved = True
                                break
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break

        # cross pass: a stacked bin's rider (non-mega stop) may trade places
        # with a solo stop when that shortens total drive — e.g. Lakewood
        # rides with Lake Highlands only if no better neighbor exists.
        def cross_swap_once():
            for sbi, (Sg, st) in enumerate(night_bins):
                if st != 2:
                    continue
                for x in [s for s in Sg if s not in mega]:
                    for bi, B in enumerate(solo_bins):
                        for y in B:
                            S2 = [s for s in Sg if s is not x] + [y]
                            B2 = [s for s in B if s is not y] + [x]
                            if fits_night(S2, 2) and fits_night(B2, 1) and \
                               night_drive(S2) + night_drive(B2) < \
                               night_drive(Sg) + night_drive(B) - 0.5:
                                night_bins[sbi] = (S2, 2)
                                solo_bins[bi] = B2
                                return True
            return False

        while cross_swap_once():
            pass
        night_bins.extend((b, 1) for b in solo_bins)

    # Assign to nights: every night runs ALL 3 CREWS, and same-night crews
    # work NEAR each other (mutual troubleshooting; an early finisher can
    # go assist). We brute-force the grouping of routes into nights,
    # minimizing the crew-to-crew drive within each night. A stacked bin
    # claims 2 of its night's 3 crew slots, so it pairs with one solo
    # route; the remaining solos form nights of up to 3 routes.
    import math as _m2
    import itertools as _it
    slots_needed = sum(2 if st == 2 else 1 for _, st in night_bins)
    N_NIGHTS = _m2.ceil(slots_needed / 3)
    if N_NIGHTS > len(DALLAS_DAYS):
        raise RuntimeError("Mi Cocina week overflow — check night packing")

    stacked_b = [b for b in night_bins if b[1] == 2]
    solos_b = [b for b in night_bins if b[1] == 1]

    def inter_route(a, b):
        """Crew-to-crew proximity: closest stop-pair drive (min), minutes."""
        return min(min(leg(D, x["midx"], y["midx"]), leg(D, y["midx"], x["midx"]))
                   for x in a[0] for y in b[0]) / 60.0

    def partitions(items, ngroups, maxsize=3):
        """All ways to split items into ngroups unordered groups <= maxsize."""
        if ngroups <= 0:
            # Nothing left to place (every Dallas night came back frozen
            # from the notebook) -- the empty plan is the only plan.
            if not items:
                yield []
            return
        if ngroups == 1:
            if len(items) <= maxsize:
                yield [list(items)]
            return
        first = items[0]
        rest = items[1:]
        for size in range(0, min(maxsize, len(items)) + 1):
            for mates in _it.combinations(rest, size - 1) if size >= 1 else []:
                grp = [first] + list(mates)
                remaining = [x for x in rest if x not in mates]
                for sub in partitions(remaining, ngroups - 1, maxsize):
                    yield [grp] + sub

    free_nights = N_NIGHTS - len(stacked_b)
    best_cost, best_plan = None, None
    for comb in _it.permutations(range(len(solos_b)), len(stacked_b)):
        anchored = [[stacked_b[k], solos_b[comb[k]]]
                    for k in range(len(stacked_b))]
        rest = [solos_b[i] for i in range(len(solos_b)) if i not in comb]
        for grouping in partitions(rest, free_nights):
            nights = anchored + grouping
            cost = sum(inter_route(a, b)
                       for night in nights
                       for a, b in _it.combinations(night, 2))
            # under-min routes must share ONE night (the buffer)
            um_nights = sum(1 for night in nights
                            if any(st == 1 and um(grp) for grp, st in night))
            cost += 900 * max(0, um_nights - 1)
            if best_cost is None or cost < best_cost:
                best_cost, best_plan = cost, nights
    plan = best_plan
    _prox = sum(inter_route(a, b) for night in plan
                for a, b in _it.combinations(night, 2))
    print(f"  Mi Cocina co-location: avg crew-to-crew distance "
          f"{_prox / max(1, sum(len(n) * (len(n) - 1) // 2 for n in plan)):.0f} min")

    # FRONT-LOAD the week (user rule): after the forced mega nights, assign
    # the remaining night-groups to dates heaviest-first, so the LAST night
    # is the lightest — the buffer for overruns, pushes, and loose ends.
    def route_min(b):
        grp, st = b
        return (sum(c["cal_hours"] for c in grp) / st) * 60 + night_drive(grp)
    anchored_n = [n for n in plan if any(st == 2 for _, st in n)]
    free_n = sorted((n for n in plan if n not in anchored_n),
                    key=lambda n: (any(st == 1 and um(grp) for grp, st in n),
                                   -sum(route_min(b) for b in n)))
    plan = anchored_n + free_n

    # TOP-UP pass (user rule): every night except the LAST must carry
    # 6.5-7.5h of work. A route under the minimum pulls its nearest
    # neighbor stop from the latest possible night (last night donates
    # first — it is the buffer and has no minimum); a non-last donor
    # never drops below the minimum itself.
    for ni in range(len(plan) - 1):
        for grp, st in plan[ni]:
            if st != 1:
                continue
            while route_min((grp, 1)) < NIGHT_MIN:
                best = None
                for nj in range(len(plan) - 1, ni, -1):
                    for g2, s2 in plan[nj]:
                        if s2 != 1 or len(g2) <= 1:
                            continue
                        donor_is_last = (nj == len(plan) - 1)
                        for c in g2:
                            rem = [x for x in g2 if x is not c]
                            if not donor_is_last and \
                               route_min((rem, 1)) < NIGHT_MIN:
                                continue
                            dmin = min(leg(D, c["midx"], x["midx"]) for x in grp)
                            if dmin <= RADIUS_S and fits_night(grp + [c], 1) \
                               and (best is None or dmin < best[0]):
                                best = (dmin, g2, c)
                    if best is not None:
                        break
                if best is None:
                    break
                _, g2, c = best
                g2.remove(c)
                grp.append(c)
                print(f"  top-up: {c['name'].replace('M Crowd ', '')} pulled "
                      f"forward to night {ni + 1}")

    for di, night in enumerate(plan):
        avail = list(CREWS)
        buff = (" LAST NIGHT kept light on purpose — buffer for pushed stops "
                "and loose ends.") if di == len(plan) - 1 else ""
        for stops, stacked in night:
            if stacked == 2:
                # JOINT NIGHT, one card PER CREW: both crews meet at the mega
                # restaurant at 11pm (each carries half its hours), then each
                # crew splits off to its own nearby stops.
                mega_stop = next(s for s in stops if s in mega)
                riders = [s for s in stops if s is not mega_stop]
                crews2, avail = avail[:2], avail[2:]
                sides = {cr: [] for cr in crews2}
                for r in sorted(riders, key=lambda c: -c["cal_hours"]):
                    side = min(crews2,
                               key=lambda cr: sum(x["cal_hours"] for x in sides[cr]))
                    sides[side].append(r)
                for cr in crews2:
                    other = crews2[1] if cr == crews2[0] else crews2[0]
                    mname = mega_stop["name"].replace("M Crowd ", "")
                    days.append(build_day(
                        D, cr, DALLAS_DAYS[di], [mega_stop] + sides[cr], by_idx,
                        "M Crowd", depot_anchored=False, stacked_crews=1,
                        window=NIGHT, lunch=0,
                        half_rows={mega_stop["row"]}, start_row=mega_stop["row"],
                        joint_with=other,
                        note=f"JOINT: both crews open {mname} together at 11pm "
                             f"(hours split with {other}), then each runs its "
                             f"own stops. Mi Cocina night 11pm-6am incl drive."
                             + buff))
            else:
                crew = avail.pop(0)
                days.append(build_day(D, crew, DALLAS_DAYS[di], stops, by_idx,
                                      "M Crowd", depot_anchored=False,
                                      stacked_crews=1, window=NIGHT, lunch=0,
                                      note="Mi Cocina night shift 11pm-6am incl "
                                           "drive; 3 crews every night; "
                                           "Crew 1 + Crew 2 both on Dallas trip"
                                           + buff))
    used = sum(1 for n in plan if n)
    print(f"  Mi Cocina: 3 crews x {used} nights "
          f"({len(night_bins)} crew-nights)")

    # ---- Rule 3: Capital Banks, Fri Nov 27 -- ALL 8 branches, ONE crew, ONE
    #      day (user, 2026-07-31: "keep capital bank in one group, it can
    #      break the rules"). Baytown (east) to Katy (west) spans the full
    #      Houston metro, so this deliberately blows the normal 10h cap and
    #      the absolute 8am-8pm legal window -- window set generously wide
    #      on purpose; Crew 1 stays free for the client-requested Carlton
    #      Woods club the same Friday. ----
    banks = take(lambda c: c["category"] == "Capital Bank")
    if banks:      # empty when the notebook already froze the bank Friday
        days.append(build_day(D, "Crew 2", BANK_FRIDAY, banks, by_idx, "Capital Bank",
                              window=960,
                              note="All 8 banks in one crew, one day per client "
                                   "request -- spans the full Houston metro "
                                   "(Baytown to Katy), so this intentionally runs "
                                   "well past the normal 10h cap."))
    consumed.update({(BANK_FRIDAY, "Crew 2"), (BANK_FRIDAY, "Crew 1")})

    # ---- Rule 4: Rotary House, Sunday Nov 29 ----
    rotary = take(lambda c: c["category"] == "Rotary House")
    if rotary:
        days.append(build_day(D, "Crew 3", ROTARY_SUNDAY, rotary, by_idx,
                              "Rotary House", note="Only allowed Sunday (business exception)"))
        consumed.add((ROTARY_SUNDAY, "Crew 3"))

    # ---- Claim pinned (email-dated) clients before the standard pool forms ----
    brenda = take(lambda c: c["category"] == CLIENT_CONFIG["single_crew_priority"]["category"])
    nicklaus = names([CARLTON_NICKLAUS])
    outdoor = names([CARLTON_OUTDOOR])
    fazio = names([CARLTON_FAZIO])
    wcc30 = names(WCC_NOV30)                      # Palmer, Legacy, Trails
    players = names([WCC_PLAYERS])
    royal = names([ROYAL]) + take(lambda c: c["category"] == "Country Club")  # +any stray
    marek = names(CLIENT_CONFIG["pairing_names"]["marek"])
    sims_darcy = names(CLIENT_CONFIG["pairing_names"]["sims_darcy"])  # confirmed 2026-12-02

    # One client's geocode used to send them through a manual isolation
    # pairing here (user, 2026-08-01: fixed a bad address parse that made
    # them look ~35mi from where they actually are) -- removed, they now
    # fall through to the standard pool and cluster normally.

    # Two clients stay a manual pin even after their address was corrected,
    # because the automatic packer's alternative placement was worse and
    # neither has a meaningfully closer option regardless (user, 2026-08-01
    # -- see client_config.json's pairing_notes.musser_serenity for detail).
    musser_serenity = names(CLIENT_CONFIG["pairing_names"]["musser_serenity"])

    # Rule (user, 2026-07-31): one client's house needs 2 full crews to
    # complete -- combined with 2 close neighbors into one 2-crew joint day
    # instead of splitting across two separate single-crew days. See
    # client_config.json's pairing_notes.two_crew_woodlands.
    two_crew_woodlands = names(CLIENT_CONFIG["pairing_names"]["two_crew_woodlands"])

    # Rule (user, 2026-07-31): one client is uncertain to happen at all --
    # kept fully standalone (easy to cancel without disrupting anyone else)
    # instead of paired with another. See pairing_notes.mercedes.
    mercedes = names(CLIENT_CONFIG["pairing_names"]["mercedes"])
    # A third client goes onto this pairing's day instead (client note: not
    # the other 2 club days, already full). See pairing_notes.hampton_crane_waterway.
    hampton_crane_waterway = names(CLIENT_CONFIG["pairing_names"]["hampton_crane_waterway"])

    # Rule (user, 2026-07-31): two clients ~1.3min apart (essentially the
    # same address) but on separate days 5 weeks apart -- moved onto one
    # day. Fits comfortably inside the normal 10h cap -- no exception
    # needed. See pairing_notes.sullivan_mattix.
    sullivan_mattix = names(CLIENT_CONFIG["pairing_names"]["sullivan_mattix"])

    # Rule (user, 2026-07-31): one client was alone; 2 others 17-21min away
    # had spare room. Combined day runs ~10h44m -- a modest exception past
    # the normal 10h cap. See pairing_notes.citizens_ingram_northside.
    citizens_ingram_northside = names(CLIENT_CONFIG["pairing_names"]["citizens_ingram_northside"])

    # Rule (2026 Install Date column, client note "1/3, 2/3, 3/3 Same Day"):
    # one client's 3 locations must be worked in one visit. All 3 fit
    # comfortably inside the normal 10h cap (~7h26m total), so no exception
    # needed here.
    a_hug_away = names(CLIENT_CONFIG["pairing_names"]["a_hug_away"])
    if a_hug_away:
        days.append(build_day(
            D, "Crew 3", "2026-11-12", a_hug_away, by_idx, "Standard",
            note=CLIENT_CONFIG["pairing_notes"]["a_hug_away"]))
        consumed.add(("2026-11-12", "Crew 3"))

    # Rule (2026 Install Date column, client note): two clients must be
    # worked the SAME day, one of them FIRST (their boxes are stored at the
    # other's location). Combined install alone is 10h45m -- already past
    # the normal cap before any drive -- so this is an explicit exception
    # (same generous window as Capital Bank), pinned first via start_row
    # per the client's stated order requirement.
    lewis_lts = names(CLIENT_CONFIG["pairing_names"]["lewis_lts"])
    if lewis_lts:
        lts_row = next(c["row"] for c in lewis_lts
                       if c["name"] == CLIENT_CONFIG["lead_names"]["lewis_lts"])
        days.append(build_day(
            D, "Crew 1", "2026-11-13", lewis_lts, by_idx, "Standard",
            window=960, start_row=lts_row,
            note=CLIENT_CONFIG["pairing_notes"]["lewis_lts"]))
        consumed.add(("2026-11-13", "Crew 1"))

    # Rule (user, 2026-07-31): one client's 3 Bellville locations (house,
    # office, store) must all be worked in ONE visit rather than split
    # across two trips. Bellville is ~70min each way from depot, so this
    # trades 2 depot round-trips for 1 (net LESS total drive across the
    # week) at the cost of a single long day (~11h40m). Explicit exception
    # to the normal 10h cap, capped instead at the absolute 8am-8pm legal
    # window -- same pattern as the M Crowd Corporate Office exception above.
    kerri_byler = names(CLIENT_CONFIG["pairing_names"]["kerri_byler"])
    if kerri_byler:
        days.append(build_day(
            D, "Crew 2", "2026-11-17", kerri_byler, by_idx, "Standard",
            window=WINDOW,
            note=CLIENT_CONFIG["pairing_notes"]["kerri_byler"]))
        consumed.add(("2026-11-17", "Crew 2"))

    # Rule (user, 2026-07-31): one client was sitting alone on a light
    # single-stop day; her only real neighbor (Clear Lake/Bay Area, ~19min
    # away) was ALSO a lone single-stop day elsewhere -- pairing them cuts
    # one full depot round-trip AND a duplicate lunch (~2h net savings
    # across the week), at the cost of a single ~10h53m day. Same
    # absolute-window exception as the Bellville 3-location client above.
    # Client OK with any date the last week of November.
    schultea_pitcock = names(CLIENT_CONFIG["pairing_names"]["schultea_pitcock"])
    if schultea_pitcock:
        days.append(build_day(
            D, "Crew 1", "2026-11-23", schultea_pitcock, by_idx, "Standard",
            window=WINDOW,
            note=CLIENT_CONFIG["pairing_notes"]["schultea_pitcock"]))
        consumed.add(("2026-11-23", "Crew 1"))

    # Rule (user, 2026-08-01): kept as a manual pin even after an address
    # fix because the automatic packer's alternative (splitting them into
    # two separate single-stop days) was worse, and one client has no
    # meaningfully closer option regardless. See pairing_notes.musser_serenity.
    if musser_serenity:
        days.append(build_day(
            D, "Crew 2", "2026-11-13", musser_serenity, by_idx, "Standard",
            window=780,
            note=CLIENT_CONFIG["pairing_notes"]["musser_serenity"]))
        consumed.add(("2026-11-13", "Crew 2"))

    # Rule (user, 2026-07-31): one client is uncertain to even happen --
    # keep it fully standalone so it can be dropped without disrupting
    # anyone else.
    if mercedes:
        days.append(build_day(D, "Crew 1", "2026-12-02", mercedes, by_idx,
                              "Standard", allow_single=True,
                              note=CLIENT_CONFIG["pairing_notes"]["mercedes"]))
        consumed.add(("2026-12-02", "Crew 1"))

    # Rule (user, 2026-07-31): a third client goes with this pairing's day
    # instead (client note: not the other 2 club days, which are already
    # full) -- reasonably close (~20min). See pairing_notes.hampton_crane_waterway.
    if hampton_crane_waterway:
        days.append(build_day(
            D, "Crew 3", "2026-12-01", hampton_crane_waterway, by_idx, "Standard",
            note=CLIENT_CONFIG["pairing_notes"]["hampton_crane_waterway"]))
        consumed.add(("2026-12-01", "Crew 3"))

    # Rule (user, 2026-07-31): two clients ~1.3min apart, moved onto one
    # existing day. See pairing_notes.sullivan_mattix.
    if sullivan_mattix:
        days.append(build_day(
            D, "Crew 3", "2026-11-17", sullivan_mattix, by_idx, "Standard",
            note=CLIENT_CONFIG["pairing_notes"]["sullivan_mattix"]))
        consumed.add(("2026-11-17", "Crew 3"))

    # Rule (user, 2026-07-31): 3 clients 17-21min apart, combined instead of
    # one sitting alone. See pairing_notes.citizens_ingram_northside.
    if citizens_ingram_northside:
        days.append(build_day(
            D, "Crew 3", "2026-11-25", citizens_ingram_northside, by_idx,
            "Standard", window=680,
            note=CLIENT_CONFIG["pairing_notes"]["citizens_ingram_northside"]))
        consumed.add(("2026-11-25", "Crew 3"))

    # Rule (user, 2026-07-31): one client always wants a 9am start -- pinned
    # first in the route (start_row) on her existing day. Moved off Nov 9 ->
    # Nov 17 (user, 2026-08-01: round-1 no longer starts that early; Nov 17
    # is Crew 1's first open weekday in the new window). start_row (9am-
    # first) is independent of which date carries the day.
    roane_day = names(CLIENT_CONFIG["pairing_names"]["roane_day"])
    if roane_day:
        roane_row = next(c["row"] for c in roane_day
                         if c["name"] == CLIENT_CONFIG["lead_names"]["roane_day"])
        days.append(build_day(D, "Crew 1", "2026-11-17", roane_day, by_idx,
                              "Standard", start_row=roane_row,
                              note=CLIENT_CONFIG["pairing_notes"]["roane_day"]))
        consumed.add(("2026-11-17", "Crew 1"))

    # Rule (user, 2026-07-31): one client likes to go first -- pinned first
    # in the route (start_row) instead of last. Moved off Nov 9 -> Nov 13
    # (user, 2026-08-01: round-1 no longer starts that early; Nov 13 is
    # Crew 3's first open weekday in the new window).
    jinks_day = names(CLIENT_CONFIG["pairing_names"]["jinks_day"])
    if jinks_day:
        jinks_row = next(c["row"] for c in jinks_day
                         if c["name"] == CLIENT_CONFIG["lead_names"]["jinks_day"])
        days.append(build_day(D, "Crew 3", "2026-11-13", jinks_day, by_idx,
                              "Standard", start_row=jinks_row,
                              note=CLIENT_CONFIG["pairing_notes"]["jinks_day"]))
        consumed.add(("2026-11-13", "Crew 3"))

    standard = take(lambda c: True)              # everything still unassigned

    def fill_nearby(seeds, n):
        """Pull up to n standard clients from the pinned day's OWN neighborhood
        (within RADIUS_S of the group) while the day stays under the 10h cap."""
        if not seeds or n <= 0:
            return []
        picked = []
        while len(picked) < n:
            grp = seeds + picked
            cands = [c for c in standard if c not in picked and
                     min(leg(D, c["midx"], x["midx"]) for x in grp) <= RADIUS_S]
            cands.sort(key=lambda c: min(leg(D, c["midx"], x["midx"]) for x in grp))
            added = False
            for c in cands:
                trial = grp + [c]
                _, drive = route_loop(D, [x["midx"] for x in trial])
                if day_totals(sum(x["cal_hours"] for x in trial), drive) <= DAY_CAP:
                    picked.append(c)
                    added = True
                    break
            if not added:
                break
        for c in picked:
            standard.remove(c)
        return picked

    def pin_day(crew, date, seeds, category, note, fill=0, stacked=1, base_crews=None):
        if not seeds:
            return
        stops = list(seeds) + fill_nearby(seeds, fill)
        days.append(build_day(D, crew, date, stops, by_idx, category,
                              stacked_crews=stacked, note=note))
        for bc in (base_crews or [crew]):
            consumed.add((date, bc))

    def joint_convoy(crews2, date, stops, category, note):
        """A required two-crew joint job, one card PER CREW: both crews work
        every stop together (each side carries half the hours), identical
        route on both cards."""
        if not stops:      # already frozen by the notebook
            return
        rows = {s["row"] for s in stops}
        for cr in crews2:
            other = crews2[1] if cr == crews2[0] else crews2[0]
            days.append(build_day(D, cr, date, list(stops), by_idx, category,
                                  stacked_crews=1, half_rows=rows,
                                  joint_with=other,
                                  note=note + f" (working jointly with {other}'s crew)"))
            consumed.add((date, cr))

    # Rule (user, 2026-07-31): one client's house needs 2 full crews to
    # complete it -- combined with 2 close Woodlands neighbors into ONE
    # 2-crew joint day instead of splitting across 2 separate single-crew
    # days. See pairing_notes.two_crew_woodlands.
    if two_crew_woodlands:
        joint_convoy(["Crew 1", "Crew 2"], "2026-11-12", two_crew_woodlands,
                     "Standard", CLIENT_CONFIG["pairing_notes"]["two_crew_woodlands"])

    # Rule (user, 2026-07-31): one client does NOT need two separate crews
    # dispatched to her -- she needs a well-staffed SINGLE crew (extra
    # hands), freeing the other crew for its own independent work that day.
    # A previously force-attached "nearby residence" fill only needs 1 crew
    # too -- released back to the standard pool for its own normal placement.
    pin_day("Crew 1", "2026-11-24", brenda, "Standard",
            CLIENT_CONFIG["pairing_notes"]["brenda"], fill=2)

    # --- Email-pinned clubs & appointments (client requests win over Mondays rule) ---
    joint_convoy(["Crew 1", "Crew 2"], "2026-11-30", wcc30, "Country Club",
                 CLIENT_CONFIG["pairing_notes"]["wcc30"])
    pin_day("Crew 3", "2026-11-30", marek, "Standard",
            CLIENT_CONFIG["pairing_notes"]["marek"], fill=3)
    # Rule (user, 2026-07-31): this club is a 2-crew SOLE FOCUS day -- no
    # fill. (2 clients previously fill here, return to the standard pool
    # for their own normal placement.)
    joint_convoy(["Crew 1", "Crew 2"], "2026-11-25", players, "Country Club",
                 CLIENT_CONFIG["pairing_notes"]["players"])
    # Rule (user, 2026-07-31): split this club's 2 jobs (one stays Fri
    # 11/27, the other moves to Sat 11/28) per client.
    pin_day("Crew 1", "2026-11-27", nicklaus, "Country Club",
            CLIENT_CONFIG["pairing_notes"]["nicklaus"])
    pin_day("Crew 1", "2026-11-28", outdoor, "Country Club",
            CLIENT_CONFIG["pairing_notes"]["outdoor"])
    pin_day("Crew 1", "2026-12-01", fazio, "Country Club",
            CLIENT_CONFIG["pairing_notes"]["fazio"], fill=2)
    pin_day("Crew 1", "2026-11-16", royal, "Country Club",
            CLIENT_CONFIG["pairing_notes"]["royal"], fill=3)
    pin_day("Crew 2", "2026-12-02", sims_darcy, "Standard",
            CLIENT_CONFIG["pairing_notes"]["sims_darcy"], fill=2)

    # Rule (user, 2026-07-30): NOBODY on a Saturday unless their 2025
    # install was ALSO on a Saturday. Businesses were already weekend-
    # excluded; this restricts residences too. Split the Saturday-history
    # clients out and cluster them separately BEFORE the general geographic
    # packing, so a Saturday-eligible client never gets welded into a bin
    # with an ineligible neighbor (which would make the whole bin
    # ineligible) -- and so ordinary weekday packing doesn't quietly count
    # on Saturday capacity that no longer exists for most clients.
    def prior_was_saturday(c):
        d = c.get("prior_install_date", "")
        if not d or len(d) < 10:
            return False
        try:
            return datetime.date.fromisoformat(d[:10]).weekday() == 5  # Sat
        except ValueError:
            return False

    sat_eligible = [c for c in standard
                    if c["business"] == "Residence" and prior_was_saturday(c)]
    for c in sat_eligible:
        standard.remove(c)
    print(f"  Saturday-eligible (2025 install was a Saturday): "
          f"{[c['name'] for c in sat_eligible]}")

    sat_bins = merge_singletons(D, pack_bins(D, sat_eligible, by_idx)) \
        if sat_eligible else []

    # Rule (user, 2026-07-31): a Saturday-eligible client with NO other
    # Saturday-eligible client nearby gets nothing out of a lone Saturday
    # slot -- send them back to the standard weekday pool, where they can
    # pair with their REAL geographic neighbors instead of sitting alone
    # (eligibility is a ceiling, not a floor -- see rule above).
    sat_singles = [b for b in sat_bins if len(b) == 1]
    sat_bins = [b for b in sat_bins if len(b) != 1]
    for b in sat_singles:
        standard.extend(b)
        print(f"  Saturday-eligible, no eligible neighbor nearby -> back to "
              f"weekday pool: {[c['name'] for c in b]}")

    bins = pack_bins(D, standard, by_idx)
    bins = merge_singletons(D, bins)

    # classify the (Saturday-ineligible) remainder: business vs residence
    # is no longer a Saturday/weekday split -- both are weekday-only now.
    biz_bins, res_bins = [], []
    for b in bins:
        (res_bins if all(x["business"] == "Residence" for x in b) else biz_bins).append(b)

    # calendar slots: Nov 9 & 16 Mondays are freed (clubs moved to client dates);
    # exclude any (date, crew) already consumed by special/pinned days.
    weekday_slots = [(dt, cr) for dt in STD_WEEKDAYS for cr in CREWS
                     if (dt, cr) not in consumed]
    sat_slots = [(dt, cr) for dt in SATURDAYS for cr in CREWS
                 if (dt, cr) not in consumed]
    # Fill dates that already have a pinned/special day FIRST, so a
    # client-pinned date runs all 3 crews instead of one lone crew while
    # the others idle. Houston installs must START Monday Nov 9 (user
    # rule, 2026-07-31) -- treated with the same top priority as a pinned
    # date so it's always the very first date filled. Among the rest of
    # the UNpinned dates, fill the latest ones first (prefer any leftover
    # gap land later in the season, not stranded between two working
    # days). The true overflow tail (used only if November genuinely
    # runs out of room) stays last-resort and chronological.
    pinned_dates = {dt for (dt, cr) in consumed}

    def _ord(dt):
        return datetime.date.fromisoformat(dt).toordinal()

    def _tier(dt):
        if dt in pinned_dates or dt in FORCE_START:
            return 0
        if dt in OVERFLOW_TAIL:
            return 2
        return 1
    weekday_slots.sort(key=lambda s: (_tier(s[0]),
                                      -_ord(s[0]) if _tier(s[0]) == 1 else _ord(s[0])))

    slot_load = defaultdict(float)
    assignments = []

    unplaced = []

    # Prefer landing a bin close to its clients' prior-year date (user,
    # 2026-08-01: "as close to the dates from 2025 as possible" -- 2025 is
    # the primary reference, 2024 a backup when 2025 is missing). A client
    # whose 2026 note flags their prior date as a mistake (installed too
    # late, etc.) is excluded from the average -- anchoring near a date we
    # already know was wrong would just repeat it.
    def prior_target_ord(bin_stops):
        ords = []
        for s in bin_stops:
            note = (s.get("install_2026_note") or "").lower()
            if "too late" in note or "needs to be earlier" in note:
                continue
            d = s.get("prior_install_date") or s.get("date_2024")
            if not d or len(d) < 10:
                continue
            try:
                ords.append(_ord(d[:10]))
            except ValueError:
                continue
        return sum(ords) / len(ords) if ords else None

    def place(bin_stops, slot_pool):
        if not slot_pool:
            unplaced.append(bin_stops)
            return None
        target = prior_target_ord(bin_stops)
        if target is not None:
            slot = min(slot_pool,
                       key=lambda s: (abs(_ord(s[0]) - target), slot_load[s]))
        else:
            slot = min(slot_pool, key=lambda s: slot_load[s])
        slot_pool.remove(slot)
        slot_load[slot] += sum(x["cal_hours"] for x in bin_stops)
        return slot

    # Saturday-eligible bins prefer a Saturday but fall back to a weekday
    # if Saturday capacity runs out (eligibility is a ceiling, not a floor
    # -- nobody is REQUIRED to work Saturday).
    for b in sorted(sat_bins, key=lambda b: -sum(x["cal_hours"] for x in b)):
        pool = sat_slots if sat_slots else weekday_slots
        slot = place(b, pool)
        if slot:
            assignments.append((slot, b, "Standard"))
    # Everyone else: weekday only, never Saturday.
    for b in sorted(res_bins, key=lambda b: -sum(x["cal_hours"] for x in b)):
        slot = place(b, weekday_slots)
        if slot:
            assignments.append((slot, b, "Standard"))
    for b in sorted(biz_bins, key=lambda b: -sum(x["cal_hours"] for x in b)):
        slot = place(b, weekday_slots)
        if slot:
            assignments.append((slot, b, "Standard"))
    if unplaced:
        print(f"  !! {len(unplaced)} bins UNPLACED (out of calendar slots)")

    for (date, crew), stops, cat in assignments:
        days.append(build_day(D, crew, date, stops, by_idx, cat))

    # sort days chronologically then crew
    days.sort(key=lambda d: (d["date"], d["crew"]))

    result = {
        "depot": depot,
        "days": days,
        "flagged_noaddr": [{"name": c["name"], "reason": "NEED ADDRESS"} for c in flagged_noaddr],
        "dropped": [{"name": c["name"], "reason": "NO INSTALL 2026 (client note)"} for c in dropped],
        "all_clients": clients,
    }
    with open(os.path.join(CACHE, "schedule.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    # report
    total_stops = sum(len(d["stops"]) for d in days)
    over = [d for d in days if any("OVER" in f for f in d["flags"])]
    print(f"Crew-days: {len(days)}")
    print(f"Stops placed: {total_stops} (routable clients: {len(routable)})")
    print(f"No-address flagged: {[c['name'] for c in flagged_noaddr]}")
    print(f"Dropped (no 2026 install): {[c['name'] for c in dropped]}")
    print(f"Days OVER 12h: {len(over)}")
    for d in over:
        print(f"  !! {d['date']} {d['crew']}: {d['total_min']}min  {d['flags']}")
    singles = [d for d in days if any("single-stop" in f for f in d["flags"])]
    print(f"Single-stop days (flagged): {[(d['date'], d['crew'], d['stops'][0]['name']) for d in singles]}")


def partition_days(stops, target=6.5, min_stops=2):
    """Split a crew's stops into balanced days: a stop that fills a day
    (>target hrs) gets its own day; the rest are balanced across
    ceil(sum/target) days, keeping >=min_stops per day where possible."""
    import math
    big = [s for s in stops if s["cal_hours"] > target]
    small = [s for s in stops if s["cal_hours"] <= target]
    days = [[b] for b in big]
    if small:
        total = sum(s["cal_hours"] for s in small)
        nd = max(1, math.ceil(total / target))
        if len(small) >= min_stops:
            nd = min(nd, len(small) // min_stops)
        nd = max(1, nd)
        buckets = [[] for _ in range(nd)]
        bload = [0.0] * nd
        for s in small:  # already in geographic order
            i = min(range(nd), key=lambda k: bload[k])
            buckets[i].append(s)
            bload[i] += s["cal_hours"]
        days += [b for b in buckets if b]
    return days


def merge_singletons(D, bins):
    """Coalesce leftover 1-stop bins with the nearest bin of ANY size
    (including another single) within RADIUS_S, if the combined day fits
    the 10h cap. Iterates until stable so two neighboring leftovers can
    pair up into a proper 2-stop day. Never merges across the radius —
    an isolated single-area day beats welding a cross-town stop on."""
    def day_min_of(b):
        order, drive = route_loop(D, [x["midx"] for x in b])
        return day_totals(sum(x["cal_hours"] for x in b), drive)

    changed = True
    while changed:
        changed = False
        for s in [b for b in bins
                  if len(b) == 1 or day_min_of(b) < DAY_MIN]:
            if s not in bins:
                continue
            c = s[0]
            # rural pockets (>45 min from depot) spread wider than the urban
            # 30-min rule — allow up to 45 min there; a longer local hop still
            # beats a second 2.5h round-trip from the depot.
            eff_r = RADIUS_S if leg(D, 0, c["midx"]) <= 2700 else 2700
            others = sorted((b for b in bins if b is not s),
                            key=lambda b: min(leg(D, c["midx"], x["midx"]) for x in b))
            for b in others:
                if min(leg(D, c["midx"], x["midx"]) for x in b) > eff_r:
                    break
                trial = b + s
                order, drive = route_loop(D, [x["midx"] for x in trial])
                if day_totals(sum(x["cal_hours"] for x in trial), drive) <= DAY_CAP:
                    b.extend(s)
                    bins.remove(s)
                    changed = True
                    break
        if changed:
            continue
    return bins


if __name__ == "__main__":
    main()
