-- Move saved clients out of a JSON blob and into a real table.
--
-- Why: clients used to live in a single db.storage JSON document keyed by user.
-- That had two fatal problems for a hosted, multi-person app:
--   1. Every add/delete rewrote the WHOLE list, so two people editing at the
--      same moment silently clobbered each other (last write wins).
--   2. The file lived on local disk, which a host like Render wipes on every
--      restart and redeploy — the client list would just vanish.
--
-- Clients are TEAM-WIDE: no user_id column. `created_by` is attribution only.
-- The unique index on the normalised name enforces "no duplicate clients" in
-- the database itself, so concurrent creates produce one winner and a clean
-- error rather than a lost write.

CREATE TABLE IF NOT EXISTS clients (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    notes       TEXT,
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS clients_unique_name
    ON clients (LOWER(TRIM(name)));
