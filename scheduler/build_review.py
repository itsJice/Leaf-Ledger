#!/usr/bin/env python3
"""
TBDG 2026 — interactive team-review page (review.html).

Single self-contained HTML file (Leaflet from CDN, OSM tiles) with:
  - date strip -> day-by-day navigation, crew-by-crew cards
  - exact, name-labeled pins colored by crew; routes drawn depot->stops->depot
  - per-card: people needed, 2025 real hours, storage/boxes, route legs, 10h bar
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

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "review.html")

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
}

payload_obj = {
    "depot": {"lat": sched["depot"]["lat"], "lon": sched["depot"]["lon"]},
    "clients": clients, "days": days, "node": node, "durs": durs,
    "noaddr": sched.get("flagged_noaddr", []),
    "dropped": sched.get("dropped", []),
    "spec": spec,
}
# Version stamps the inputs, so saved state from before a regeneration is
# caught and reconciled rather than silently misapplied to shifted days.
spec["version"] = hashlib.sha256(
    json.dumps({"d": days, "c": clients}, sort_keys=True).encode()
).hexdigest()[:12]

payload = json.dumps(payload_obj, separators=(",", ":"))

HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>TBDG 2026 Install Review</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
<style>
:root{
  /* Leaf & Ledger tokens */
  --page:#f7f4ef;          /* warm cream page */
  --surface:#ffffff;       /* cards */
  --line:#e7e5e4;          /* stone-200 hairline */
  --ink:#292524;           /* stone-800 */
  --mut:#78716c;           /* stone-500 */
  --faint:#a8a29e;         /* stone-400 */
  --brand:#2d5a33;         /* primary green */
  --brand-hover:#24492a;
  --brand-deep:#1f3d2b;    /* chrome / sidebar green */
  --brand-deepest:#162d20;
  --brand-soft:#e8f0e8;    /* soft badge */
  --ok:#15803d; --ok-ink:#14532d;
  --warn:#ca8a04; --warn-soft:#fef3e2; --warn-ink:#92400e;
  --danger:#b91c1c; --danger-soft:#fef2f2;
  --gold:#f4b400;
  --radius:8px;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;font-family:'Montserrat',sans-serif;color:var(--ink);background:var(--page)}
#app{display:flex;flex-direction:column;height:100%}
header{background:var(--page);color:var(--ink);padding:14px 24px 12px;
  display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;
  border-bottom:1px solid var(--line)}
header h1{display:flex;align-items:center;gap:8px;font-family:Georgia,serif;font-weight:600;
  font-size:20px;margin:0;white-space:nowrap;color:var(--ink)}
header h1 svg{color:var(--brand)}
#headtitle p{margin:2px 0 0;font-size:12px;color:var(--mut)}
#datestrip{display:flex;gap:6px;flex-wrap:wrap;flex:1 1 100%;margin-top:12px}
.dchip{border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:12px;cursor:pointer;
  font-family:'Montserrat',sans-serif;background:#fff;color:#57534e;font-weight:600;
  letter-spacing:.01em;transition:all .15s}
.dchip:hover{background:#fafaf9;border-color:#d6d3d1}
.dchip.wknd{background:var(--warn-soft);color:var(--warn-ink);border-color:#fde3ad}
.dchip.tagged{border-color:#7c3aed;border-width:2px}
.dtag{display:inline-block;margin-left:6px;padding:1px 5px;border-radius:4px;
  background:#7c3aed;color:#fff;font-size:9px;font-weight:800;letter-spacing:.3px;
  vertical-align:1px}
#daytag{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:5px;
  background:#7c3aed;color:#fff;font-size:10px;font-weight:800;letter-spacing:.4px}
.dchip.wknd:hover{background:#fdecc8}
/* Nothing scheduled here yet -- still a real, draggable date, just visibly
   empty so it reads differently from a day with actual work on it. Wins
   over .wknd (an empty Saturday is still, first and foremost, empty). */
.dchip.empty{background:#f4f3f1;color:var(--faint);border-style:dashed;border-color:#d6d3d1}
.dchip.empty:hover{background:#ecebe8;color:var(--mut)}
.dchip.sel{background:var(--brand);color:#fff;border-color:var(--brand);border-style:solid}
.dchip.dragover{outline:2px dashed var(--brand);outline-offset:1px}
.nothingyet{font-size:12.5px;color:var(--mut);margin:2px 2px 12px}
.emptycrew{display:flex;align-items:center;gap:9px;border:1.5px dashed var(--line);border-radius:10px;
  padding:16px 14px;margin-bottom:10px;font-size:12.5px;color:var(--mut);
  background:var(--surface);transition:border-color .12s,background .12s}
.emptycrew .cdot{width:11px;height:11px;border-radius:50%;flex:none;opacity:.55}
.emptycrew.dragover{border-color:var(--crew-color,var(--brand));border-style:solid;
  background:var(--brand-soft);color:var(--ink)}
.addcrewbtn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;
  border:1.5px dashed var(--line);border-radius:10px;padding:14px;margin-bottom:10px;
  font-family:'Montserrat',sans-serif;font-size:13px;font-weight:600;color:var(--mut);
  background:var(--surface);cursor:pointer;transition:border-color .12s,background .12s,color .12s}
.addcrewbtn:hover{border-color:var(--brand);background:var(--brand-soft);color:var(--ink)}
.addcrewbtn .plus{font-size:16px;font-weight:700;line-height:1}
#main{flex:1;display:flex;min-height:0}
#side{width:460px;min-width:380px;overflow-y:auto;padding:14px;background:var(--page)}
#map{flex:1}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);margin-bottom:14px;
  box-shadow:0 1px 2px rgba(41,37,36,.05)}
.card.approved{border:2px solid var(--ok)}
.card.overwin{border:2px solid var(--danger)}
.card.dragover{outline:3px dashed var(--brand);outline-offset:-3px}
.card.focused{box-shadow:0 0 0 2px var(--brand)}
.chead{display:flex;align-items:center;gap:9px;padding:11px 14px;border-bottom:1px solid var(--line);background:linear-gradient(#fff,#fbfaf8)}
.chead-crew{display:flex;align-items:center;gap:9px;cursor:pointer;border-radius:5px;padding:2px 5px;margin:-2px -5px}
.chead-crew:hover{background:var(--brand-soft)}
.cdot{width:13px;height:13px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 2px rgba(255,255,255,.4)}
.cname{font-family:Georgia,serif;letter-spacing:.03em;font-weight:600;font-size:15px;flex:1;color:var(--ink)}
.cpeople{font-size:11.5px;color:var(--mut);white-space:nowrap;font-weight:500}
.sched{display:flex;gap:16px;padding:8px 14px;font-size:11.5px;color:var(--mut);
  background:var(--brand-soft);border-bottom:1px solid var(--line)}
.sched b{color:var(--ink);font-weight:700}
.sched .ic{width:12px;height:12px;vertical-align:-1.5px;margin-right:2px}
.okbtn{border:1.5px solid var(--ok);color:var(--ok);background:#fff;border-radius:6px;font-family:'Montserrat',sans-serif;
  padding:4px 12px;cursor:pointer;font-size:12px;font-weight:600;letter-spacing:.02em;transition:all .15s}
.okbtn:hover{background:#f0fdf4}
.okbtn.on{background:var(--ok);color:#fff}
.stop{display:flex;align-items:center;gap:9px;padding:8px 14px;border-bottom:1px solid #f5f5f4;cursor:grab;background:var(--surface)}
.stop:hover{background:#fafaf9}
.stop:active{cursor:grabbing}
.stop .num{width:20px;height:20px;border-radius:50%;background:var(--ink);color:#fff;
  font-size:10.5px;display:flex;align-items:center;justify-content:center;flex:none;font-weight:700}
.stop .nm{font-weight:600;font-size:13px;color:var(--ink)}
.stop .sub{font-size:11px;color:var(--mut);margin-top:1px}
.stop .body{flex:1;min-width:0}
.badge{display:inline-block;font-size:10px;border-radius:5px;padding:1.5px 6px;margin-left:4px;
  background:var(--brand-soft);color:var(--brand-deep);font-weight:600;letter-spacing:.01em}
.badge.store{background:var(--brand-soft);color:var(--ok-ink)}
.badge.approx{background:var(--warn-soft);color:var(--warn-ink)}
.mv{border:1px solid var(--line);background:#fff;border-radius:6px;font-size:11px;font-family:'Montserrat',sans-serif;
  padding:3px 8px;cursor:pointer;color:var(--brand);font-weight:600}
.mv:hover{background:var(--brand-soft)}
.leg{font-size:10.5px;color:var(--faint);padding:1px 14px 1px 44px;background:var(--surface)}
.cfoot{padding:10px 14px;font-size:12px;background:#fbfaf8;border-top:1px solid #f5f5f4;border-radius:0 0 var(--radius) var(--radius)}
.bar{height:7px;border-radius:4px;background:var(--line);overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;border-radius:4px}
.tot{display:flex;justify-content:space-between;color:var(--mut);font-weight:500}
.note{font-size:11px;color:var(--brand);padding:8px 14px;font-style:italic;border-top:1px dashed var(--line)}
.ovtitle{margin:0 0 10px;font-size:15px;font-family:Georgia,serif;letter-spacing:.03em;font-weight:600;color:var(--ink)}
.ovdate{font-size:12px;font-weight:700;color:var(--brand-deep);letter-spacing:.03em;
  margin:16px 0 6px;padding-bottom:4px;border-bottom:2px solid var(--brand-soft)}
.ovdate:first-of-type{margin-top:0}
#log{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px;font-size:12px;box-shadow:0 1px 2px rgba(41,37,36,.05)}
#log h3{margin:0 0 8px;font-size:14px;font-family:Georgia,serif;letter-spacing:.03em;font-weight:600}
#log .ent{color:var(--mut);margin:3px 0}
#log button{margin-right:6px;margin-top:8px;border:1px solid var(--line);background:#fff;font-family:'Montserrat',sans-serif;
  border-radius:6px;padding:5px 10px;cursor:pointer;font-size:11.5px;font-weight:600;color:var(--ink)}
#log button:hover{background:var(--brand-soft);border-color:var(--brand)}
.name-label{background:rgba(255,255,255,.95);border:1px solid var(--line);border-radius:5px;
  padding:0 5px;font-size:10.5px;font-family:'Montserrat',sans-serif;font-weight:600;color:var(--ink);white-space:nowrap;
  box-shadow:0 1px 3px rgba(41,37,36,.2)}
dialog{border:1px solid var(--line);border-radius:10px;padding:18px;max-width:340px;font-family:'Montserrat',sans-serif;
  box-shadow:0 8px 30px rgba(41,37,36,.18)}
dialog b{font-family:Georgia,serif;letter-spacing:.02em}
dialog select,dialog input[type=text],dialog input[type=number]{width:100%;margin:4px 0 7px;padding:7px;
  font-size:13px;font-family:'Montserrat',sans-serif;border:1px solid var(--line);border-radius:6px;
  background:#fff;color:var(--ink);box-sizing:border-box}
dialog select:focus,dialog input:focus{outline:none;border-color:var(--brand)}
.nclabel{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);
  font-weight:700;display:block;margin-top:6px}
dialog .btns{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
dialog button{padding:7px 14px;border-radius:6px;border:1px solid var(--line);cursor:pointer;
  font-family:'Montserrat',sans-serif;font-weight:600;font-size:12.5px;background:#fff;color:var(--ink)}
dialog .go{background:var(--brand);color:#fff;border:none}
dialog .go:hover{background:var(--brand-hover)}
dialog option:disabled{color:#b6b3ae}
#mvnote{font-size:11.5px;color:var(--mut);margin-top:6px;min-height:14px}
#mvnote .warn{color:var(--warn-ink)}
#mvdlg{max-width:400px}
#mvcrewinfo{display:flex;flex-direction:column;gap:5px;margin:4px 0 2px}
.mvcrewrow{display:flex;gap:7px;font-size:11.5px;border-radius:6px;padding:5px 7px;background:var(--surface)}
.mvcrewrow.mvsel{background:var(--brand-soft)}
.mvcrewrow .cdot{width:9px;height:9px;border-radius:50%;flex:none;margin-top:3px}
.mvcrewrow .mvcrewnames{color:var(--mut)}
.mvcrewrow .mvcrewnames b{color:var(--ink);font-weight:600}
.mvcrewrow .mvcrewempty{color:var(--faint);font-style:italic}
#sfdlg{max-width:500px}
#ncdlg{max-width:380px}
.ncerr{font-size:11.5px;color:var(--warn-ink);margin-top:2px;min-height:14px}
#histdlg{max-width:440px}
.histsub{font-size:11.5px;color:var(--mut);margin:2px 0 10px}
#histbody{max-height:56vh;overflow-y:auto;padding-right:2px}
.histrow{display:flex;align-items:center;justify-content:space-between;gap:10px;
  border:1px solid var(--line);border-radius:9px;padding:9px 12px;margin-bottom:8px;
  background:var(--surface)}
.histrow.histcurrent{border-color:var(--brand);background:var(--brand-soft)}
.histwhen{font-size:12.5px;color:var(--ink);font-weight:600}
.histwho{font-size:11px;color:var(--mut)}
.histempty,.histloading{font-size:12.5px;color:var(--mut);padding:8px 2px}
#sflab{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);
  font-weight:700;display:block;margin-top:12px}
#sfbody{margin-top:12px;max-height:56vh;overflow-y:auto;padding-right:2px}
.sfrow{border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin-bottom:9px;
  position:relative;background:var(--surface);transition:border-color .12s,box-shadow .12s}
.sfrow:hover{border-color:var(--brand);box-shadow:0 1px 6px rgba(41,37,36,.08)}
.sfrow.top{border-color:var(--brand);background:#fcfdfc}
.sfhead{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding-right:100px}
.sfdate{font-family:Georgia,serif;font-size:15px;font-weight:600;color:var(--ink)}
.sfcrew{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;color:var(--mut)}
.sfcrew i{width:9px;height:9px;border-radius:50%;display:inline-block}
.badge.best{background:var(--brand);color:#fff}
.sfstats{display:flex;gap:24px;margin-top:9px;padding-right:100px}
.sfstat{display:flex;flex-direction:column;gap:1px;min-width:98px}
.sflab{font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);font-weight:700}
.sfval{font-size:13px;font-weight:700;color:var(--ink)}
.sfval .sfmut{font-weight:500;color:var(--faint)}
.sfval.good{color:var(--ok-ink)}
.sfval.bad{color:var(--warn-ink)}
.sfbar{display:block;height:4px;border-radius:3px;background:var(--line);
  overflow:hidden;margin-top:4px;width:98px}
.sfbar i{display:block;height:100%;border-radius:3px}
.sfrow .sfwarn{margin:9px 0 0;padding:0 100px 0 16px;list-style:none;
  font-size:11px;color:var(--warn-ink);line-height:1.45}
.sfrow .sfwarn li{position:relative;margin-top:2px}
.sfrow .sfwarn li:before{content:'!';position:absolute;left:-16px;top:1px;width:12px;height:12px;
  border-radius:50%;background:var(--warn-soft);color:var(--warn-ink);font-size:9px;font-weight:800;
  display:flex;align-items:center;justify-content:center}
.sfrow .sfgo{position:absolute;right:12px;top:12px;padding:6px 12px;font-size:12px}
.sfnone{font-size:12.5px;color:var(--mut);margin-bottom:11px;line-height:1.5}
.sfsrc{font-size:11.5px;color:var(--warn-ink);background:var(--warn-soft);
  border-radius:7px;padding:8px 10px;margin-bottom:11px;line-height:1.45}
.stopbtns{display:flex;flex-direction:column;gap:4px;flex:none}
.undobar{display:flex;gap:6px;margin-top:10px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.undobar button{margin-top:0}
#log button:disabled{opacity:.4;cursor:default}
.badge.lock{background:var(--warn-soft);color:var(--warn-ink)}
.badge.visittype{background:#e8e0f0;color:#4a2e7a}
.stop .sub.advice{color:var(--warn-ink);font-style:italic;margin-top:3px}
#summarybar{font-size:12px;color:var(--mut);white-space:nowrap;font-weight:500;margin-top:3px}
#newclientbtn{align-self:center;padding:8px 14px;border-radius:8px;border:1.5px solid var(--brand);
  background:#fff;color:var(--brand);font-family:'Montserrat',sans-serif;font-weight:700;
  font-size:12.5px;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
#newclientbtn:hover{background:var(--brand);color:#fff}
#billexportbtn{align-self:center;padding:8px 14px;border-radius:8px;border:1.5px solid var(--line);
  background:#fff;color:var(--ink);font-family:'Montserrat',sans-serif;font-weight:700;
  font-size:12.5px;cursor:pointer;white-space:nowrap;transition:background .12s}
#billexportbtn:hover{background:var(--brand-soft)}
#billdlg{max-width:360px}
#billdlg .billscope{display:flex;flex-direction:column;gap:8px;margin:14px 0}
#billdlg .billscope button{padding:10px 14px;border-radius:8px;border:1.5px solid var(--line);
  background:#fff;color:var(--ink);font-family:'Montserrat',sans-serif;font-weight:600;
  font-size:13px;cursor:pointer;text-align:left}
#billdlg .billscope button:hover{border-color:var(--brand);background:var(--brand-soft)}
#billdlg .billnote{font-size:11.5px;color:var(--mut);line-height:1.5;margin-top:2px}
#billdlg .billscope button.sel{border-color:var(--brand);background:var(--brand-soft);font-weight:700}
#billdlg .billfmt{display:flex;gap:8px;margin:8px 0 4px}
#billdlg .billfmt button{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;
  padding:10px 6px;border-radius:8px;border:1.5px solid var(--line);background:#fff;
  cursor:pointer;font-weight:700;font-size:12.5px}
#billdlg .billfmt button:hover{border-color:var(--brand);background:var(--brand-soft)}
#billdlg .billfmt button.sel{border-color:var(--brand);border-width:2px;
  background:var(--brand-soft);box-shadow:inset 0 0 0 1px var(--brand-soft)}
#billdlg .billfmt button.sel small{color:var(--brand)}
/* ---- view toggle + calendar ---- */
.viewtog{display:inline-flex;border:1.5px solid var(--line);border-radius:9px;overflow:hidden;
  margin-right:10px;vertical-align:middle}
.viewtog button{padding:7px 13px;border:0;background:#fff;cursor:pointer;font-weight:700;
  font-size:12.5px;color:var(--mut)}
.viewtog button.sel{background:var(--brand);color:#fff}
#calwrap{padding:16px 20px 40px}
.calmonth{margin-bottom:26px}
.calmonth h2{font-family:var(--serif);font-size:22px;margin:0 0 10px}
.calgrid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.caldow{font-size:11px;font-weight:800;color:var(--mut);text-transform:uppercase;
  letter-spacing:.5px;text-align:center;padding:4px 0}
.calcell{min-height:118px;border:1.5px solid var(--line);border-radius:9px;background:#fff;
  padding:7px 8px;font-size:11.5px;overflow:hidden;cursor:pointer}
.calcell.empty{background:#faf9f7;border-style:dashed;cursor:default}
.calcell.off{visibility:hidden}
.calcell:hover:not(.empty){border-color:var(--brand)}
.calcell.tagged{border-color:#7c3aed;border-width:2px}
.calnum{font-weight:800;font-size:15px}
.calnum small{font-weight:600;color:var(--mut);font-size:10.5px;margin-left:4px}
.calcrew{margin-top:4px;line-height:1.35}
.calcrew b{font-weight:800}
.calnames{color:var(--mut);font-size:10.5px;display:block;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.calfoot{margin-top:5px;padding-top:4px;border-top:1px solid var(--line);
  font-weight:800;font-size:11px}
.calbox{color:#8a5a00}
.caltag{display:inline-block;padding:0 5px;border-radius:4px;background:#7c3aed;color:#fff;
  font-size:9px;font-weight:800;margin-left:4px;vertical-align:2px}
.printbtn{margin-left:auto;padding:4px 10px;border-radius:7px;border:1.5px solid var(--line);
  background:#fff;cursor:pointer;font-size:11.5px;font-weight:700;color:var(--mut)}
.printbtn:hover{border-color:var(--brand);color:var(--brand);background:var(--brand-soft)}
#billdlg .billfmt small{font-weight:500;font-size:10px;color:var(--mut)}
#searchwrap{position:relative;margin-left:auto;width:280px;max-width:100%}
#searchbox{width:100%;padding:8px 12px;font-size:12.5px;font-family:'Montserrat',sans-serif;
  border:1.5px solid var(--line);border-radius:8px;background:#fff;color:var(--ink)}
#searchbox:focus{outline:none;border-color:var(--brand)}
#searchresults{display:none;position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:20;
  background:var(--surface);border:1px solid var(--line);border-radius:8px;
  box-shadow:0 8px 24px rgba(41,37,36,.14);max-height:340px;overflow-y:auto}
.srow{display:flex;justify-content:space-between;gap:10px;padding:8px 12px;cursor:pointer;
  font-size:12.5px;border-bottom:1px solid #f5f5f4}
.srow:last-child{border-bottom:none}
.srow:hover{background:var(--brand-soft)}
.srname{color:var(--ink);font-weight:600}
.srwhere{color:var(--mut);white-space:nowrap}
.srnone{padding:10px 12px;font-size:12px;color:var(--mut)}
@keyframes flashrow{0%,100%{background:var(--surface)}30%,70%{background:var(--brand-soft)}}
.stop.flash{animation:flashrow 1.1s ease-in-out 2}
#statewarn{grid-column:1/-1;margin-top:8px;padding:8px 12px;border-radius:6px;
  background:var(--warn-soft);color:var(--warn-ink);font-size:12px;font-weight:600;
  border:1px solid rgba(0,0,0,.06)}
.edited{font-size:10px;color:#c2410c;font-weight:700;margin-left:6px;font-family:'Montserrat',sans-serif}
.ic{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vertical-align:-2px;display:inline-block}
</style></head>
<body><div id="app">
<header>
  <div id="headtitle">
    <h1><svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 7 9h2.5L5 15h3l-3.5 5h15L16 15h3l-4.5-6H17L12 2Z"/><path d="M12 22v-2"/></svg>TBDG · 2026 Install Schedule</h1>
    <p>Crew routes, drive times &amp; approvals for every install day — drag a stop to reschedule it.</p>
  </div>
  <div id="searchwrap">
    <input id="searchbox" type="text" placeholder="Find a client… (which day are they on?)" autocomplete="off">
    <div id="searchresults"></div>
  </div>
  <div class="viewtog">
    <button id="viewdays" class="sel" type="button">Days</button>
    <button id="viewcal" type="button">Calendar</button>
  </div>
  <button id="newclientbtn" type="button">+ New client</button>
  <button id="billexportbtn" type="button">⬇ Export</button>
  <div id="summarybar"></div>
  <div id="statewarn" style="display:none"></div>
  <div id="datestrip"></div>
</header>
<div id="calwrap" style="display:none"></div>
<div id="main">
  <div id="side"></div>
  <div id="map"></div>
</div>
</div>
<dialog id="mvdlg">
  <b id="mvtitle">Move stop</b>
  <select id="mvdate"></select>
  <select id="mvcrew"></select>
  <div id="mvcrewinfo"></div>
  <div id="mvnote"></div>
  <div class="btns"><button onclick="mvdlg.close()">Cancel</button>
  <button class="go" id="mvgo">Move</button></div>
</dialog>
<dialog id="sfdlg">
  <b id="sftitle">Find a new date</b>
  <label id="sflab">Client asked for</label>
  <select id="sfwant"></select>
  <div id="sfbody"></div>
  <div class="btns"><button onclick="sfdlg.close()">Close</button></div>
</dialog>
<dialog id="ncdlg">
  <b>New client / job</b>
  <label class="nclabel">Name</label>
  <input id="ncname" type="text" placeholder="e.g. Client X - Reinstall, or Client Y - Callback">
  <label class="nclabel">Address</label>
  <input id="ncaddr" type="text" placeholder="Street, city, state zip">
  <label class="nclabel">Est. install time (hours)</label>
  <input id="nchours" type="number" step="0.25" min="0" value="1">
  <label class="nclabel">Crew size (people, optional)</label>
  <input id="ncpeople" type="number" step="1" min="0" placeholder="e.g. 5">
  <label class="nclabel">Type</label>
  <select id="nctype">
    <option value="Standard">Standard</option>
    <option value="Install">Install</option>
    <option value="Takedown">Takedown (event teardown)</option>
    <option value="Reinstall">Reinstall (after event)</option>
    <option value="Callback">Callback (bought more / fix / unfinished)</option>
  </select>
  <label class="nclabel">Notes (optional)</label>
  <input id="ncnotes" type="text" placeholder="Anything worth flagging">
  <div id="ncerr" class="ncerr"></div>
  <div class="btns"><button onclick="ncdlg.close()">Cancel</button>
  <button class="go" id="ncgo">Look up &amp; add</button></div>
</dialog>
<dialog id="histdlg">
  <b>Change history</b>
  <p id="histsub" class="histsub"></p>
  <div id="histbody"></div>
  <div class="btns"><button onclick="histdlg.close()">Close</button></div>
</dialog>
<dialog id="billdlg">
  <b>Export</b>
  <p class="billnote">One row per client: name, bill-to, address / city / state /
    zip, install date, and 2026 install / takedown / storage priced off the
    client's real 2025 invoice +5% (storage carried over flat). Shows the 2025
    figure it was derived from, so every number is checkable. Contract accounts
    are marked, not guessed. Column totals at the bottom.</p>
  <label class="nclabel">Who</label>
  <div class="billscope">
    <button data-scope="all" class="sel">Everyone</button>
    <button data-scope="houston">Houston only</button>
    <button data-scope="dallas">Dallas only (Mi Cocina week)</button>
  </div>
  <label class="nclabel">Format</label>
  <div class="billfmt">
    <button data-fmt="xlsx" class="sel">Excel<small>.xlsx</small></button>
    <button data-fmt="csv">CSV<small>.csv</small></button>
    <button data-fmt="pdf">PDF<small>print</small></button>
  </div>
  <div class="btns"><button onclick="billdlg.close()">Cancel</button>
  <button class="go" id="billgo">Download</button></div>
</dialog>
<script>
const DATA = __DATA__;
const IC={
 users:'<svg class="ic" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
 link:'<svg class="ic" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
 box:'<svg class="ic" viewBox="0 0 24 24"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>',
 truck:'<svg class="ic" viewBox="0 0 24 24"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>',
 sun:'<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
 moon:'<svg class="ic" viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>',
 phone:'<svg class="ic" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
 check:'<svg class="ic" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
 down:'<svg class="ic" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>',
 undo:'<svg class="ic" viewBox="0 0 24 24"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>',
 home:'<svg class="ic" viewBox="0 0 24 24" style="width:11px;height:11px"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
 clock:'<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'};
const CREW_COLORS = {"Crew 1":"#c2410c","Crew 2":"#0369a1","Crew 3":"#2d5a33",
  "Crew 1 + Crew 2 (stacked)":"#7d3c98","Crew 1 + Crew 2 + Crew 3 (stacked)":"#b9770e"};
const BASE_CREWS = ["Crew 1","Crew 2","Crew 3"];
const SPEC = DATA.spec, K = SPEC.const;
const LUNCH = K.LUNCH;
const N = DATA.node, D = DATA.durs, C = DATA.clients;

// ---------- manually-added clients (new jobs, anomalies, callbacks) ----------
// D/N only cover the clients baked in at build time from the spreadsheet.
// A client added in the browser (a same-day-teardown/reinstall anomaly, a
// one-off event takedown, a callback because something broke or they
// bought more) gets a brand-new matrix node instead. On creation this
// live-fetches REAL OSRM drive times against every existing client (same
// public OSRM /table service the rest of the tool already depends on) --
// the straight-line estimate below only kicks in if that fetch fails, or
// for the rare case of two synthetic clients' distance to EACH OTHER
// (not worth a full re-fetch chain for something this uncommon).
const REAL_NODE_COUNT = D.length;   // real clients are always 0..this-1
const NODE_LATLON = {0: [DATA.depot.lat, DATA.depot.lon]};
Object.values(C).forEach(c=>{ if(N[c.row]!=null) NODE_LATLON[N[c.row]] = [c.lat, c.lon]; });

function haversineMi(a, b){
  const R=3958.8, toRad=x=>x*Math.PI/180;
  const dLat=toRad(b[0]-a[0]), dLon=toRad(b[1]-a[1]);
  const s = Math.sin(dLat/2)**2 +
    Math.cos(toRad(a[0]))*Math.cos(toRad(b[0]))*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(s));
}
const ROAD_FUDGE = 1.35, EST_AVG_MPH = 27;   // fallback only, see note above
function estSeconds(a, b){
  return Math.round(haversineMi(a,b) * ROAD_FUDGE / EST_AVG_MPH * 3600);
}
/** Live OSRM /table fetch: (lat,lon) vs every REAL client, both directions
 * (durations are asymmetric -- one-ways, ramps). Two targeted sources/
 * destinations calls instead of a full matrix, so this stays fast (well
 * under a second) and small regardless of how many synthetic clients
 * already exist. Returns null on any failure -- caller falls back to
 * the haversine estimate. */
async function fetchRealLegs(lat, lon){
  try{
    const coords=[]; for(let i=0;i<REAL_NODE_COUNT;i++) coords.push(NODE_LATLON[i]);
    coords.push([lat,lon]);
    const newIdx=REAL_NODE_COUNT;
    const coordStr=coords.map(([la,lo])=>`${lo},${la}`).join(';');
    const dests=Array.from({length:REAL_NODE_COUNT},(_,i)=>i).join(';');
    const base=`https://router.project-osrm.org/table/v1/driving/${coordStr}`;
    const [outRes,inRes]=await Promise.all([
      fetch(`${base}?sources=${newIdx}&destinations=${dests}`),
      fetch(`${base}?sources=${dests}&destinations=${newIdx}`),
    ]);
    const [outJ,inJ]=await Promise.all([outRes.json(),inRes.json()]);
    if(outJ.code!=='Ok'||inJ.code!=='Ok') return null;
    return {outRow: outJ.durations[0], inCol: inJ.durations.map(r=>r[0])};
  }catch(e){ return null; }
}
/** Extend D/N/NODE_LATLON in place with one new node at (lat, lon), using
 * REAL legs (outRow/inCol, vs the REAL_NODE_COUNT base clients) where
 * given and the straight-line estimate everywhere else -- other synthetic
 * nodes beyond REAL_NODE_COUNT, or the whole row/column when outRow/inCol
 * is null. Synchronous; the live fetch (if any) already happened. */
function extendMatrix(lat, lon, outRow, inCol){
  const idx = D.length, pt = [lat, lon];
  D.forEach((row, i)=>{
    row.push(outRow && inCol && i<REAL_NODE_COUNT ? inCol[i] : estSeconds(NODE_LATLON[i], pt));
  });
  const newRow = D.map((_, i)=>
    outRow && inCol && i<REAL_NODE_COUNT ? outRow[i] : estSeconds(pt, NODE_LATLON[i]));
  newRow.push(0);
  D.push(newRow);
  NODE_LATLON[idx] = pt;
  return idx;
}
// Synthetic rows live well above any real spreadsheet row so they can
// never collide with one, now or after a future spreadsheet regeneration.
let nextSyntheticRow = 900001 + Object.keys(C).filter(r=>C[r].synthetic).length;
/** Register a client row from already-known data -- restoring saved state
 * (outRow/inCol were captured once at creation and persisted, so this
 * never re-fetches) or as the final step after a live creation fetch.
 * Synchronous. */
// Mirrors prep.py's classify() for the one thing a synthetic client still
// needs guessed: Business vs Residence drives which soft weekend warning
// applies (BIZ_SAT vs SAT_HIST) -- getting it wrong doesn't block anything,
// but shows staff the wrong "confirm ___" message.
const SYN_BUSINESS_KEYWORDS = ['m crowd','bank','club','cc','hotel','suites','inn','church',
  'daycare','academy','office','salon','market','grill','cafe','center','rotary','llc',
  'inc','company','school','corporate','restaurant','cocina','tavern','group','medical',
  'clinic','mercury','district'];
function classifyBusiness(name){
  const n = (name||'').toLowerCase();
  const personPattern = /^[A-Za-z'`.\- ]+,\s*[A-Za-z]/.test(name||'');
  const kw = k => new RegExp('\\b'+k+'\\b').test(n);
  if(personPattern && !n.includes('crowd')
     && !SYN_BUSINESS_KEYWORDS.filter(k=>k!=='cc'&&k!=='club').some(kw)) return 'Residence';
  if(n.includes('residence')) return 'Residence';
  if(SYN_BUSINESS_KEYWORDS.some(kw)) return 'Business';
  return personPattern ? 'Residence' : 'Business';
}
function addSyntheticClientSync({name, street, city, zip, lat, lon, hours, visitType, notes,
                                  people, row, outRow, inCol}){
  const r = row!=null ? row : nextSyntheticRow++;
  const idx = extendMatrix(lat, lon, outRow||null, inCol||null);
  C[r] = {
    row:r, name, street:street||'', city:city||'', st:'TX', zip:zip||'',
    phone:'', email:'', storage:'', boxes:'',
    d24:'', d25:'', real25:null, crew25:'', size25:null, people:(people!=null?people:null),
    h26:hours, basis:'manual entry', zone:city||'', area:'',
    cat:'Standard', bus:classifyBusiness(name), lat, lon,
    // Real OSRM legs -> treat like a normal street-geocoded client (no
    // "approx pin" flag); estimate-only -> flag it so staff know to
    // sanity-check drive time if it matters for this one.
    geo: (outRow && inCol) ? 'street' : 'synthetic',
    locked:'', advice:notes||'',
    // No fee history for a client the spreadsheet never had -- billing
    // export leaves these blank rather than guessing.
    storageFee:null, installFee:null, takedownFee:null, invoice25:null,
    repairNotes:'', install24:null, storage24:null, install25:null, storage25:null,
    visitType: visitType||'Standard', synthetic:true,
    outRow: outRow||null, inCol: inCol||null,
  };
  N[r] = idx;
  return r;
}
/** Create a new client row from the "add a client" dialog: live-fetches
 * real OSRM legs first, then registers the row. */
async function createSyntheticClient(def){
  const legs = await fetchRealLegs(def.lat, def.lon);
  return addSyntheticClientSync({...def, outRow: legs?legs.outRow:null, inCol: legs?legs.inCol:null});
}

// ---------- day metadata ----------
// Metadata is keyed by day id in an immutable side map, so a day that gets
// emptied and later refilled keeps its negotiated window, note and joint
// wiring instead of silently reverting to a bare 10h default.
function metaFor(id){
  const m = SPEC.dayMeta[id];
  if(m) return m;
  const crew = (id||'').split('|')[1] || '';
  return {cat:'Standard', anchored:true, stacked:1, note:'', win:K.DAY_CAP,
          lunchMin:K.LUNCH, half:[], joint:'', startRow:null, winReason:'',
          flags:[], zones:[], _synthetic:true, crew};
}
function hydrate(d){
  const m = metaFor(d.id);
  return {...d, stops:[...d.stops],
          cat:m.cat, anchored:m.anchored, stacked:m.stacked, note:m.note,
          win:m.win, lunchMin:m.lunchMin, half:[...(m.half||[])],
          joint:m.joint, startRow:m.startRow, winReason:m.winReason};
}

// ---------- state ----------
let days = DATA.days.map(hydrate);
// Snapshot of each baseline day's original stop set, so restoring saved
// state can tell which days a placement actually changed. A day whose
// composition no longer matches this must not be drawn with the precomputed
// route geometry -- that geometry was traced for the OLD stop set, and a
// stale line rendered against the NEW markers visibly misses whichever stop
// moved (the line simply doesn't reach that dot).
const BASELINE_STOPS = {};
DATA.days.forEach(d=>{ BASELINE_STOPS[d.id] = [...d.stops].sort((a,b)=>a-b); });
let approved = new Set(), moves = [], selDate = null;
let focusDayId = null;   // click a crew header to zoom the map to just their day
let stateWarning = null;

// Authoritative saved state is a SNAPSHOT ({row -> dayId}), not a replay
// log. Replaying a move list was order-dependent and broke outright when a
// pipeline re-run shifted day ids; a snapshot is idempotent and can be
// reconciled against a regenerated baseline.
const LS_KEY = 'tbdg2026review';
function baselinePlacement(){
  const m = {};
  DATA.days.forEach(d=>d.stops.forEach(r=>{ (m[r] = m[r] || []).push(d.id); }));
  return m;
}
function currentPlacement(){
  const m = {};
  days.forEach(d=>d.stops.forEach(r=>{ (m[r] = m[r] || []).push(d.id); }));
  return m;
}
function applyPlacement(place){
  const want = {};
  Object.entries(place).forEach(([r,ids])=>{ want[+r] = ids; });
  const byId = new Map(days.map(d=>[d.id,d]));
  days.forEach(d=>{ d.stops = []; });
  let missing = 0;
  Object.entries(want).forEach(([r,ids])=>{
    ids.forEach(id=>{
      let d = byId.get(id);
      if(!d){
        // A day may be absent for two very different reasons: the user
        // created it during a previous session (legitimate -- rebuild it),
        // or it referred to a baseline day that a pipeline re-run removed
        // (stale -- drop it and say so). Tell them apart by whether the
        // id names a real working date and crew.
        const [date,crew] = id.split('|');
        const ci = SPEC.calendar.find(x=>x.date===date);
        if(!ci || !K.CREWS.includes(crew)){ missing++; return; }
        d = hydrate({id, date, crew, dow:ci.dow,
                     stops:[], geom:null, mi:null, legMi:null});
        d.edited = true;
        days.push(d); byId.set(id,d);
      }
      d.stops.push(+r);
    });
  });
  days.forEach(d=>{
    const cur = [...d.stops].sort((a,b)=>a-b);
    const base = BASELINE_STOPS[d.id] || [];
    if(cur.length!==base.length || cur.some((v,i)=>v!==base[i])) d.edited = true;
  });
  days = days.filter(d=>d.stops.length);
  return missing;
}
/** Restore clients added in a previous session (or by another device) --
 * lat/lon are already known, so this is synchronous, no re-geocoding.
 * Must run BEFORE applyPlacement(), which references these rows. */
function restoreSyntheticClients(list){
  (list||[]).forEach(def=>{
    if(C[def.row]) return;   // already present -- idempotent
    addSyntheticClientSync(def);
    if(def.row >= nextSyntheticRow) nextSyntheticRow = def.row + 1;
  });
}
try{
  const s = JSON.parse(localStorage.getItem(LS_KEY)||'{}');
  if(s.version && SPEC.version && s.version !== SPEC.version){
    stateWarning = 'Saved changes were made against an older schedule build. '
                 + 'They have NOT been applied — re-check them before saving.';
  } else if(s.placement){
    restoreSyntheticClients(s.newClients);
    const missing = applyPlacement(s.placement);
    moves = s.moves || [];
    approved = new Set((s.approved||[]).filter(id=>days.some(d=>d.id===id)));
    if(missing) stateWarning = missing+' saved stop(s) pointed at days that no '
                             + 'longer exist and were left at their baseline.';
  } else if(s.moves && s.moves.length){
    // one-time migration off the old replay-log format
    s.moves.forEach(m=>{ try{ applyMove(m.row, m.to, false); }catch(e){} });
    moves = s.moves;
    approved = new Set((s.approved||[]).filter(id=>days.some(d=>d.id===id)));
    stateWarning = 'Migrated saved changes to the new format — please review.';
  }
}catch(e){}
function snapshot(){
  const newClients = Object.values(C).filter(c=>c.synthetic).map(c=>(
    {row:c.row, name:c.name, street:c.street, lat:c.lat, lon:c.lon,
     hours:c.h26, visitType:c.visitType, notes:c.advice,
     people:c.people, business:c.bus,
     outRow:c.outRow, inCol:c.inCol}));
  return {version:SPEC.version, placement:currentPlacement(),
          moves, approved:[...approved], newClients, savedAt:Date.now()};
}
// Shared save. Several staff work reschedule requests over the same
// season, so state lives server-side keyed on the schedule build. The
// parent app posts its auth token in (this page runs in a srcDoc iframe,
// same origin but with no token of its own); with no token we stay on
// localStorage alone, which is what the standalone file does.
let AUTH = null, syncState = 'local';
window.addEventListener('message', e=>{
  // Only ever accept a token from our own origin. srcDoc inherits the
  // parent's origin, so a same-origin check is the right gate; anything
  // cross-origin trying to hand us a bearer token is not the host app.
  if(e.origin !== window.location.origin) return;
  if(e.source !== window.parent) return;
  if(e.data && e.data.type==='tbdg-auth' && typeof e.data.token==='string'){
    AUTH = e.data.token;
    pullShared();
  }
});
async function pullShared(){
  if(!AUTH) return;
  try{
    const r = await fetch(`/api/install-schedule/state?version=${encodeURIComponent(SPEC.version)}`,
                          {headers:{Authorization:AUTH}});
    if(!r.ok) throw new Error(r.status);
    const j = await r.json();
    if(j.state && j.state.placement){
      // Guard against a real data-loss race: if THIS device's last local
      // save (already applied at bootstrap, from localStorage) happened
      // AFTER the server's last recorded write, our own debounced push
      // from before a page refresh may simply not have landed yet.
      // Applying the server's older state here would silently throw away
      // a real edit -- local wins instead, and gets pushed up to match.
      const localSaved = (JSON.parse(localStorage.getItem(LS_KEY)||'{}')||{}).savedAt || 0;
      const serverSaved = j.updatedAt ? new Date(j.updatedAt).getTime() : 0;
      if(localSaved > serverSaved){
        syncState = 'shared';
        pushSharedNow();
        return;
      }
      restoreSyntheticClients(j.state.newClients);
      const missing = applyPlacement(j.state.placement);
      moves = j.state.moves || [];
      approved = new Set((j.state.approved||[]).filter(id=>days.some(d=>d.id===id)));
      syncState = 'shared';
      stateWarning = missing
        ? missing+' shared stop(s) pointed at days that no longer exist.'
        : null;
      render();
    } else { syncState = 'shared'; }
  }catch(e){ syncState = 'local'; }
}
let pushTimer = null;
// Short debounce -- just enough to coalesce a fast drag/edit burst into
// one request, not so long that a quick refresh can race past it (see
// pullShared's local-wins guard above for the remaining edge of that).
function pushShared(){
  if(!AUTH) return;
  clearTimeout(pushTimer);
  pushTimer = setTimeout(pushSharedNow, 200);
}
function persist(){
  localStorage.setItem(LS_KEY, JSON.stringify(snapshot()));
  pushShared();
}
/** Immediate, awaited PUT -- bypasses the 600ms debounce. Used only by
 * history restore, where the user is waiting on a deliberate action and
 * needs to know whether it actually landed before the dialog closes. */
async function pushSharedNow(){
  if(!AUTH) return false;
  clearTimeout(pushTimer);
  try{
    const r = await fetch('/api/install-schedule/state', {
      method:'PUT',
      headers:{'Content-Type':'application/json', Authorization:AUTH},
      body: JSON.stringify({version:SPEC.version, state:snapshot()}),
    });
    return r.ok;
  }catch(e){ return false; }
}

// ---------- change history ----------
// Shared save history, so several staff working the same schedule can see
// who changed what and roll back a mistake -- same idea as a Google Doc's
// version history. Restoring an old save doesn't erase anything: it just
// applies that old state locally and saves it as a new current version
// (through the normal persist path), so the trail only ever grows.
const histdlg=document.getElementById('histdlg');
function fmtWhen(iso){
  if(!iso) return '';
  const d=new Date(iso);
  return d.toLocaleDateString(undefined,{month:'short',day:'numeric'})+' · '
       + d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
}
function fmtWho(id){
  if(!id) return 'unknown';
  return id.length>18 ? id.slice(0,8)+'…' : id;
}
async function openHistory(){
  const body=document.getElementById('histbody');
  const sub=document.getElementById('histsub');
  histdlg.showModal();
  if(!AUTH){
    sub.textContent='';
    body.innerHTML='<div class="histempty">History needs the shared schedule connection -- '
      +'open this tool from the main app (not the standalone file) to use it.</div>';
    return;
  }
  sub.textContent='Loading…';
  body.innerHTML='<div class="histloading">Loading past saves…</div>';
  try{
    const r=await fetch(`/api/install-schedule/history?version=${encodeURIComponent(SPEC.version)}`,
                        {headers:{Authorization:AUTH}});
    const j=await r.json();
    const entries=j.entries||[];
    sub.textContent=entries.length
      ? `${entries.length} saved version${entries.length===1?'':'s'} -- newest first`
      : 'No saved versions yet.';
    body.innerHTML = entries.length ? entries.map((e,i)=>`
      <div class="histrow${i===0?' histcurrent':''}" data-id="${e.id}">
        <div><div class="histwhen">${fmtWhen(e.createdAt)}${i===0?' (current)':''}</div>
        <div class="histwho">${fmtWho(e.updatedBy)}</div></div>
        ${i===0?'':'<button class="histrestore">Restore</button>'}
      </div>`).join('') : '<div class="histempty">No saved versions yet.</div>';
    body.querySelectorAll('.histrestore').forEach(btn=>{
      btn.onclick=()=>restoreHistoryEntry(+btn.closest('.histrow').dataset.id, btn);
    });
  }catch(e){
    sub.textContent='';
    body.innerHTML='<div class="histempty">Couldn\'t load history (network error).</div>';
  }
}
async function restoreHistoryEntry(entryId, btn){
  const row=document.querySelector(`.histrow[data-id="${entryId}"]`);
  const when=row?.querySelector('.histwhen')?.textContent||'this version';
  if(!confirm(`Restore to ${when}?\n\nThis replaces the current shared schedule state with `
    +`that saved version. Nothing is deleted -- you can restore back to now afterward if needed.`))
    return;
  btn.disabled=true; btn.textContent='Restoring…';
  try{
    const r=await fetch(`/api/install-schedule/history/${entryId}?version=${encodeURIComponent(SPEC.version)}`,
                        {headers:{Authorization:AUTH}});
    if(!r.ok) throw new Error(r.status);
    const j=await r.json();
    const st=j.state;
    if(!st || !st.placement) throw new Error('empty state');
    restoreSyntheticClients(st.newClients);
    applyPlacement(st.placement);
    moves = st.moves || [];
    approved = new Set((st.approved||[]).filter(dayId=>days.some(d=>d.id===dayId)));
    undoStack=[]; redoStack=[];   // local undo history no longer matches reality
    const ok = await pushSharedNow();
    localStorage.setItem(LS_KEY, JSON.stringify(snapshot()));
    histdlg.close();
    render();
    if(!ok) alert('Restored locally, but saving it back to the shared schedule failed -- '
      +'your next edit will retry the save automatically.');
  }catch(e){
    btn.disabled=false; btn.textContent='Restore';
    alert('Could not restore that version (network error) -- try again.');
  }
}
// ---------- undo / redo ----------
// Deep history: a season's worth of reschedule calls is a lot of small
// edits, and "I've just undone one thing" is rarely what you want when you
// realise a mistake three moves back. Snapshots are small (a row->day map),
// so 100 of them is cheap. Session-scoped: reloading starts a fresh
// history, which is the usual expectation.
const UNDO_LIMIT = 100;
let undoStack = [], redoStack = [];
function stateBlob(){
  return JSON.stringify({placement:currentPlacement(),
                         approved:[...approved], moves});
}
function restoreBlob(blob){
  const s = JSON.parse(blob);
  applyPlacement(s.placement);
  approved = new Set((s.approved||[]).filter(id=>days.some(d=>d.id===id)));
  moves = s.moves || [];
}
/** Call immediately BEFORE mutating, so the stack holds the prior state. */
function pushUndo(){
  undoStack.push(stateBlob());
  if(undoStack.length > UNDO_LIMIT) undoStack.shift();
  redoStack = [];      // a fresh edit invalidates the redo branch
}
function undo(){
  if(!undoStack.length) return;
  redoStack.push(stateBlob());
  restoreBlob(undoStack.pop());
  persist(); render();
}
function redo(){
  if(!redoStack.length) return;
  undoStack.push(stateBlob());
  restoreBlob(redoStack.pop());
  persist(); render();
}
document.addEventListener('keydown', e=>{
  const z = (e.key||'').toLowerCase()==='z';
  if(!z || !(e.metaKey||e.ctrlKey)) return;
  if(document.querySelector('dialog[open]')) return;
  e.preventDefault();
  e.shiftKey ? redo() : undo();
});

// ---------- routing (embedded OSRM matrix) ----------
function leg(a,b){ return D[a][b]||0; }
function routeDay(d){
  const idx = d.stops.map(r=>N[r]).filter(i=>i!==undefined);
  if(!idx.length) return {order:[],drive:0};
  if(!d.edited){
    // Unedited day: trust the server's planned order as-is. It's already
    // exhaustively optimal (route_exact) and may carry a hard ordering
    // requirement (e.g. a joint job's lead stop, or a client's "X must go
    // first" note) that this client-side NN+2-opt has no way to know about.
    // Only an edited day (stops changed via drag) needs a fresh recompute.
    let drive=0;
    const seq=(d.anchored?[0]:[]).concat(d.stops.map(r=>N[r])).concat(d.anchored?[0]:[]);
    for(let i=0;i<seq.length-1;i++) drive+=leg(seq[i],seq[i+1]);
    return {order:[...d.stops], drive:drive/60,
            path:d.stops.map(r=>N[r])};
  }
  // Edited day: re-route with the SAME algorithm the Python pipeline uses
  // (route_exact -- exhaustive permutation over the true asymmetric
  // durations), so the hours shown here are the pipeline's numbers rather
  // than an approximation of them. Days are <=8 stops, so 8! x 9 lookups is
  // a few milliseconds. Held-Karp covers the larger cases an edit can
  // create. A forced-first stop is pinned and only the remainder permuted,
  // exactly as build_day does.
  const startIdx = (d.startRow!=null && d.stops.includes(d.startRow))
                 ? N[d.startRow] : null;
  const free = startIdx==null ? idx : idx.filter(i=>i!==startIdx);
  const head = d.anchored ? [0] : [];
  const tail = d.anchored ? [0] : [];
  let best=null, bestSeq=null;

  const score = perm => {
    const seq = head.concat(startIdx==null?[]:[startIdx], perm, tail);
    let t=0; for(let i=0;i<seq.length-1;i++) t+=leg(seq[i],seq[i+1]);
    return {t, seq};
  };
  if(free.length<=8){
    const perm=[], used=new Array(free.length).fill(false);
    (function rec(){
      if(perm.length===free.length){
        const s=score(perm);
        if(best===null || s.t<best){ best=s.t; bestSeq=s.seq.slice(); }
        return;
      }
      for(let i=0;i<free.length;i++){
        if(used[i]) continue;
        used[i]=true; perm.push(free[i]); rec(); perm.pop(); used[i]=false;
      }
    })();
  } else {
    // Held-Karp over the free stops, with a fixed start and (for anchored
    // days) a fixed return to the depot.
    const n=free.length, FULL=1<<n;
    const from = startIdx!=null ? startIdx : (d.anchored?0:free[0]);
    const dp=new Float64Array(FULL*n).fill(Infinity);
    const par=new Int16Array(FULL*n).fill(-1);
    for(let i=0;i<n;i++) dp[(1<<i)*n+i]=leg(from,free[i]);
    for(let m=1;m<FULL;m++) for(let i=0;i<n;i++){
      const cur=dp[m*n+i];
      if(!(m&(1<<i))||cur===Infinity) continue;
      for(let j=0;j<n;j++){
        if(m&(1<<j)) continue;
        const nm2=m|(1<<j), v=cur+leg(free[i],free[j]);
        if(v<dp[nm2*n+j]){ dp[nm2*n+j]=v; par[nm2*n+j]=i; }
      }
    }
    let endBest=Infinity, endI=0;
    for(let i=0;i<n;i++){
      const v=dp[(FULL-1)*n+i]+(d.anchored?leg(free[i],0):0);
      if(v<endBest){ endBest=v; endI=i; }
    }
    const order=[]; let m=FULL-1, i=endI;
    while(i>=0){ order.push(free[i]); const p=par[m*n+i]; m^=(1<<i); i=p; }
    order.reverse();
    bestSeq = head.concat(startIdx==null?[]:[startIdx], order, tail);
    best = endBest + (startIdx!=null?0:0);
  }
  let drive=0; for(let i=0;i<bestSeq.length-1;i++) drive+=leg(bestSeq[i],bestSeq[i+1]);
  const inner = d.anchored? bestSeq.slice(1,-1): bestSeq;
  const idx2row={}; d.stops.forEach(r=>idx2row[N[r]]=r);
  return {order: inner.map(i=>idx2row[i]), drive: drive/60, path:bestSeq};
}
function effH(d,r){
  return (d.half||[]).includes(r) ? (C[r].h26||0)/2 : (C[r].h26||0);
}
// PURE. This used to assign d.stops, and it runs during paint (from both
// buildDayCard and drawDate) -- so merely previewing a candidate day would
// silently reorder days the user never touched. Callers that want the
// reordering apply calc.order themselves.
function dayCalc(d){
  const rt=routeDay(d);
  const order = rt.order.length? rt.order : d.stops;
  const inst = order.reduce((a,r)=>a+effH(d,r),0)/(d.stacked||1);
  const total = inst*60 + rt.drive + (order.length?(d.lunchMin??LUNCH):0);
  return {inst, drive:rt.drive, total, path:rt.path, order};
}

// ---------- moves ----------
function dayById(id, create){
  let d = days.find(x=>x.id===id);
  if(d || !create) return d;
  const [date,crew] = id.split('|');
  d = hydrate({id, date, crew,
               dow:(DATA.days.find(x=>x.date===date)||{}).dow
                   || (SPEC.calendar.find(x=>x.date===date)||{}).dow || '',
               stops:[], geom:null, mi:null, legMi:null});
  days.push(d);
  return d;
}
function applyMove(row, toId, record=true){
  // A brand-new client (just created, never placed anywhere) has no
  // "from" day -- that's a real case, not a bug: just add it to `to`
  // without touching a nonexistent source day.
  const from = days.find(x=>x.stops.includes(row));
  const to = dayById(toId, true);
  if(from){
    from.stops = from.stops.filter(r=>r!==row);
    from.edited = true;
    approved.delete(from.id);
  }
  to.stops.push(row);
  to.edited = true;
  approved.delete(to.id);
  if(record){
    moves.push({row, name:C[row].name, from: from?from.id:null, to:to.id});
    persist();
  }
  days = days.filter(x=>x.stops.length>0 || x.id===toId);
  // Drop approvals for days that no longer exist, so the summary count
  // can't drift upward over a session.
  const live = new Set(days.map(x=>x.id));
  [...approved].forEach(id=>{ if(!live.has(id)) approved.delete(id); });
}

// ---------- constraint engine ----------
// Static rules (dates, categories, weekend/Saturday history, deposits) were
// evaluated in Python by the same predicates validate.py uses; we look the
// answer up. Only the rules that depend on what a day currently CONTAINS
// are evaluated here, because only those change as the user edits.
const ELIG = SPEC.eligibility;
const DATE_IX = {}; ELIG.dates.forEach((dt,i)=>DATE_IX[dt]=i);
const GROUP_OF = {};
SPEC.groups.forEach(g=>g.rows.forEach(r=>GROUP_OF[r]=g));

function staticBlockers(row, date){
  const seq = ELIG.byRow[row];
  const i = DATE_IX[date];
  if(i===undefined) return ['NO_DATE'];
  return seq ? ELIG.sets[seq[i]] : [];
}
function codeMsg(c){ return (SPEC.codes[c]||{}).msg || c; }
// Soft codes constrain how the schedule is BUILT but must not stop a human
// honouring an explicit client request -- Saturdays above all.
function codeSoft(c){ return !!(SPEC.codes[c]||{}).soft; }
function hardBlockers(row, date){ return staticBlockers(row,date).filter(c=>!codeSoft(c)); }
// hardBlockers() alone doesn't know what day it is -- pastBlockers() is
// defined further down (it needs todayISO/minAllowedDate). Combined here
// so every date-legality check in one place includes both.
function dateBlockers(row, date){ return hardBlockers(row,date).concat(pastBlockers(row,date)); }
// Suffix for a date option: a hard-blocker reason if the date is actually
// disabled, else an informational note for the one day worth flagging even
// though it's still workable (Thanksgiving) -- SOFT_CODES elsewhere stay
// silent here on purpose (that's the declutter the move dialog already
// relies on; only THANKS gets called out unconditionally).
function dateLabel(row, date){
  const bl = dateBlockers(row, date);
  if(bl.length) return ` — ${codeMsg(bl[0])}`;
  const ci = SPEC.calendar.find(x=>x.date===date);
  // A standing commitment (e.g. HYROX) doesn't block the date -- staff can
  // still book it -- but it must be visible in the picker so nobody
  // schedules over one without realising.
  if(ci && ci.label) return ` — ${ci.label}`;
  if(ci && ci.kind === 'thanksgiving') return ` — ${codeMsg('THANKS')}`;
  return '';
}

// Deep-enough clone for what-if evaluation. checkPlan must never touch live
// state -- previewing a candidate is not an edit.
function cloneDays(){ return days.map(d=>({...d, stops:[...d.stops]})); }

function radiusOK(row, day){
  if(!day.stops.length) return true;
  // Mirror Python's DIRECTION exactly: candidate -> member. Using the
  // symmetric min would quietly diverge from pack_bins/fill_nearby.
  const v = N[row];
  let best = Infinity;
  day.stops.forEach(s=>{ const t=leg(v, N[s]); if(t<best) best=t; });
  const depotFar = leg(0, v) > 2700;   // rural pockets get the wider radius
  return best <= (depotFar ? K.RADIUS_RURAL_S : K.RADIUS_S);
}

/**
 * Validate a proposed transaction: [{row, to}] applied together.
 * Single drag is just a one-op plan; groups and joint days need the
 * multi-op form or a legal intent gets blocked one atom at a time.
 */
function checkPlan(ops){
  const sim = cloneDays();
  const byId = new Map(sim.map(d=>[d.id,d]));
  const blockers=[], warnings=[];
  const touched = new Set();

  ops.forEach(op=>{
    const from = sim.find(d=>d.stops.includes(op.row));
    if(from){ from.stops = from.stops.filter(r=>r!==op.row); touched.add(from.id); }
    let to = byId.get(op.to);
    if(!to){
      const m = metaFor(op.to);
      const [date,crew] = op.to.split('|');
      to = {...hydrate({id:op.to, date, crew, dow:(SPEC.calendar.find(x=>x.date===date)||{}).dow||'',
                        stops:[], geom:null, mi:null, legMi:null})};
      sim.push(to); byId.set(op.to, to);
    }
    to.stops.push(op.row); to.edited = true; touched.add(to.id);
  });

  const moving = new Set(ops.map(o=>o.row));

  ops.forEach(op=>{
    const [date, crew] = op.to.split('|');
    const c = C[op.row];
    // static
    staticBlockers(op.row, date).forEach(code=>
      (codeSoft(code)?warnings:blockers).push(
        {code, msg:`${c.name}: ${codeMsg(code)}`, short:codeMsg(code)}));
    // joint-day integrity: a half-hours row lives on TWO cards. Moving one
    // side leaves it on the partner at half hours AND here at full hours.
    const src = days.find(d=>d.stops.includes(op.row));
    if(src && (src.half||[]).includes(op.row)){
      const partners = days.filter(d=>d.date===src.date && d.id!==src.id
                                    && d.stops.includes(op.row));
      const alsoMoving = partners.every(p=>ops.some(o=>o.row===op.row && o.to!==p.id)
                                        && ops.filter(o=>o.row===op.row).length>1);
      if(partners.length && !alsoMoving)
        blockers.push({code:'JOINT', msg:`${c.name} is a two-crew job shared with `
          +`${src.joint||'another crew'} — move the whole day, not one card`});
    }
    // same-day group cohesion
    const g = GROUP_OF[op.row];
    if(g){
      const dates = new Set();
      g.rows.forEach(r=>{ const d=sim.find(x=>x.stops.includes(r)); if(d) dates.add(d.date); });
      if(dates.size>1)
        blockers.push({code:'GROUP', msg:`${g.label} must stay on one day — ${g.why}`});
    }
    // geography
    const tgt = byId.get(op.to);
    const others = {...tgt, stops: tgt.stops.filter(r=>!moving.has(r))};
    if(others.stops.length && !radiusOK(op.row, others))
      warnings.push({code:'RADIUS', msg:`${c.name} is more than 30 min from the `
        +`rest of that day — it will add real drive time`,
        short:'30+ min from the rest of that day'});
  });

  // R2 coverage: a club stop needs Crew 1 among the crews working it.
  sim.forEach(d=>d.stops.forEach(r=>{
    if(C[r].cat!=='Country Club') return;
    const crews = sim.filter(x=>x.date===d.date && x.stops.includes(r)).map(x=>x.crew);
    if(!crews.some(c2=>c2.includes('Crew 1')))
      blockers.push({code:'CLUB_CREW', msg:`${C[r].name}: ${codeMsg('CLUB_CREW')}`});
  }));

  // capacity + shape, on every day the plan disturbed
  const deltas = {};
  touched.forEach(id=>{
    const after = byId.get(id) || sim.find(d=>d.id===id);
    const before = days.find(d=>d.id===id);
    const bc = before ? dayCalc(before) : {total:0, drive:0};
    if(!after || !after.stops.length){
      deltas[id] = {before:bc.total, after:0, gone:true};
      return;
    }
    const ac = dayCalc({...after, edited:true});
    deltas[id] = {before:bc.total, after:ac.total,
                  driveBefore:bc.drive, driveAfter:ac.drive,
                  win:after.win, crew:after.crew, date:after.date};
    if(ac.total > after.win)
      // Advisory, not a block (user, 2026-08-01): the day-hours bar and
      // Est. Finish time already say exactly how far over and what time
      // they'd actually get back -- that's enough for a human to judge,
      // unlike the structural rules above (joint-day integrity, deposited
      // dates, same-day groups) which stay hard blocks because breaking
      // those corrupts data rather than just running a long day.
      warnings.push({code:'OVER', dayId:id,
        msg:`${after.crew} on ${after.date} would run `
        +`${(ac.total/60).toFixed(1)}h, past its ${(after.win/60).toFixed(1)}h limit`
        +(after.winReason?` (${after.winReason})`:''),
        short:`runs ${(ac.total/60).toFixed(1)}h — over the ${(after.win/60).toFixed(1)}h limit`});
    else if(after.win > K.DAY_CAP && ac.total > K.DAY_CAP
            && ac.total > bc.total){
      // A stretched window is a negotiated exception for the clients
      // already on that day, NOT spare capacity to fill. Adding to it is
      // legal but should never look free.
      deltas[id].exception = true;
      warnings.push({code:'EXCEPT', dayId:id,
        msg:`${after.crew} on ${after.date} is already an `
        +`over-length day by exception (${after.winReason||'client request'}) — `
        +`adding here pushes it to ${(ac.total/60).toFixed(1)}h`,
        short:'already an over-length day by exception'});
    }
    else if(ac.total < K.DAY_MIN && after.cat==='Standard')
      warnings.push({code:'LIGHT', dayId:id,
        msg:`${after.crew} on ${after.date} drops to `
        +`${(ac.total/60).toFixed(1)}h — under the 7.5h they like to work`,
        short:`light day — ${(ac.total/60).toFixed(1)}h`});
    if(after.stops.length===1 && !after.joint && after.cat==='Standard')
      warnings.push({code:'SINGLE', dayId:id,
        msg:`${after.crew} on ${after.date} would be a single-stop day`,
        short:'their only stop that day'});
  });
  // dedupe by message
  const seen=new Set(), uniq=a=>a.filter(x=>!seen.has(x.msg)&&seen.add(x.msg));
  return {blockers:uniq(blockers), warnings:uniq(warnings), deltas, ok:!blockers.length};
}

/** Everything that moving `row` implies -- groups and joint days travel together. */
function planFor(row, toId){
  const g = GROUP_OF[row];
  const src = days.find(d=>d.stops.includes(row));
  const rows = new Set([row]);
  if(g && g.rows.every(r=>{
      const d=days.find(x=>x.stops.includes(r));
      return d && src && d.date===src.date; }))
    g.rows.forEach(r=>rows.add(r));
  return [...rows].map(r=>({row:r, to:toId}));
}

// ---------- slot finder ----------
// "This client wants Nov 18" -> ranked legal (date, crew) options.
function candidateSlots(){
  const out = [];
  SPEC.calendar.forEach(ci=>{
    const existing = days.filter(d=>d.date===ci.date);
    existing.forEach(d=>out.push({id:d.id, date:d.date, crew:d.crew, day:d, isNew:false}));
    BASE_CREWS.filter(cr=>!existing.some(d=>d.crew===cr)).forEach(cr=>{
      const id=`${ci.date}|${cr}|0`;
      out.push({id, date:ci.date, crew:cr, day:null, isNew:true});
    });
  });
  return out;
}
/** Marginal insertion cost, asymmetric-safe. Upper bound on the re-optimised delta. */
function insertionCost(row, day){
  if(!day || !day.stops.length) return day&&day.anchored ? leg(0,N[row])+leg(N[row],0) : 0;
  const v=N[row], seq=(day.anchored?[0]:[]).concat(day.stops.map(r=>N[r]))
                      .concat(day.anchored?[0]:[]);
  let best=Infinity;
  for(let i=0;i<seq.length-1;i++)
    best=Math.min(best, leg(seq[i],v)+leg(v,seq[i+1])-leg(seq[i],seq[i+1]));
  if(!day.anchored){   // open path: prepend/append are legal too
    best=Math.min(best, leg(v,seq[0]), leg(seq[seq.length-1],v));
  }
  return best;
}
function findSlots(row, wantDate, limit=8){
  const src = days.find(d=>d.stops.includes(row));
  const scored = [];
  candidateSlots().forEach(s=>{
    if(src && s.id===src.id) return;
    if(dateBlockers(row, s.date).length) return;
    const chk = checkPlan(planFor(row, s.id));
    if(!chk.ok) return;
    const dNew = chk.deltas[s.id]||{};
    const dOld = src ? (chk.deltas[src.id]||{}) : {};
    const addTarget = (dNew.driveAfter||0)-(dNew.driveBefore||0);
    const saveSource = (dOld.driveAfter||0)-(dOld.driveBefore||0);
    const net = addTarget + saveSource;
    // Warnings about the day they're LEAVING are identical for every
    // option, so they belong once at the top, not repeated on each row.
    const srcId = src ? src.id : null;
    const isSrc = w => srcId && w.dayId === srcId;
    scored.push({
      slot:s, net, addTarget, saveSource,
      totalAfter:dNew.after, win:dNew.win,
      warnings:chk.warnings.filter(w=>!isSrc(w)),
      sourceWarnings:chk.warnings.filter(isSrc),
      rank:[ wantDate && s.date===wantDate ? 0 : 1,
             dNew.exception ? 1 : 0,   // never present an exception day as free capacity
             s.isNew ? 1 : 0,
             net,
             chk.warnings.length ],
    });
  });
  scored.sort((a,b)=>{
    for(let i=0;i<a.rank.length;i++){
      if(a.rank[i]!==b.rank[i]) return a.rank[i]-b.rank[i];
    }
    return 0;
  });
  // A brand-new crew-day on an empty date is identical whichever crew
  // takes it -- offering the same option three times is noise. Keep the
  // first and note that any crew is free.
  const seenNewDate = new Set();
  const out = [];
  scored.forEach(r=>{
    if(r.slot.isNew && !(r.slot.day && r.slot.day.stops.length)){
      if(seenNewDate.has(r.slot.date)) return;
      seenNewDate.add(r.slot.date);
      r.anyCrew = true;
    }
    out.push(r);
  });
  return out.slice(0, limit);
}

// ---------- real road geometry & mileage ----------
// Every day ships with its real road-following path + exact mileage,
// precomputed offline by route_geometry.py (OSRM /route, not the /table
// durations used to plan the stop order). The instant a day is edited
// that geometry is for the OLD order, so we fetch a fresh one live
// (OSRM's public server allows cross-origin requests) and fall back to
// straight stop-to-stop segments while it's in flight or if it fails.
const MI_PER_M = 1/1609.344;
const liveRouteCache = new Map();
const pendingFetches = new Set();

function seqKeyFor(d){
  return (d.anchored?['D']:[]).concat(d.stops).concat(d.anchored?['D']:[]).join(',');
}
function straightPts(d){
  const pts=[];
  if(d.anchored) pts.push([DATA.depot.lat,DATA.depot.lon]);
  d.stops.forEach(r=>pts.push([C[r].lat,C[r].lon]));
  if(d.anchored) pts.push([DATA.depot.lat,DATA.depot.lon]);
  return pts;
}
async function fetchLiveRoute(d){
  const coords=[];
  if(d.anchored) coords.push([DATA.depot.lon,DATA.depot.lat]);
  d.stops.forEach(r=>coords.push([C[r].lon,C[r].lat]));
  if(d.anchored) coords.push([DATA.depot.lon,DATA.depot.lat]);
  if(coords.length<2) return null;
  const coordStr=coords.map(c=>c.join(',')).join(';');
  try{
    const res=await fetch(`https://router.project-osrm.org/route/v1/driving/${coordStr}`+
      `?overview=full&geometries=geojson&annotations=distance`);
    const j=await res.json();
    if(j.code!=='Ok') return null;
    const route=j.routes[0];
    return {
      geom: route.geometry.coordinates.map(([lo,la])=>[la,lo]),
      mi: route.distance*MI_PER_M,
      legMi: route.legs.map(l=>l.distance*MI_PER_M),
    };
  }catch(e){ return null; }
}
/** {pts, mi, legMi, real, pending} for the day's CURRENT stop order. Uses
 * the precomputed path when untouched; live-fetches (once, cached) after
 * an edit and redraws when it lands. */
function routeGeom(d){
  if(!d.edited && d.geom && d.geom.length){
    return {pts:d.geom, mi:d.mi, legMi:d.legMi||[], real:true, pending:false};
  }
  const key=seqKeyFor(d);
  if(liveRouteCache.has(key)){
    const r=liveRouteCache.get(key);
    return r ? {pts:r.geom, mi:r.mi, legMi:r.legMi, real:true, pending:false}
             : {pts:straightPts(d), mi:null, legMi:[], real:false, pending:false};
  }
  if(!pendingFetches.has(key)){
    pendingFetches.add(key);
    fetchLiveRoute(d).then(r=>{
      liveRouteCache.set(key, r);
      pendingFetches.delete(key);
      render();
    });
  }
  return {pts:straightPts(d), mi:null, legMi:[], real:false, pending:true};
}
function miTxt(mi, pending){
  if(pending) return 'calculating…';
  if(mi==null) return 'mileage n/a';
  return mi.toFixed(1)+' mi';
}

// ---------- map ----------
const map = L.map('map',{zoomSnap:.5});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
const depotIcon = L.divIcon({className:'',html:
  '<div style="background:#1f3d2b;color:#fff;border-radius:6px;padding:2px 7px;font-size:11px;font-weight:700;font-family:Montserrat,sans-serif;letter-spacing:.03em;border:1px solid #162d20">'+IC.home+' DEPOT</div>',iconAnchor:[28,10]});
L.marker([DATA.depot.lat,DATA.depot.lon],{icon:depotIcon,zIndexOffset:1000}).addTo(map)
  .bindPopup('<b>DEPOT</b><br>2860 Antoine Dr, Houston 77092');
let layerGroup = L.layerGroup().addTo(map);

function isOverview(sel){ return ['ALL','ALL-HOU','ALL-DAL'].includes(sel); }
function daysFor(sel){
  if(sel==='ALL') return days;
  if(sel==='ALL-HOU') return days.filter(d=>d.cat!=='M Crowd');
  if(sel==='ALL-DAL') return days.filter(d=>d.cat==='M Crowd');
  return days.filter(d=>d.date===sel);
}
// US format throughout -- this is a Houston crew reading it. Anything
// day-first invites a real misread ("01/12/26" for Dec 1 looks like Jan 12).
function fmtMDY(iso){
  const [y,m,d]=iso.split('-');
  return `${m}/${d}/${y.slice(2)}`;
}
function dowOf(iso){
  const ci=(SPEC.calendar||[]).find(x=>x.date===iso);
  if(ci) return ci.dow;
  const d=days.find(x=>x.date===iso);
  return d?d.dow:'';
}
/** "Mon 11/23/26" -- weekday first, because staff think in weekdays. */
function fmtDate(iso){
  const dw=dowOf(iso);
  return (dw?dw+' ':'')+fmtMDY(iso);
}
// TODAY, read live from the browser clock -- not baked in at build time.
// This file gets used for weeks after it's generated, so "today" has to
// mean whatever day it actually is when someone opens it, not the day
// build_review.py happened to run.
function todayISO(){
  const d=new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
       + `-${String(d.getDate()).padStart(2,'0')}`;
}
function addDaysISO(iso, n){
  const [y,m,d]=iso.split('-').map(Number);
  const dt=new Date(Date.UTC(y,m-1,d));
  dt.setUTCDate(dt.getUTCDate()+n);
  return dt.toISOString().slice(0,10);
}
/** Earliest date this client can legally move to.
 *
 * Ordinarily that's just today -- you cannot schedule an install into the
 * past. But if their CURRENT day already IS today, today is presumably
 * already in motion (the crew may be en route or on site), so the floor
 * steps to tomorrow instead. A client whose install already passed with no
 * action gets floored at today, same as anyone else -- there's no reason
 * to force the new date later than that. */
function minAllowedDate(row){
  const t=todayISO();
  const src=days.find(d=>d.stops.includes(row));
  return (src && src.date===t) ? addDaysISO(t,1) : t;
}
/** Only reason a date can be off the table independent of any client or
 * rule: it's before the floor above. */
function pastBlockers(row, date){
  return date < minAllowedDate(row) ? ['PAST'] : [];
}
function drawDate(date){
  layerGroup.clearLayers();
  let todays = daysFor(date);
  // A crew header was clicked: zoom to just that one crew-day instead of
  // the whole date/pool (cleared back to the full view by picking a date
  // tab again).
  if(focusDayId){
    const focused=todays.find(d=>d.id===focusDayId);
    if(focused) todays=[focused];
  }
  // Dallas nights: crews stay in DFW (no Antoine round-trip) — center on
  // the night's stops. Houston days include the depot in the frame.
  const bounds=[];
  if(date==='ALL' || date==='ALL-HOU' || todays.some(d=>d.anchored))
    bounds.push([DATA.depot.lat,DATA.depot.lon]);
  todays.forEach(d=>{
    const col = CREW_COLORS[d.crew]||'#555';
    const calc = dayCalc(d);
    // route line: real road-following path when we have one (solid),
    // straight stop-to-stop fallback while a live fetch is pending or
    // failed (dashed) — never an "as the crow flies" line presented as real
    if(!isOverview(date)){
      const rg = routeGeom(d);
      if(rg.pts.length>1)
        layerGroup.addLayer(L.polyline(rg.pts,{color:col,weight:rg.real?3.5:2.5,
          opacity:.7,dashArray:rg.real?null:'6 6'})
          .bindPopup(`${d.crew}<br><b>${miTxt(rg.mi,rg.pending)}</b>`));
    }
    d.stops.forEach((r,i)=>{
      const c=C[r]; bounds.push([c.lat,c.lon]);
      const approx = !['street','manual','census'].includes(c.geo);
      const mk=L.circleMarker([c.lat,c.lon],{radius:8,color:'#222',weight:1.5,
        fillColor:col,fillOpacity:.95,dashArray:approx?'3 3':null});
      mk.bindPopup(`<b>${c.name}</b><br>${c.street}, ${c.city} ${c.zip}`+
        `<br>${IC.phone} ${c.phone||'—'}<br>2026: ${c.h26}h · 2025 real: ${c.real25??'—'}h`+
        `<br>Storage: ${c.storage||'—'} ${c.boxes?('· '+c.boxes+' boxes'):''}`+
        `<br><i>${d.crew} · stop ${i+1}${approx?' · approx pin':''}</i>`);
      if(!isOverview(date)){
        mk.bindTooltip(`${i+1}. ${c.name}`,{permanent:true,direction:'right',
          offset:[9,0],className:'name-label'});
      } else {
        const isHalf=(d.half||[]).includes(r);
        const estH=isHalf?(c.h26/2).toFixed(1):c.h26;
        mk.bindTooltip(`<b>${c.name}</b><br>${fmtDate(d.date)} · ${d.crew}`+
          `<br>Est. time: ${estH}h · Box count: ${c.boxes||'—'}`,
          {direction:'top',offset:[0,-8]});
      }
      layerGroup.addLayer(mk);
    });
  });
  if(bounds.length>1){ map.invalidateSize(); map.fitBounds(bounds,{padding:[40,40]}); }
}

// ---------- search ----------
// "Which day is this client on?" -- a plain substring match over C, ranked
// by whether the match starts a word (so a first-name search surfaces the
// matching "Lastname, Firstname" entry before a name that merely contains
// those letters mid-string).
const searchBox = document.getElementById('searchbox');
const searchResults = document.getElementById('searchresults');
function searchClients(q){
  q = q.trim().toLowerCase();
  if(!q) return [];
  const out = [];
  for(const r in C){
    const name = C[r].name, lc = name.toLowerCase();
    const i = lc.indexOf(q);
    if(i<0) continue;
    const wordStart = i===0 || /[\s,.|"]/.test(lc[i-1]);
    out.push({row:+r, name, rank:[wordStart?0:1, i, name.length]});
  }
  out.sort((a,b)=>{
    for(let k=0;k<3;k++) if(a.rank[k]!==b.rank[k]) return a.rank[k]-b.rank[k];
    return 0;
  });
  return out.slice(0,10);
}
/** Navigate to a client's day, zoom the map to their crew, and flash their
 * row in the stop list so it's unmistakable which one you searched for. */
function jumpToClient(row){
  const d = days.find(x=>x.stops.includes(row));
  if(!d){
    alert(C[row].name+' isn\'t on the schedule (dropped, or no address).');
    return;
  }
  selDate = d.date; focusDayId = d.id; render();
  requestAnimationFrame(()=>{
    const el = side.querySelector(`.stop[data-row="${row}"]`);
    if(el){
      el.scrollIntoView({block:'center', behavior:'smooth'});
      el.classList.add('flash');
      setTimeout(()=>el.classList.remove('flash'), 2200);
    }
  });
}
function renderSearch(q){
  const results = searchClients(q);
  if(!q.trim()){ searchResults.style.display='none'; searchResults.innerHTML=''; return; }
  searchResults.innerHTML = results.length ? results.map(r=>{
    const d = days.find(x=>x.stops.includes(r.row));
    const where = d ? `${fmtDate(d.date)} · ${d.crew}` : 'not scheduled';
    return `<div class="srow" data-row="${r.row}">
      <span class="srname">${r.name}</span>
      <span class="srwhere">${where}</span></div>`;
  }).join('') : `<div class="srnone">No client matches "${q}"</div>`;
  searchResults.style.display='block';
  searchResults.querySelectorAll('.srow').forEach(el=>{
    el.onclick=()=>{ jumpToClient(+el.dataset.row);
      searchBox.value=''; searchResults.style.display='none'; searchBox.blur(); };
  });
}
searchBox.addEventListener('input', ()=>renderSearch(searchBox.value));
searchBox.addEventListener('focus', ()=>{ if(searchBox.value) renderSearch(searchBox.value); });
searchBox.addEventListener('keydown', e=>{
  if(e.key==='Escape'){ searchBox.value=''; searchResults.style.display='none'; searchBox.blur(); }
});
document.addEventListener('click', e=>{
  if(!e.target.closest('#searchwrap')) searchResults.style.display='none';
});

// ---------- UI ----------
const strip = document.getElementById('datestrip');
const side = document.getElementById('side');
// Every date on the working calendar, not just ones that happen to have a
// crew-day -- an empty date used to be invisible in the strip, which meant
// there was nowhere to drag a stop TO if you wanted to start a fresh day.
function allDates(){ return SPEC.calendar.map(ci=>ci.date); }

function renderStrip(){
  strip.innerHTML='';
  const mk=(label,val,wknd,empty,tag)=>{
    const b=document.createElement('button');
    b.className='dchip'+(wknd?' wknd':'')+(empty?' empty':'')+(selDate===val?' sel':'')
             +(tag?' tagged':'');
    b.textContent=label; b.dataset.val=val;
    if(tag){
      const s=document.createElement('span'); s.className='dtag'; s.textContent=tag;
      b.appendChild(s);
      b.title=`${tag} — still bookable, just flagged`;
    }
    b.onclick=()=>{selDate=val; focusDayId=null; render();};
    b.ondragover=e=>{e.preventDefault();b.classList.add('dragover');};
    b.ondragleave=()=>b.classList.remove('dragover');
    b.ondrop=e=>{e.preventDefault();b.classList.remove('dragover');
      const row=+e.dataTransfer.getData('row'); if(row&&!isOverview(val)) openMoveDlg(row,val);};
    strip.appendChild(b);
  };
  mk('All','ALL',false);
  mk('All Houston','ALL-HOU',false);
  mk('All Dallas','ALL-DAL',false);
  allDates().forEach(dt=>{
    const ci=SPEC.calendar.find(x=>x.date===dt);
    const dow=dowOf(dt);
    const wknd=['Sat','Sun'].includes(dow);
    const empty=!days.some(x=>x.date===dt);
    mk(`${dow} ${dt.slice(5).replace('-','/')}`,dt,wknd,empty,(ci&&ci.label)||'');
  });
}

function fmtH(m){ return (m/60).toFixed(1)+'h'; }
// Houston day shape (user rule): crews arrive depot 8:00am, roll out 8:30am
// -- only meaningful for a real depot round-trip day (d.anchored); Mi
// Cocina nights and the M Crowd Corporate Office daytime install run on
// their own fixed shift windows instead.
const ARRIVE_MIN = 8*60, DEPART_MIN = 8*60+30;
function fmtClock(mins){
  const h=Math.floor(mins/60)%24, m=Math.round(mins)%60;
  const ap=h>=12?'PM':'AM', h12=h%12===0?12:h%12;
  return `${h12}:${String(m).padStart(2,'0')} ${ap}`;
}
function buildDayCard(d){
  const col=CREW_COLORS[d.crew]||'#555';
  const calc=dayCalc(d);
  const card=document.createElement('div');
  const WIN=d.win||600;
  card.className='card'+(approved.has(d.id)?' approved':'')+(calc.total>WIN?' overwin':'')+
    (focusDayId===d.id?' focused':'');
  card.dataset.dayid=d.id;
  card.innerHTML=`<div class="chead">
    <span class="chead-crew" title="Click to zoom the map to just ${d.crew}'s stops">
      <span class="cdot" style="background:${col}"></span>
      <span class="cname">${d.crew}${d.edited?'<span class="edited">EDITED</span>':''}</span>
    </span>
    <span class="cpeople">${d.joint?IC.link+' with '+d.joint:(d.stacked>1?'×'+d.stacked+' crews':'')}</span>
    <button class="printbtn" title="Print this crew's run sheet for the day">Print sheet</button>
    <button class="okbtn ${approved.has(d.id)?'on':''}">${IC.check} ${approved.has(d.id)?'Approved':'Approve'}</button>
  </div>`;
  card.querySelector('.printbtn').onclick=(e)=>{
    e.stopPropagation();
    printManifests([d], `${d.crew} — ${fmtMDYYYY(d.date)}`);
  };
  card.querySelector('.chead-crew').onclick=()=>{
    focusDayId=d.id;
    document.querySelectorAll('.card.focused').forEach(c=>c.classList.remove('focused'));
    card.classList.add('focused');
    drawDate(selDate);
  };
  card.querySelector('.okbtn').onclick=()=>{
    pushUndo();
    approved.has(d.id)?approved.delete(d.id):approved.add(d.id); persist(); render();};
  if(d.anchored){
    const finishMin=DEPART_MIN+calc.total;
    card.insertAdjacentHTML('beforeend',`<div class="sched">
      <span>${IC.clock} Arrive Depot <b>${fmtClock(ARRIVE_MIN)}</b></span>
      <span>Depart <b>${fmtClock(DEPART_MIN)}</b></span>
      <span>Est. Finish <b>${fmtClock(finishMin)}</b></span>
    </div>`);
  }
  // stops + legs (mileage from the real road path — precomputed if the
  // day is untouched, live-fetched once if it's been edited)
  const path=calc.path||[];
  const rg=routeGeom(d);
  const legMiTxt=(idx)=> rg.pending?' · …mi':(rg.legMi&&rg.legMi[idx]!=null?` · ${rg.legMi[idx].toFixed(1)} mi`:'');
  let legIdx=0;
  d.stops.forEach((r,i)=>{
    const c=C[r];
    if(d.anchored&&i===0&&path.length){
      card.insertAdjacentHTML('beforeend',`<div class="leg">${IC.truck} ${(leg(0,N[r])/60).toFixed(0)} min from depot${legMiTxt(legIdx)}</div>`);
      legIdx++;
    }
    const el=document.createElement('div');
    el.className='stop'; el.draggable=true; el.dataset.row=r;
    const approx=!['street','manual','census'].includes(c.geo);
    const isHalf=(d.half||[]).includes(r);
    const locked=c.locked && c.locked===d.date;
    el.innerHTML=`<span class="num" style="background:${col}">${i+1}</span>
      <div class="body"><div class="nm">${c.name}
        ${isHalf?`<span class="badge" style="background:#e8f0e8;color:#1f3d2b">${IC.link} joint w/ ${d.joint} — ${(c.h26/2).toFixed(1)}h each</span>`:''}
        ${locked?'<span class="badge lock">deposited — date reserved</span>':''}
        ${SPEC.forceFirst[r]?'<span class="badge">goes first</span>':''}
        ${c.visitType && c.visitType!=='Standard'?`<span class="badge visittype">${c.visitType}</span>`:''}
        ${approx?'<span class="badge approx">approx pin</span>':''}</div>
      <div class="sub">${c.zone}</div>
      <div class="sub">Est install time: <b>${isHalf?(c.h26/2).toFixed(1):c.h26}h</b></div>
      <div class="sub">Box count: <b>${c.boxes||'—'}</b></div>
      ${c.advice?`<div class="sub advice">${c.advice}</div>`:''}</div>
      <div class="stopbtns">
        <button class="mv find">find date</button>
        <button class="mv">move ▾</button>
      </div>`;
    el.querySelector('.find').onclick=()=>openSlotFinder(r);
    el.querySelector('.mv:not(.find)').onclick=()=>openMoveDlg(r,null);
    el.ondragstart=e=>e.dataTransfer.setData('row',r);
    card.appendChild(el);
    const nxt=d.stops[i+1];
    if(nxt!==undefined){
      card.insertAdjacentHTML('beforeend',`<div class="leg">${IC.truck} ${(leg(N[r],N[nxt])/60).toFixed(0)} min${legMiTxt(legIdx)}</div>`);
      legIdx++;
    } else if(d.anchored){
      card.insertAdjacentHTML('beforeend',`<div class="leg">${IC.truck} ${(leg(N[r],0)/60).toFixed(0)} min back to depot${legMiTxt(legIdx)}</div>`);
      legIdx++;
    }
  });
  const pct=Math.min(100,calc.total/WIN*100);
  const barcol=calc.total>WIN?'#b91c1c':(pct>92?'#ca8a04':'#2d5a33');
  const winH=(WIN/60)%1?(WIN/60).toFixed(1):(WIN/60).toFixed(0);
  const shiftTxt=(d.lunchMin??40)?`incl. ${((d.lunchMin??40)/60).toFixed(1)}h lunch`:
    (d.win===480?`${IC.sun} day shift 9am-5pm`:`${IC.moon} night shift`);
  card.insertAdjacentHTML('beforeend',`<div class="cfoot">
    <div class="tot"><span>Total day hours</span>
    <b style="color:${barcol}">${fmtH(calc.total)} / ${winH}h</b></div>
    <div class="bar"><i style="width:${pct}%;background:${barcol}"></i></div>
    <div class="tot" style="margin-top:6px"><span>Total Install Time:</span><b>${calc.inst.toFixed(1)}h</b></div>
    <div class="tot"><span>Total Drive Time:</span><b>${fmtH(calc.drive)} (${miTxt(rg.mi,rg.pending)})</b></div>
    <div class="tot"><span>Total Day Work Time (estimated):</span><b style="color:${barcol}">${fmtH(calc.total)} · ${shiftTxt}</b></div>
  </div>`);
  card.ondragover=e=>{e.preventDefault();card.classList.add('dragover');};
  card.ondragleave=()=>card.classList.remove('dragover');
  card.ondrop=e=>{e.preventDefault();card.classList.remove('dragover');
    const row=+e.dataTransfer.getData('row');
    if(row && !d.stops.includes(row)) commitPlan(planFor(row, d.id));};
  return card;
}
function renderCards(){
  side.innerHTML='';
  if(isOverview(selDate)){
    // Full detail, every crew-day in the pool, long-form list grouped by
    // date (client request: same crew/stop detail as a single day, just
    // stacked for the whole Houston or Dallas run).
    const pool=daysFor(selDate);
    const title=selDate==='ALL'?'Overview':(selDate==='ALL-HOU'?'Houston — all days':'Dallas — all nights (Mi Cocina)');
    const hdr=document.createElement('h3'); hdr.className='ovtitle'; hdr.textContent=title;
    side.appendChild(hdr);
    const dates=[...new Set(pool.map(d=>d.date))].sort();
    dates.forEach(dt=>{
      const ds=pool.filter(d=>d.date===dt).sort((a,b)=>a.crew.localeCompare(b.crew));
      const dh=document.createElement('div'); dh.className='ovdate';
      dh.textContent=`${ds[0].dow} ${dt}`;
      side.appendChild(dh);
      ds.forEach(d=>side.appendChild(buildDayCard(d)));
    });
    renderLog(); return;
  }
  const onThisDate = days.filter(d=>d.date===selDate);
  // Standing commitment for this date (HYROX etc.) -- advisory banner, shown
  // whether or not anything is booked, so an empty tagged day still explains
  // itself rather than just looking free.
  const ciSel = SPEC.calendar.find(x=>x.date===selDate);
  if(ciSel && ciSel.label){
    const t=document.createElement('div'); t.className='ovdate';
    t.innerHTML=`${fmtDate(selDate)} <span id="daytag">${ciSel.label}</span>`
              + `<div class="mvcrewempty" style="font-weight:500;margin-top:3px">`
              + `Reserved for ${ciSel.label} — you can still book work here.</div>`;
    side.appendChild(t);
  }
  if(!onThisDate.length){
    const p=document.createElement('p'); p.className='nothingyet';
    p.textContent=`Nothing on ${fmtDate(selDate)} yet.`;
    side.appendChild(p);
  }
  if(onThisDate.length>1){
    const all=document.createElement('button');
    all.className='printbtn'; all.style.cssText='margin:0 0 10px;width:100%';
    all.textContent=`Print all ${onThisDate.length} crew sheets for ${fmtDate(selDate)}`;
    all.onclick=()=>printDate(selDate);
    side.appendChild(all);
  }
  onThisDate.forEach(d=>side.appendChild(buildDayCard(d)));
  // Blank boxes the user clicked "+ Add a crew" for but hasn't dropped a
  // stop into yet -- a real day with that crew name now exists means the
  // pending placeholder did its job, so drop it instead of showing both.
  pendingSlots[selDate] = (pendingSlots[selDate]||[])
    .filter(cr=>!onThisDate.some(d=>d.crew===cr));
  pendingSlots[selDate].forEach(cr=>side.appendChild(buildCrewSlot(selDate, cr)));
  side.appendChild(buildAddCrewButton(selDate));
  renderLog();
}
let pendingSlots = {};   // date -> ["Crew 4", ...] clicked but not yet filled
/** The next unused occurrence id for (date, crew) -- ids are
 * date|crew|occurrence, and a crew can legitimately run two separate
 * day-instances on the same date (e.g. a stacked overflow job). */
function nextOccId(date, crew){
  let i=0;
  while(days.some(d=>d.id===`${date}|${crew}|${i}`)) i++;
  return `${date}|${crew}|${i}`;
}
/** One blank, draggable-into box for `crew` on `date`. Used for a slot the
 * user just clicked "+ Add a crew" for -- becomes a real card the moment
 * something's dropped into it. */
function buildCrewSlot(date, crew){
  const id = nextOccId(date, crew);
  const zone=document.createElement('div');
  zone.className='emptycrew'; zone.dataset.crew=crew;
  zone.style.setProperty('--crew-color', CREW_COLORS[crew]||'#555');
  zone.innerHTML=`<span class="cdot" style="background:${CREW_COLORS[crew]||'#555'}"></span>`
                +`Drag a stop here to start ${crew}'s day`;
  zone.ondragover=e=>{e.preventDefault();zone.classList.add('dragover');};
  zone.ondragleave=()=>zone.classList.remove('dragover');
  zone.ondrop=e=>{e.preventDefault();zone.classList.remove('dragover');
    const row=+e.dataTransfer.getData('row');
    if(row) commitPlan(planFor(row, id));};
  return zone;
}
/** Single "+ Add a crew" button. Each click appends one more blank box,
 * numbered one past however many crews (real + still-pending) are already
 * on this date -- 3 crews present -> "Crew 4", 2 present -> "Crew 3", and
 * so on. Not limited to the 3 base crews: a big day can genuinely need a
 * 4th, ad-hoc crew. */
function buildAddCrewButton(date){
  const btn=document.createElement('button');
  btn.className='addcrewbtn'; btn.type='button';
  btn.innerHTML=`<span class="plus">+</span> Add a crew`;
  btn.onclick=()=>{
    const have=days.filter(d=>d.date===date).length + (pendingSlots[date]||[]).length;
    const label=`Crew ${have+1}`;
    pendingSlots[date]=[...(pendingSlots[date]||[]), label];
    render();
  };
  return btn;
}
function renderLog(){
  const log=document.createElement('div'); log.id='log';
  const fmtId=id=>{if(!id) return 'new'; const [dt,cr]=id.split('|'); return `${fmtMDY(dt)} ${cr}`;};
  log.innerHTML=`<h3>Session changes (${moves.length} moves · ${approved.size} approved)</h3>`+
    moves.slice(-8).map(m=>`<div class="ent">→ ${m.name}: ${fmtId(m.from)} → ${fmtId(m.to)}</div>`).join('')+
    `<div class="undobar">
       <button id="undoBtn" ${undoStack.length?'':'disabled'}>${IC.undo} Undo${
         undoStack.length>1?` (${undoStack.length})`:''}</button>
       <button id="redoBtn" ${redoStack.length?'':'disabled'}>Redo${
         redoStack.length>1?` (${redoStack.length})`:''}</button>
       <button id="histBtn">${IC.clock} History</button>
     </div>
     <div><button onclick="exportNotebook()">${IC.down} Save notebook</button>
     <button onclick="exportCSV()">${IC.down} Export CSV</button>
     <button onclick="exportJSON()">${IC.down} Export JSON</button>
     <button onclick="resetAll()">Reset all</button></div>`;
  side.appendChild(log);
  const u=log.querySelector('#undoBtn'), r=log.querySelector('#redoBtn');
  if(u) u.onclick=undo;
  if(r) r.onclick=redo;
  log.querySelector('#histBtn').onclick=openHistory;
}

// ---------- commit gate ----------
// Every user-initiated edit goes through here. Deliberately NOT inside
// applyMove: loading saved state replays through applyMove and must not be
// re-validated against intermediate states.
function commitPlan(ops, {force=false}={}){
  const chk = checkPlan(ops);
  if(chk.blockers.length && !force){
    alert('Cannot make this change:\n\n'
      + chk.blockers.map(b=>'  • '+b.msg).join('\n'));
    return false;
  }
  if(chk.warnings.length && !confirm('Heads up:\n\n'
      + chk.warnings.map(w=>'  • '+w.msg).join('\n')
      + '\n\nMake the change anyway?')) return false;
  pushUndo();
  ops.forEach(o=>applyMove(o.row, o.to));
  render();
  return true;
}

// ---------- move dialog ----------
const mvdlg=document.getElementById('mvdlg');
let mvRow=null;
function openMoveDlg(row,presetDate){
  mvRow=row;
  const c=C[row];
  document.getElementById('mvtitle').textContent='Move: '+c.name;
  const dsel=document.getElementById('mvdate'), csel=document.getElementById('mvcrew');
  // Every LEGAL date, not just ones that already have crews. The old list
  // was built from staffed days, which hid 10 working dates -- including
  // the open days deliberately left in the schedule for exactly this.
  dsel.innerHTML=SPEC.calendar.map(ci=>{
    const bl=dateBlockers(row, ci.date);
    const lab=`${fmtDate(ci.date)}${dateLabel(row, ci.date)}`;
    return `<option value="${ci.date}" ${bl.length?'disabled':''} `
         + `${ci.date===(presetDate||selDate)&&!bl.length?'selected':''}>${lab}</option>`;
  }).join('');
  if(dsel.selectedIndex<0 || dsel.options[dsel.selectedIndex].disabled){
    const first=[...dsel.options].findIndex(o=>!o.disabled);
    if(first>=0) dsel.selectedIndex=first;
  }
  // Split in two: rebuilding csel's <option> list resets its selection to
  // the browser default, so that rebuild must only run when the DATE
  // changes (the set of valid crews changed) -- never from csel's own
  // onchange, or picking Crew 2/3 would immediately snap back to Crew 1
  // the moment the rebuild ran. Each option's checkPlan result is already
  // per-crew and independent of which one is currently selected, so a
  // crew-only change never needs the options themselves recomputed.
  const renderCrewInfo=()=>{ const dt=dsel.value;
    const existing=days.filter(d=>d.date===dt);
    // Quick answer to "which crew should I drag this onto" -- every crew's
    // current property list for this date, at a glance, before picking one.
    const info=document.getElementById('mvcrewinfo');
    info.innerHTML=BASE_CREWS.map(cr=>{
      // A crew can have more than one day-instance here (stacked/overflow
      // job) -- fold every occurrence's stops together for the glance view.
      const ds=existing.filter(x=>x.crew===cr);
      const names=ds.flatMap(d=>d.stops.filter(r=>r!==row).map(r=>C[r].name));
      const isSel=csel.value.startsWith(`${dt}|${cr}|`);
      return `<div class="mvcrewrow${isSel?' mvsel':''}">`
        +`<span class="cdot" style="background:${CREW_COLORS[cr]||'#555'}"></span>`
        +`<span class="mvcrewnames"><b>${cr}</b>`
        +(names.length?': '+names.join(', '):(ds.length?' <span class="mvcrewempty">(only this stop)</span>':' <span class="mvcrewempty">not working this date</span>'))
        +'</span></div>';
    }).join('');
    const note=document.getElementById('mvnote');
    const sel=csel.value;
    if(sel){
      const chk=checkPlan(planFor(row, sel));
      const d=chk.deltas[sel]||{};
      note.innerHTML = d.after!=null
        ? `That day would run <b>${(d.after/60).toFixed(1)}h</b> of `
          +`${(d.win/60).toFixed(1)}h`
          + (chk.warnings.length?`<br><span class="warn">${chk.warnings.map(w=>w.msg).join('<br>')}</span>`:'')
        : '';
    } else note.innerHTML='';
  };
  const fillCrews=()=>{ const dt=dsel.value;
    const existing=days.filter(d=>d.date===dt);
    // A crew can have two separate day-instances on the same date (a
    // stacked/overflow job added via the "add a crew" zone) -- disambiguate
    // those options by stop count, otherwise they're identical labels.
    const crewCounts={};
    existing.forEach(d=>{ crewCounts[d.crew]=(crewCounts[d.crew]||0)+1; });
    const opts=existing.map(d=>{
      const chk=checkPlan(planFor(row, d.id));
      const tag=d.win===480?' (day shift 9-5)':(d.win===K.NIGHT?' (night)':'');
      const dupe=crewCounts[d.crew]>1?` — ${d.stops.length} stop${d.stops.length===1?'':'s'}`:'';
      return `<option value="${d.id}" ${chk.ok?'':'disabled'}>${d.crew}${tag}${dupe}`
           + `${chk.ok?'':' — '+chk.blockers[0].msg}</option>`;});
    BASE_CREWS.filter(cr=>!existing.some(d=>d.crew===cr)).forEach(cr=>{
      const id=`${dt}|${cr}|0`;
      const chk=checkPlan(planFor(row, id));
      opts.push(`<option value="${id}" ${chk.ok?'':'disabled'}>${cr} (new day)`
              + `${chk.ok?'':' — '+chk.blockers[0].msg}</option>`);});
    csel.innerHTML=opts.join('');
    renderCrewInfo();
  };
  dsel.onchange=fillCrews; csel.onchange=renderCrewInfo; fillCrews();
  mvdlg.showModal();
}
document.getElementById('mvgo').onclick=()=>{
  const to=document.getElementById('mvcrew').value;
  if(!to) return;
  if(commitPlan(planFor(mvRow, to))) mvdlg.close();
};

// ---------- new client / manual stop ----------
// Covers three cases in one form: a genuinely new job, a multi-visit
// anomaly (install -> event takedown -> reinstall, or install-one-day
// -> takedown-next-day -- each visit is its own entry here, scheduled on
// its own date), and a callback add-on (bought more / broke something /
// didn't finish). All three are just "a new addressable stop" underneath.
const ncdlg=document.getElementById('ncdlg');
document.getElementById('newclientbtn').onclick=()=>{
  ['ncname','ncaddr','ncnotes'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('nchours').value='1';
  document.getElementById('ncpeople').value='';
  document.getElementById('nctype').value='Standard';
  document.getElementById('ncerr').textContent='';
  ncdlg.showModal();
};
async function geocodeAddress(q){
  const res = await fetch(`https://nominatim.openstreetmap.org/search`
    + `?format=json&limit=1&countrycodes=us&q=${encodeURIComponent(q)}`);
  const j = await res.json();
  if(!j.length) return null;
  return {lat:+j[0].lat, lon:+j[0].lon, display:j[0].display_name};
}
document.getElementById('ncgo').onclick=async()=>{
  const name=document.getElementById('ncname').value.trim();
  const addr=document.getElementById('ncaddr').value.trim();
  const hours=+document.getElementById('nchours').value || 0;
  const people=+document.getElementById('ncpeople').value || null;
  const visitType=document.getElementById('nctype').value;
  const notes=document.getElementById('ncnotes').value.trim();
  const err=document.getElementById('ncerr');
  const go=document.getElementById('ncgo');
  err.textContent='';
  if(!name){ err.textContent='Name is required.'; return; }
  if(!addr){ err.textContent='Address is required -- needed to place it on the map and check drive time.'; return; }
  go.disabled=true; go.textContent='Looking up address…';
  try{
    const geo = await geocodeAddress(addr);
    if(!geo){
      err.textContent='Couldn\'t find that address -- try adding city/state, or a more exact street match.';
      return;
    }
    go.textContent='Checking drive times…';
    const row = await createSyntheticClient({name, street:addr, lat:geo.lat, lon:geo.lon,
      hours, visitType, notes, people});
    persist();
    ncdlg.close();
    openMoveDlg(row, null);
  }catch(e){
    err.textContent='Address lookup failed (network error) -- try again.';
  }finally{
    go.disabled=false; go.textContent='Look up & add';
  }
};

// ---------- slot finder ----------
const sfdlg=document.getElementById('sfdlg');
function openSlotFinder(row){
  const c=C[row];
  document.getElementById('sftitle').textContent='Find a new date: '+c.name;
  const wsel=document.getElementById('sfwant');
  wsel.innerHTML='<option value="">Any date that works</option>'
    + SPEC.calendar.map(ci=>{
        const bl=dateBlockers(row, ci.date);
        return `<option value="${ci.date}" ${bl.length?'disabled':''}>`
             + `${fmtDate(ci.date)}${dateLabel(row, ci.date)}</option>`;}).join('');
  const body=document.getElementById('sfbody');
  const run=()=>{
    const want=wsel.value||null;
    const res=findSlots(row, want);
    const cur=days.find(d=>d.stops.includes(row));
    let head='';
    if(want && !res.some(r=>r.slot.date===want)){
      head=`<div class="sfnone"><b>No crew can take them on ${fmtDate(want)}.</b>`
         + ` Closest workable options:</div>`;
    }
    // Consequences for the day they're LEAVING are the same whichever
    // option is chosen -- state them once.
    const sw = res.length ? res[0].sourceWarnings : [];
    if(sw.length && cur)
      head += `<div class="sfsrc"><b>Leaving ${cur.crew} on ${fmtDate(cur.date)}:</b> `
            + sw.map(w=>w.short||w.msg).join(' · ')+`</div>`;
    body.innerHTML = head + (res.length? res.map((r,i)=>{
      // deltas are already in MINUTES (dayCalc divides seconds by 60)
      const s=r.slot, mins=Math.round(r.net);
      const pct=Math.min(100, r.totalAfter/r.win*100);
      const tight=pct>92;
      // Extra driving is the number staff actually weigh; say it plainly.
      const drive = mins<=-2 ? {t:`saves ${Math.abs(mins)} min`, k:'good'}
                  : mins<=2  ? {t:'no extra driving',            k:'good'}
                  : mins<=30 ? {t:`+${mins} min driving`,        k:''}
                             : {t:`+${mins} min driving`,        k:'bad'};
      const dot = CREW_COLORS[s.crew]||'#555';
      return `<div class="sfrow${i===0?' top':''}" data-to="${s.id}">
        <div class="sfhead">
          <span class="sfdate">${fmtDate(s.date)}</span>
          <span class="sfcrew"><i style="background:${dot}"></i>${r.anyCrew?'any crew':s.crew}</span>
          ${want&&s.date===want?'<span class="badge store">their date</span>':''}
          ${s.isNew?'<span class="badge">new crew-day</span>':''}
          ${i===0?'<span class="badge best">best fit</span>':''}
        </div>
        <div class="sfstats">
          <div class="sfstat">
            <span class="sflab">Day length</span>
            <span class="sfval">${(r.totalAfter/60).toFixed(1)}h<span class="sfmut"> / ${(r.win/60).toFixed(0)}h</span></span>
            <span class="sfbar"><i style="width:${pct}%;background:${tight?'#ca8a04':'#2d5a33'}"></i></span>
          </div>
          <div class="sfstat">
            <span class="sflab">Driving</span>
            <span class="sfval ${drive.k}">${drive.t}</span>
          </div>
        </div>
        ${r.warnings.length?`<ul class="sfwarn">${r.warnings.map(w=>
          `<li>${w.short||w.msg}</li>`).join('')}</ul>`:''}
        <button class="go sfgo">Move here</button></div>`;}).join('')
      : `<div class="sfnone">No workable slot found for ${c.name}.</div>`);
    body.querySelectorAll('.sfgo').forEach(b=>b.onclick=()=>{
      const to=b.closest('.sfrow').dataset.to;
      if(commitPlan(planFor(row, to))) sfdlg.close();
    });
  };
  wsel.onchange=run; run();
  sfdlg.showModal();
}

// ---------- export ----------
function exportJSON(){
  const out={approved:[...approved],moves,final:days.map(d=>({date:d.date,crew:d.crew,
    stops:d.stops.map(r=>C[r].name)}))};
  dl('tbdg-2026-review-changes.json',JSON.stringify(out,null,2));
}
function exportCSV(){
  let rows=[['Client','Date','Crew','Order']];
  days.forEach(d=>d.stops.forEach((r,i)=>rows.push([C[r].name,d.date,d.crew,i+1])));
  dl('tbdg-2026-assignments.csv',rows.map(r=>r.map(x=>`"${x}"`).join(',')).join('\n'));
}
function dl(name,text){const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([text]));a.download=name;a.click();}
// RFC4180-ish: always quote, double up embedded quotes. exportCSV above
// doesn't bother (its fields can't contain commas/quotes) -- billing rows
// pull free-text notes and addresses, which routinely do.
function csvCell(v){
  const s = v==null ? '' : String(v);
  return `"${s.replace(/"/g,'""')}"`;
}
/** One mailable address line from the sheet's messy parts.
 * Several source rows jam the whole address into the street cell (or into
 * CITY), so naively joining street+city+state+zip yields "…Houston, TX
 * 77024, TX". Append each part only when it isn't already present. */
/** Split the sheet's messy address cells into real ADDRESS / CITY / ST / ZIP
 * columns. Six source rows need repair: some jam the whole address into the
 * street cell (or into CITY, leaving street holding a first name), some
 * repeat "City, TX" on the end of the street, and one carries the client's
 * own name on the first line. */
/** MM/DD/YYYY for the billing export. fmtMDY() is the UI's 2-digit-year
 * form; an invoice wants the full year. */
function fmtMDYYYY(iso){
  const [y,m,d]=String(iso).split('-');
  return (y&&m&&d) ? `${m}/${d}/${y}` : String(iso||'');
}
function addrParts(c){
  const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  let street=(c.street||'').replace(/\s*\n\s*/g,', ').trim();
  let city=(c.city||'').trim(), st=(c.st||'TX').trim(), zip=(c.zip||'').trim();
  // CITY sometimes holds the real street (street cell holds a first name).
  if(city && /\d/.test(city) && !/\d/.test(street)){
    const p=city.split(',').map(s=>s.trim()).filter(Boolean);
    if(p.length>=2){ street=p[0]; city=p[1].replace(/\s*(TX|Texas)$/i,'').trim(); }
  }
  // A manually-added client can carry the whole "street, city, ST zip" in
  // the street cell with CITY/ZIP empty -- pull them back out.
  if(!city || !zip){
    const m=street.match(/^(.*?),\s*([A-Za-z .'-]+),\s*(TX|Texas)\s*(\d{5})?\s*$/i);
    if(m){ street=m[1].trim(); city=city||m[2].trim(); st=st||'TX'; zip=zip||(m[4]||''); }
  }
  if(!zip){ const z=street.match(/\b(\d{5})\b\s*$/); if(z){ zip=z[1]; street=street.replace(/\s*\b\d{5}\b\s*$/,'').replace(/,\s*$/,'').trim(); } }
  // Drop the client's own name if it leaked onto the street line.
  const first=(c.name||'').split(',')[0].trim();
  if(first) street=street.replace(new RegExp('^'+esc(c.name)+'\\s*,\\s*','i'),'')
                         .replace(new RegExp('^'+esc(first)+'\\s*,\\s*','i'),'').trim();
  // Strip a duplicated ", City TX 77xxx" tail off the street.
  if(city) street=street.replace(
    new RegExp(',?\\s*'+esc(city)+'\\s*,?\\s*(TX|Texas)?\\s*\\d{0,5}\\s*$','i'),'').trim();
  street=street.replace(/,?\s*(TX|Texas)\s*\d{0,5}\s*$/i,'').replace(/,\s*$/,'').trim();
  return {street, city, st, zip};
}
/** 2026 price from what the client was ACTUALLY invoiced in 2025 (user,
 * 2026-08-12), so the number is defensible line by line:
 *
 *   storage      = boxes x $75, carried over UNCHANGED (the rate didn't move)
 *   remainder    = 2025 actual invoice - storage
 *   install      = remainder / 2, +5%
 *   takedown     = remainder / 2, +5%
 *   2026 total   = install + takedown + storage
 *
 * Only clients with a real 2025 invoice are priced this way. M Crowd and the
 * contract accounts bill on their own terms, so they're marked rather than
 * guessed at; a 2025 invoice smaller than the storage owed is a data gap,
 * not a $0 job, so it goes to manual review instead of a negative. */
const UPLIFT = 1.05;
/** 2026 price for one client, in preference order:
 *   1. M Crowd -- contract, billed outside this sheet entirely.
 *   2. Carlton Woods and Woodlands CC -- negotiated per club, left blank on
 *      purpose (user, 2026-08-17) rather than guessed. Matched by NAME, not
 *      by the "Country Club" category: Royal Oaks is also a country club but
 *      has a real 2025 invoice, and blanketing the category silently dropped
 *      it from the priced list.
 *   3. A real 2025 invoice -> that +5%. Storage carries over flat, and the
 *      remainder splits evenly between install and takedown because the
 *      2025 sheet's own takedown formula is literally "=install".
 *   4. No 2025 invoice -> the sheet's own ideal figure (crew x rate x
 *      hours off the 2026 rate card). No uplift: that rate card is already
 *      2026 pricing, so adding 5% would double-count the increase.
 *   5. Nothing to work from -> blank, flagged for manual pricing. */
function price2026(c){
  const S = typeof c.storageFee==='number' ? c.storageFee : 0;
  const R = c.invoice25;
  if(c.cat==='M Crowd')     return {basis:'Contract — M Crowd billed separately'};
  if(/carlton woods|woodlands cc/i.test(c.name))
                            return {basis:'Club contract — priced separately'};
  if(typeof R==='number'){
    if(R - S < 0)           return {basis:'MANUAL — 2025 invoice below storage owed', stor:S};
    const inst = Math.round(((R - S) / 2) * UPLIFT * 100) / 100;
    return {inst, tdwn:inst, stor:S, total:Math.round((inst*2 + S)*100)/100,
            basis:'2025 invoice +5% (storage flat)'};
  }
  if(typeof c.installFee==='number'){
    const inst = c.installFee;
    const tdwn = typeof c.takedownFee==='number' ? c.takedownFee : inst;
    return {inst, tdwn, stor:S, total:Math.round((inst + tdwn + S)*100)/100,
            basis:'2026 ideal (crew × rate × hours) — no 2025 invoice on file'};
  }
  return {basis:'MANUAL — no 2025 invoice and no rate-card estimate'};
}
function buildBillingRows(scope){
  const scopedDays = scope==='houston' ? days.filter(d=>d.cat!=='M Crowd')
                    : scope==='dallas'  ? days.filter(d=>d.cat==='M Crowd')
                    : days;
  // A joint job sits on two crews' cards for the same date -- one billing
  // line per CLIENT, not per crew-assignment, or a two-crew job would look
  // like two separate charges.
  const seen = new Map();
  scopedDays.forEach(d=>d.stops.forEach(r=>{ if(!seen.has(r)) seen.set(r, d.date); }));
  // 2025 total sits immediately right of the 2026 total so the year-over-year
  // comparison is a single glance, with the basis right after it.
  const rows = [['Client name','Bill-to name/company','ADDRESS','CITY','ST','ZIP','Install date',
    '2026 install price','2026 takedown price','2026 storage price','2026 TOTAL invoice',
    '2025 total invoice (actual)','Pricing basis',
    'Repairs & install notes','Billing notes']];
  [...seen.entries()]
    .sort((a,b)=> a[1]<b[1] ? -1 : a[1]>b[1] ? 1 : C[a[0]].name.localeCompare(C[b[0]].name))
    .forEach(([r,date])=>{
      const c = C[r], a = addrParts(c), p = price2026(c);
      rows.push([
        c.name, c.name, a.street, a.city, a.st, a.zip, fmtMDYYYY(date),
        p.inst ?? '', p.tdwn ?? '', p.stor ?? '', p.total ?? '',
        c.invoice25 ?? '', p.basis,
        c.repairNotes || '', '',
      ]);
    });
  // Footer: column totals, blank-separated so a spreadsheet's own SUM over
  // the data range doesn't swallow the total row. Only the money columns
  // add up; the rest stay blank rather than showing a meaningless count.
  const MONEY=[7,8,9,10,11];
  const body=rows.slice(1);
  const sums={};
  MONEY.forEach(i=>{ sums[i]=body.reduce((s,r)=>s+(typeof r[i]==='number'?r[i]:0),0); });
  const priced=body.filter(r=>typeof r[10]==='number').length;
  const foot=rows[0].map(()=>'');
  foot[0]=`TOTAL — ${body.length} clients (${priced} priced)`;
  MONEY.forEach(i=>{ foot[i]=Math.round(sums[i]*100)/100; });
  rows.push(rows[0].map(()=>''));   // spacer
  rows.push(foot);
  return rows;
}

// ---------- export writers (CSV / real .xlsx / print-to-PDF) ----------
// The tool is one self-contained file with no CDN access, so .xlsx is built
// by hand: an xlsx IS a zip of XML parts, and a zip written with the STORED
// (uncompressed) method needs nothing but a CRC32. Worth it over dumping CSV
// with an .xls extension -- numbers arrive as numbers, money is formatted,
// the header freezes, and Excel opens it without a "corrupt file" warning.
const CRC_TABLE=(()=>{const t=new Uint32Array(256);
  for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);t[n]=c>>>0;}
  return t;})();
function crc32(bytes){let c=0xFFFFFFFF;
  for(let i=0;i<bytes.length;i++) c=CRC_TABLE[(c^bytes[i])&0xFF]^(c>>>8);
  return (c^0xFFFFFFFF)>>>0;}
function zipFile(files){
  const enc=new TextEncoder(), chunks=[], central=[]; let offset=0;
  const d=new Date(), dosT=((d.getHours()<<11)|(d.getMinutes()<<5)|(d.getSeconds()/2))&0xFFFF;
  const dosD=(((d.getFullYear()-1980)<<9)|((d.getMonth()+1)<<5)|d.getDate())&0xFFFF;
  const u16=v=>[v&255,(v>>8)&255], u32=v=>[v&255,(v>>8)&255,(v>>16)&255,(v>>24)&255];
  files.forEach(f=>{
    const name=enc.encode(f.name), body=enc.encode(f.data), crc=crc32(body);
    const local=[...u32(0x04034b50),...u16(20),...u16(0),...u16(0),...u16(dosT),...u16(dosD),
      ...u32(crc),...u32(body.length),...u32(body.length),...u16(name.length),...u16(0)];
    chunks.push(new Uint8Array(local),name,body);
    central.push([...u32(0x02014b50),...u16(20),...u16(20),...u16(0),...u16(0),...u16(dosT),
      ...u16(dosD),...u32(crc),...u32(body.length),...u32(body.length),...u16(name.length),
      ...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(offset),
      ...Array.from(name)]);
    offset+=local.length+name.length+body.length;
  });
  const cd=[].concat(...central), cdBytes=new Uint8Array(cd);
  const end=new Uint8Array([...u32(0x06054b50),...u16(0),...u16(0),...u16(files.length),
    ...u16(files.length),...u32(cdBytes.length),...u32(offset),...u16(0)]);
  return new Blob([...chunks,cdBytes,end],
    {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
function colLetter(i){let s='';i++;while(i>0){const m=(i-1)%26;s=String.fromCharCode(65+m)+s;i=(i-m-1)/26;}return s;}
function xesc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/\x00-\x08|\x0B|\x0C|\x0E-\x1F/g,'');}
function rowsToXlsx(rows, moneyCols, sheetName){
  const money=new Set(moneyCols);
  const body=rows.map((r,ri)=>{
    const cells=r.map((v,ci)=>{
      const ref=colLetter(ci)+(ri+1);
      const isNum = typeof v==='number' && isFinite(v);
      const last = ri===rows.length-1 && rows[rows.length-1][0];
      let s = ri===0 ? 1 : (money.has(ci) ? (last?4:2) : (last?3:0));
      if(isNum) return `<c r="${ref}" s="${s}"><v>${v}</v></c>`;
      if(v===''||v==null) return `<c r="${ref}" s="${s}"/>`;
      return `<c r="${ref}" s="${s}" t="inlineStr"><is><t xml:space="preserve">${xesc(v)}</t></is></c>`;
    }).join('');
    return `<row r="${ri+1}">${cells}</row>`;
  }).join('');
  const widths=rows[0].map((h,i)=>
    `<col min="${i+1}" max="${i+1}" width="${money.has(i)?14:(i===0||i===1?30:(i===2?26:(i>=13?34:12)))}" customWidth="1"/>`).join('');
  const sheet=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
    +`<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">`
    +`<sheetViews><sheetView workbookViewId="0" tabSelected="1">`
    +`<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>`
    +`</sheetView></sheetViews><cols>${widths}</cols><sheetData>${body}</sheetData>`
    +`<autoFilter ref="A1:${colLetter(rows[0].length-1)}1"/></worksheet>`;
  const styles=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
    +`<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">`
    +`<numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;$&quot;#,##0.00"/></numFmts>`
    +`<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>`
    +`<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>`
    +`<fills count="3"><fill><patternFill patternType="none"/></fill>`
    +`<fill><patternFill patternType="gray125"/></fill>`
    +`<fill><patternFill patternType="solid"><fgColor rgb="FFE8EFE9"/><bgColor indexed="64"/></patternFill></fill></fills>`
    +`<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>`
    +`<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>`
    +`<cellXfs count="5">`
    +`<xf xfId="0" numFmtId="0" fontId="0" fillId="0" borderId="0"/>`
    +`<xf xfId="0" numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"/>`
    +`<xf xfId="0" numFmtId="164" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>`
    +`<xf xfId="0" numFmtId="0" fontId="1" fillId="0" borderId="0" applyFont="1"/>`
    +`<xf xfId="0" numFmtId="164" fontId="1" fillId="0" borderId="0" applyNumberFormat="1" applyFont="1"/>`
    +`</cellXfs>`
    // Without a <cellStyles> entry some readers warn "workbook contains no
    // default style" -- harmless but it makes the file look malformed.
    +`<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>`
    +`</styleSheet>`;
  return zipFile([
    {name:'[Content_Types].xml', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
      +`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">`
      +`<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>`
      +`<Default Extension="xml" ContentType="application/xml"/>`
      +`<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>`
      +`<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`
      +`<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>`
      +`</Types>`},
    {name:'_rels/.rels', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
      +`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
      +`<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>`
      +`</Relationships>`},
    {name:'xl/workbook.xml', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
      +`<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" `
      +`xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">`
      +`<sheets><sheet name="${xesc(sheetName).slice(0,31)}" sheetId="1" r:id="rId1"/></sheets></workbook>`},
    {name:'xl/_rels/workbook.xml.rels', data:`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
      +`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
      +`<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>`
      +`<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>`
      +`</Relationships>`},
    {name:'xl/styles.xml', data:styles},
    {name:'xl/worksheets/sheet1.xml', data:sheet},
  ]);
}
function openPrintView(rows, moneyCols, title){
  const money=new Set(moneyCols);
  const fmt=(v,ci)=> typeof v==='number'
      ? (money.has(ci) ? '$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : v)
      : (v==null?'':v);
  const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const head=rows[0].map(h=>`<th>${esc(h)}</th>`).join('');
  const body=rows.slice(1).map(r=>{
    const blank=r.every(c=>c==='');
    if(blank) return '';
    const isTot=/^TOTAL/.test(String(r[0]));
    return `<tr class="${isTot?'tot':''}">`+r.map((v,ci)=>
      `<td class="${money.has(ci)?'num':''}">${esc(fmt(v,ci))}</td>`).join('')+`</tr>`;
  }).join('');
  const w=window.open('','_blank');
  if(!w){ alert('Pop-up blocked — allow pop-ups for this page to print/save as PDF.'); return; }
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
  <style>
    @page{size:landscape;margin:10mm}
    body{font:10px/1.35 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1a1a;margin:0}
    h1{font-size:15px;margin:0 0 2px}
    .sub{font-size:10px;color:#666;margin:0 0 10px}
    table{border-collapse:collapse;width:100%}
    th,td{border:1px solid #ccd;padding:3px 5px;text-align:left;vertical-align:top}
    th{background:#e8efe9;font-weight:700;font-size:9px;text-transform:uppercase;letter-spacing:.2px}
    td.num,th:nth-child(n+8):nth-child(-n+12){text-align:right;white-space:nowrap}
    tr.tot td{font-weight:800;border-top:2px solid #333;background:#f4f6f4}
    thead{display:table-header-group}
    tr{break-inside:avoid}
  </style></head><body>
  <h1>${esc(title)}</h1>
  <p class="sub">TBDG 2026 Christmas installs · ${rows.length-3} clients</p>
  <table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
  <script>window.onload=function(){setTimeout(function(){window.print();},250);};<\/script>
  </body></html>`);
  w.document.close();
}
function runExport(scope, fmt){
  const rows = buildBillingRows(scope);
  const MONEY=[7,8,9,10,11];
  const label = scope==='houston' ? 'Houston' : scope==='dallas' ? 'Dallas' : 'All clients';
  const base = `TBDG 2026 install billing — ${label}`;
  const file = `tbdg-2026-billing-${scope}`;
  if(fmt==='csv'){
    dl(`${file}.csv`, rows.map(r=>r.map(csvCell).join(',')).join('\r\n'));
  } else if(fmt==='pdf'){
    openPrintView(rows, MONEY, base);
  } else {
    const blob=rowsToXlsx(rows, MONEY, label);
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download=`${file}.xlsx`; a.click();
    setTimeout(()=>URL.revokeObjectURL(a.href), 5000);
  }
}
const billdlg = document.getElementById('billdlg');
let billScope='all', billFmt='xlsx';
// Both rows are CHOICES; nothing downloads until the explicit button. Picking
// a scope or format used to fire the export immediately, which made it easy
// to grab the wrong file and gave no chance to review the pair first.
const SCOPE_LABEL={all:'everyone',houston:'Houston',dallas:'Dallas'};
const FMT_LABEL={xlsx:'Excel',csv:'CSV',pdf:'PDF'};
function syncBillBtn(){
  const go=document.getElementById('billgo');
  go.textContent = billFmt==='pdf'
    ? `Open PDF — ${SCOPE_LABEL[billScope]}`
    : `Download ${FMT_LABEL[billFmt]} — ${SCOPE_LABEL[billScope]}`;
}
function pick(group, val, key){
  billdlg.querySelectorAll(group+' button').forEach(x=>
    x.classList.toggle('sel', x.dataset[key]===val));
  syncBillBtn();
}
document.getElementById('viewdays').onclick = ()=> setView('days');
document.getElementById('viewcal').onclick  = ()=> setView('cal');
document.getElementById('billexportbtn').onclick = ()=>{ syncBillBtn(); billdlg.showModal(); };
billdlg.querySelectorAll('.billscope button').forEach(b=>{
  b.onclick = ()=>{ billScope=b.dataset.scope; pick('.billscope', billScope, 'scope'); };
});
billdlg.querySelectorAll('.billfmt button').forEach(b=>{
  b.onclick = ()=>{ billFmt=b.dataset.fmt; pick('.billfmt', billFmt, 'fmt'); };
});
document.getElementById('billgo').onclick = ()=>{ runExport(billScope, billFmt); billdlg.close(); };
// Back-compat for anything still calling the old name.
function exportBilling(scope){ runExport(scope||'all','csv'); }
function resetAll(){ if(confirm('Discard all moves & approvals?')){
  localStorage.removeItem('tbdg2026review'); location.reload(); }}

// ---------- the notebook ----------
// Freezes the schedule as promised to clients, so re-running the pipeline
// from an updated spreadsheet puts everyone back where they were told
// rather than re-solving from scratch. Everything is keyed by client NAME,
// never by spreadsheet row: adding a row to the sheet renumbers rows and
// would otherwise reattach dates to the wrong people.
function exportNotebook(){
  // Clients added in the review tool (anomaly jobs, callbacks) aren't in
  // the spreadsheet at all -- schedule.py needs their full definition,
  // not just a name, to recreate them on a full rebuild.
  const newClients = Object.values(C).filter(c=>c.synthetic).map(c=>(
    {row:c.row, name:c.name, street:c.street, lat:c.lat, lon:c.lon,
     hours:c.h26, visitType:c.visitType, notes:c.advice,
     people:c.people, business:c.bus,
     outRow:c.outRow, inCol:c.inCol}));
  const out = {
    kind: 'tbdg-install-overrides',
    version: SPEC.version,
    savedAt: new Date().toISOString(),
    new_clients: newClients,
    days: days.filter(d=>d.stops.length).map(d=>({
      date: d.date, crew: d.crew, cat: d.cat,
      stops: d.stops.map(r=>C[r].name),
      win: d.win, lunch: d.lunchMin, anchored: d.anchored,
      stacked: d.stacked, joint: d.joint || '',
      half: (d.half||[]).filter(r=>d.stops.includes(r)).map(r=>C[r].name),
      startRow: (d.startRow!=null && d.stops.includes(d.startRow))
                ? C[d.startRow].name : null,
      note: d.note || '',
    })),
  };
  dl('overrides.json', JSON.stringify(out, null, 2));
  alert('Saved overrides.json.\n\nPut it in the scheduler folder. The next '
      + 'rebuild will read it first and keep everyone on the date they were '
      + 'promised — new clients from the spreadsheet fill in around them.');
}

// ---------- render ----------
// ---------- calendar view ----------
// Built for the warehouse wall screen, so it answers production's questions
// at a glance rather than the planner's: what installs that day, which crew,
// and -- the one that drives the pull list -- how many boxes come off the
// rack. Clicking a day drops into the normal day view.
const MONTHS=['January','February','March','April','May','June','July',
  'August','September','October','November','December'];
function dayBoxes(d){
  return d.stops.reduce((a,r)=>a+(parseFloat(C[r].boxes)||0),0);
}
function renderCalendar(){
  const wrap=document.getElementById('calwrap');
  const dates=SPEC.calendar.map(c=>c.date).sort();
  if(!dates.length){ wrap.innerHTML=''; return; }
  // group the calendar's own dates by month, then pad each grid to whole weeks
  const byMonth={};
  dates.forEach(dt=>{ const k=dt.slice(0,7); (byMonth[k]=byMonth[k]||[]).push(dt); });
  let html='';
  Object.keys(byMonth).sort().forEach(k=>{
    const [y,m]=k.split('-').map(Number);
    const first=new Date(y,m-1,1), last=new Date(y,m,0).getDate();
    html+=`<div class="calmonth"><h2>${MONTHS[m-1]} ${y}</h2><div class="calgrid">`;
    ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d=>html+=`<div class="caldow">${d}</div>`);
    for(let i=0;i<first.getDay();i++) html+=`<div class="calcell off"></div>`;
    for(let dnum=1;dnum<=last;dnum++){
      const iso=`${y}-${String(m).padStart(2,'0')}-${String(dnum).padStart(2,'0')}`;
      const ci=SPEC.calendar.find(c=>c.date===iso);
      const ds=days.filter(x=>x.date===iso).sort((a,b)=>a.crew.localeCompare(b.crew));
      const dow=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][new Date(y,m-1,dnum).getDay()];
      if(!ci && !ds.length){ html+=`<div class="calcell empty"><div class="calnum">${dnum}</div></div>`; continue; }
      const tag=ci&&ci.label?`<span class="caltag">${ci.label}</span>`:'';
      let inner=`<div class="calnum">${dnum}<small>${dow}</small>${tag}</div>`;
      let stops=0, boxes=0, hrs=0;
      ds.forEach(d=>{
        const c=dayCalc(d); stops+=d.stops.length; boxes+=dayBoxes(d); hrs+=c.total/60;
        const names=d.stops.map(r=>C[r].name.split('|')[0].trim()).join(', ');
        inner+=`<div class="calcrew"><b>${d.crew.replace('Crew ','C')}</b> · `
             + `${d.stops.length} stop${d.stops.length===1?'':'s'}`
             + `<span class="calnames">${names}</span></div>`;
      });
      if(ds.length) inner+=`<div class="calfoot">${stops} stops · ${hrs.toFixed(1)}h`
                         + (boxes?` · <span class="calbox">${boxes} boxes</span>`:'')+`</div>`;
      html+=`<div class="calcell${ds.length?'':' empty'}${ci&&ci.label?' tagged':''}" `
          + `data-date="${iso}">${inner}</div>`;
    }
    html+=`</div></div>`;
  });
  wrap.innerHTML=html;
  wrap.querySelectorAll('.calcell[data-date]').forEach(c=>{
    c.onclick=()=>{ selDate=c.dataset.date; focusDayId=null; setView('days'); };
  });
}
let viewMode='days';
function setView(v){
  viewMode=v;
  document.getElementById('viewdays').classList.toggle('sel',v==='days');
  document.getElementById('viewcal').classList.toggle('sel',v==='cal');
  document.getElementById('calwrap').style.display = v==='cal' ? 'block':'none';
  document.getElementById('main').style.display   = v==='cal' ? 'none':'';
  document.getElementById('datestrip').style.display = v==='cal' ? 'none':'';
  render();
}

// ---------- printable crew manifest ----------
// One page per crew-day: the running order with everything the crew needs on
// site (address, contact, box count, install time) and the drive to the next
// stop between them, so the sheet reads as the day's actual flow.
function manifestHTML(d){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const calc=dayCalc(d), order=calc.order.length?calc.order:d.stops;
  const anchored=d.anchored!==false;
  let clock=DEPART_MIN, rows='';
  if(anchored && order.length) clock+=leg(0,N[order[0]])/60;
  order.forEach((r,i)=>{
    const c=C[r], mins=effH(d,r)*60/(d.stacked||1);
    const addr=[c.street,[c.city,c.st].filter(Boolean).join(', '),c.zip].filter(Boolean).join(' · ');
    const note=[c.advice,c.repairNotes].filter(Boolean).join(' — ');
    rows+=`<tr class="stop"><td class="n">${i+1}</td><td>
      <div class="nm">${esc(c.name)}</div>
      <div class="ad">${esc(addr)||'<i>no address on file</i>'}</div>
      ${c.phone||c.email?`<div class="ct">${esc(c.phone||'')}${c.phone&&c.email?' · ':''}${esc(c.email||'')}</div>`:''}
      ${note?`<div class="nt">${esc(note)}</div>`:''}
    </td>
    <td class="c">${c.boxes||'—'}</td>
    <td class="c">${(mins/60).toFixed(2)}h</td>
    <td class="c">${fmtClock(clock)}</td></tr>`;
    clock+=mins;
    const nxt=order[i+1];
    if(nxt!==undefined){
      const dr=leg(N[r],N[nxt])/60;
      rows+=`<tr class="drive"><td></td><td colspan="4">▼ drive ${Math.round(dr)} min to ${esc(C[nxt].name)}</td></tr>`;
      clock+=dr;
    }
  });
  const boxes=dayBoxes(d);
  return `<section class="sheet">
    <div class="shead">
      <div><h1>${esc(d.crew)} — ${esc(d.dow)} ${fmtMDYYYY(d.date)}</h1>
        <p>${order.length} stop${order.length===1?'':'s'} · ${boxes||0} boxes to pull
        ${d.joint?` · joint with ${esc(d.joint)}`:''}${d.note?` · ${esc(d.note)}`:''}</p></div>
      <div class="stot"><b>${(calc.total/60).toFixed(1)}h</b><span>total day</span></div>
    </div>
    <table><thead><tr><th></th><th>Client</th><th class="c">Boxes</th>
      <th class="c">Install</th><th class="c">Arrive ≈</th></tr></thead>
      <tbody>${anchored?`<tr class="depot"><td></td><td colspan="4">Depot — depart ${fmtClock(DEPART_MIN)}</td></tr>`:''}
      ${rows}
      ${anchored&&order.length?`<tr class="depot"><td></td><td colspan="4">Return to depot ≈ ${fmtClock(clock+leg(N[order[order.length-1]],0)/60)}</td></tr>`:''}
      </tbody></table>
    <div class="sfoot">Install ${(calc.inst).toFixed(1)}h · Drive ${(calc.drive/60).toFixed(1)}h
      ${order.length?` · Lunch ${((d.lunchMin??LUNCH)/60).toFixed(1)}h`:''} · Boxes ${boxes||0}</div>
  </section>`;
}
function printManifests(list, title){
  if(!list.length){ alert('Nothing scheduled to print for that selection.'); return; }
  const w=window.open('','_blank');
  if(!w){ alert('Pop-up blocked — allow pop-ups for this page to print.'); return; }
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><style>
    @page{size:portrait;margin:12mm}
    body{font:12px/1.4 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1a1a;margin:0}
    .sheet{page-break-after:always;break-after:page}
    .sheet:last-child{page-break-after:auto;break-after:auto}
    .shead{display:flex;justify-content:space-between;align-items:flex-start;
      border-bottom:2.5px solid #2d5a33;padding-bottom:7px;margin-bottom:11px}
    h1{font-size:19px;margin:0}
    .shead p{margin:3px 0 0;color:#555;font-size:11.5px}
    .stot{text-align:right;white-space:nowrap;padding-left:14px}
    .stot b{display:block;font-size:21px;line-height:1}
    .stot span{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.4px}
    table{border-collapse:collapse;width:100%}
    th{font-size:9.5px;text-transform:uppercase;letter-spacing:.4px;color:#666;
      text-align:left;border-bottom:1px solid #bbb;padding:0 6px 4px}
    td{padding:7px 6px;vertical-align:top;border-bottom:1px solid #eee}
    td.n{font-weight:800;font-size:15px;width:26px;color:#2d5a33}
    td.c{text-align:center;white-space:nowrap;width:64px}
    .nm{font-weight:700;font-size:13px}
    .ad{color:#444;font-size:11px;margin-top:1px}
    .ct{color:#666;font-size:10.5px;margin-top:1px}
    .nt{margin-top:3px;font-size:10.5px;color:#8a5a00;font-style:italic}
    tr.drive td{border:0;padding:2px 6px 2px 32px;color:#777;font-size:10.5px}
    tr.depot td{border:0;padding:4px 6px;color:#2d5a33;font-weight:700;font-size:11px;
      text-transform:uppercase;letter-spacing:.3px}
    tr.stop{break-inside:avoid}
    .sfoot{margin-top:11px;padding-top:6px;border-top:1.5px solid #333;font-weight:700;font-size:11.5px}
  </style></head><body>${list.map(manifestHTML).join('')}
  <script>window.onload=function(){setTimeout(function(){window.print();},250);};<\/script>
  </body></html>`);
  w.document.close();
}
function printDate(dt){
  printManifests(days.filter(d=>d.date===dt).sort((a,b)=>a.crew.localeCompare(b.crew)),
    `Crew sheets — ${fmtMDYYYY(dt)}`);
}

function render(){
  // Settle stop ordering ONCE, in the state phase. dayCalc is pure, so
  // paint can no longer mutate the schedule as a side effect of drawing.
  days.forEach(d=>{ if(d.edited) d.stops = dayCalc(d).order; });
  if(viewMode==='cal'){ renderCalendar(); }
  else { renderStrip(); renderCards(); drawDate(selDate); }
  const n=days.reduce((a,d)=>a+d.stops.length,0);
  document.getElementById('summarybar').textContent=
    `${n} stops · ${days.length} crew-days · ${approved.size} approved`;
  const w=document.getElementById('statewarn');
  if(w){ w.textContent = stateWarning||''; w.style.display = stateWarning?'block':'none'; }
}
// Land on the first date that actually has work, not just the first date
// on the calendar -- allDates() now includes empty/unused dates too.
selDate = (days.map(d=>d.date).sort()[0]) || allDates()[0];
render();
</script></body></html>"""

with open(OUT, "w") as f:
    f.write(HTML.replace("__DATA__", payload))
print("Wrote", OUT, f"({os.path.getsize(OUT)//1024} KB)")
print("Run publish_pages.py to push this to the deployed tool "
      "(it's served from Postgres now, not a file -- see RULES.md \xa712).")
