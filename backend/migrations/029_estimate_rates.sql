-- Install estimate rates (2026-11-08): minutes per item and the night,
-- commercial and first-year factors that app.libs.install_estimate uses when
-- a client has no real on-site time yet (spec: app/libs/install_estimate.md).
-- One row per (season, key); a season without its own value for a key uses
-- the latest earlier season's. A key with no row anywhere is NEEDS INPUT.
-- Edited in Settings > Install Estimates (admins); seeded by a dry-run-first
-- least-squares fit on 2025 jobs (outside git). The app creates the table
-- itself on first use (app.apis.install_estimate.ensure_schema).
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.estimate_rates (
    season     text NOT NULL,
    key        text NOT NULL,
    amount     numeric(10, 3) NOT NULL CHECK (amount >= 0),
    note       text,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, key)
);
