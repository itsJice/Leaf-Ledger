// Types and pure helpers for the lead pages (pages/Shifts.tsx), kept free of
// imports so they can be unit-tested without the app shell.

export interface Person {
  id: string;
  name: string;
  title: string;
  phone: string;
}
export interface TimeEntry {
  id: number;
  row: number;
  personId: string;
  personName: string;
  startedAt: string;
  endedAt: string | null;
}
export interface Note {
  id: number;
  row: number;
  kind: "note" | "client_request";
  text: string;
  author: string | null;
  savedToClient: boolean;
  createdAt: string;
}
export interface Stop {
  row: number;
  name: string;
  street: string;
  city: string;
  st: string;
  zip: string;
  phone: string;
  mapsUrl: string;
  advice: string;
  repairNotes: string;
  hours: number | null;
  timeEntries: TimeEntry[];
  notes: Note[];
}
export interface Day {
  id: string;
  date: string;
  crewLabel: string;
  note: string;
  lead: Person | null;
  crew: Person[];
  stops: Stop[];
}
export interface ShiftsResponse {
  season: string;
  today: string;
  supervisor: boolean;
  me: Person | null;
  leads: Person[];
  days: Day[];
}

// ─── time helpers ────────────────────────────────────────────────────────────

export function minutesOf(e: TimeEntry, now: number): number {
  const end = e.endedAt ? new Date(e.endedAt).getTime() : now;
  return Math.max(0, (end - new Date(e.startedAt).getTime()) / 60000);
}

export function formatMinutes(min: number): string {
  const m = Math.round(min);
  const h = Math.floor(m / 60);
  return h ? `${h}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function hhmm(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** A time typed on the phone, on the shift's date, in the phone's timezone. */
export function atTime(date: string, time: string): string {
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  return new Date(y, mo - 1, d, h, mi).toISOString();
}

export function longDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
}

export type StopStatus = "todo" | "active" | "done";

export function stopStatus(stop: Stop): StopStatus {
  if (stop.timeEntries.some((e) => !e.endedAt)) return "active";
  return stop.timeEntries.length ? "done" : "todo";
}

/** Where the crew should be heading: the stop they're at, else the first one not started. */
export function nextStopRow(day: Day): number | null {
  const active = day.stops.find((s) => stopStatus(s) === "active");
  if (active) return active.row;
  return day.stops.find((s) => stopStatus(s) === "todo")?.row ?? null;
}

export function addressLine(s: Stop): string {
  return [s.street, s.city, [s.st, s.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
}
