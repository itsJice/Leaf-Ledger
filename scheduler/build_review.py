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
import json
import os

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

clients = {}
for c in sched["all_clients"]:
    if c.get("lat") is None:
        continue
    clients[c["row"]] = {
        "row": c["row"], "name": c["name"], "street": c["street"],
        "city": c["city"], "zip": c["zip"], "phone": c.get("phone", ""),
        "email": c.get("email", ""), "storage": c.get("storage", ""),
        "boxes": c.get("box_count") or "", "d24": c.get("date_2024", ""),
        "d25": c.get("prior_install_date", ""),
        "real25": c.get("real_hours"), "crew25": c.get("crew_2025", ""),
        "size25": c.get("crew_size_2025"), "people": c.get("people_needed"),
        "h26": c.get("cal_hours"), "basis": c.get("hours_basis", ""),
        "zone": c["zone"], "area": c["area"], "cat": c["category"],
        "bus": c["business"], "lat": c["lat"], "lon": c["lon"],
        "geo": c.get("geo_source", ""),
    }

days = []
for i, d in enumerate(sched["days"]):
    days.append({
        "id": f'{d["date"]}|{d["crew"]}|{i}',
        "date": d["date"], "dow": d["dow"], "crew": d["crew"],
        "cat": d["category"], "anchored": d["depot_anchored"],
        "stacked": d["stacked_crews"], "note": d["note"],
        "stops": [s["row"] for s in d["stops"]],
        "win": d.get("window_min", 600), "lunchMin": d.get("lunch", 40),
        "half": d.get("half_rows", []), "joint": d.get("joint_with", ""),
        # Real road-following path + actual mileage from route_geometry.py
        # (OSRM /route -- distinct from the /table durations used to plan
        # the stop order). Goes stale the moment the day is edited; the
        # client re-fetches live in that case (see liveRoute() in the JS).
        "geom": d.get("geometry"), "mi": d.get("distance_mi"),
        "legMi": d.get("leg_mi"),
    })

