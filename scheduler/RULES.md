# TBDG Christmas Install Scheduling — RULEBOOK
*The accumulated business rules from building the 2026 schedule. Feed next
year's raw client spreadsheet through the pipeline with these rules and the
first pass should be ~90% right. Last updated: 2026-09-02.*
*To actually run the next season, start at §13 — it is the ordered checklist;
the rest of this file is the WHY behind it.*

---

## 1. Reading the raw spreadsheet
- Sheet `<season> Christmas`, header row 1. Columns are looked up BY HEADER
  NAME, never by position — the order already shifted once between file
  revisions, and an index list misreads data silently on the next reshuffle.
  The positions below are only where they sat in 2026: name(1), address(2),
  city(3), ZIP(5, float→5-digit string), boxes(13), staffing(16-19),
  est hours(20), prior-year install date(22), prior-year REAL hours(23),
  storage(12), phone(8), email(9), crew name(28). The exact header SPELLINGS
  prep.py requires — and which ones abort vs. warn — are in §13.1.
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
- Pin every client-communicated date in `scheduler/client_config.json`'s
  `pins` (PIN validations catch drift) -- see §12 for why that file, not
  schedule.py/rules.py, is where every named client rule lives now.

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
  runs badly stale (2026 audit found several clients off by 2-4x, one by
  10x; ~22 clients had counts only in the binder). Photograph the binder
  each season and load
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

