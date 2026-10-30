/**
 * The Install Schedule's four screens, each its own entry in the main nav
 * (user, 2026-10-08): Days, Calendar, Staffing and Roster used to be a tab row
 * inside the schedule page itself.
 *
 * All four routes render ONE <InstallSchedule> (a pathless parent route in
 * user-routes.tsx), so switching between them never reloads or remounts the
 * schedule iframe: the host just tells the page which view to show
 * (postMessage `tbdg-view`). Pure helpers only, so tests can import this.
 */

/** The page's own names for its views (scheduler/review_template.html). */
export type InstallView = "days" | "cal" | "staff" | "roster";

export const INSTALL_VIEWS: ReadonlyArray<{ view: InstallView; path: string; label: string }> = [
  { view: "days", path: "/install-schedule", label: "Install Schedule" },
  { view: "cal", path: "/install-calendar", label: "Install Calendar" },
  { view: "staff", path: "/install-staffing", label: "Install Staffing" },
  { view: "roster", path: "/install-roster", label: "Install Roster" },
];

export const INSTALL_PATHS: string[] = INSTALL_VIEWS.map((v) => v.path);

function trimSlash(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
}

/** True on any of the four schedule routes. */
export function isInstallPath(pathname: string): boolean {
  return INSTALL_PATHS.includes(trimSlash(pathname));
}

/** Which view a route shows (Days for anything unknown). */
export function viewForPath(pathname: string): InstallView {
  const p = trimSlash(pathname);
  return INSTALL_VIEWS.find((v) => v.path === p)?.view ?? "days";
}

export function pathForView(view: string): string {
  return INSTALL_VIEWS.find((v) => v.view === view)?.path ?? INSTALL_VIEWS[0].path;
}

const LEGACY: Record<string, InstallView> = {
  days: "days",
  day: "days",
  schedule: "days",
  cal: "cal",
  calendar: "cal",
  staff: "staff",
  staffing: "staff",
  shifts: "staff",
  roster: "roster",
};

/**
 * A view picked by an old-style link: `/install-schedule?view=calendar`,
 * `?tab=roster` or `#staffing`. Null when the link doesn't name one, so a
 * plain bookmark keeps opening the Days view.
 */
export function legacyView(search: string, hash: string): InstallView | null {
  const q = new URLSearchParams(search);
  const raw = (q.get("view") || q.get("tab") || hash.replace(/^#/, "") || "").trim().toLowerCase();
  return LEGACY[raw] ?? null;
}

/**
 * Flags the tool reads at startup, before its first paint:
 *  - TBDG_HOSTED / TBDG_VIEW: it's inside the app, which now has the Days /
 *    Calendar / Staffing / Roster entries in its own nav, so the page hides
 *    its in-page tab row and opens on the view this route names.
 *  - TBDG_VIEWONLY / TBDG_DISPLAY: the warehouse display login gets view-only
 *    mode from the very first paint rather than after the token message
 *    arrives (the server refuses that login's saves either way).
 */
export function withHostFlags(html: string, view: InstallView, viewOnly: boolean, display: boolean): string {
  let js = `window.TBDG_HOSTED=true;window.TBDG_VIEW=${JSON.stringify(view)};`;
  // TBDG_DISPLAY: the warehouse TV login also opens in TV mode on the wall
  // calendar; a view-only office login (production) opens normally.
  if (viewOnly) js += `window.TBDG_VIEWONLY=true;window.TBDG_DISPLAY=${display};`;
  const flag = `<script>${js}</script>`;
  return html.includes("<head>") ? html.replace("<head>", `<head>${flag}`) : flag + html;
}

/** `?date=YYYY-MM-DD` on /install-schedule: the date to open (the home
 *  page's "stops have install notes" link). null when absent or malformed. */
export function dateFromSearch(search: string): string | null {
  const d = new URLSearchParams(search).get("date") || "";
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null;
}

/** Where the app's Teams buttons go: the Roster view with the Teams builder
 *  open (user, 2026-10-30: "the teams edit button should be on all the install
 *  related tabs"). The schedule's own views have a Teams button in their
 *  toolbar; the React install pages link here. */
export const TEAMS_PATH = "/install-roster?teams=1";

/** `?teams=1` on a schedule route: open the Teams builder once it's loaded. */
export function teamsFromSearch(search: string): boolean {
  const v = new URLSearchParams(search).get("teams");
  return v === "1" || v === "true";
}

/** Who gets a Teams button: people who can edit the schedule (staff and up,
 *  not a view-only login). Leads and crew only ever see their own shifts. */
export function canEditTeams(me: { role: string; viewOnly?: boolean } | null | undefined): boolean {
  if (!me || me.viewOnly) return false;
  return me.role === "staff" || me.role === "admin" || me.role === "super_admin";
}