payload = json.dumps({
    "depot": {"lat": sched["depot"]["lat"], "lon": sched["depot"]["lon"]},
    "clients": clients, "days": days, "node": node, "durs": durs,
    "noaddr": sched.get("flagged_noaddr", []),
    "dropped": sched.get("dropped", []),
}, separators=(",", ":"))

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
.dchip.wknd:hover{background:#fdecc8}
.dchip.sel{background:var(--brand);color:#fff;border-color:var(--brand)}
.dchip.dragover{outline:2px dashed var(--brand);outline-offset:1px}
#main{flex:1;display:flex;min-height:0}
#side{width:460px;min-width:380px;overflow-y:auto;padding:14px;background:var(--page)}
#map{flex:1}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);margin-bottom:14px;
  box-shadow:0 1px 2px rgba(41,37,36,.05)}
.card.approved{border:2px solid var(--ok)}
.card.overwin{border:2px solid var(--danger)}
.card.dragover{outline:3px dashed var(--brand);outline-offset:-3px}
.chead{display:flex;align-items:center;gap:9px;padding:11px 14px;border-bottom:1px solid var(--line);background:linear-gradient(#fff,#fbfaf8)}
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
dialog select{width:100%;margin:7px 0;padding:7px;font-size:13px;font-family:'Montserrat',sans-serif;
  border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink)}
dialog .btns{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
dialog button{padding:7px 14px;border-radius:6px;border:1px solid var(--line);cursor:pointer;
  font-family:'Montserrat',sans-serif;font-weight:600;font-size:12.5px;background:#fff;color:var(--ink)}
dialog .go{background:var(--brand);color:#fff;border:none}
dialog .go:hover{background:var(--brand-hover)}
#summarybar{font-size:12px;color:var(--mut);white-space:nowrap;font-weight:500;margin-top:3px}
.edited{font-size:10px;color:#c2410c;font-weight:700;margin-left:6px;font-family:'Montserrat',sans-serif}
.ic{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vertical-align:-2px;display:inline-block}
</style></head>
<body><div id="app">
<header>
  <div id="headtitle">
    <h1><svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 7 9h2.5L5 15h3l-3.5 5h15L16 15h3l-4.5-6H17L12 2Z"/><path d="M12 22v-2"/></svg>TBDG · 2026 Install Schedule</h1>
    <p>Crew routes, drive times &amp; approvals for every install day — drag a stop to reschedule it.</p>
  </div>
  <div id="summarybar"></div>
  <div id="datestrip"></div>
</header>
<div id="main">
  <div id="side"></div>
  <div id="map"></div>
</div>
</div>
<dialog id="mvdlg">
  <b id="mvtitle">Move stop</b>
  <select id="mvdate"></select>
  <select id="mvcrew"></select>
  <div class="btns"><button onclick="mvdlg.close()">Cancel</button>
  <button class="go" id="mvgo">Move</button></div>
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
const LUNCH=40;
const N = DATA.node, D = DATA.durs, C = DATA.clients;

// ---------- state ----------
let days = DATA.days.map(d=>({...d, stops:[...d.stops]}));
let approved = new Set(), moves = [], selDate = null;
try{
  const s = JSON.parse(localStorage.getItem('tbdg2026review')||'{}');
  if(s.moves){ s.moves.forEach(m=>applyMove(m.row, m.to, false)); moves = s.moves; }
  if(s.approved) approved = new Set(s.approved);
}catch(e){}
function persist(){ localStorage.setItem('tbdg2026review',
  JSON.stringify({moves, approved:[...approved]})); }

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
  let path;
  if(d.anchored){
    let unv=[...idx], cur=0; path=[];
    while(unv.length){ let best=unv.reduce((p,s)=>leg(cur,s)<leg(cur,p)?s:p,unv[0]);
      path.push(best); unv=unv.filter(x=>x!==best); cur=best; }
    path=[0,...path,0];
  } else {
    let seed=idx.reduce((p,s)=>sum(s)<sum(p)?s:p,idx[0]);
    function sum(s){return idx.reduce((a,t)=>a+leg(s,t),0);}
    let unv=idx.filter(x=>x!==seed), cur=seed; path=[seed];
    while(unv.length){ let best=unv.reduce((p,s)=>leg(cur,s)<leg(cur,p)?s:p,unv[0]);
      path.push(best); unv=unv.filter(x=>x!==best); cur=best; }
  }
  // 2-opt (fixed ends)
  let imp=true;
  while(imp){ imp=false;
    for(let i=1;i<path.length-2;i++) for(let k=i+1;k<path.length-1;k++){
      const a=path[i-1],b=path[i],c2=path[k],e=path[k+1];
      if(leg(a,c2)+leg(b,e) < leg(a,b)+leg(c2,e)-1e-9){
        path=path.slice(0,i).concat(path.slice(i,k+1).reverse(),path.slice(k+1)); imp=true; }
    } }
  let drive=0; for(let i=0;i<path.length-1;i++) drive+=leg(path[i],path[i+1]);
  const inner = d.anchored? path.slice(1,-1): path;
  const idx2row={}; d.stops.forEach(r=>idx2row[N[r]]=r);
  return {order: inner.map(i=>idx2row[i]), drive: drive/60, path};
}
function effH(d,r){
  return (d.half||[]).includes(r) ? (C[r].h26||0)/2 : (C[r].h26||0);
}
function dayCalc(d){
  const rt=routeDay(d);
  d.stops = rt.order.length? rt.order : d.stops;
  const inst = d.stops.reduce((a,r)=>a+effH(d,r),0)/(d.stacked||1);
  const total = inst*60 + rt.drive + (d.stops.length?(d.lunchMin??LUNCH):0);
  return {inst, drive:rt.drive, total, path:rt.path};
}

// ---------- moves ----------
function applyMove(row, toId, record=true){
  const from = days.find(x=>x.stops.includes(row)); if(!from) return;
  let to = days.find(x=>x.id===toId);
  if(!to){ // create new crew-day
    const [date,crew]=toId.split('|');
    const dow = days.find(x=>x.date===date)?.dow || '';
    to={id:toId,date,dow,crew,cat:'Standard',anchored:true,stacked:1,note:'(new day)',stops:[]};
    days.push(to);
  }
  from.stops = from.stops.filter(r=>r!==row);
  to.stops.push(row);
  from.edited = to.edited = true;
  if(record){
    moves.push({row, name:C[row].name, from:from.id, to:to.id});
    persist();
  }
  days = days.filter(x=>x.stops.length>0 || x.id===toId);
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
function fmtDDMMYY(iso){
  const [y,m,dd]=iso.split('-');
  return `${dd}/${m}/${y.slice(2)}`;
}
function drawDate(date){
  layerGroup.clearLayers();
  const todays = daysFor(date);
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
        mk.bindTooltip(`<b>${c.name}</b><br>${fmtDDMMYY(d.date)} · ${d.crew}`+
          `<br>Est. time: ${estH}h · Box count: ${c.boxes||'—'}`,
          {direction:'top',offset:[0,-8]});
      }
      layerGroup.addLayer(mk);
    });
  });
  if(bounds.length>1){ map.invalidateSize(); map.fitBounds(bounds,{padding:[40,40]}); }
}

// ---------- UI ----------
const strip = document.getElementById('datestrip');
const side = document.getElementById('side');
function allDates(){ return [...new Set(days.map(d=>d.date))].sort(); }

function renderStrip(){
  strip.innerHTML='';
  const mk=(label,val,wknd)=>{
    const b=document.createElement('button');
    b.className='dchip'+(wknd?' wknd':'')+(selDate===val?' sel':'');
    b.textContent=label; b.dataset.val=val;
    b.onclick=()=>{selDate=val; render();};
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
    const d=days.find(x=>x.date===dt);
    const wknd=['Sat','Sun'].includes(d.dow);
    mk(`${d.dow} ${dt.slice(5).replace('-','/')}`,dt,wknd);
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
  card.className='card'+(approved.has(d.id)?' approved':'')+(calc.total>WIN?' overwin':'');
  card.dataset.dayid=d.id;
  card.innerHTML=`<div class="chead">
    <span class="cdot" style="background:${col}"></span>
    <span class="cname">${d.crew}${d.edited?'<span class="edited">EDITED</span>':''}</span>
    <span class="cpeople">${d.joint?IC.link+' with '+d.joint:(d.stacked>1?'×'+d.stacked+' crews':'')}</span>
    <button class="okbtn ${approved.has(d.id)?'on':''}">${IC.check} ${approved.has(d.id)?'Approved':'Approve'}</button>
  </div>`;
  card.querySelector('.okbtn').onclick=()=>{
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
    el.innerHTML=`<span class="num" style="background:${col}">${i+1}</span>
      <div class="body"><div class="nm">${c.name}
        ${isHalf?`<span class="badge" style="background:#e8f0e8;color:#1f3d2b">${IC.link} joint w/ ${d.joint} — ${(c.h26/2).toFixed(1)}h each</span>`:''}
        ${approx?'<span class="badge approx">approx pin</span>':''}</div>
      <div class="sub">${c.zone}</div>
      <div class="sub">Est install time: <b>${isHalf?(c.h26/2).toFixed(1):c.h26}h</b></div>
      <div class="sub">Box count: <b>${c.boxes||'—'}</b></div></div>
      <button class="mv">move ▾</button>`;
    el.querySelector('.mv').onclick=()=>openMoveDlg(r,null);
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
    if(row && !d.stops.includes(row)){ applyMove(row,d.id); render(); }};
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
  days.filter(d=>d.date===selDate).forEach(d=>side.appendChild(buildDayCard(d)));
  renderLog();
}
function renderLog(){
  const log=document.createElement('div'); log.id='log';
  log.innerHTML=`<h3>Session changes (${moves.length} moves · ${approved.size} approved)</h3>`+
    moves.slice(-8).map(m=>`<div class="ent">→ ${m.name}: ${m.from.replace('|',' / ')} → ${m.to.replace('|',' / ')}</div>`).join('')+
    `<div><button onclick="exportJSON()">${IC.down} Export JSON</button>
     <button onclick="exportCSV()">${IC.down} Export CSV</button>
     <button onclick="resetAll()">${IC.undo} Reset all</button></div>`;
  side.appendChild(log);
}

// ---------- move dialog ----------
const mvdlg=document.getElementById('mvdlg');
let mvRow=null;
function openMoveDlg(row,presetDate){
  mvRow=row;
  document.getElementById('mvtitle').textContent='Move: '+C[row].name;
  const dsel=document.getElementById('mvdate'), csel=document.getElementById('mvcrew');
  dsel.innerHTML=allDates().map(dt=>{
    const dow=days.find(x=>x.date===dt).dow;
    return `<option value="${dt}" ${dt===(presetDate||selDate)?'selected':''}>${dow} ${dt}</option>`;}).join('');
  const fillCrews=()=>{ const dt=dsel.value;
    const existing=days.filter(d=>d.date===dt);
    const opts=existing.map(d=>
      `<option value="${d.id}">${d.crew}${d.win===480?' (day shift 9-5)':(d.win===420?' (night)':'')}</option>`);
    BASE_CREWS.filter(cr=>!existing.some(d=>d.crew===cr)).forEach(cr=>
      opts.push(`<option value="${dt}|${cr}|new">${cr} (new day)</option>`));
    csel.innerHTML=opts.join('');};
  dsel.onchange=fillCrews; fillCrews();
  mvdlg.showModal();
}
document.getElementById('mvgo').onclick=()=>{
  applyMove(mvRow,document.getElementById('mvcrew').value);
  mvdlg.close(); render();
};

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
function resetAll(){ if(confirm('Discard all moves & approvals?')){
  localStorage.removeItem('tbdg2026review'); location.reload(); }}

// ---------- render ----------
function render(){
  renderStrip(); renderCards(); drawDate(selDate);
  const n=days.reduce((a,d)=>a+d.stops.length,0);
  document.getElementById('summarybar').textContent=
    `${n} stops · ${days.length} crew-days · ${approved.size} approved`;
}
selDate = allDates()[0];
render();
</script></body></html>"""

with open(OUT, "w") as f:
    f.write(HTML.replace("__DATA__", payload))
print("Wrote", OUT, f"({os.path.getsize(OUT)//1024} KB)")

# Keep the embedded Leaf & Ledger copy in sync (Install Schedule tab).
# PROTECTED dir — served only through the authenticated
# /api/install-schedule/page endpoint, never from public/ (client PII).
LL_PROTECTED = os.path.normpath(
    os.path.join(HERE, "..", "backend", "protected", "install-schedule"))
if os.path.isdir(LL_PROTECTED):
    import shutil
    shutil.copyfile(OUT, os.path.join(LL_PROTECTED, "index.html"))
    map_src = os.path.join(HERE, "map.html")
    if os.path.exists(map_src):
        shutil.copyfile(map_src, os.path.join(LL_PROTECTED, "map.html"))
    print("Synced into Leaf & Ledger backend/protected/install-schedule/")
