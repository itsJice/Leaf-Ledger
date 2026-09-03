-- Tree counts: what was actually on a tree at install or teardown.
--
-- The ornament calculator's golden table is the designer's instinct written
-- down once. This is the calibration loop ("next time we take one down, take
-- note"): each row is one real tree's per-size ornament counts plus enhancer
-- count. The Tree Counts page averages rows at each golden height and shows
-- drift against the approved row; a designer copies an approved average back
-- into GOLDEN_RECIPES by hand. Nothing writes the table automatically.
--
-- App-owned, so it lives in ll_app (same as feedback / user_preferences /
-- install_schedule). The API creates this lazily on first use with the
-- identical DDL (backend/app/apis/tree_counts/__init__.py); it is kept here so
-- a rebuilt database gets it without a first request having to do it.
--
-- `counts` is a jsonb object of ornament size in inches (string key, e.g.
-- "4.75") -> pieces. Zero-count sizes are simply absent.

CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.tree_counts (
    id           bigserial PRIMARY KEY,
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    kind         text NOT NULL CHECK (kind IN ('install', 'teardown')),
    height_ft    numeric(5,2) NOT NULL,
    width_in     numeric(6,2) NOT NULL,
    profile      text,
    style        text,
    label        text,
    counts       jsonb NOT NULL DEFAULT '{}'::jsonb,
    enhancers    integer NOT NULL DEFAULT 0,
    notes        text,
    created_by   text,
    created_name text
);
CREATE INDEX IF NOT EXISTS tree_counts_recorded_idx
    ON ll_app.tree_counts (recorded_at DESC);
CREATE INDEX IF NOT EXISTS tree_counts_height_idx
    ON ll_app.tree_counts (height_ft);
