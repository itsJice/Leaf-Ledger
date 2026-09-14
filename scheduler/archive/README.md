# Archived scheduler scripts

Moved here (5.1 scheduler-common), not deleted -- each is a one-off or
already-applied script, not part of the regular pipeline (RULES.md §8).

- **audit_geocode.py** -- one-off audit (2026-08-01) that sanity-checked
  every client's geocoded lat/lon against their own ZIP centroid, to catch a
  bad-geocode bug where Nominatim returned a confident but wrong coordinate.
  Archived because the bug it was written to catch is fixed and it isn't run
  regularly; kept for reference if a similar geocode anomaly needs auditing
  again.
- **backfill_summary_wording.py** -- one-time database backfill that
  rewrote already-stored `client_activity.summary` rows to the season-neutral
  wording (`sync_clients.py`'s `summarize()` already writes the new wording
  going forward). Archived because it has already been run against
  production and a second run is a no-op by design (idempotent), not because
  it stopped working.
- **make_updated_copy.py** -- produced an annotated copy of the *original*
  2026 Christmas client spreadsheet (uniform zoning + 2026 date/crew/order
  columns appended) as a deliverable for that season's planning meeting.
  Archived because it is hard-coded to the 2026 sheet name, output filename
  and column letters (`SHEET = "2026 Christmas"`, `OUT = "2025 CHRISTMAS
  CLIENTS (2026 zoning + assignments).xlsx"`) rather than derived from
  `season.py` like the rest of the pipeline -- it was a single-season
  deliverable, not a reusable stage.
