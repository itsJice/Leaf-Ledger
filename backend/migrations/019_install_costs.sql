-- The install cost card: what a Christmas install costs US to run, one row
-- per (season, key). The billing rate card (018, ll_app.pricing_rates) says
-- what we charge; this says what we pay, so a job's price can be held up
-- against its crew, vans, gas and overhead (app.libs.install_costs).
--
-- Keys are the fixed cost keys (van_day, mpg, overhead_pct, ...) plus one
-- ``pay:<class>`` row per pay class, whose ``label`` is the class's name.
-- A NULL amount is a deliberate removal in that season, so an older
-- season's value does not come back through inheritance.
--
-- Who is paid as which class lives in ll_app.install_pay_assignments, keyed
-- by the roster person id. It is deliberately NOT in the schedule state
-- document: that document is readable by the warehouse display and by crew
-- leads, and pay is admin-only.
--
-- App-owned, so it lives in ll_app. The install-costs API creates both
-- lazily with the identical DDL (backend/app/apis/install_costs/__init__.py).
--
-- 2026 values from Justice, 2026-09-29: 1099 installers paid hourly for the
-- whole shift (lunch, drive and loading paid; no overtime, burden, night
-- extra or minimum). One van ($225/day) and one trailer ($125/day) per crew
-- every time they go out. Gas at 10 mpg and $4/gal against the route miles.
-- $20 a crew-day for the things that just come up.
--
-- Overhead 19.4%: Brooke's projected Sep 29 - Dec 31 operating expenses
-- ($149,409) less the crew and van costs now charged to jobs (fall 2025
-- pattern: contract labor $54,175, gas $4,611, auto other $1,862, routine
-- repairs $3,442 = $64,090) leaves $85,319, over $439,103 of projected
-- collections. Target profit 16%: Brooke's base case (100% - 50% job costs
-- - 34% overhead).

CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.install_cost_rates (
    season      text        NOT NULL,
    key         text        NOT NULL,
    amount      numeric(10,4),
    label       text,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, key)
);

CREATE TABLE IF NOT EXISTS ll_app.install_pay_assignments (
    person_id     text        PRIMARY KEY,
    person_name   text,
    pay_class     text,
    rate_override numeric(10,2),
    updated_by    text,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO ll_app.install_cost_rates (season, key, amount, label, updated_by) VALUES
    ('2026', 'pay:lead',              18.00, 'Lead',              'migration 019'),
    ('2026', 'pay:lead_assist',       17.00, 'Lead Assist',       'migration 019'),
    ('2026', 'pay:general',           15.00, 'General Installer', 'migration 019'),
    ('2026', 'pay:junior',            12.00, 'Junior Installer',  'migration 019'),
    ('2026', 'pay:designer',          16.50, 'Designer',          'migration 019'),
    ('2026', 'van_day',              225,    NULL,                'migration 019'),
    ('2026', 'trailer_day',          125,    NULL,                'migration 019'),
    ('2026', 'vans_per_crew',          1,    NULL,                'migration 019'),
    ('2026', 'trailers_per_crew',      1,    NULL,                'migration 019'),
    ('2026', 'mpg',                   10,    NULL,                'migration 019'),
    ('2026', 'gas_per_gallon',         4,    NULL,                'migration 019'),
    ('2026', 'ancillary_day',         20,    NULL,                'migration 019'),
    ('2026', 'load_min_per_box',       2,    NULL,                'migration 019'),
    ('2026', 'overhead_pct',          19.4,  NULL,                'migration 019'),
    ('2026', 'target_profit_pct',     16,    NULL,                'migration 019')
ON CONFLICT (season, key) DO NOTHING;
