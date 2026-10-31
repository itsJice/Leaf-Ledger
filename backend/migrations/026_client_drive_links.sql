-- A client's Google Drive folder, and the photos folder inside it, on the
-- client record (not per season: the folder stays the same year to year).
-- The Clients card and the Install Schedule stop popup show a "Drive folder"
-- button (and "Photos" when set); staff and up set them through
-- PUT /api/clients/{id}/drive-links, which only accepts
-- https://drive.google.com/ links (app.libs.drive_links). Bulk-filled by
-- backend/scripts/import_drive_folders.py. The app adds the columns itself
-- on first use (app.apis.clients.ensure_schema).
ALTER TABLE clients ADD COLUMN IF NOT EXISTS drive_folder_url text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS drive_photos_url text;
