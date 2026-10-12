-- Install Changes backfill (app/apis/schedule_changes,
-- scripts/backfill_schedule_history.py): older Install Schedule states
-- recovered from backups, kept apart from ll_app.install_schedule_history,
-- which the backfill never writes. kind 'plan' is a spreadsheet build of the
-- schedule; 'save' a saved state of the board. dedupe_key makes the importer
-- safe to re-run. Applied by the app itself through ensure_schema_once; this
-- file is the record.
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.install_schedule_history_archive (
    id          bigserial PRIMARY KEY,
    kind        text NOT NULL DEFAULT 'save',
    version     text,
    season      text NOT NULL,
    state       jsonb NOT NULL,
    updated_by  text,
    created_at  timestamptz NOT NULL,
    source      text NOT NULL,
    source_ref  text,
    dedupe_key  text NOT NULL UNIQUE,
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS install_schedule_history_archive_season_idx
    ON ll_app.install_schedule_history_archive (season, created_at);
