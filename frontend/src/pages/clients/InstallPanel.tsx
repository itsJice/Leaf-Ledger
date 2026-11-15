import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowUpRight, Building2, CalendarDays, Clock, Lock, MapPinned, MessageSquare, Pencil, Plus, TreePine, Users,
} from "components/icons";
import { apiFetch } from "utils/apiFetch";
import { currentMe, isReadOnly } from "utils/me";

/**
 * The client page's "2026 Install" panel (Comments #23): everything Cynthia
 * needs before calling a client, at a glance, without opening the schedule.
 *
 *   1. The board date (the Install Schedule owns dates), with a green
 *      "Confirmed" badge and who confirmed it when, the crew, and a link to
 *      that day on the schedule. Confirming only happens there (the lock
 *      button), so this shows it and links to it.
 *   2. The preferred install time (clients.time_preference).
 *   3. Scheduling restrictions (clients.schedule_restrictions, free text) and
 *      whether the stop is a business or a residence, as the schedule sees it.
 *   4. The job's size: hours, crew size, crews and crew-days, plus "Whole day"
 *      and "Multi-crew", always worked out, never typed.
 *   5. The season's contact log: the last three calls, voicemails, texts,
 *      emails or visits, "See all", and "+ Log contact".
 *
 * Read from GET /api/clients/{id}/install-summary; contacts are appended with
 * POST /api/clients/{id}/seasons/{season}/contacts. Office staff and up only:
 * the server refuses everyone else, and this panel isn't drawn for them.
 * Nothing here is money.
 */

export type ContactMethod = "call" | "voicemail" | "text" | "email" | "in_person";

export const CONTACT_METHODS: Array<[ContactMethod, string]> = [
  ["call", "Call"],
  ["voicemail", "Voicemail"],
  ["text", "Text"],
  ["email", "Email"],
  ["in_person", "In person"],
];
const METHOD_LABEL = Object.fromEntries(CONTACT_METHODS) as Record<string, string>;

export interface ContactEntry {
  date: string;
  method: ContactMethod | string;
  note?: string | null;
  by?: string | null;
  at?: string | null;
}

export interface CrewDay {
  day_id: string;
  date: string;
  crew: string;
  crew_title: string;
  lead: string | null;
  staffed: number;
  stops: number;
}

export interface InstallSummary {
  client_id: number;
  season: string;
  board_available: boolean;
  on_board: boolean;
  board_date: string | null;
  board_dates: string[];
  card_date: string | null;
  date_mismatch: boolean;
  crews: CrewDay[];
  confirmed: boolean;
  confirmed_at: string | null;
  confirmed_by: string | null;
  hold: boolean;
  not_installing: boolean;
  visit_type: string | null;
  property_type: "Business" | "Residence" | null;
  time_preference: string | null;
  schedule_restrictions: string | null;
  size: {
    est_hours: number | null;
    hours_basis: string;
    crew_size: number | null;
    roles: Record<string, number>;
    crew_size_basis: string;
    crews: number;
    crew_days: number;
    days: number;
    whole_day: boolean;
    multi_crew: boolean;
  };
  contacts: ContactEntry[];
  contact_count: number;
  legacy_confirmation_notes: string | null;
}

const PANEL_ROLES = new Set(["staff", "admin", "super_admin"]);
export const RESTRICTIONS_MAX = 500;
const RECENT = 3;

/** Office staff and up. Viewer, production, leads and crew never see it. */
export function canSeeInstallPanel(): boolean {
  const me = currentMe();
  return Boolean(me && PANEL_ROLES.has(me.role) && !isReadOnly());
}

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2026-11-19" -> "Thu 11/19/2026". */
export function boardDateLabel(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return iso || "";
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return `${DOW[d.getDay()]} ${m[2]}/${m[3]}/${m[1]}`;
}

