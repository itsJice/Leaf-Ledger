-- Per-client install-time preference, and the per-season fields contract.
--
-- time_preference is the one thing here that needs a column: it is a fact
-- about the client ("the daycare has to be done before the kids arrive"),
-- not about a season, so it lives on `clients` next to the address. The
-- scheduling tool reads it off /clients/list and orders a crew's stops
-- morning -> flexible -> afternoon -> late (see scheduler/RULES.md).
--
-- Everything per-season (storing with us, on hold, boxes, fees, crew, real
-- hours, takedown, invoice total, notes) goes into the jsonb `detail` of
-- that season's client_activity row and needs no DDL. The keys and the
-- rules for which of them the spreadsheet sync may overwrite are in
-- backend/app/libs/client_season.py -- in short: a value edited in the app
-- is stamped in detail.app_edits and the sync leaves it alone.
--
-- Applied to Supabase on 2026-09-16. Kept here so any rebuilt database
-- gets it.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS time_preference TEXT;

-- A CHECK rather than an enum type: three values, and adding a fourth is
-- an ALTER on this constraint, not a type migration.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'clients_time_preference_check'
    ) THEN
        ALTER TABLE clients
            ADD CONSTRAINT clients_time_preference_check
            CHECK (time_preference IS NULL
                   OR time_preference IN ('morning', 'afternoon', 'late'));
    END IF;
END $$;
