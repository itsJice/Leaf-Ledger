-- Give clients a real address, and a real cross-year history.
--
-- Two things converge here. First, the Christmas-install pipeline
-- (scheduler/) has its own client list -- names, addresses, phones, emails,
-- install history back to 2022 -- that has never touched this table. It's
-- being synced in (see scheduler/sync_clients.py) so a client's greenery
-- work and their Christmas install work live in one record instead of two
-- disconnected systems.
--
-- Second, that sync must not fight a human who edited a client's contact
-- info in the app: christmas_synced_snapshot remembers what the last sync
-- actually pushed for the mergeable fields (phone/email/street/city/state/
-- zip), so a later sync can tell "this field only differs because someone
-- hand-edited it here" apart from "the spreadsheet itself changed this
-- field" -- only the second case should overwrite. See sync_clients.py for
-- the compare.
--
-- Applied to Supabase on 2026-08-28. Kept here so any rebuilt database
-- gets it.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS street TEXT,
    ADD COLUMN IF NOT EXISTS city TEXT,
    ADD COLUMN IF NOT EXISTS state TEXT,
    ADD COLUMN IF NOT EXISTS zip TEXT,
    ADD COLUMN IF NOT EXISTS christmas_synced_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS christmas_synced_at TIMESTAMPTZ;

-- One row per (client, season): a client's activity feed, Christmas
-- install history today, room for other kinds (e.g. a logged project
-- milestone) without a new table later. Upserted on the season's unique
-- key, so re-running the sync updates a season's row instead of piling up
-- duplicates.
CREATE TABLE IF NOT EXISTS client_activity (
    id          BIGSERIAL PRIMARY KEY,
    client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    season      TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail      JSONB,
    occurred_at DATE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS client_activity_unique_season
    ON client_activity (client_id, kind, season);

CREATE INDEX IF NOT EXISTS client_activity_client_idx
    ON client_activity (client_id);
