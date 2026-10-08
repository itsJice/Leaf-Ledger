-- A client's name as parts, so nobody has to type "Last, First" into one box.
-- Every client card offers the same four boxes; fill whichever apply:
--
--   first_name   a person
--   last_name    a person
--   company      a business name
--   site         a location ("House", "Nicklaus Clubhouse", "Daycare")
--
-- clients.name stays the canonical spelling that everything else matches on
-- (arrangements, jobs, requests, shifts, the sheet sync, the billing-export
-- loader, the Install Schedule page, search, former_names). It is composed
-- from the parts on every save, in the styles the data already uses:
--
--   Last, First                         "Scheib, Nataliya"
--   Last, First - Location              "Byler, Kerri - House"
--   Business                            "Hilton Garden Inn"
--   Business | Location                 "The Club at Carlton Woods | Nicklaus Clubhouse"
--   Business | Last, First [- Location] "A Hug Away | Frazier, Marissa"
--
-- and a change that alters it goes through the rename-everywhere path
-- (PUT /clients/update, NAME_MIRRORS). All four columns are nullable: rows
-- without them derive the parts from name on the fly
-- (app.libs.client_names.name_parts). scripts/split_client_names.py proposes
-- a backfill (dry run by default; it never changes name).
--
-- The app adds these itself on first use (app.apis.clients.ensure_schema);
-- this file is the record, for any rebuilt database.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS first_name text,
    ADD COLUMN IF NOT EXISTS last_name text,
    ADD COLUMN IF NOT EXISTS company text,
    ADD COLUMN IF NOT EXISTS site text;
