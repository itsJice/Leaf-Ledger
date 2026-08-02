# TBDG Christmas Install Scheduling — RULEBOOK
*The accumulated business rules from building the 2026 schedule. Feed next
year's raw client spreadsheet through the pipeline with these rules and the
first pass should be ~90% right. Last updated: 2026-08-02.*

---

## 1. Reading the raw spreadsheet
- Sheet `<year> Christmas`, header row 1. Key columns: name(1), address(2),
  city(3), ZIP(5, float→5-digit string), boxes(13), staffing(16-19),
  est hours(20), prior-year install date(22), prior-year REAL hours(23),
  storage(12), phone(8), email(9), crew name(28).
- EXCLUDE billing line-items: GENERAL INSTALL LABOR, PICKUP & DELIVERY
  (INSTALL/TAKEDOWN), SPECIALTY INSTALL LABOR, STORAGE FEE PER BOX, CREW
  LEAD, DESIGNER ART DIRECTOR LEAD.
- Addresses are messy: strip trailing "city, ST zip" from the street cell;
  some rows hide the address in the city cell.
- Flag clients with no usable address as NEED ADDRESS — never guess.

## 2. Zones, geocoding, drive times
- Recompute Area/Zone from ZIP (hardcoded map in prep.py). ZIP wins over
  whatever labels the file has — several are wrong every year.
- Geocode: Nominatim with query `"street, TX zip"` (NO city name — the city
  string kills house-number matches). Fallback → US Census geocoder
  (rooftop-accurate) → per-ZIP centroid via free-form `"zip, TX"`. NEVER use
  Nominatim's structured city+postalcode query (returns city centroid and
  collapses clients). Cache everything.
- Drive times: OSRM table API, tiled ≤90 coords/request, cached. Durations
  are ASYMMETRIC — classic 2-opt cycles forever on them; only accept route
  changes that shorten the full recomputed tour. Final routes: exhaustive
  permutation for days ≤8 stops (provably optimal).

## 3. Estimating hours & people — ACTUALS BEAT ESTIMATES
- 2026 install hours: prior-year REAL hours if present; else estimate ×0.81
  (estimates run ~19% high); else zone median of real hours.
- Crew size: actual prior-year crew size beats the staffing-ask columns
  (16-19), which run ~2× high. Default 5 (lead + 4).
- Mi Cocina special case: the flat "3.0" real-hours entries are block
  estimates, not measurements. The precisely-timed installs cluster ~2.2h,
  which matches the observed 3-4 installs/night pace. Recalibrate exact-3.0
  entries to the measured median (~2.17h). Megas (Lake Highlands ~9h,
  Highland Park ~8.75h) are real.

## 4. Classification & categories
- Residence = "Lastname, Firstname" pattern or contains "Residence";
  Business = keyword list (bank, club, CC, hotel, church, office, LLC…).
- Categories: M Crowd/Mi Cocina (name starts "M Crowd", all DFW),
  Country Club (Carlton Woods / Country Club / CC / Club), Capital Bank,
  Rotary House, Brenda Ryan, else Standard.

## 5. HOUSTON rules
- Depot: 2860 Antoine Dr — every Houston day starts/ends there.
- Day shape: arrive depot 8:00, roll out 8:30. Route day = install + drive
  + 40-min lunch. **Max 10h** (back ~6:30pm), **soft min 7.5h** (teams like
  to work). Light days merge into neighbors when geography allows; the
  leftovers are rule-driven or isolated-area and get flagged, not hidden.
- Grouping is proximity-FIRST: plot all points, link stops within a
  **30-min real drive** into clusters (45-min allowed in rural pockets —
  Bellville/Brenham — where a longer hop beats a second 2.5h round trip),
  then split clusters into balanced days. Never weld a stop across town.
- No businesses on weekends. Residences may take Saturdays. Rotary House is
  the ONLY Sunday (Sunday after Thanksgiving).
- Capital Banks: all 8 on Black Friday; won't fit one crew — split 2 crews
  by east/west. Schedule so Crew 1 stays free if a club falls that day.
