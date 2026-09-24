import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Clock,
  Loader2,
  MapPin,
  MessageSquarePlus,
  Navigation,
  Phone,
  Play,
  Square,
  Trash2,
  Users,
} from "components/icons";
import { toast } from "sonner";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import {
  addressLine,
  atTime,
  clock,
  formatMinutes,
  hhmm,
  longDate,
  minutesOf,
  nextStopRow,
  stopStatus,
} from "utils/shifts";
import type { Day, Note, ShiftsResponse, Stop, TimeEntry } from "utils/shifts";

// A crew lead's day on a phone: their shifts only (the server decides which --
// backend app/apis/lead), stops in route order, tap an address for directions,
// start/stop each person's clock at each property, and leave notes or client
// requests that land on the client's record. Office staff open the same page
// to see every crew-day and what leads recorded.

const JSON_HEADERS = { "content-type": "application/json" };

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json())?.detail || detail;
    } catch {}
    throw new Error(detail || "Request failed");
  }
  return r.json();
}
const send = <T,>(method: string, path: string, body?: unknown) =>
  call<T>(path, { method, headers: JSON_HEADERS, body: body === undefined ? undefined : JSON.stringify(body) });

// ─── page ────────────────────────────────────────────────────────────────────

export default function Shifts() {
  const [data, setData] = useState<ShiftsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [leadFilter, setLeadFilter] = useState("");
  const [openDay, setOpenDay] = useState<string | null>(null);
  const [showPast, setShowPast] = useState(false);
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    try {
      const q = leadFilter ? `?person_id=${encodeURIComponent(leadFilter)}` : "";
      const d = await call<ShiftsResponse>(`/api/lead/shifts${q}`);
      setData(d);
      setError(null);
      setOpenDay((cur) => cur ?? d.days.find((x) => x.date === d.today)?.id ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [leadFilter]);

  useEffect(() => {
    load();
  }, [load]);

  // Running clocks tick, and another phone's changes show up without a reload.
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30000);
    const r = window.setInterval(() => load(), 60000);
    return () => {
      window.clearInterval(t);
      window.clearInterval(r);
    };
  }, [load]);

  const groups = useMemo(() => {
    const days = data?.days ?? [];
    const today = data?.today ?? "";
    return {
      today: days.filter((d) => d.date === today),
      upcoming: days.filter((d) => d.date > today),
      past: days.filter((d) => d.date < today).reverse(),
    };
  }, [data]);

  const title = data?.supervisor ? "Crew Shifts" : "My Shifts";

  return (
    <Layout>
      <div className="mx-auto w-full max-w-2xl px-4 pb-16 pt-4">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">{title}</h1>
            {data && <p className="text-xs text-stone-500">{data.season} install season</p>}
          </div>
          {data?.supervisor && (
            <select
              value={leadFilter}
              onChange={(e) => {
                setLeadFilter(e.target.value);
                setOpenDay(null);
              }}
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
              aria-label="Show shifts for"
            >
              <option value="">All crews</option>
              {data.leads.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {error && !data && <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>}
        {!data && !error && (
          <div className="flex justify-center py-16">
            <Loader2 className="animate-spin text-stone-400" />
          </div>
        )}

        {data && data.days.length === 0 && (
          <div className="rounded-xl border border-stone-200 bg-white p-6 text-center text-sm text-stone-600">
            {data.supervisor
              ? "No crew-days on the schedule yet."
              : data.me
                ? "You aren't the Lead on any shifts yet. The office assigns leads in the install schedule."
                : "Your email isn't on the install crew roster yet. Ask the office to add it to your roster entry."}
          </div>
        )}

        {data && (
          <>
            <Section label="Today" days={groups.today} empty={data.days.length ? "No shift today." : null} {...{ data, openDay, setOpenDay, now, reload: load }} />
            <Section label="Upcoming" days={groups.upcoming} empty={null} {...{ data, openDay, setOpenDay, now, reload: load }} />
            {groups.past.length > 0 && (
              <div className="mt-6">
                <button
                  type="button"
                  onClick={() => setShowPast((v) => !v)}
                  className="flex items-center gap-1 text-sm font-semibold text-stone-600"
                >
                  {showPast ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Past shifts ({groups.past.length})
                </button>
                {showPast && <Section label="" days={groups.past} empty={null} {...{ data, openDay, setOpenDay, now, reload: load }} />}
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}

interface SectionProps {
  label: string;
  days: Day[];
  empty: string | null;
  data: ShiftsResponse;
  openDay: string | null;
  setOpenDay: (id: string | null) => void;
  now: number;
  reload: () => Promise<void>;
}

function Section({ label, days, empty, data, openDay, setOpenDay, now, reload }: SectionProps) {
  if (!days.length && !empty) return null;
  return (
    <section className="mt-5">
      {label && <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-stone-500">{label}</h2>}
      {!days.length && <p className="text-sm text-stone-500">{empty}</p>}
      <div className="space-y-3">
        {days.map((d) => (
          <DayCard
            key={d.id}
            day={d}
            data={data}
            open={openDay === d.id}
            onToggle={() => setOpenDay(openDay === d.id ? null : d.id)}
            now={now}
            reload={reload}
          />
        ))}
      </div>
    </section>
  );
}

function DayCard({ day, data, open, onToggle, now, reload }: {
  day: Day;
  data: ShiftsResponse;
  open: boolean;
  onToggle: () => void;
  now: number;
  reload: () => Promise<void>;
}) {
  const isToday = day.date === data.today;
  const canRecord = isToday || data.supervisor;
  const next = nextStopRow(day);
  const nextStop = day.stops.find((s) => s.row === next);
  const done = day.stops.filter((s) => stopStatus(s) === "done").length;
  const total = day.stops.reduce((m, s) => m + s.timeEntries.reduce((a, e) => a + minutesOf(e, now), 0), 0);

  return (
    <div className={`overflow-hidden rounded-xl border bg-white ${isToday ? "border-emerald-600" : "border-stone-200"}`}>
      <button type="button" onClick={onToggle} className="flex w-full items-start justify-between gap-3 p-4 text-left">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-stone-900">
            <CalendarDays size={15} className="text-emerald-700" /> {longDate(day.date)}
          </p>
          <p className="mt-0.5 text-xs text-stone-500">
            {day.crewLabel}
            {data.supervisor && day.lead ? ` · Lead: ${day.lead.name}` : ""} · {day.stops.length} stop{day.stops.length === 1 ? "" : "s"}
            {done ? ` · ${done} done` : ""}
            {total ? ` · ${formatMinutes(total)} logged` : ""}
          </p>
        </div>
        {open ? <ChevronDown size={18} className="mt-0.5 shrink-0 text-stone-400" /> : <ChevronRight size={18} className="mt-0.5 shrink-0 text-stone-400" />}
      </button>

      {isToday && nextStop && nextStop.mapsUrl && (
        <a
          href={nextStop.mapsUrl}
          target="_blank"
          rel="noreferrer"
          className="mx-4 mb-4 flex items-center justify-between gap-3 rounded-lg bg-emerald-700 px-4 py-3 text-white"
        >
          <span className="min-w-0">
            <span className="block text-[11px] font-semibold uppercase tracking-wide text-white/75">
              {stopStatus(nextStop) === "active" ? "At now" : "Next stop"}
            </span>
            <span className="block truncate text-sm font-semibold">{nextStop.name}</span>
            <span className="block truncate text-xs text-white/85">{addressLine(nextStop)}</span>
          </span>
          <Navigation size={20} className="shrink-0" />
        </a>
      )}

      {open && (
        <div className="border-t border-stone-100 px-4 pb-4">
          {day.note && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">{day.note}</p>}
          <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-stone-600">
            <Users size={14} className="text-stone-400" />
            {day.crew.map((p) => (
              <span key={p.id} className="rounded-full bg-stone-100 px-2 py-0.5">
                {p.name}
                {p.title === "Lead" ? " (Lead)" : ""}
              </span>
            ))}
          </p>
          <ol className="mt-3 space-y-3">
            {day.stops.map((s, i) => (
              <StopCard
                key={s.row}
                index={i + 1}
                stop={s}
                day={day}
                isNext={isToday && s.row === next}
                canRecord={canRecord}
                supervisor={data.supervisor}
                now={now}
                reload={reload}
              />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function StopCard({ index, stop, day, isNext, canRecord, supervisor, now, reload }: {
  index: number;
  stop: Stop;
  day: Day;
  isNext: boolean;
  canRecord: boolean;
  supervisor: boolean;
  now: number;
  reload: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const status = stopStatus(stop);
  const open = (pid: string) => stop.timeEntries.find((e) => e.personId === pid && !e.endedAt);
  const onClock = day.crew.filter((p) => open(p.id));
  const offClock = day.crew.filter((p) => !open(p.id));

  const act = async (kind: "start" | "stop", personIds: string[]) => {
    if (!personIds.length) return;
    setBusy(true);
    try {
      await send("POST", `/api/lead/time/${kind}`, { dayId: day.id, row: stop.row, personIds });
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const badge =
    status === "active" ? "bg-emerald-100 text-emerald-800" : status === "done" ? "bg-stone-200 text-stone-700" : "bg-white text-stone-500 border border-stone-200";

  return (
    <li className={`rounded-lg border p-3 ${isNext ? "border-emerald-500 bg-emerald-50/40" : "border-stone-200"}`}>
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${badge}`}>{index}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-stone-900">{stop.name}</p>
          {stop.mapsUrl ? (
            <a href={stop.mapsUrl} target="_blank" rel="noreferrer" className="mt-0.5 flex items-start gap-1 text-sm text-emerald-800 underline decoration-emerald-300 underline-offset-2">
              <MapPin size={14} className="mt-0.5 shrink-0" /> {addressLine(stop)}
            </a>
          ) : (
            <p className="mt-0.5 text-sm text-stone-500">{addressLine(stop) || "No address on file"}</p>
          )}
          {stop.phone && (
            <a href={`tel:${stop.phone}`} className="mt-1 flex items-center gap-1 text-xs text-stone-600">
              <Phone size={12} /> {stop.phone}
            </a>
          )}
          {(stop.advice || stop.repairNotes) && (
            <div className="mt-2 space-y-1 text-xs text-stone-600">
              {stop.advice && <p>{stop.advice}</p>}
              {stop.repairNotes && <p><span className="font-semibold">Production:</span> {stop.repairNotes}</p>}
            </div>
          )}
        </div>
      </div>

      {/* Time */}
      <div className="mt-3 rounded-lg bg-stone-50 p-2">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="flex items-center gap-1 text-xs font-semibold text-stone-700">
            <Clock size={13} /> Time
          </p>
          {canRecord && day.crew.length > 0 && (
            <div className="flex gap-2">
              {offClock.length > 0 && (
                <button type="button" disabled={busy} onClick={() => act("start", offClock.map((p) => p.id))} className="rounded-md bg-emerald-700 px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50">
                  Start all
                </button>
              )}
              {onClock.length > 0 && (
                <button type="button" disabled={busy} onClick={() => act("stop", onClock.map((p) => p.id))} className="rounded-md bg-stone-800 px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50">
                  Stop all
                </button>
              )}
            </div>
          )}
        </div>
        <ul className="divide-y divide-stone-200">
          {day.crew.map((p) => {
            const entries = stop.timeEntries.filter((e) => e.personId === p.id);
            const running = open(p.id);
            const mins = entries.reduce((a, e) => a + minutesOf(e, now), 0);
            return (
              <li key={p.id} className="py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-sm text-stone-800">{p.name}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className={`text-xs tabular-nums ${running ? "font-semibold text-emerald-700" : "text-stone-500"}`}>{mins ? formatMinutes(mins) : "—"}</span>
                    {canRecord &&
                      (running ? (
                        <button type="button" disabled={busy} onClick={() => act("stop", [p.id])} aria-label={`Stop ${p.name}`} className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-800 text-white disabled:opacity-50">
                          <Square size={14} />
                        </button>
                      ) : (
                        <button type="button" disabled={busy} onClick={() => act("start", [p.id])} aria-label={`Start ${p.name}`} className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-700 text-white disabled:opacity-50">
                          <Play size={14} />
                        </button>
                      ))}
                  </span>
                </div>
                {entries.map((e) => (
                  <EntryRow key={e.id} entry={e} date={day.date} editable={canRecord} reload={reload} />
                ))}
              </li>
            );
          })}
        </ul>
        {!canRecord && !supervisor && <p className="mt-1 text-[11px] text-stone-500">Time can be recorded on the day of the shift.</p>}
      </div>

      <Notes stop={stop} day={day} reload={reload} />
    </li>
  );
}

function EntryRow({ entry, date, editable, reload }: { entry: TimeEntry; date: string; editable: boolean; reload: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [start, setStart] = useState(hhmm(entry.startedAt));
  const [end, setEnd] = useState(entry.endedAt ? hhmm(entry.endedAt) : "");

  const save = async () => {
    try {
      await send("PATCH", `/api/lead/time/${entry.id}`, {
        startedAt: atTime(date, start),
        ...(end ? { endedAt: atTime(date, end) } : {}),
      });
      setEditing(false);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const remove = async () => {
    if (!window.confirm("Delete this time entry?")) return;
    try {
      await send("DELETE", `/api/lead/time/${entry.id}`);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (editing) {
    return (
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
        <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className="rounded border border-stone-300 px-1.5 py-1" aria-label="Start time" />
        <span>to</span>
        <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded border border-stone-300 px-1.5 py-1" aria-label="Stop time" />
        <button type="button" onClick={save} className="rounded bg-emerald-700 px-2 py-1 font-semibold text-white">Save</button>
        <button type="button" onClick={() => setEditing(false)} className="px-1 text-stone-500">Cancel</button>
        <button type="button" onClick={remove} aria-label="Delete entry" className="ml-auto text-red-600"><Trash2 size={14} /></button>
      </div>
    );
  }
  return (
    <button
      type="button"
      disabled={!editable}
      onClick={() => setEditing(true)}
      className="mt-0.5 block text-left text-[11px] text-stone-500 enabled:hover:text-stone-800"
    >
      {clock(entry.startedAt)} – {entry.endedAt ? clock(entry.endedAt) : "now"}
      {editable && <span className="ml-1 underline">edit</span>}
    </button>
  );
}

function Notes({ stop, day, reload }: { stop: Stop; day: Day; reload: () => Promise<void> }) {
  const [text, setText] = useState("");
  const [kind, setKind] = useState<Note["kind"]>("note");
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);

  const save = async () => {
    if (!text.trim()) return;
    setSaving(true);
    try {
      const n = await send<Note>("POST", "/api/lead/notes", { dayId: day.id, row: stop.row, kind, text });
      setText("");
      setOpen(false);
      toast.success(n.savedToClient ? "Saved to the client's record" : "Saved (no matching client record, so it stays on this shift)");
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  const remove = async (id: number) => {
    if (!window.confirm("Delete this note?")) return;
    try {
      await send("DELETE", `/api/lead/notes/${id}`);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="mt-3">
      {stop.notes.length > 0 && (
        <ul className="mb-2 space-y-1.5">
          {stop.notes.map((n) => (
            <li key={n.id} className={`rounded-lg p-2 text-xs ${n.kind === "client_request" ? "bg-sky-50 text-sky-900" : "bg-stone-50 text-stone-700"}`}>
              <div className="flex items-start justify-between gap-2">
                <p>
                  <span className="font-semibold">{n.kind === "client_request" ? "Client request: " : "Note: "}</span>
                  {n.text}
                </p>
                <button type="button" onClick={() => remove(n.id)} aria-label="Delete note" className="shrink-0 text-stone-400 hover:text-red-600">
                  <Trash2 size={13} />
                </button>
              </div>
              <p className="mt-0.5 text-[10px] opacity-70">
                {n.author} · {new Date(n.createdAt).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
              </p>
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <div className="space-y-2">
          <div className="flex gap-1 rounded-lg bg-stone-100 p-1 text-xs font-semibold">
            {(["note", "client_request"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`flex-1 rounded-md px-2 py-1.5 ${kind === k ? "bg-white text-stone-900 shadow-sm" : "text-stone-500"}`}
              >
                {k === "note" ? "What happened" : "Client wants something new"}
              </button>
            ))}
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder={kind === "note" ? "e.g. Replaced 2 strands on the porch rail" : "e.g. Wants a wreath on the garage next year"}
            className="w-full rounded-lg border border-stone-300 p-2 text-sm outline-none focus:border-emerald-600"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setOpen(false)} className="px-3 py-1.5 text-xs text-stone-500">Cancel</button>
            <button type="button" disabled={saving || !text.trim()} onClick={save} className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-1 text-xs font-semibold text-emerald-800">
          <MessageSquarePlus size={14} /> Add note or client request
        </button>
      )}
    </div>
  );
}