/** "2026-11-03" -> "11/03/2026". */
export function mdy(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[2]}/${m[3]}/${m[1]}` : iso || "";
}

/** An ISO timestamp as "Nov 3, 4:02 PM CT". */
export function whenCT(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago",
  }) + " CT";
}

const PREF_LABEL: Record<string, string> = { morning: "Early morning", afternoon: "Afternoon", late: "Late" };
const ROLE_LABEL: Record<string, string> = { leads: "lead", specialty: "specialty", designer: "designer", general: "general" };

function rolesLine(roles: Record<string, number>): string {
  return Object.entries(roles || {})
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${ROLE_LABEL[k] || k}${n === 1 || k === "general" || k === "specialty" ? "" : "s"}`)
    .join(", ");
}

/** Today in Central time, YYYY-MM-DD (the log's default date). */
export function todayCT(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
  return parts; // en-CA formats as YYYY-MM-DD
}

const LABEL = "mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400";
const CELL = "min-w-0 rounded-lg border border-stone-200 bg-stone-50/60 px-3 py-3";
const TAG = "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold";
const INPUT = "w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-base text-stone-800 outline-none focus:border-emerald-500 sm:text-sm";
const BTN = "inline-flex min-h-[40px] items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 text-xs font-semibold text-stone-700 hover:border-emerald-300 hover:text-emerald-700 sm:min-h-[32px]";
const GO = "inline-flex min-h-[40px] items-center justify-center rounded-lg px-4 text-xs font-semibold text-white disabled:opacity-50 sm:min-h-[32px]";

export interface ViewProps {
  summary: InstallSummary;
  editable?: boolean;
  onOpenSchedule?: (date: string) => void;
  onSaveRestrictions?: (text: string) => Promise<void>;
  onLogContact?: (entry: { method: ContactMethod; date: string; note: string }) => Promise<void>;
  /** Start with the contact form / full log open (tests, screenshots). */
  initialLogOpen?: boolean;
  initialShowAll?: boolean;
}

