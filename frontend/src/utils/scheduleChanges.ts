/**
 * The Install Schedule "Changes" list (Comment #19, user 2026-10-12): what
 * changed on the board, in plain words, newest first, grouped by day, with a
 * per-user "follow" that marks what's new since they last looked.
 *
 * The server does the work (backend app/apis/schedule_changes). These are the
 * pure helpers the page and the menu badge share, kept DOM-free for tests.
 */

export const CHANGES_PATH = "/install-changes";
/** Fired after "Mark all seen" / follow changes so the menu badge refreshes. */
export const CHANGES_SEEN_EVENT = "leaf-ledger-schedule-changes-seen";

export type ChangeType = "moves" | "adds" | "holds" | "approvals" | "staffing" | "locks" | "dates";

export interface ChangeEvent {
  id: string;
  kind: string;
  type: ChangeType;
  text: string;
  clients: string[];
  dates: string[];
  /** Central-time day the change was made (YYYY-MM-DD). */
  day: string;
  /** 12-hour Central time, e.g. "4:02 PM". */
  time: string;
  at: string;
  by: string;
  isNew: boolean;
  mine: boolean;
}

export interface ChangesPage {
  events: ChangeEvent[];
  next: string | null;
  total: number;
  following: boolean;
  lastSeenAt: string | null;
  unseen: number;
  newest: string | null;
}

export interface ChangeStatus {
  following: boolean;
  unseen: number;
}

export const TYPE_FILTERS: ReadonlyArray<{ type: ChangeType; label: string }> = [
  { type: "moves", label: "Moves" },
  { type: "adds", label: "Adds & removals" },
  { type: "holds", label: "Holds" },
  { type: "approvals", label: "Approvals" },
  { type: "staffing", label: "Staffing" },
  { type: "locks", label: "Locks" },
  { type: "dates", label: "Dates & crews" },
];

export interface ChangeFilters {
  q: string;
  from: string;
  to: string;
  types: ChangeType[];
}

export const EMPTY_FILTERS: ChangeFilters = { q: "", from: "", to: "", types: [] };

export function hasFilters(f: ChangeFilters): boolean {
  return Boolean(f.q.trim() || f.from || f.to || f.types.length);
}

/** The feed's query string for a page of results. */
export function changesQuery(f: ChangeFilters, before?: string | null, limit = 50): string {
  const p = new URLSearchParams();
  p.set("limit", String(limit));
  if (before) p.set("before", before);
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.from) p.set("from", f.from);
  if (f.to) p.set("to", f.to);
  if (f.types.length) p.set("type", f.types.join(","));
  return p.toString();
}

export function toggleType(types: ChangeType[], t: ChangeType): ChangeType[] {
  return types.includes(t) ? types.filter((x) => x !== t) : [...types, t];
}

/** Today's date in Central time, YYYY-MM-DD. */
export function centralToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}

/** "Today", "Yesterday", or "Mon 10/12" (with the year when it isn't this one). */
export function dayHeading(day: string, today: string = centralToday()): string {
  if (day === today) return "Today";
  if (day === addDays(today, -1)) return "Yesterday";
  const [y, m, d] = day.split("-").map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  const year = y === Number(today.slice(0, 4)) ? "" : `/${y}`;
  return `${dow} ${m}/${d}${year}`;
}

export interface DayGroup {
  day: string;
  heading: string;
  events: ChangeEvent[];
  newCount: number;
}

/** Newest-first events into day groups, keeping their order. */
export function groupByDay(events: ChangeEvent[], today: string = centralToday()): DayGroup[] {
  const out: DayGroup[] = [];
  for (const e of events) {
    let g = out[out.length - 1];
    if (!g || g.day !== e.day) {
      g = { day: e.day, heading: dayHeading(e.day, today), events: [], newCount: 0 };
      out.push(g);
    }
    g.events.push(e);
    if (e.isNew) g.newCount += 1;
  }
  return out;
}

/** Joins a further page onto what's shown, dropping any repeats. */
export function mergePages(shown: ChangeEvent[], more: ChangeEvent[]): ChangeEvent[] {
  const seen = new Set(shown.map((e) => e.id));
  return [...shown, ...more.filter((e) => !seen.has(e.id))];
}

/** The menu badge's text: nothing at zero, "99+" past 99. */
export function badgeText(unseen: number): string {
  if (!unseen || unseen < 1) return "";
  return unseen > 99 ? "99+" : String(unseen);
}

/** Short type label for an event's tag. */
export function typeLabel(t: ChangeType): string {
  return TYPE_FILTERS.find((f) => f.type === t)?.label ?? t;
}
