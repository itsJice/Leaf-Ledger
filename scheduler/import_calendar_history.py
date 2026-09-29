#!/usr/bin/env python3
"""
Bring an old season's office calendar onto the client cards.

    .venv/bin/python3 import_calendar_history.py --events calendar-2015.json --season 2015
    .venv/bin/python3 import_calendar_history.py --events ... --season 2015 --apply

Input is a transcription of the office's Google Calendar agenda for one
season (the 2015 one was a 44-page scanned printout, transcribed to one JSON
object per calendar entry: date, kind, crew, client, phones, address,
prices, description, boxes, storage_loc ...). Dry run by default.

What it does:

* Groups the entries into clients. The same client is written differently
  on the install and the takedown entry ("Mr. Pitcock" / "Pitcock, James"),
  so entries join on a shared phone, street address or name -- but a shared
  phone or address only joins entries whose names also overlap: Doug
  Pitcock's home and his company's Reliant Center job share a phone and are
  two different jobs.
* Matches each client to the app by phone, street, full name and
  surname+first initial, with the same overlap rule.
* A matched client gets a season row (install/takedown dates, crews, fees,
  boxes, storage location, the calendar's notes). A season row that already
  exists is only filled where blank, like import_workbook.py.
* A client not in the app gets a card, with the calendar's address, phone
  and email, created_by 'calendar_<season>' so the batch can be found.
* Ambiguous matches are written nowhere and reported.

Everything written is stamped "import:<date>" in app_edits (the Clients tab
shows a blue dot), so no sync ever touches it.

Price groups are read as install / takedown / storage, the office's
convention ("950/950/550"): two numbers are install / takedown, one is the
install. A figure more than 5x the others in its group is a typo on the
calendar ("450/4350/300") and is dropped, not guessed at.
"""
import argparse
import asyncio
import collections
import datetime
import json
import os
import re
import sys

import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import load_env, ENV_FILE  # noqa: E402
import season as _bridge  # noqa: E402,F401  (puts backend/ on sys.path)
from app.libs import client_season  # noqa: E402

STOP = {"2015", "tnp", "install", "take", "down", "takedown", "tale", "takew", "cancelled", "mr", "mrs", "ms",
        "dr", "the", "and", "of", "at", "by", "office", "residence", "home", "house", "garland", "lights",
        "wreath", "wreaths", "tree", "trees", "decor", "store", "inc", "llc", "co", "center", "new", "ave",
        "design", "designs", "see", "vicki", "crew"}
JOB_KINDS = ("install", "takedown", "repair", "delivery")
OFFICE_EMAILS = {"campacynthia@gmail.com"}


def toks(n):
    n = re.sub(r"\(.*?\)", "", n or "")
    n = re.sub(r"[^a-z ]", " ", n.lower())
    return [t for t in n.split() if len(t) > 2 and t not in STOP]