/** The panel itself, from a loaded summary. Pure apart from its own form state. */
export function InstallPanelView({
  summary: s, editable = false, onOpenSchedule, onSaveRestrictions, onLogContact,
  initialLogOpen = false, initialShowAll = false,
}: ViewProps) {
  const [editingRestrictions, setEditingRestrictions] = useState(false);
  const [restrictionsDraft, setRestrictionsDraft] = useState(s.schedule_restrictions || "");
  const [savingRestrictions, setSavingRestrictions] = useState(false);
  const [logOpen, setLogOpen] = useState(initialLogOpen);
  const [showAll, setShowAll] = useState(initialShowAll);
  const [method, setMethod] = useState<ContactMethod>("call");
  const [logDate, setLogDate] = useState(todayCT());
  const [note, setNote] = useState("");
  const [logging, setLogging] = useState(false);

  const pref = s.time_preference && PREF_LABEL[s.time_preference] ? PREF_LABEL[s.time_preference] : null;
  const contacts = showAll ? s.contacts : s.contacts.slice(0, RECENT);
  const firstCrew = s.crews[0];
  const size = s.size;
  const crewSummary = size.crew_days
    ? `${size.crews} crew${size.crews === 1 ? "" : "s"}${size.crew_days !== size.crews ? ` · ${size.crew_days} crew-days` : ""}${size.days > 1 ? ` over ${size.days} days` : ""}`
    : "";

  const saveRestrictions = async () => {
    if (!onSaveRestrictions) return;
    setSavingRestrictions(true);
    try {
      await onSaveRestrictions(restrictionsDraft.trim());
      setEditingRestrictions(false);
    } finally {
      setSavingRestrictions(false);
    }
  };
  const logContact = async () => {
    if (!onLogContact) return;
    setLogging(true);
    try {
      await onLogContact({ method, date: logDate, note: note.trim() });
      setNote("");
      setLogOpen(false);
    } finally {
      setLogging(false);
    }
  };

  return (
    <section className="mb-4 rounded-xl border border-stone-200 bg-white" aria-label={`${s.season} Install`} data-install-panel>
      <div className="flex flex-wrap items-center gap-2 border-b border-stone-100 px-4 py-3">
        <TreePine size={15} className="text-emerald-600" />
        <h3 className="text-sm font-semibold text-stone-800" style={{ fontFamily: "Sora, sans-serif" }}>{s.season} Install</h3>
        {s.hold && <span className={`${TAG} border-amber-200 bg-amber-50 text-amber-800`}>On hold</span>}
        {s.not_installing && <span className={`${TAG} border-stone-200 bg-stone-100 text-stone-600`}>Not installing</span>}
        {s.visit_type && <span className={`${TAG} border-stone-200 bg-stone-50 text-stone-600`}>{s.visit_type}</span>}
        {s.board_date && onOpenSchedule && (
          <a
            href={`/install-schedule?date=${s.board_date}`}
            onClick={(e) => { e.preventDefault(); onOpenSchedule(s.board_date as string); }}
            className="ml-auto inline-flex min-h-[40px] items-center gap-1 text-xs font-semibold text-emerald-700 hover:underline sm:min-h-0"
          >
            Open on schedule <ArrowUpRight size={13} />
          </a>
        )}
      </div>

      <div className="grid gap-3 p-3 sm:grid-cols-2 sm:p-4 xl:grid-cols-4">
        {/* 1. Install date */}
        <div className={CELL}>
          <p className={LABEL}>Install date</p>
          {s.on_board && s.board_date ? (
            <>
              <p className="flex flex-wrap items-center gap-2 text-lg font-semibold leading-tight text-stone-800">
                <CalendarDays size={16} className="text-stone-400" />
                {boardDateLabel(s.board_date)}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {s.confirmed ? (
                  <span className={`${TAG} border-emerald-200 bg-emerald-50 text-emerald-800`} data-confirmed>
                    <Lock size={11} /> Confirmed
                  </span>
                ) : (
                  <span className={`${TAG} border-stone-200 bg-white text-stone-500`}>Not confirmed yet</span>
                )}
              </div>
              {s.confirmed && (s.confirmed_by || s.confirmed_at) && (
                <p className="mt-1 text-[11px] text-stone-500">
                  {[s.confirmed_by ? `by ${s.confirmed_by}` : "", whenCT(s.confirmed_at)].filter(Boolean).join(", ")}
                </p>
              )}
              {firstCrew && (
                <p className="mt-1.5 text-xs text-stone-600">
                  {s.crews.map((c) => c.crew_title).join(" + ")}
                  {firstCrew.lead ? ` · Lead ${firstCrew.lead}` : ""}
                  {s.board_dates.length > 1 ? ` · also ${s.board_dates.slice(1).map(mdy).join(", ")}` : ""}
                </p>
              )}
              {s.date_mismatch && s.card_date && (
                <p className="mt-1 text-[11px] text-amber-700">Season card says {mdy(s.card_date)}. The schedule wins.</p>
              )}
            </>
          ) : (
            <>
              <p className="text-sm font-semibold text-stone-700">
                {s.card_date ? mdy(s.card_date) : "No date yet"}
              </p>
              <p className="mt-1 text-[11px] text-stone-500">
                {!s.board_available ? "Couldn't read the schedule" : s.card_date ? "From the season card, not on board" : "Not on the schedule"}
              </p>
            </>
          )}
        </div>

        {/* 2. Preferred time */}
        <div className={CELL}>
          <p className={LABEL}>Preferred time</p>
          {pref ? (
            <span className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-base font-semibold text-emerald-900" data-pref>
              <Clock size={16} /> {pref}
            </span>
          ) : (
            <p className="text-sm text-stone-500">No preference</p>
          )}
        </div>

        {/* 3. Restrictions + business / residence */}
        <div className={CELL}>
          <div className="flex items-center gap-2">
            <p className={`${LABEL} flex-1`}>Scheduling restrictions</p>
            {editable && !editingRestrictions && (
              <button
                type="button"
                onClick={() => { setRestrictionsDraft(s.schedule_restrictions || ""); setEditingRestrictions(true); }}
                className="-m-2 inline-flex min-h-[40px] items-center gap-1 p-2 text-[11px] font-semibold text-stone-500 hover:text-emerald-700 sm:min-h-0"
                aria-label="Edit scheduling restrictions"
              >
                <Pencil size={12} /> Edit
              </button>
            )}
          </div>
          {editingRestrictions ? (
            <div className="grid gap-2">
              <textarea
                rows={3}
                value={restrictionsDraft}
                maxLength={RESTRICTIONS_MAX}
                onChange={(e) => setRestrictionsDraft(e.target.value)}
                placeholder="e.g. No Fridays. Gate closes at 3 PM. Call before arriving."
                className={INPUT}
                aria-label="Scheduling restrictions"
              />
              <div className="flex gap-2">
                <button type="button" className={BTN} onClick={() => setEditingRestrictions(false)}>Cancel</button>
                <button type="button" className={GO} style={{ backgroundColor: "rgb(var(--ll-brand))" }} disabled={savingRestrictions} onClick={saveRestrictions}>
                  {savingRestrictions ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          ) : s.schedule_restrictions ? (
            <p className="whitespace-pre-wrap text-sm font-medium text-stone-800" data-restrictions>{s.schedule_restrictions}</p>
          ) : (
            <p className="text-sm text-stone-500">None</p>
          )}
          {s.property_type && (
            <span className={`${TAG} mt-2 border-stone-200 bg-white text-stone-600`} title="As the Install Schedule classifies this stop">
              {s.property_type === "Business" ? <Building2 size={11} /> : <MapPinned size={11} />}
              {s.property_type}
            </span>
          )}
        </div>

        {/* 4. Size */}
        <div className={CELL}>
          <p className={LABEL}>Size of the job</p>
          <p className="text-sm text-stone-800">
            {size.est_hours != null ? <><b className="text-base">{Number(size.est_hours.toFixed(2))}h</b> install</> : <span className="text-stone-500">Hours not set</span>}
          </p>
          {size.crew_size != null && (
            <p className="mt-1 flex items-center gap-1.5 text-xs text-stone-600">
              <Users size={12} className="text-stone-400" />
              {size.crew_size} {size.crew_size === 1 ? "person" : "people"}
              {rolesLine(size.roles) ? ` (${rolesLine(size.roles)})` : ""}
            </p>
          )}
          {crewSummary && <p className="mt-1 text-xs text-stone-600">{crewSummary}</p>}
          {(size.whole_day || size.multi_crew) && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {size.whole_day && <span className={`${TAG} border-emerald-200 bg-emerald-50 text-emerald-800`}>Whole day</span>}
              {size.multi_crew && <span className={`${TAG} border-amber-200 bg-amber-50 text-amber-800`}>Multi-crew</span>}
            </div>
          )}
        </div>
      </div>

      {/* 5. Contact log */}
      <div className="border-t border-stone-100 px-4 py-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <p className="flex flex-1 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
            <MessageSquare size={12} /> Contact log
          </p>
          {s.contact_count > RECENT && (
            <button type="button" className="min-h-[40px] text-xs font-semibold text-emerald-700 hover:underline sm:min-h-0" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `See all (${s.contact_count})`}
            </button>
          )}
          {editable && !logOpen && (
            <button type="button" className={BTN} onClick={() => { setLogDate(todayCT()); setLogOpen(true); }}>
              <Plus size={13} /> Log contact
            </button>
          )}
        </div>

        {logOpen && editable && (
          <div className="mb-3 grid gap-2 rounded-lg border border-stone-200 bg-stone-50/60 p-3" data-log-form>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="How you reached them">
              {CONTACT_METHODS.map(([v, l]) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={method === v}
                  onClick={() => setMethod(v)}
                  className={`min-h-[40px] rounded-lg border px-3 text-xs font-semibold sm:min-h-[32px] ${method === v
                    ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                    : "border-stone-200 bg-white text-stone-600 hover:border-stone-300"}`}
                >
                  {l}
                </button>
              ))}
            </div>
            <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
              <input type="date" value={logDate} max={todayCT()} onChange={(e) => setLogDate(e.target.value)} className={INPUT} aria-label="Date" />
              <input
                type="text"
                value={note}
                maxLength={1000}
                onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") logContact(); }}
                placeholder="What was said, e.g. confirmed 11/19, prefers morning"
                className={INPUT}
                aria-label="Note"
              />
            </div>
            <div className="flex gap-2">
              <button type="button" className={BTN} onClick={() => setLogOpen(false)}>Cancel</button>
              <button type="button" className={GO} style={{ backgroundColor: "rgb(var(--ll-brand))" }} disabled={logging} onClick={logContact}>
                {logging ? "Saving…" : "Save contact"}
              </button>
            </div>
          </div>
        )}

        {contacts.length === 0 && !s.legacy_confirmation_notes && (
          <p className="text-xs italic text-stone-400">No contacts logged yet.</p>
        )}
        {contacts.length > 0 && (
          <ul className="grid gap-1.5">
            {contacts.map((c, i) => (
              <li key={`${c.at || ""}-${i}`} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs">
                <span className="font-semibold text-stone-700">{mdy(c.date)}</span>
                <span className={`${TAG} border-stone-200 bg-stone-50 text-stone-600`}>{METHOD_LABEL[c.method] || c.method}</span>
                {c.note && <span className="min-w-0 flex-1 break-words text-stone-700">{c.note}</span>}
                {c.by && <span className="ml-auto text-[11px] text-stone-400">{c.by}</span>}
              </li>
            ))}
          </ul>
        )}
        {s.legacy_confirmation_notes && (
          <p className="mt-2 text-[11px] text-stone-500" data-legacy>
            <span className="font-semibold">Earlier confirmation note:</span> {s.legacy_confirmation_notes}
          </p>
        )}
      </div>
    </section>
  );
}

