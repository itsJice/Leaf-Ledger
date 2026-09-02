-- Keep every season's schedule, the way the spreadsheet used to.
--
-- install_schedule_pages was keyed on the filename alone -- one row for
-- 'index.html', one for 'map.html'. Publishing a new season overwrote them, so
-- the previous season's tool stopped existing. Its saved state survived in
-- install_schedule_state (that table is keyed on the build hash, which changes
-- per season), but survived unreadably: state is a placement document keyed on
-- row numbers, and without the page that renders it, it is 4 KB of JSON nobody
-- can open.
--
-- Client-level history was never at risk -- client_activity already holds 2022
-- through 2026 and a new season only adds rows. What was at risk is the
-- schedule itself: the routed plan, crews, stop order, drive times, approvals
-- and staffing. That is the half of the old workbook that had not survived the
-- move, and this is what keeps it.
--
-- Run once, before the first rollover. There is exactly one page pair and one
-- state row to migrate today; after a season turns over there would be more.

-- ---------------------------------------------------------------------------
-- 1. Pages: key on (season, name)
-- ---------------------------------------------------------------------------
ALTER TABLE ll_app.install_schedule_pages
  ADD COLUMN IF NOT EXISTS season text;

-- Everything published so far is the 2026 season.
UPDATE ll_app.install_schedule_pages SET season = '2026' WHERE season IS NULL;

ALTER TABLE ll_app.install_schedule_pages
  ALTER COLUMN season SET NOT NULL;

ALTER TABLE ll_app.install_schedule_pages
  DROP CONSTRAINT IF EXISTS install_schedule_pages_pkey;

ALTER TABLE ll_app.install_schedule_pages
  ADD CONSTRAINT install_schedule_pages_pkey PRIMARY KEY (season, name);

-- ---------------------------------------------------------------------------
-- 2. State: findable by season, still keyed by build
-- ---------------------------------------------------------------------------
-- version stays the primary key: it is what guarantees a 2026 placement
-- document can never be replayed onto a 2027 build (row numbers are
-- re-assigned by each season's sheet, so a cross-build restore would silently
-- hand stops to different clients). season is added alongside it purely so a
-- season can be FOUND without knowing its hash.
ALTER TABLE ll_app.install_schedule_state
  ADD COLUMN IF NOT EXISTS season text;

UPDATE ll_app.install_schedule_state SET season = '2026' WHERE season IS NULL;

CREATE INDEX IF NOT EXISTS install_schedule_state_season_idx
  ON ll_app.install_schedule_state (season);

ALTER TABLE ll_app.install_schedule_history
  ADD COLUMN IF NOT EXISTS season text;

UPDATE ll_app.install_schedule_history SET season = '2026' WHERE season IS NULL;