- Crew 1 must be on EVERY country-club job. Brenda Ryan requires Crew 1
  AND Crew 2 together (joint day).
- Client-requested dates from email ALWAYS override generic rules (e.g.
  clubs-on-Mondays yields to Carlton Woods' emailed Fri/Tue dates).
- Fill pinned/client dates first so those days run all 3 crews; empty days
  consolidate into a buffer block before Thanksgiving.
- SATURDAYS ARE RESTRICTED (user rule, 2026-07-30): a client may be
  scheduled on a Saturday ONLY IF their prior-year install was ALSO on a
  Saturday (checked from prior_install_date's actual weekday, not
  inferred). This is a ceiling, not a floor -- a Saturday-eligible client
  can still land on a weekday (e.g. as filler for a pinned day) and that's
  fine; the rule is only violated if an INELIGIBLE client ends up on a
  Saturday. Implementation: split eligible residences out of the standard
  pool and cluster them separately BEFORE the general geographic packing
  (schedule.py) -- clustering them together with the general pool first
  would weld an eligible client into a bin with ineligible neighbors and
  make the whole bin ineligible. Businesses were already weekend-excluded
  by the no-business-on-weekends rule, so this only ever affects
  residences. validate.py R12 checks every Saturday stop's history.

## 6. DALLAS / Mi Cocina rules
- Out-of-town trip: crews STAY in Dallas (no depot). ~25 restaurants.
- All work at NIGHT except **M Crowd Corporate Office** (business hours
  9am-5pm — install it on arrival day: drive up in the morning, install,
  hotel, first night shift that night).
- Nights start 11pm. **6.5-7.5h of work per crew-night** (done 5:30-6:30am)
  on every night EXCEPT the last; 8am is the absolute hard wall (6:30-8am
  = overrun buffer only). No lunch modeled on nights.
- A route under 6.5h is acceptable only if MAX-PACKED (adding even the
  smallest remaining restaurant would exceed 7.5h) or on the final night.
- **3 crews every night.** Crews are named by lead: Crew 1, Crew 2, Crew 3.
- Mega restaurants (>7h solo) get TWO crews jointly: both meet at the mega
  at 11pm (halve its hours), then split to their own nearby stops. Show as
  one card PER CREW with a joint badge — never a merged "stacked" card.
- CO-LOCATION: same-night crews work near each other (avg ~20 min apart)
  for troubleshooting and assists. Fort Worth night, Plano night, etc.
- FRONT-LOAD the week: heaviest nights first; the LAST night is the buffer
  for pushed stops and loose ends (and gets the under-min leftovers).
- 4 nights is the proven minimum at the 2025 pace; Friday freed.

## 7. Email integration
- Client install-date requests live in joybells@thebranchdesigngroup.com
  (shared Christmas account). Search for `<year>` install dates; EXCLUDE
  prior-year installs, takedowns ("TD Crew", tear down), and January HOLD
  events. Confirmed calendar events beat email requests beat internal notes.
- Pin every client-communicated date in schedule.py (PIN validations catch
  drift). Known 2026 pins: Keffer Nov 18 (appt), Marek Nov 30, Carlton
  Nicklaus+Outdoor Nov 27 (+tweak 11/30), Fazio Dec 1, WCC Players Nov 25,
  WCC Palmer/Legacy/Trails Nov 30, WCC Tournament = no install.

## 8. Process / tooling
- Pipeline: `prep.py` (parse→zones→hours→geocode→matrix, all cached) →
  `schedule.py` (rules + routing, orders stops for minimum real DRIVE
  TIME) → `route_geometry.py` (fetches each day's real road-following
  path + actual mileage from OSRM /route, cached by stop sequence) →
  `validate.py` (27 assertions — run after EVERY change) →
  `outputs.py`, `team_review.py`, `make_updated_copy.py`,
  `build_review.py`. Re-run `route_geometry.py` before the output
  scripts any time schedule.py changes the plan — cached, so unchanged
  days don't refetch.
- Deliverables: schedule workbook, Team Review workbook (all history
  columns side-by-side), annotated copy of the ORIGINAL file (uniform
  zoning + date/crew/order appended, everything else untouched),
  `review.html` (living meeting tool: All/All Houston/All Dallas tabs,
  per-crew cards, drag-drop moves re-routed live from the OSRM matrix,
  approvals, Export JSON→ feed decisions back as pins).
- Joint stops appear on two crews' cards; spreadsheets show merged
  "Crew 1 + Crew 2 (joint)" labels; count DISTINCT clients for coverage.
- Serve preview via `.claude/launch.json` ("review", autoPort).

## 9. Box counts / truck loading
- The STORAGE-ROOM BINDER (photographed sheets + physical box labels) is
  the source of truth for box counts — the spreadsheet's BOX COUNT column
  runs badly stale (2026 audit: Nicklaus 83 vs sheet's 20, Fazio 31 vs 10,
  Moss 35 vs 14, Royal Oaks 42 vs 38; ~22 clients had counts only in the
  binder). Photograph the binder each season and load
  `STORAGE_BOX_COUNTS` in prep.py; pipeline keeps both values
  (`box_count` = verified, `box_count_sheet` = original) and the annotated
  workbook adds a highlighted "Storage Boxes (verified)" column.
- Binder ambiguity to confirm each year: entries like "Mc Crowd 9 Boxes"
  with no location (assumed Corporate Office in 2026).

## 10. Leaf & Ledger integration
- The Install Schedule tool is embedded in the Leaf & Ledger app as a
  sidebar tab (Workspace → "Install Schedule", TreePine icon, route
  `/install-schedule`). The page is client names, home addresses and
  phone numbers, so it is served ONLY from the authenticated
  `GET /api/install-schedule/page` route (backend/app/apis/install_schedule)
  and synced into `backend/protected/install-schedule/` — never
  `frontend/public/`, which is served to anyone with the URL. The
  frontend page fetches it with the signed-in user's token and injects
  it into a `srcDoc` iframe (`frontend/src/pages/InstallSchedule.tsx`),
  then `postMessage`s the auth token in so the tool's shared-state calls
  (§12) can authenticate — with no token it falls back to localStorage
  only, same as running the standalone file offline.
- `build_review.py` auto-syncs review.html + map.html into
  `backend/protected/install-schedule/` on every regenerate — restart
  or redeploy the backend to ship updates (no frontend rebuild needed;
  the page is fetched at request time, not bundled).

## 11. Real road geometry, mileage & map robustness
- `route_geometry.py` fetches each day's REAL road-following path + actual
  mileage from OSRM's /route service (distinct from /table, which only
  gives point-to-point durations, not the path or the distance). Cached by
  stop sequence; `overview=simplified` + 5-decimal rounding keeps the
  embedded payload small (~2k points across all days, not ~74k).
