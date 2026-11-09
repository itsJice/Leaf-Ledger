// Install Times: the typed-time rules, the twin of backend
// app/libs/install_times.py (the server re-parses what is sent, so the two
// must agree; both are pinned to the same values in their tests).
//
// * Fast typing: "10:15p", "1:30a", "1030pm", "10:15 PM", "22:15", "10p",
//   "noon", "midnight".
// * No am/pm: a DAY shift reads 7..11 as morning and 12..6 as afternoon; a
//   NIGHT shift (Dallas) reads 6..11 as evening, 12 as midnight, 1..5 as early
//   morning. 24-hour times ("22:15", "0015", "09:30") are taken as written.
// * A Leave with no am/pm is the soonest such time after the Arrive
//   (10:59 AM to "2:05" is 2:05 PM; 10:15 PM to "1:30" is 1:30 AM).
// * A Leave earlier than (or equal to) the Arrive is the next day; on a night
//   shift an arrival before noon is the next morning.

export type Kind = "install" | "takedown";
export type JobType = "residential" | "commercial" | "restaurant";

export interface Actual {
  id: number;
  clientId: number | null;
  clientName: string;
  row: number | null;
  season: string;
  kind: Kind;
  date: string;
  dayId: string | null;
  crewLabel: string | null;
  crewLead: string | null;
  arriveAt: string | null;
  departAt: string | null;
  arrive: string;
  depart: string;
  actualHours: number | null;
  peopleCount: number | null;
  photosDone: boolean | null;
  scopeNote: string;
  estHours: number | null;
  jobType: JobType | null;
  night: boolean;
  source: string;
  enteredBy: string | null;
  createdAt: string;
  supersedesId: number | null;
  corrections: number;
  diffHours?: number | null;
  diffPct?: number | null;
}

export interface Stop {
  row: number;
  name: string;
  city: string;
  estHours: number | null;
  jobType: JobType | null;
  actual: Actual | null;
}

export interface CrewGroup {
  dayId: string;
  dayIds: string[];
  date: string;
  label: string;
  lead: string | null;
  night: boolean;
  kind: Kind;
  headcount: number | null;
  stops: Stop[];
}

export interface DayResponse {
  season: string;
  date: string | null;
  today: string;
  dates: string[];
  role: string;
  office: boolean;
  me: { id: string; name: string } | null;
  crews: CrewGroup[];
}

export class TimeParseError extends Error {}

const SUFFIX = /(a\.?m?\.?|p\.?m?\.?)$/;

/** Minutes after midnight (0..1439), or null for blank. Throws
 *  TimeParseError with a message safe to show. */
export function parseClock(text: string | null | undefined, night = false): number | null {
  return parse(text, night)[0];
}

/** A typed Leave time. With no am/pm ("2:05", "1:30") it is the soonest such
 *  time after the Arrive: 10:59 AM then "2:05" is 2:05 PM, 10:15 PM then
 *  "1:30" is 1:30 AM. Explicit am/pm and 24-hour times are taken as written. */
export function parseLeave(text: string | null | undefined, arriveMin: number | null, night = false): number | null {
  const [minutes, guessed] = parse(text, night);
  if (minutes == null || arriveMin == null || !guessed) return minutes;
  const after = (m: number) => ((((m - arriveMin) % 1440) + 1440) % 1440) || 1440;
  const other = (minutes + 720) % 1440;
  return after(other) < after(minutes) ? other : minutes;
}

/** [minutes, guessed]: guessed when am/pm came from the shift (1..12, no am/pm). */
function parse(text: string | null | undefined, night: boolean): [number | null, boolean] {
  let s = String(text ?? "").toLowerCase().replace(/\s+/g, "");
  if (!s) return [null, false];
  if (s === "noon" || s === "12n") return [12 * 60, false];
  if (s === "midnight" || s === "12m") return [0, false];
  const shown = String(text).trim();
  const bad = () => new TimeParseError(`Can't read "${shown}" as a time. Try 10:15p or 1:30a.`);
  let ap = "";
  const m = SUFFIX.exec(s);
  if (m) {
    ap = m[1][0];
    s = s.slice(0, m.index);
  }
  let hs: string;
  let ms: string;
  if (/^\d{1,2}[:.]\d{2}$/.test(s)) {
    [hs, ms] = s.split(/[:.]/);
  } else if (/^\d{1,4}$/.test(s)) {
    if (s.length <= 2) {
      hs = s;
      ms = "0";
    } else {
      hs = s.slice(0, -2);
      ms = s.slice(-2);
    }
  } else {
    throw bad();
  }
  let h = Number(hs);
  const mi = Number(ms);
  if (mi > 59) throw new TimeParseError(`"${shown}": minutes must be 00 to 59.`);
  if (ap) {
    if (h < 1 || h > 12) throw new TimeParseError(`"${shown}": with am/pm the hour must be 1 to 12.`);
    return [((h % 12) + (ap === "p" ? 12 : 0)) * 60 + mi, false];
  }
  if (h > 23) throw new TimeParseError(`"${shown}": the hour must be 0 to 23.`);
  if (h === 0 || h >= 13 || (hs.length === 2 && hs.startsWith("0"))) return [h * 60 + mi, false];
  if (night) {
    if (h >= 6 && h <= 11) h += 12;
    else if (h === 12) h = 0;
  } else if (h >= 1 && h <= 6) {
    h += 12;
  }
  return [h * 60 + mi, true];
}

