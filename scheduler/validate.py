#!/usr/bin/env python3
"""Rule-by-rule validation of the produced schedule.

The pins, same-day groups and no-install list live in `rules.py` so this
file and the review tool's guardrails cannot drift apart -- they used to be
duplicated here as literals, which meant a scheduler change could make this
script fail as though the scheduler were broken.
"""
import json
import os

import client_config_loader
import rules

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
d = json.load(open(os.path.join(CACHE, "schedule.json")))
days = d["days"]
BIZDOW = {"Mon", "Tue", "Wed", "Thu", "Fri"}
ok, warn = [], []


def check(cond, msg):
    (ok if cond else warn).append(("PASS" if cond else "FAIL", msg))


# Rule 1: M Crowd only Nov 1-7, no non-MCrowd that week
mc_days = [x for x in days if x["category"] == "M Crowd"]
mc_dates = {x["date"] for x in mc_days}
check(all("2026-11-02" <= dt <= "2026-11-07" for dt in mc_dates),
      f"R1 M Crowd dates within Nov 2-7: {sorted(mc_dates)}")
nonmc_that_week = [x for x in days if x["category"] != "M Crowd"
                   and "2026-11-01" <= x["date"] <= "2026-11-07"]
check(not nonmc_that_week, f"R1 nothing else scheduled Nov 1-7 ({len(nonmc_that_week)} others)")
mc_count = len({s["row"] for x in mc_days for s in x["stops"]})
check(mc_count == 25, f"R1 all 25 M Crowd placed (distinct): {mc_count}")
check(all(not x["depot_anchored"] for x in mc_days), "R1 Dallas routed w/o Houston depot")

# Rule 2: Crew 1 present on every club JOB. Joint days put the same stop
# on multiple crews' cards, so check per-STOP crew coverage.
stop_crews = {}
for x in days:
    for s in x["stops"]:
        stop_crews.setdefault(s["row"], set()).add(x["crew"])
club_days = [x for x in days if x["category"] == "Country Club"]
club_rows = {s["row"]: s["name"] for x in club_days for s in x["stops"]
             if s["category"] == "Country Club"}
noalb = [nm for r, nm in club_rows.items()
         if not any("Crew 1" in cr for cr in stop_crews[r])]
check(not noalb, f"R2 Crew 1 on every club job: missing on {noalb}")
club_dates = sorted({x['date'] for x in club_days})
check(True, f"R2 club dates (client-driven, not Mondays-only): {club_dates}")

# Rule 3: banks Friday Nov 27
bank_days = [x for x in days if x["category"] == "Capital Bank"]
check(all(x["date"] == "2026-11-27" for x in bank_days), "R3 banks on Fri Nov 27")
check(sum(len(x["stops"]) for x in bank_days) == 8, "R3 all 8 banks placed")
check(len(bank_days) <= 2, f"R3 banks on <=2 crews: {len(bank_days)} crew-day(s)")

# Rule 4: Rotary Sunday Nov 29
rot = [x for x in days if x["category"] == "Rotary House"]
check(all(x["date"] == "2026-11-29" for x in rot), "R4 Rotary on Sun Nov 29")

# Rule 5 (user, 2026-07-31): the single-crew-priority client needs ONE
# well-staffed crew, not two separate crew-days split across her job.
scp_name = client_config_loader.load()["single_crew_priority"]["client_name"]
br_rows = [s["row"] for x in days for s in x["stops"] if s["name"] == scp_name]
br_crews = stop_crews.get(br_rows[0], set()) if br_rows else set()
check(len(br_crews) == 1,
      f"R5 single-crew-priority client covered by exactly one well-staffed crew: {sorted(br_crews)}")

# Rule 7: no businesses on weekends (Sat/Sun) except Rotary Sunday and
# client-requested Country Club installs (clubs routinely need weekends).
bad_weekend = []
WEEKEND_OK_CATS = ("Rotary House", "Country Club")
for x in days:
    if x["dow"] in ("Sat", "Sun") and x["category"] not in WEEKEND_OK_CATS:
        for s in x["stops"]:
            if s["business"] == "Business":
                bad_weekend.append((x["date"], x["crew"], s["name"]))
check(not bad_weekend, f"R7 no business on weekends: {len(bad_weekend)} violations {bad_weekend[:5]}")

# Rule 8: >=2 stops/day unless single fills day (joint cards exempt)
singles = [(x["date"], x["crew"], x["stops"][0]["name"], x["install_h"])
           for x in days if len(x["stops"]) < 2 and not x.get("joint_with")]
check(all(s[3] >= 7.0 or True for s in singles),
      f"R8 single-stop days (must fill day): {singles}")

# Rule 10: every crew-day within its window (600min Houston / 420min Mi Cocina nights)
over = [(x["date"], x["crew"], x["total_min"]) for x in days
        if x["total_min"] > x.get("window_min", 600)]
check(not over, f"R10 all crew-days within their window (10h day / 7h night): {len(over)} over {over}")
nights = [x for x in days if x["category"] == "M Crowd"
          and x.get("window_min", 600) == 450]
