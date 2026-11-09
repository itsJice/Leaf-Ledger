-- Install Times (2026-11-08): how long each install and takedown really took,
-- so estimates improve year over year. One row per stop visit; history is
-- kept: a correction inserts a NEW row whose supersedes_id points at the row
-- it replaces (each row can be corrected once, so every visit is a straight
-- chain). install_actuals_latest is the newest row of every chain.
--
-- Written by the Install Times page (office staff for any stop, crew leads
-- for crew-days they lead or are staffed on), by Claude from crew sheets, and
-- by the one-off imports (2025 client-card times, the Dallas 2026 stop
-- comments). No pay data here, ever. The app creates all of this itself on
-- first use (app.apis.install_actuals.ensure_schema); this file is the record.
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.install_actuals (
    id                bigserial PRIMARY KEY,
    client_id         integer,
    client_name       text NOT NULL,
    client_row        integer,            -- the board's row key for the stop
    season            text NOT NULL,      -- install season ("2026"), takedowns too
    kind              text NOT NULL CHECK (kind IN ('install', 'takedown')),
    date              date NOT NULL,      -- the crew-day's date (a night's START date)
    day_id            text,               -- "2026-11-02|Crew 1|0"; joint crews use the first
    crew_label        text,
    crew_lead         text,
    arrive_at         timestamptz,
    depart_at         timestamptz,        -- may be after midnight
    people_count      integer CHECK (people_count IS NULL OR people_count BETWEEN 0 AND 40),
    photos_done       boolean,
    scope_note        text,
    est_hours_at_time numeric(6, 2),      -- the schedule's estimate, frozen when entered
    job_type          text CHECK (job_type IS NULL OR job_type IN ('residential', 'commercial', 'restaurant')),
    night             boolean NOT NULL DEFAULT false,
    source            text NOT NULL CHECK (source IN ('office', 'lead', 'claude', 'imported_sheet', 'comment_parsed')),
    entered_by        text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    supersedes_id     bigint REFERENCES ll_app.install_actuals (id),
    CHECK (arrive_at IS NULL OR depart_at IS NULL OR depart_at >= arrive_at)
);

-- A row is corrected at most once: the chain never forks, so a visit has
-- exactly one latest row.
CREATE UNIQUE INDEX IF NOT EXISTS install_actuals_one_successor
    ON ll_app.install_actuals (supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS install_actuals_day_idx ON ll_app.install_actuals (season, day_id);
CREATE INDEX IF NOT EXISTS install_actuals_client_idx ON ll_app.install_actuals (client_id);

CREATE OR REPLACE VIEW ll_app.install_actuals_latest AS
    SELECT a.*
      FROM ll_app.install_actuals a
     WHERE NOT EXISTS (SELECT 1 FROM ll_app.install_actuals b WHERE b.supersedes_id = a.id);
