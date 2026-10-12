-- Install Schedule "Changes" list (app/apis/schedule_changes): who follows it
-- and when they last looked, one row per login. Applied by the app itself
-- through ensure_schema_once; this file is the record.
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.schedule_change_follows (
    user_id      text PRIMARY KEY,
    following    boolean NOT NULL DEFAULT true,
    last_seen_at timestamptz,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
