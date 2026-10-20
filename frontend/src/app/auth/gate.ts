import { DISPLAY_HOME, FIELD_HOME, pageAllowed } from "utils/me";
import type { Me } from "utils/me";
import { isInstallPath } from "utils/installViews";
import { CHANGES_PATH } from "utils/scheduleChanges";
import { isHelpPath } from "utils/howto";

/**
 * Where RoleGate sends an account that may not open `path`, or null when it
 * may. Pure, so the rules are tested (app/auth/__tests__/gate.test.ts).
 * The server checks every API call on its own; this only keeps a login off a
 * page that would fail for it.
 */
export function gateRedirect(
  me: Pick<Me, "pages" | "home" | "viewOnly" | "fieldOnly">,
  path: string,
): string | null {
  // Restricted logins (production): only their pages; anything else -- the
  // Dashboard at "/" included -- goes to their home page. Help is in their
  // list (backend roles.PRODUCTION_PAGES).
  if (me.pages && !pageAllowed(me as Me, path)) {
    return me.home || me.pages[0] || "/login";
  }
  // The display login keeps the whole schedule: its four views are four
  // routes now (Days, Calendar, Staffing, Roster), as they were four tabs.
  // It may also read the Changes list (the server allows its GETs) and the
  // how-to videos.
  if (me.viewOnly && !isInstallPath(path) && path !== CHANGES_PATH && !isHelpPath(path)) {
    return DISPLAY_HOME;
  }
  // Installers and leads: their shifts, a form (the product request form is
  // filled in the field, on a phone -- the form page only, never responses)
  // and the how-to videos.
  const onFormPage = /^\/forms\/[^/]+\/?$/.test(path);
  if (me.fieldOnly && path !== FIELD_HOME && !onFormPage && !isHelpPath(path)) {
    return FIELD_HOME;
  }
  return null;
}