- **No client names in the codebase (user, 2026-08-02: "in the codebase"
  no, "in the UI" yes).** Every named client rule -- deposited-date pins,
  same-day groups, forced-first stops, drops, the ~15 one-off manual
  pairings built up over the season, ZIP/storage/coordinate overrides,
  and the single-crew-priority category special-case -- lives in
  `scheduler/client_config.json` (gitignored, never tracked, required to
  build a correct schedule). `scheduler/client_config_loader.py` is the
  one shared loader (`load()`, hard-errors on a missing file rather than
  silently building a wrong schedule with empty rules); `prep.py`,
  `schedule.py`, `validate.py` and `outputs.py` all call it directly
  since prep.py runs before schedule.py exists as an importable module
  and can't reuse its loaded copy. `rules.py` is the one exception --
  it reuses `schedule.py`'s already-loaded `CLIENT_CONFIG` for
  `PINS`/`FORCE_FIRST`/`SAME_DAY_GROUPS`/`NO_INSTALL` instead of loading
  a second time. Code keeps its exact structure (crew, date, window,
  fill -- all non-PII scheduling parameters) as literals; only names,
  name-bearing notes, and the one name-derived category value are
  config-driven. The generated tool (review.html/map.html) is
  unaffected -- it still embeds full client data, sourced from
  `cache/clients.json` same as always, and reaches the deployed app
  through Postgres (see §10), never through git.
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
  Note (2026-08-02): the soft flags on SUNDAY/BIZ_SAT/SAT_HIST only
  reach a date if `calendar()` gives it a real `kind` in the first
  place -- every Saturday/Sunday except the named exceptions (Rotary
  Sunday, Bank Friday) fell through to `kind="unused"` -> the hard
  NO_DATE code, disabling the whole date regardless of those rules'
  soft flags. Fixed by giving every Saturday/Sunday its own kind
  (`"saturday"`/`"sunday"`) in `calendar()` so they reach the soft
  checks instead of being excluded before those checks ever run.
  Same bug, same fix, extended (user, 2026-08-02) to every remaining
  weekday in `DOW`'s Nov 1-Dec 10 range that sat outside this round's
  automated pool (before/after the window `schedule.py` filled first,
  plus Thanksgiving) -- those now get `kind="weekday"` (Thanksgiving
  gets its own `"thanksgiving"` kind). Thanksgiving is workable like
  every other soft-blocked date, but is worth flagging even though it
  isn't disabled -- `build_review.py`'s `dateLabel()` helper appends
  " — Thanksgiving Day" to its option label unconditionally (not just
  when something's actually disabling it), the one exception to "soft
  codes stay silent in the dropdown."
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

## 13. ROLLING OVER TO THE NEXT SEASON — the October checklist
Everything year-shaped is now DERIVED from one season number; this section is
what a human still has to do, in order. Nothing here requires reading the
code. Skim §13.0 once, then work 1→7.

### 13.0 The season model (read this first)
- A season runs **1 Oct (Y) → 31 Jan (Y+1)** and is **named for October's
  year**: on 15 Jan 2027 the crews are finishing the **2026** season, not
  starting 2027 — installs are Oct–Dec, takedowns spill into January, and
  splitting that at New Year would cut one season's work in half.
- The rollover boundary is **1 February**. Before it, "this season" is last
  October's; on and after it, planning has moved to the coming autumn. That
  is what makes rollover automatic — nobody edits a year to make it happen.
- `scheduler/season.py` is the **single definition** (`season_for`,
  `season_of_date`, `season_span`, `year_of_month`, `takedown_cutoff`,
  `nth_weekday`, `thanksgiving`, `black_friday`,
  `sunday_after_thanksgiving`). `backend/app/libs/season.py` is its deployed
  twin because the build pipeline runs outside the deployed image and can't
  import it — **change both together**; `backend/tests/test_season.py` fails
  if they disagree. No other file may compute a year.
- **`TBDG_SEASON` overrides it**, everywhere (prep.py, schedule.py,
  build_review.py, publish_pages.py all read it before falling back to
  `season_for()`), for rebuilding a closed season or getting the coming
  season's tool up before 1 Feb:
  `TBDG_SEASON=2026 .venv/bin/python3 prep.py`
  Set it for the **whole chain or none of it** — a half-set chain builds one
  season's clients against another season's calendar, and every stage will
  look like it worked. Each stage prints the season it is building; read that
  line before trusting the run.

### 13.1 Prepare the source workbook
- In `CHRISTMAS CLIENTS - Storage - Delivery - Install +Takedown.xlsx`, add a
  sheet named exactly **`<season> Christmas`** (header row 1). prep.py aborts
  with the sheet list if it isn't there.
- Header **spelling** is load-bearing; the year-named ones are **not
  regular** — the year leads on some, trails on another, and one is shouted.
  Copy last season's sheet and re-year these:
  - `<season> Install Date` — **REQUIRED**. A real date = client deposited
    and reserved that date (hard pin); free text carries "same day as X"
    groupings and "no install" cancellations. This was historically the most
    dangerous cell in the pipeline: a missed header used to yield every pin
    ignored, every grouping note lost and every cancelled client scheduled
    anyway, with **no error**. prep.py now aborts instead.
  - `TBDG CLIENT`, `ADDRESS`, `ZIP` — also **REQUIRED** (abort).
  - `<season-1> Real Hours For Install` — optional; without it hours
    calibration falls back to est×0.81 / zone median for EVERY client.
  - `Install Date <season-1>` — **year LAST**; optional; without it nobody is
    Saturday-eligible (§5 reads that date's actual weekday).
  - `<season-2> INSTALL DATE` — **ALL CAPS**; optional.
  - `<season-1> Crew Name` (falls back to `Crew Name`),
    `<season-1> Production Notes` (falls back to `Production Notes`).
  - `<season-1> Invoice Total Actual Created` — optional, but its absence
    blanks the ENTIRE billing export.
  - Year-free and unchanged: `CITY`, `ST`, `PHONE`, `EMAIL`, `BOX COUNT`,
    `TBDG STORAGE YES/NO`, `ESTIMATED TOTAL HOURS FOR INSTALL`, the four
    `#` staffing columns, `INSTALL LABOR FEE`, `TAKEDOWN LABOR FEE`,
    `STORAGE FEE (BASED ON # OF BOXES)`.
- prep.py checks the header row ONCE, up front: required → abort naming the
  exact spelling; optional → a `!!` line per column saying what goes blank.
  **Read those warnings.** Blank is never fine, only sometimes expected — a
  first season legitimately has no prior-year history; a fifth one does not.
- History workbook: `CHRISTMAS Historical Reference (<season-2>-<season-1>).xlsx`,
  with sheets `<season-1> Christmas` (headers on **row 2**; `INSTALL LABOR
  FEE`, `STORAGE FEE (BASED ON # OF BOXES)`) and `<season-2> Christmas`
  (headers on **row 1**; `TOTAL INSTALL LABOR FEE`, `TOTAL TBDG STORAGE FEE
  (BASED ON # OF BOXES)`). Two shapes, one file — that's why they're read
  separately. Closed-season file: its CACHED VALUES are the fact, not its
  formulas. Entirely optional, and every miss warns by name.
- Photograph the storage binder and refresh the verified box counts (§9) —
  the sheet's BOX COUNT column runs badly stale every year.

### 13.2 Decide the per-season CONFIG (the only judgement calls left)
All in `SEASON_CONFIG` at the top of `schedule.py`. **Add a NEW key for the
season; never edit last season's block** — that is what keeps a past season
reproducible. schedule.py aborts if the season has no block. Entries are
`(month, day)` pairs, never full dates: the calendar year comes from the
season, so a January entry lands in the following year automatically and no
entry can drift to the wrong year.
- `dallas_week` — which Monday of November the Dallas / Mi Cocina run starts
  on (1 = first Monday). The run is that Mon–Fri; §6 is the trip's rules.
- `club_mondays` — which Mondays of November are country-club days
  (1 = first Monday). Client-emailed dates still override (§5).
- `hou_weekdays` — Houston weekday capacity for the season.
- `std_weekdays` — the SUBSET this round's optimizer may auto-fill. Keep it
  narrower than `hou_weekdays` on purpose: the wider calendar stays available
  for later manual reschedule accommodation without the optimizer
  pre-spending it.
- `saturdays` — standard Saturday capacity, if any (§5: Saturdays are a
  ceiling, not a floor).
- `force_start` — dates that must be filled before anything else.
- `overflow_tail` — last-resort dates, used only if November runs out.
- `labels` — standing commitments and event blackouts. **Labels, not
  blocks**: the tag shows on the date chip and day card so nobody schedules
  over one by accident, but staff can still place work there (§12's
  blockers-vs-warnings rule).
- `dow_spans` — the stretch shown as real date bubbles in the review tool
  (`"all"` = weekends included, `"weekdays"` = Mon–Fri). Everything else in
  the Oct–Jan span still reaches the tool through `EXTRA_DOW` as an addable
  date.
- `dow_omit` — dates deliberately held out of `dow_spans`.
- Per-client rules (pins, same-day groups, drops, clubs, ZIP/storage/coord
  overrides) do NOT live here — see §12 and §13.4.

### 13.3 DERIVED — never hand-edit, never hand-type
Computed from the season (+ CONFIG) and asserted; typing any of these back in
is how a calendar silently drifts a year:
- Thanksgiving (4th Thursday of Nov), **Black Friday** (bank day, §5),
  **Rotary Sunday** (Sunday after Thanksgiving, the only Sunday, §5).
- `DALLAS_DAYS` and `DALLAS_WEEK_SPAN` (the whole Sun–Sat week the run owns —
  rules.py needs the boundary), `CLUB_MONDAYS`.
- Every **day-of-week label** (`DOW`). rules.py reads `S.DOW` to decide the
  Saturday/Sunday rules, so one mistyped label would silently break every
  weekday rule for that date.
- The **Oct 1 – Jan 31 span** (`season_span`) and therefore `EXTRA_DOW`, the
  addable-date pool — including the January takedown tail.
- The **takedown cutoff** (25 Dec; installs run through Christmas, anything
  later is takedown).
- A startup assertion fails the build if any working date (Dallas, clubs,
  Houston, std, Saturdays, bank Friday, Rotary Sunday) isn't on the rendered
  calendar — a slot nothing could legally be dropped onto.

### 13.4 Refresh the per-client rule files — THEY HAVE NO SEASON STAMP
- `client_config.json` (gitignored, required, §12) holds pins, same-day
  groups, forced-first stops, drops/no-install, club and lead names, ZIP /
  storage / coordinate overrides. `pins` and `force_first` are **dates for
  one specific season**.
- `overrides.json` is the review tool's notebook — frozen (date, crew, stops)
  days plus manually-added clients, replayed verbatim before anything else
  runs so a rebuild can't move people who were already told their date.
- **Neither file records which season it belongs to**, and nothing checks:
  a leftover file replays LAST season's dates into the new season's build and
  the run looks entirely successful. So, as a step: archive both
  (`client_config.<season-1>.json`, `overrides.<season-1>.json`), then start
  the new season from a reviewed copy with last season's dated entries
  cleared. Known debt — see §13.7.

### 13.5 Run the pipeline
- Order and per-stage detail: **§8**. Don't duplicate it here; run it there.
- prep.py first, and check its banner line names the season and sheet you
  meant. The geocode cache is keyed by address and the OSRM matrix by
  coordinates, so a new season only fetches what actually changed — nothing
  to clear, and clearing them costs an hour of rate-limited refetching.
- `validate.py` after EVERY change, as always.

### 13.6 Publish — the archive is per season
- `publish_pages.py` pushes review.html/map.html into Postgres keyed on
  **(season, name)**, so publishing a new autumn ADDS to the archive instead
  of erasing last year (migration `013_season_keyed_schedule.sql`; run once
  before the first rollover). Last season's routed plan, crews, stop order
  and approvals stay openable — that half of the old workbook is the part
  that had not survived the move off spreadsheets.
- `GET /api/install-schedule/seasons` lists what's published (newest first)
  and reports the current season separately, because the two disagree between
  1 Feb and the day the new tool is first built: with nothing published for
  the new season the page falls back to the newest PUBLISHED one rather than
  404ing.
- A past season opens **read-only**: its saved reschedule state is keyed on
  the build version that produced it (and the tool's localStorage key is
  season-scoped), so an archived season's snapshot can never be restored over
  the live one — two seasons open in one browser are two separate schedules.
- Publishing under a season you didn't mean creates a junk row that shows in
  the picker forever, so `TBDG_SEASON` is validated as a four-digit year here
  rather than trusted.

### 13.7 Known debt to expect (not bugs — flagged so nobody "fixes" them blind)
- **`_2026` field names.** prep.py still emits `install_2026_confirmed`,
  `install_2026_note`, `install_2026_no_install`, `install_fee_2026`,
  `takedown_fee_2026`, and `invoice_2025_total` / `crew_2025` /
  `crew_size_2025` / `date_2024` / `install_fee_2025` / `storage_fee_2024`.
  The VALUES are season-derived and correct; only the key spelling is frozen.
  Read them as `_2026` = **this season**, `_2025` = last season, `_2024` =
  two back. Renaming them is a separate change that must land in ONE commit
  across `rules.py`, `schedule.py`, `validate.py`, `sync_clients.py` and
  `build_review.py` — plus any saved `overrides.json` / shared state keyed on
  them. Renaming in prep.py alone silently breaks all five consumers.
- **`client_config.json` / `overrides.json` carry no season stamp** (§13.4).
  The real fix is a `"season"` field written at export and refused on
  mismatch at load; until then it is a manual checklist step.
- **`dow_omit`** exists only to reproduce a Sunday that was missing from the
  hand-typed 2026 calendar. Once someone confirms it should be an ordinary
  gray Sunday bubble, delete the entry — don't copy it into a new season.