def digits(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else None


def street(a):
    m = re.match(r"\s*(\d{2,6})\s+([A-Za-z]+)", str(a or ""))
    return (m.group(1), m.group(2).lower()[:5]) if m else None


def sname(n):
    if "," in n:
        last = toks(n.split(",")[0])
        first = toks(",".join(n.split(",")[1:]))
        return (last[0], (first or [""])[0][:3]) if last else None
    t = toks(n)
    return (t[-1], t[0][:3]) if len(t) >= 2 else None


def keys_for(name, phones, addr):
    t = toks(name)
    ks = [("p", digits(p)) for p in phones or [] if digits(p)]
    s = street(addr)
    ks += [("a", s)] if s else []
    if t:
        ks.append(("n", " ".join(sorted(t))))
    sn = sname(name)
    ks += [("s",) + sn] if sn else []
    return ks, set(t)


def group_jobs(events):
    jobs = [e for e in events if e.get("kind") in JOB_KINDS and e.get("client")]
    par = list(range(len(jobs)))

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    info = [keys_for(e["client"], e.get("phones"), e.get("address")) for e in jobs]
    idx = collections.defaultdict(list)
    for i, (ks, _) in enumerate(info):
        for k in ks:
            idx[k].append(i)
    for k, v in idx.items():
        for a in v[1:]:
            b = v[0]
            if k[0] in ("p", "a") and info[a][1] and info[b][1] and not (info[a][1] & info[b][1]):
                continue
            par[f(a)] = f(b)
    groups = collections.defaultdict(list)
    for i, e in enumerate(jobs):
        groups[f(i)].append(e)
    return list(groups.values())


def fees(prices):
    p = [float(x) for x in (prices or []) if isinstance(x, (int, float)) and x > 0]
    if len(p) >= 2:
        med = sorted(p)[len(p) // 2]
        p = [x for x in p if x <= 5 * med] if med else p
    out = {}
    for k, v in zip(("install_fee", "takedown_fee", "storage_fee"), p[:3]):
        out[k] = round(v, 2)
    return out


def crew_text(e):
    parts = []
    for c in e.get("crew") or []:
        nm = str(c.get("name") or "").strip()
        if nm:
            parts.append(f"{nm} #{c['slot']}" if c.get("slot") else nm)
    return " + ".join(parts) or None


def season_detail(js, season):
    """One client's season, from all of its calendar entries."""
    js = sorted(js, key=lambda e: (e["date"], e.get("time") or ""))
    cancelled = any(re.search(r"(?i)cancel", e.get("title_raw") or "") for e in js)
    inst = [e for e in js if e["kind"] == "install"]
    take = [e for e in js if e["kind"] == "takedown"]
    priced = next((e for e in inst if e.get("prices")), None) or next((e for e in js if e.get("prices")), None)
    d = {}
    if inst:
        d["install_date"] = inst[0]["date"]
        d["crew"] = crew_text(inst[0])
    if take:
        d["takedown_date"] = take[0]["date"]
        d["takedown_crew"] = crew_text(take[0])
    if priced:
        d.update(fees(priced["prices"]))
        if len([k for k in ("install_fee", "takedown_fee", "storage_fee") if k in d]) >= 2:
            d["total"] = round(sum(d.get(k) or 0 for k in ("install_fee", "takedown_fee", "storage_fee")), 2)
    boxes = [e["boxes"] for e in js if isinstance(e.get("boxes"), int)]
    if boxes:
        d["boxes"] = max(boxes)
    loc = next((e["storage_loc"] for e in js if e.get("storage_loc")), None)
    if loc:
        d["storage_loc"] = loc
    if any(e.get("tnp") for e in js):
        d["tnp"] = True
    notes = []
    for e in js:
        t = (e.get("description") or "").strip()
        if t and t not in notes:
            notes.append(t)
    if notes:
        d["notes"] = " | ".join(notes)
    extra = [e for e in js if e["kind"] in ("repair", "delivery")]
    if extra:
        d["service_visits"] = [f"{e['date']} {e['kind']}: {e.get('title_raw')}" for e in extra]
    d["calendar_entries"] = [f"{e['date']} {e.get('time') or ''} {e.get('title_raw') or ''}".strip() for e in js]
    d["source"] = f"{season} office calendar (Vickie Lupher / Cynthia Campa)"
    if cancelled:
        d["cancelled"] = True
    return {k: v for k, v in d.items() if v not in (None, "", [])}


CITIES = ["The Woodlands", "Woodlands", "Houston", "Spring", "Humble", "Katy", "Cypress", "Kingwood", "Sugar Land",
          "Tomball", "Conroe", "League City", "Pearland", "Magnolia", "Bellaire", "Montgomery", "Richmond",
          "Missouri City", "Friendswood", "Seabrook", "Waco", "College Station", "Bryan", "Fulshear", "Stafford",
          "Baytown", "Pasadena", "Webster", "Kemah", "Clear Lake", "West University Place", "Hockley", "Porter",
          "Shenandoah", "Oak Ridge North", "Hunters Creek Village", "Piney Point Village", "Hedwig Village",
          "Bunker Hill Village", "Spring Valley", "Brenham", "Bellville", "Sealy", "Dickinson", "Galveston"]
TYPOS = {"hosuton": "Houston", "houstn": "Houston", "surgar land": "Sugar Land", "kinwood": "Kingwood"}


def split_address(addr):
    """(street, city, zip) from one calendar "Where:" line. Lines come both
    comma-separated ("424 West 27th Street Unit E Houston, TX. 77008") and not
    ("18719 Regatta Humble TX. 77346"), so the city is found by name at the
    end of the street part rather than by position."""
    if not addr:
        return None, None, None
    a = re.sub(r"\s+", " ", str(addr)).strip()
    z = re.search(r"\b(7\d{4})\b", a)
    zipc = z.group(1) if z else None
    a = re.sub(r"(?i),?\s*(united states|usa)\.?\s*$", "", a)
    a = re.sub(r"(?i),?\s*\b(tx|texas|xt)\b\.?,?\s*(7\d{3,4})?\s*$", "", a).strip(" ,.")
    for bad, good in TYPOS.items():
        a = re.sub(rf"(?i)\b{bad}\b", good, a)
    city = None
    for c in sorted(CITIES, key=len, reverse=True):
        m = re.search(rf"(?i)[,\s]+{re.escape(c)}\s*$", a)
        if m:
            city, a = c, a[:m.start()]
            break
    st = a.strip(" ,.") or None
    return st, city, zipc


def contact_from(js):
    phones = [digits(p) for e in js for p in e.get("phones") or [] if digits(p)]
    phone = None
    if phones:
        p = collections.Counter(phones).most_common(1)[0][0]
        phone = f"({p[:3]}) {p[3:6]}-{p[6:]}"
    addr = next((e["address"] for e in js if e.get("address") and street(e["address"])), None)
    st, city, zipc = split_address(addr)
    email = None
    for e in js:
        for em in re.split(r"[,\s]+", e.get("who") or ""):
            if "@" in em and em.lower() not in OFFICE_EMAILS:
                email = em.strip()
                break
    return {"street": st, "city": city, "state": "TX" if st else None, "zip": zipc, "phone": phone, "email": email}


def display_name(js):
    """The most complete way the calendar wrote the name: "Last, First" if any
    entry did, else the longest."""
    names = [re.sub(r"\s+", " ", e["client"]).strip(" ,.") for e in js]
    comma = [n for n in names if "," in n]
    pool = comma or names
    return max(pool, key=lambda n: (len(toks(n)), len(n)))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--season", required=True)
    ap.add_argument("--map", action="append", default=[],
                    help='"<calendar name>=<app client name>": force a match')
    ap.add_argument("--skip", action="append", default=[], help="calendar name to leave out entirely")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    season = str(args.season)
    stamp = "import:" + datetime.date.today().isoformat()
    events = json.load(open(args.events))
    groups = group_jobs(events)
    forced = {}
    for m in args.map:
        a, b = m.split("=", 1)
        forced[a.strip().lower()] = b.strip()
    skip = {s.strip().lower() for s in args.skip}

    load_env(ENV_FILE)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    rep = collections.defaultdict(list)
    counts = collections.Counter()
    try:
        clients = await conn.fetch("SELECT id, name, sheet_name, former_names, street, phone, secondary_contacts FROM clients")
        seasons = {r["client_id"]: max(r["s"]) for r in await conn.fetch(
            "SELECT client_id, array_agg(season) s FROM client_activity WHERE kind='christmas_install' GROUP BY client_id")}
        byname = {c["name"].strip().lower(): c for c in clients}
        cidx = collections.defaultdict(set)
        ctok = {}
        for c in clients:
            sc = c["secondary_contacts"]
            sc = json.loads(sc) if isinstance(sc, str) else (sc or [])
            phones = [c["phone"]] + [s.get("phone") for s in sc]
            tk = set()
            for n in [c["name"], c["sheet_name"], *(c["former_names"] or [])]:
                if n:
                    ks, t = keys_for(n, phones, c["street"])
                    tk |= t
                    for k in ks:
                        cidx[k].add(c["id"])
            ctok[c["id"]] = tk
        byid = {c["id"]: c for c in clients}

        tx = conn.transaction()
        await tx.start()
        try:
            for js in groups:
                names = sorted({e["client"] for e in js})
                if any(n.strip().lower() in skip for n in names):
                    rep["skipped"].append(names)
                    continue
                target = next((forced[n.strip().lower()] for n in names if n.strip().lower() in forced), None)
                cid = None
                if target:
                    c = byname.get(target.lower())
                    if not c:
                        raise SystemExit(f"--map target not in the app: {target!r}")
                    cid = c["id"]
                    rep["forced"].append({"calendar": names, "client": c["name"]})
                else:
                    votes = collections.Counter()
                    why = collections.defaultdict(set)
                    gt = set()
                    for e in js:
                        ks, t = keys_for(e["client"], e.get("phones"), e.get("address"))
                        gt |= t
                        for k in ks:
                            for x in cidx.get(k, ()):
                                if k[0] in ("p", "a") and t and ctok[x] and not (t & ctok[x]):
                                    continue
                                votes[x] += {"p": 3, "a": 3, "n": 2, "s": 2}[k[0]]
                                why[x].add(k[0])
                    if votes:
                        top = max(votes.values())
                        tops = [x for x, v in votes.items() if v == top]
                        if len(tops) > 1 and len({frozenset(ctok[x]) for x in tops}) == 1:
                            tops = [max(tops, key=lambda x: seasons.get(x, "0"))]  # the app's own duplicates
                        if len(tops) == 1:
                            cid = tops[0]
                            rep["matched"].append({"calendar": names, "client": byid[cid]["name"],
                                                   "evidence": sorted(why[cid])})
                        else:
                            rep["ambiguous"].append({"calendar": names, "candidates": [byid[x]["name"] for x in tops]})
                            continue
                detail = season_detail(js, season)
                if cid is None:
                    name = display_name(js)
                    ct = contact_from(js)
                    cid = await conn.fetchval(
                        "INSERT INTO clients (name, created_by, street, city, state, zip, phone, email, notes) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
                        "ON CONFLICT (LOWER(TRIM(name))) DO NOTHING RETURNING id",
                        name, f"calendar_{season}", ct["street"], ct["city"], ct["state"], ct["zip"],
                        ct["phone"], ct["email"],
                        f"Christmas client in {season} (from the {season} office calendar).")
                    if cid is None:
                        rep["name_taken"].append(name)
                        continue
                    counts["cards_created"] += 1
                    rep["created"].append({"name": name, **{k: v for k, v in ct.items() if v}})
                prior = await conn.fetchval(
                    "SELECT detail FROM client_activity WHERE client_id=$1 AND kind='christmas_install' AND season=$2",
                    cid, season)
                prior = json.loads(prior) if isinstance(prior, str) else prior
                out = dict(prior or {})
                owned = client_season.app_owned_keys(prior)
                filled = [k for k, v in detail.items() if k not in owned and out.get(k) in (None, "", [])]
                for k in filled:
                    out[k] = detail[k]
                if not filled:
                    continue
                client_season.stamp(out, filled, stamp)
                counts["season_rows_written"] += 1
                counts["fields_filled"] += len(filled)
                await conn.execute(
                    "INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at) "
                    "VALUES ($1, 'christmas_install', $2, $3, $4::jsonb, $5::date) "
                    "ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment' DO UPDATE SET "
                    "summary=EXCLUDED.summary, detail=EXCLUDED.detail, occurred_at=EXCLUDED.occurred_at, updated_at=now()",
                    cid, season, client_season.summarize(out), json.dumps(out, default=str),
                    datetime.date.fromisoformat(out["install_date"]) if out.get("install_date") else None)
            if args.apply:
                await tx.commit()
            else:
                await tx.rollback()
        except BaseException:
            await tx.rollback()
            raise
    finally:
        await conn.close()

    print(f"{'APPLIED' if args.apply else 'DRY RUN -- nothing written'}: season {season}, "
          f"{len(groups)} calendar clients")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    for k in ("matched", "forced", "created", "ambiguous", "skipped", "name_taken"):
        print(f"  {k}: {len(rep.get(k, []))}")
    for a in rep.get("ambiguous", []):
        print("    ambiguous:", a)
    if args.report:
        json.dump(rep, open(args.report, "w"), indent=1, default=str)


if __name__ == "__main__":
    asyncio.run(main())
