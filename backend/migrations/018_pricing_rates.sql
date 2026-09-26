-- Christmas install rate card, one row per (season, key).
--
-- Until now the only rate card lived in the client spreadsheet's Rates tab
-- and, for the billing export, as literals inside the scheduler's review page
-- JavaScript (a 5% uplift, $75 a box, a hard-coded club list). Nothing in
-- the app could say what a job SHOULD cost. This table is the one place
-- rates live, versioned by season, so 2027 is a new set of rows rather than
-- an edit to code.
--
-- The ideal price of a job is computed from these and the client's
-- Christmas card (app.libs.pricing): on-site labour per person-hour for
-- each role, storage per box, and a pickup & delivery fee that replaces the
-- old flat $150 each way. That fee is built from the three logistics rows:
-- the van crew's hourly rate, minutes to move one box between shelf and
-- trailer, and a fallback one-way drive time for a client the scheduler has
-- not mapped yet.
--
-- App-owned, so it lives in ll_app. The pricing API creates this lazily on
-- first use with the identical DDL (backend/app/apis/pricing/__init__.py);
-- it is kept here so a rebuilt database gets it without a first request
-- having to do it. A season with no rows falls back to the latest earlier
-- season at read time.
--
-- Applied to Supabase on 2026-09-25.

CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.pricing_rates (
    season      text        NOT NULL,
    key         text        NOT NULL,
    amount      numeric(10,2) NOT NULL,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, key)
);

-- 2025 and 2026 from the spreadsheet's Rates tab (identical both years).
-- The three logistics parameters are starting points, tuned in Settings.
INSERT INTO ll_app.pricing_rates (season, key, amount, updated_by) VALUES
    ('2025', 'crew_lead',            100, 'migration 018'),
    ('2025', 'specialty',            135, 'migration 018'),
    ('2025', 'designer',             150, 'migration 018'),
    ('2025', 'general',               75, 'migration 018'),
    ('2025', 'storage_box',           75, 'migration 018'),
    ('2025', 'van_crew_rate',        150, 'migration 018'),
    ('2025', 'handling_min_per_box',   2, 'migration 018'),
    ('2025', 'drive_min_default',     30, 'migration 018'),
    ('2026', 'crew_lead',            100, 'migration 018'),
    ('2026', 'specialty',            135, 'migration 018'),
    ('2026', 'designer',             150, 'migration 018'),
    ('2026', 'general',               75, 'migration 018'),
    ('2026', 'storage_box',           75, 'migration 018'),
    ('2026', 'van_crew_rate',        150, 'migration 018'),
    ('2026', 'handling_min_per_box',   2, 'migration 018'),
    ('2026', 'drive_min_default',     30, 'migration 018')
ON CONFLICT (season, key) DO NOTHING;
