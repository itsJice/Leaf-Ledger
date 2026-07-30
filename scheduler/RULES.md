# TBDG Christmas Install Scheduling — RULEBOOK
*The accumulated business rules from building the 2026 schedule. Feed next
year's raw client spreadsheet through the pipeline with these rules and the
first pass should be ~90% right. Last updated: 2026-07-30.*

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
  by east/west. Schedule so Alberto stays free if a club falls that day.
- Alberto must be on EVERY country-club job. Brenda Ryan requires Alberto
  AND Lesly together (joint day).
- Client-requested dates from email ALWAYS override generic rules (e.g.
  clubs-on-Mondays yields to Carlton Woods' emailed Fri/Tue dates).
- Fill pinned/client dates first so those days run all 3 crews; empty days
  consolidate into a buffer block before Thanksgiving.

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
- **3 crews every night.** Crews are named by lead: Alberto, Lesly, Niurka.
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
  `schedule.py` (rules + routing) → `validate.py` (27 assertions — run
  after EVERY change) → `outputs.py`, `team_review.py`,
  `make_updated_copy.py`, `build_review.py`.
- Deliverables: schedule workbook, Team Review workbook (all history
  columns side-by-side), annotated copy of the ORIGINAL file (uniform
  zoning + date/crew/order appended, everything else untouched),
  `review.html` (living meeting tool: All/All Houston/All Dallas tabs,
  per-crew cards, drag-drop moves re-routed live from the OSRM matrix,
  approvals, Export JSON→ feed decisions back as pins).
- Joint stops appear on two crews' cards; spreadsheets show merged
  "Alberto + Lesly (joint)" labels; count DISTINCT clients for coverage.
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
  `/install-schedule`, page = Layout-wrapped iframe of
  `public/install-schedule/index.html`).
- `build_review.py` auto-syncs review.html + map.html into
  `leaf-and-ledger/app/frontend/public/install-schedule/` on every
  regenerate — rebuild the frontend (or redeploy) to ship updates.