- Stop ORDER is unaffected — schedule.py already orders every day for
  minimum real DRIVE TIME (route_exact, exhaustive permutation, provably
  optimal). Geometry/mileage is display + a live sanity-check, not a
  re-optimization.
- review.html: unedited days draw the precomputed geometry (offline-safe,
  exact). The moment a day is edited (drag/drop), the old geometry is
  stale — the client re-fetches live from OSRM (CORS is open on the public
  server) and swaps in the real path once it resolves; a dashed straight
  line is shown while pending/if the fetch fails. Never present a straight
  line as if it were a real route.
- MAP INIT BUG (found 2026-07-30, costly to debug): `L.map(...).fitBounds()`
  depends on reading the container's real pixel size. In some embedding
  contexts (confirmed: this project's automated browser-preview tool) the
  container/viewport reports 0x0 at load time — even `window.innerWidth`
  lies — and Leaflet computes a nonsensical zoom (e.g. 19, a random side
  street) that nothing ever self-corrects, not even `invalidateSize()` or
  a delay. FIX: don't use `fitBounds` for the initial view. Compute
  center+zoom in Python from the real data bounds (self-adjusting) and
  call `map.setView(center, zoom)` instead — it needs no container size at
  all. Normal user zoom/pan still works fine afterward. Applied in
  outputs.py's MAP_TEMPLATE; review.html's per-date `fitBounds` calls are
  interaction-triggered (not first-paint) and were not affected.

## 12. Reschedule-assist: guardrails, overrides, shared editing
Built after the base 2026 schedule shipped, for the weeks of client
reschedule requests that follow. All in `build_review.py`'s emitted JS
unless noted; rules mirror `rules.py`'s predicates so there is one
definition of "legal," not a second implementation that can drift.

- **Guardrails, not a re-solve.** Dragging a stop runs `checkPlan(ops)`
  against a CLONED copy of the day state (never live) before anything
  commits. Static rules (dates, categories, deposits) are precomputed in
  Python per (client × date) and shipped as a lookup table; dynamic
  rules (30-min radius, day window, group cohesion, joint integrity)
  are evaluated live in JS since they depend on what a day currently
  contains.
- **Blockers vs. warnings (user, 2026-08-02: staff need full override
  capability to accommodate a customer "even if something goes wrong").**
  Every DATE/category rule — Dallas week, Bank Friday, Rotary Sunday,
  a client's own deposited date, day-over-window hours — is a soft
  warning: it never disables a date in the move dialog or slot finder,
  it shows a concise "heads up, confirm to proceed" note before commit.
  What stays a hard block is scoped to what would silently corrupt a
  job, not just break a scheduling preference: a stop that needs two
  crews, a same-day client group split apart, a club job missing Crew 1
  coverage. `rules.py`'s `CODES` dict is the single switch for this
  (`soft=True`/`False` per code) — flip it there, not per call site.
- **Slot finder** (`openSlotFinder`) — "this client wants date X" → every
  legal (date, crew) ranked by a marginal-insertion-cost screen (asymmetric
  matrix, evaluated in the actual direction — never symmetrized) against
  the day's real geography, then exactly re-routed for the top candidates.
  Recommends dates before AND after the client's current one when today's
  date allows it (never a date that's already passed).
- **Notebook** (`overrides.json`, exported from the tool) — every promised
  (date, crew, stops) is a FROZEN assignment, replayed verbatim by
  `schedule.py` before anything else runs, so a spreadsheet regeneration
  doesn't silently move 30 people who were already told their date.
  Keyed by client NAME (a sheet row insertion renumbers every row after
  it, which would reattach dates to the wrong person otherwise).
- **Manually-added clients** (jobs never in the spreadsheet: an
  install → event-takedown → reinstall pattern, a one-day install with
  a next-day takedown, a callback because something broke or the client
  bought more) — a "+ New client" dialog geocodes the address live and
  fetches REAL OSRM drive times against every existing client (two
  targeted `/table` calls, both directions — durations are asymmetric,
  same as everywhere else in this codebase — not a full N×N matrix, so
  it stays fast regardless of how many manual clients already exist).
  The fetched legs are persisted with the client record (localStorage,
  shared state, and the notebook export) so a reload or a full
  `schedule.py` rebuild reuses the same real numbers instead of
  re-deriving or re-fetching them. Straight-line-plus-fudge estimate is
  a fallback only, for when the live fetch fails or for the rare case
  of two manually-added clients' distance to each other.
- **Undo/redo** — full state snapshots (placement + approvals + moves),
  100 deep, session-scoped (a reload starts fresh — see shared state
  below for what actually persists across reloads).
- **Shared state** — several staff work the same schedule over the
  season, so edits live in Postgres keyed on the schedule build version
  (`ll_app.install_schedule_state`), not per-user — a per-user document
  would let two people silently diverge. Saves are debounced 200ms and
  carry a timestamp; on load, if THIS device's last local save is newer
  than the server's last recorded write (its own debounced push from
  before a refresh may simply not have landed yet), local wins and gets
  pushed up rather than being silently overwritten by stale server data.
- **Change history** — every save also appends to
  `ll_app.install_schedule_history` (200-version retention per build)
  instead of only overwriting the current row. The tool's "History"
  panel lists past saves (who, when) with a Restore action; restoring
  never deletes anything — it applies the old state locally and saves
  it back as a new current version, same model as a Google Doc's
  version history.