/** Central wall-clock minutes now, for the Now buttons. */
export function nowClockCT(at: Date = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(at);
  const n = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return (n("hour") % 24) * 60 + n("minute");
}

/** Whether a crew-day is happening now (so Now buttons make sense): its own
 *  date, or the morning after for a night shift. */
export function isLiveDay(crewDate: string, today: string, night: boolean): boolean {
  if (crewDate === today) return true;
  if (!night) return false;
  const [y, m, d] = crewDate.split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
  return next === today;
}

/** 1335 -> "10:15 PM". */
export function fmtClock(minutes: number | null | undefined): string {
  if (minutes == null) return "";
  const t = ((Math.round(minutes) % 1440) + 1440) % 1440;
  const h = Math.floor(t / 60);
  const mi = t % 60;
  return `${h % 12 || 12}:${String(mi).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

/** Normalize typed text to "10:15 PM", or null for blank. Throws on junk. */
export function normalizeClock(text: string, night = false): string | null {
  const m = parseClock(text, night);
  return m == null ? null : fmtClock(m);
}

/** On-site minutes between two clock times, by the rollover rules:
 *  Leave at or before Arrive is the next day. Null if either is missing.
 *  (Wall-clock math: the DST night is fixed on the server, which counts
 *  real hours.) */
export function onSiteMinutes(arriveMin: number | null, departMin: number | null): number | null {
  if (arriveMin == null || departMin == null) return null;
  let d = departMin - arriveMin;
  if (d <= 0) d += 1440;
  return d;
}

/** "2 h 15 min", "45 min", "3 h". */
export function fmtDuration(hours: number | null | undefined): string {
  if (hours == null) return "";
  const total = Math.round(hours * 60);
  const h = Math.floor(Math.abs(total) / 60);
  const m = Math.abs(total) % 60;
  const sign = total < 0 ? "-" : "";
  if (!h) return `${sign}${m} min`;
  return m ? `${sign}${h} h ${m} min` : `${sign}${h} h`;
}

/** "1.5 h", "-0.25 h". */
export function fmtHours(h: number | null | undefined): string {
  if (h == null) return "";
  return `${Number(h.toFixed(2))} h`;
}

/** Actual minus estimate: "+30 min over", "15 min under", "on estimate". */
export function diffLabel(estHours: number | null, actualHours: number | null): { text: string; tone: "over" | "under" | "even" } | null {
  if (estHours == null || actualHours == null) return null;
  const mins = Math.round((actualHours - estHours) * 60);
  if (Math.abs(mins) < 5) return { text: "on estimate", tone: "even" };
  const pct = estHours ? ` (${mins > 0 ? "+" : ""}${Math.round(((actualHours - estHours) / estHours) * 100)}%)` : "";
  return mins > 0
    ? { text: `${fmtDuration(mins / 60)} over${pct}`, tone: "over" }
    : { text: `${fmtDuration(-mins / 60)} under${pct}`, tone: "under" };
}

/** "Mon 11/2" for a crew-day date. */
export function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${dt.toLocaleDateString("en-US", { weekday: "short" })} ${m}/${d}`;
}

/** "Mon, 11/02/2026". */
export function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${dt.toLocaleDateString("en-US", { weekday: "long" })}, ${String(m).padStart(2, "0")}/${String(d).padStart(2, "0")}/${y}`;
}

/** "11/8 at 4:02 PM" in Central time, for "entered by" lines. */
export function stampCT(iso: string | null | undefined): string {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  const date = dt.toLocaleDateString("en-US", { timeZone: "America/Chicago", month: "numeric", day: "numeric" });
  const time = dt.toLocaleTimeString("en-US", { timeZone: "America/Chicago", hour: "numeric", minute: "2-digit" });
  return `${date} at ${time} CT`;
}

/** The person part of an email, for "entered by" lines. */
export function who(email: string | null | undefined): string {
  if (!email) return "";
  return email.split("@")[0];
}

export const SOURCE_LABEL: Record<string, string> = {
  office: "office",
  lead: "crew lead",
  claude: "Claude, from a crew sheet",
  imported_sheet: "imported from the 2025 sheet",
  comment_parsed: "imported from a schedule note",
};

export const TYPE_LABEL: Record<string, string> = {
  residential: "Residential",
  commercial: "Commercial",
  restaurant: "Restaurant (M Crowd)",
  dallas_night: "Dallas night",
};
