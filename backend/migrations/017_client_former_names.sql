-- A client's name is used as a key in more places than the clients table:
-- arrangements.client_name, ll_app.jobs / product_requests / shift_notes /
-- shift_time_entries carry it as text, the spreadsheet sync matches on it,
-- and the scheduler page has the sheet's spelling baked in. Renaming a client
-- on the Clients tab used to change one row and silently orphan the rest.
--
-- PUT /clients/update now writes the new name through to every one of those
-- tables in the same transaction, and remembers what the client used to be
-- called:
--
--   former_names  every previous spelling, oldest first. The scheduler's
--                 client directory and the sync both match on these, so a
--                 name baked into a published page (or still on the sheet)
--                 keeps resolving to the renamed client.
--   sheet_name    the spreadsheet's own spelling as of the last sync. The
--                 sync matches on this first, so a rename in the app can
--                 never make the next sync create a duplicate under the old
--                 sheet name.
--
-- Applied to Supabase on 2026-09-25. Kept here so any rebuilt database gets it.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS former_names TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS sheet_name TEXT;

CREATE INDEX IF NOT EXISTS clients_sheet_name_idx ON clients (sheet_name);