async function failure(res: Response, fallback: string): Promise<Error> {
  let why = fallback;
  try {
    const j = await res.json();
    if (j?.detail && typeof j.detail === "string") why = j.detail;
  } catch { /* no body */ }
  return new Error(why);
}

/** Loads the summary for one client and wires the two writes. */
export function InstallPanel({ clientId, onClientSaved }: {
  clientId: number;
  /** The client record after a restrictions save (PUT /clients/update returns it). */
  onClientSaved?: (saved: unknown) => void;
}) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<InstallSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visible = canSeeInstallPanel();

  useEffect(() => {
    if (!visible) return;
    let live = true;
    setError(null);
    apiFetch(`/api/clients/${clientId}/install-summary`)
      .then(async (r) => {
        if (!r.ok) throw await failure(r, `Couldn't load the install summary (${r.status})`);
        return r.json() as Promise<InstallSummary>;
      })
      .then((j) => { if (live) setSummary(j); })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [clientId, visible]);

  if (!visible) return null;
  if (error) return <p className="mb-4 rounded-xl border border-stone-200 bg-white px-4 py-3 text-xs text-stone-500">{error}</p>;
  if (!summary) {
    return <div className="mb-4 h-28 animate-pulse rounded-xl border border-stone-200 bg-white" aria-label="Loading the install summary" />;
  }

  const saveRestrictions = async (text: string) => {
    const r = await apiFetch(`/api/clients/update/${clientId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schedule_restrictions: text }),
    });
    if (!r.ok) {
      const err = await failure(r, "Couldn't save the restrictions");
      toast.error(err.message);
      throw err;
    }
    const saved = await r.json();
    setSummary((cur) => (cur ? { ...cur, schedule_restrictions: saved.schedule_restrictions ?? null } : cur));
    onClientSaved?.(saved);
    toast.success("Restrictions saved");
  };

  const logContact = async (entry: { method: ContactMethod; date: string; note: string }) => {
    const r = await apiFetch(`/api/clients/${clientId}/seasons/${encodeURIComponent(summary.season)}/contacts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    });
    if (!r.ok) {
      const err = await failure(r, "Couldn't log that contact");
      toast.error(err.message);
      throw err;
    }
    const out = (await r.json()) as { contacts: ContactEntry[] };
    setSummary((cur) => (cur ? { ...cur, contacts: out.contacts, contact_count: out.contacts.length } : cur));
    toast.success("Contact logged");
  };

  return (
    <InstallPanelView
      summary={summary}
      editable
      onOpenSchedule={(date) => navigate(`/install-schedule?date=${date}`)}
      onSaveRestrictions={saveRestrictions}
      onLogContact={logContact}
    />
  );
}