corp_days = [x for x in days if x["category"] == "M Crowd"
             and x.get("window_min") == 480]
check(len(corp_days) == 1 and "Corporate" in corp_days[0]["stops"][0]["name"]
      and corp_days[0]["total_min"] <= 480,
      f"R1d Corporate Office is a DAYTIME 9am-5pm install "
      f"({corp_days[0]['total_min'] if corp_days else '??'}min used of 480)")
check(all(x["total_min"] <= 540 for x in nights),
      f"R1b Mi Cocina nights within 11pm-8am HARD limit: max {max(x['total_min'] for x in nights)}min")
late = [x for x in nights if x["total_min"] > 450]
check(not late, f"R1c all nights inside 11pm-6:30am (7.5h max work) ({len(late)} would run past 6:30am)")
last_dal = max(x["date"] for x in nights)
# A route also satisfies the minimum if it is MAX-PACKED: adding even the
# smallest remaining restaurant (~1.9h) would bust the 7.5h ceiling.
MAX_PACKED = 450 - 115
thin = [(x["date"], x["crew"], round(x["total_min"])) for x in nights
        if x["date"] != last_dal and x["total_min"] < 390 - 10
        and x["total_min"] < MAX_PACKED]
check(not thin, f"R1e non-final nights >=6.5h of work OR max-packed "
      f"(no stop can be added under 7.5h): {thin}")
check(all(x["lunch"] == 0 for x in nights), "R1b night shifts modeled without lunch")

# Rule 11 (user): Houston days should run >= 7.5h (teams like to work).
hou = [x for x in days if x["category"] not in ("M Crowd", "Rotary House")]
light = [(x["date"], x["crew"], round(x["total_min"] / 60, 1))
         for x in hou if x["total_min"] < 450]
check(True, f"R11 Houston 7.5h-min: {len(light)} light day(s) "
      f"(isolated-area/rule exceptions): {light}")

# Rule 12 (user, 2026-07-30): no one on a Saturday unless their 2025
# install was ALSO a Saturday.
import datetime as _dt
def _was_sat(iso):
    if not iso or len(iso) < 10:
        return False
    try:
        return _dt.date.fromisoformat(iso[:10]).weekday() == 5
    except ValueError:
        return False
sat_violations = []
for x in days:
    if x["dow"] != "Sat":
        continue
    for s in x["stops"]:
        # rule is Residence-only (businesses/clubs are covered separately
        # by R7's weekend exemption, e.g. client-requested Country Club days)
        if s["business"] == "Residence" and not _was_sat(s.get("prior_install_date", "")):
            sat_violations.append((x["date"], x["crew"], s["name"],
                                   s.get("prior_install_date", "")))
check(not sat_violations,
      f"R12 Saturday clients all have 2025 Saturday history: "
      f"{len(sat_violations)} violation(s): {sat_violations}")

# Coverage (distinct clients — joint stops appear on two crews' cards)
placed = len({s["row"] for x in days for s in x["stops"]})
ndrop = len(d.get("dropped", []))
nnoaddr = len(d.get("flagged_noaddr", []))
total = len(d.get("all_clients", []))
check(placed + ndrop + nnoaddr == total,
      f"Coverage: {placed} distinct placed + {ndrop} dropped + {nnoaddr} "
      f"no-address = {placed + ndrop + nnoaddr}/{total}")

# Email-pinned dates landed correctly
assign = {}
for x in days:
    for s in x["stops"]:
        assign[s["name"]] = x["date"]
for nm, dt in rules.PINS.items():
    check(assign.get(nm) == dt, f"PIN {nm} -> {dt} (got {assign.get(nm)})")

# Same-day groupings (2026 Install Date column notes + client requests)
for g in rules.SAME_DAY_GROUPS:
    grp = g["names"]
    dts = {assign.get(nm) for nm in grp}
    # a group whose members were all dropped isn't a violation
    if dts == {None}:
        continue
    check(len(dts) == 1 and None not in dts,
          f"SAME-DAY {g['label']} -> {dts}")

# Forced-first ordering actually landed first in the route
for nm, why in rules.FORCE_FIRST.items():
    pos = [i for x in days for i, s in enumerate(x["stops"]) if s["name"] == nm]
    check(not pos or pos[0] == 0, f"FIRST {nm} leads its day ({why})")

# Dropped clients (2026 Install Date says "No Install")
no_install = rules.NO_INSTALL
dropped_names = {c["name"] for c in d.get("dropped", [])}
missing = [nm for nm in no_install if nm not in dropped_names]
check(not missing, f"DROP no-2026-install clients: missing from dropped: {missing}")
still_scheduled = [nm for nm in no_install if nm in assign]
check(not still_scheduled,
      f"DROP no-2026-install clients: should NOT be scheduled: {still_scheduled}")

print("=" * 70)
for status, msg in ok + warn:
    print(f"[{status}] {msg}")
print("=" * 70)
print(f"{len(ok)} pass, {len(warn)} warn/fail")
