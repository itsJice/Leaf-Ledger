-- Let a login be a read-only `viewer` (the warehouse iPad on the shop TV).
--
-- ll_app.user_roles was created with an inline CHECK listing the roles. The
-- app re-states this constraint on boot (app/libs/roles.py), so this file is
-- the record, not a required step.

ALTER TABLE ll_app.user_roles DROP CONSTRAINT IF EXISTS user_roles_role_check;
ALTER TABLE ll_app.user_roles ADD CONSTRAINT user_roles_role_check
    CHECK (role IN ('crew','viewer','lead','staff','admin','super_admin'));
