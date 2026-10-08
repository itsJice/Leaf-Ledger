-- A client's name as parts, so nobody has to type "Last, First" into one box.
--
--   client_type  'person' or 'business'
--   first_name   person only
--   last_name    person only
--   company      business only
--   site         business only, optional ("Nicklaus Clubhouse", "Daycare")
--
-- clients.name stays the canonical spelling that everything else matches on
-- (arrangements, jobs, requests, shifts, the sheet sync, the billing-export
-- loader, the Install Schedule page, search, former_names). It is composed
-- from the parts on every save:
--
--   person    "Last, First"
--   business  "Company | Site", or "Company" with no site
--
-- and a change that alters it goes through the rename-everywhere path
-- (PUT /clients/update, NAME_MIRRORS). All five columns are nullable: rows
-- without them derive the parts from name on the fly
-- (app.libs.client_names.name_parts). scripts/split_client_names.py proposes
-- a backfill (dry run by default; it never changes name).
--
-- The app adds these itself on first use (app.apis.clients.ensure_schema);
-- this file is the record, for any rebuilt database.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS client_type text CHECK (client_type IN ('person', 'business')),
    ADD COLUMN IF NOT EXISTS first_name text,
    ADD COLUMN IF NOT EXISTS last_name text,
    ADD COLUMN IF NOT EXISTS company text,
    ADD COLUMN IF NOT EXISTS site text;
