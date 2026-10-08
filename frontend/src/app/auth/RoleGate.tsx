import type * as React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { DISPLAY_HOME, FIELD_HOME, pageAllowed, useMe } from "utils/me";
import { isInstallPath } from "utils/installViews";
import { useUserGuardContext } from "./UserGuard";

/**
 * Sits inside <UserGuard>: waits for the account's role, then keeps field
 * logins (leads, crew) on the lead pages. Every API call is checked on the
 * server too -- this only stops a lead landing on a page that would fail.
 */
export const RoleGate = ({ children }: { children: React.ReactNode }) => {
  const { user } = useUserGuardContext();
  const { me, error, retry } = useMe(user.id);
  const location = useLocation();

  if (!me) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#f7f6f2] px-4">
        {error ? (
          <div className="flex max-w-sm flex-col items-center gap-3 text-center">
            <p className="text-sm text-[#1f3d2b]">{error}</p>
            <button
              type="button"
              onClick={retry}
              className="rounded-lg bg-[#1f3d2b] px-4 py-2 text-sm font-semibold text-white"
            >
              Try again
            </button>
          </div>
        ) : (
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#1f3d2b] border-t-transparent" />
        )}
      </div>
    );
  }

  // Restricted logins (production): only their pages; anything else -- the
  // Dashboard at "/" included -- goes to their home page.
  if (me.pages && !pageAllowed(me, location.pathname)) {
    return <Navigate to={me.home || me.pages[0] || "/login"} replace />;
  }
  // The display login keeps the whole schedule: its four views are four
  // routes now (Days, Calendar, Staffing, Roster), as they were four tabs.
  if (me.viewOnly && !isInstallPath(location.pathname)) {
    return <Navigate to={DISPLAY_HOME} replace />;
  }
  // Installers and leads can fill out a form (the product request form is
  // filled in the field, on a phone) -- the form page only, never responses.
  const onFormPage = /^\/forms\/[^/]+\/?$/.test(location.pathname);
  if (me.fieldOnly && location.pathname !== FIELD_HOME && !onFormPage) {
    return <Navigate to={FIELD_HOME} replace />;
  }

  return <>{children}</>;
};
