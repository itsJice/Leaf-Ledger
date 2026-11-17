-- The error log (app/apis/app_events) and the "last minute" trail attached
-- to comments (app/apis/feedback). Record only: the app creates both itself
-- on first use (ensure_schema_once), so nobody runs this by hand.

CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.app_events (
    id           bigserial PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now(),
    occurred_at  timestamptz,
    kind         text NOT NULL,
    source       text NOT NULL DEFAULT 'app',
    user_sub     text,
    user_name    text,
    role         text,
    page         text,
    message      text,
    detail       jsonb,
    trail        jsonb,
    user_agent   text
);
CREATE INDEX IF NOT EXISTS app_events_created_idx ON ll_app.app_events (created_at DESC);
CREATE INDEX IF NOT EXISTS app_events_kind_idx ON ll_app.app_events (kind, created_at DESC);

ALTER TABLE ll_app.feature_requests
    ADD COLUMN IF NOT EXISTS context jsonb;
