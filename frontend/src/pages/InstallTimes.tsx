import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  Camera,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Loader2,
  Moon,
  TrendingUp,
  Users,
} from "components/icons";
import { toast } from "sonner";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import {
  SOURCE_LABEL,
  TYPE_LABEL,
  diffLabel,
  fmtClock,
  fmtDuration,
  fmtHours,
  isLiveDay,
  longDate,
  nowClockCT,
  onSiteMinutes,
  parseClock,
  parseLeave,
  shortDate,
  stampCT,
  who,
} from "utils/installTimes";
import type { Actual, CrewGroup, DayResponse, Stop } from "utils/installTimes";

// Install Times: how long each stop really took, so next year's estimates
// are right. Pick a date, see that day's stops by crew in board order, type
// Arrive and Leave ("10:15p", "1:30a"), and it saves as you go. Office staff
// see every crew and the Reports tab; leads see only their own crew-days
// (the server decides: backend app/apis/install_actuals).

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(path, init);
  if (!r.ok) {
    let detail: unknown = r.statusText;
    try {
      detail = (await r.json())?.detail || detail;
    } catch {
      /* no body */
    }
    const err = new Error(typeof detail === "string" ? detail : (detail as { message?: string })?.message || "Request failed");
    (err as Error & { status?: number; detail?: unknown }).status = r.status;
    (err as Error & { status?: number; detail?: unknown }).detail = detail;
    throw err;
  }
  return r.json();
}

const inputBase =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-base text-stone-900 placeholder:text-stone-400 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-600/20";

// ─── page ────────────────────────────────────────────────────────────────────

export default function InstallTimes() {
  const [tab, setTab] = useState<"enter" | "reports">("enter");
  const [office, setOffice] = useState(false);

  return (
    <Layout>
      <div className="mx-auto w-full max-w-3xl px-4 pb-24 pt-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Install Times</h1>
            <p className="text-xs text-stone-500">How long each stop really took, so next year's hours are right.</p>
          </div>
          {office && (
            <div role="tablist" aria-label="Install Times views" className="flex rounded-lg border border-stone-200 bg-white p-0.5 text-sm">
              {(["enter", "reports"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={tab === t}
                  onClick={() => setTab(t)}
                  className={`min-h-10 rounded-md px-4 font-semibold transition-colors ${
                    tab === t ? "bg-emerald-700 text-white" : "text-stone-600 hover:bg-stone-100"
                  }`}
                >
                  {t === "enter" ? "Enter times" : "Reports"}
                </button>
              ))}
            </div>
          )}
        </div>
        <div hidden={tab !== "enter"}>
          <EnterTimes onRole={setOffice} />
        </div>
        {office && tab === "reports" && <Reports />}
      </div>
    </Layout>
  );
}

// ─── enter ───────────────────────────────────────────────────────────────────

function EnterTimes({ onRole }: { onRole: (office: boolean) => void }) {
  const [data, setData] = useState<DayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (on: string | null) => {
    setLoading(true);
    try {
      const d = await call<DayResponse>(`/api/install-times/day${on ? `?date=${on}` : ""}`);
      setData(d);
      setDate(d.date);
      setError(null);
      onRole(d.office);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [onRole]);

  useEffect(() => {
    void load(null);
  }, [load]);

  const dates = data?.dates ?? [];
  const idx = date ? dates.indexOf(date) : -1;
  const prev = idx > 0 ? dates[idx - 1] : idx === -1 && date ? [...dates].reverse().find((d) => d < date) : undefined;
  const next = idx >= 0 && idx < dates.length - 1 ? dates[idx + 1] : idx === -1 && date ? dates.find((d) => d > date) : undefined;
  const totals = useMemo(() => {
    const stops = (data?.crews ?? []).flatMap((c) => c.stops);
    return { all: stops.length, done: stops.filter((s) => s.actual?.actualHours != null).length };
  }, [data]);
  // Keep the day's counts in step with what each stop saves.
  const onSaved = useCallback((dayId: string, row: number, actual: Actual | null) => {
    setData((d) =>
      d && {
        ...d,
        crews: d.crews.map((c) =>
          c.dayId !== dayId ? c : { ...c, stops: c.stops.map((s) => (s.row === row ? { ...s, actual } : s)) },
        ),
      },
    );
  }, []);

  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => prev && void load(prev)}
          disabled={!prev || loading}
          aria-label="Previous install day"
          className="flex h-10 w-10 flex-none items-center justify-center rounded-lg border border-stone-300 bg-white text-stone-700 disabled:opacity-40"
        >
          <ChevronLeft size={18} />
        </button>
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Install day</span>
          <input
            type="date"
            value={date ?? ""}
            onChange={(e) => e.target.value && void load(e.target.value)}
            className={`${inputBase} h-10 py-0`}
          />
        </label>
        <button
          type="button"
          onClick={() => next && void load(next)}
          disabled={!next || loading}
          aria-label="Next install day"
          className="flex h-10 w-10 flex-none items-center justify-center rounded-lg border border-stone-300 bg-white text-stone-700 disabled:opacity-40"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {error && !data && <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>}
      {!data && !error && (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin text-stone-400" />
        </div>
      )}

      {data && date && (
        <p className="mb-3 flex flex-wrap items-center gap-x-2 text-sm text-stone-600">
          <CalendarDays size={15} className="text-emerald-700" />
          <span className="font-semibold text-stone-800">{longDate(date)}</span>
          {totals.all > 0 && <MissingCount done={totals.done} all={totals.all} />}
          {loading && <Loader2 size={14} className="animate-spin text-stone-400" />}
        </p>
      )}

      {data && data.crews.length === 0 && (
        <div className="rounded-xl border border-stone-200 bg-white p-6 text-center text-sm text-stone-600">
          {data.office
            ? "No crews are scheduled on this date. Use the arrows to jump to an install day."
            : data.dates.length
              ? "None of your crews worked this date. Use the arrows to jump to your next one."
              : data.me
                ? "You aren't on any crew-days yet. The office staffs crews on the install schedule."
                : "Your email isn't on the install crew roster yet. Ask the office to add it."}
        </div>
      )}

      <div className="space-y-4">
        {data?.crews.map((c) => (
          <CrewCard key={`${data.date}|${c.dayId}`} crew={c} today={data.today} onSaved={onSaved} />
        ))}
      </div>
    </>
  );
}

/** "2 of 9 missing" in amber until every stop has both times, then a check. */
function MissingCount({ done, all, pill = false }: { done: number; all: number; pill?: boolean }) {
  const missing = all - done;
  const base = pill ? "rounded-full px-2.5 py-1 text-xs font-semibold" : "text-sm";
  if (!missing)
    return (
      <span className={`inline-flex items-center gap-1 ${base} ${pill ? "bg-emerald-50 text-emerald-800" : "font-semibold text-emerald-700"}`}>
        <Check size={13} strokeWidth={3} /> All {all} entered
      </span>
    );
  return (
    <span className={`${base} ${pill ? "bg-amber-50 text-amber-900" : "font-semibold text-amber-800"}`}>
      {missing} of {all} missing
    </span>
  );
}

function CrewCard({ crew, today, onSaved }: { crew: CrewGroup; today: string; onSaved: (dayId: string, row: number, a: Actual | null) => void }) {
  const done = crew.stops.filter((s) => s.actual?.actualHours != null).length;
  const future = crew.date > today;
  const live = !future && isLiveDay(crew.date, today, crew.night);
  return (
    <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-stone-900">{crew.label}</h2>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-stone-500">
            {crew.lead && <span>Lead: {crew.lead}</span>}
            {crew.headcount != null && (
              <span className="inline-flex items-center gap-1">
                · <Users size={12} /> {crew.headcount}
              </span>
            )}
            {crew.night && (
              <span className="inline-flex items-center gap-1">
                · <Moon size={12} /> Night shift
              </span>
            )}
            {crew.kind === "takedown" && <span>· Takedown</span>}
          </p>
        </div>
        <MissingCount done={done} all={crew.stops.length} pill />
      </header>
      {future && (
        <p className="mx-4 mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
          This crew-day hasn't happened yet. Times open up on the day.
        </p>
      )}
      <ol className="divide-y divide-stone-100">
        {crew.stops.map((s, i) => (
          <StopRow key={s.row} index={i + 1} stop={s} crew={crew} disabled={future} live={live} onSaved={onSaved} />
        ))}
      </ol>
    </section>
  );
}

type SaveState = { status: "idle" | "saving" | "saved" | "error"; message?: string };

interface Draft {
  arrive: string;
  depart: string;
  people: string;
  photos: boolean;
  note: string;
}

function draftOf(a: Actual | null, headcount: number | null): Draft {
  return {
    arrive: a?.arrive ?? "",
    depart: a?.depart ?? "",
    people: a?.peopleCount != null ? String(a.peopleCount) : headcount != null ? String(headcount) : "",
    photos: Boolean(a?.photosDone),
    note: a?.scopeNote ?? "",
  };
}

/** Both typed times as minutes (Leave read against the Arrive). Throws on junk. */
function readTimes(d: Draft, night: boolean): [number | null, number | null] {
  const arrive = parseClock(d.arrive, night);
  return [arrive, parseLeave(d.depart, arrive, night)];
}

function sameAsSaved(d: Draft, a: Actual | null, night: boolean): boolean {
  if (!a) return !d.arrive.trim() && !d.depart.trim() && !d.note.trim() && !d.photos;
  let times: [string, string];
  try {
    const [am, dm] = readTimes(d, night);
    times = [fmtClock(am), fmtClock(dm)];
  } catch {
    times = [d.arrive, d.depart];
  }
  return (
    times[0] === a.arrive &&
    times[1] === a.depart &&
    (d.people.trim() === "" ? null : Number(d.people)) === a.peopleCount &&
    d.photos === Boolean(a.photosDone) &&
    d.note.trim() === (a.scopeNote || "")
  );
}

function StopRow(props: {
  index: number;
  stop: Stop;
  crew: CrewGroup;
  disabled: boolean;
  live: boolean;
  onSaved: (dayId: string, row: number, a: Actual | null) => void;
}) {
  const { index, stop, crew, disabled, live, onSaved } = props;
  const [actual, setActual] = useState<Actual | null>(stop.actual);
  const [draft, setDraft] = useState<Draft>(() => draftOf(stop.actual, crew.headcount));
  const [save, setSave] = useState<SaveState>({ status: "idle" });
  const [showHistory, setShowHistory] = useState(false);
  const [showNote, setShowNote] = useState(Boolean(stop.actual?.scopeNote));
  const inFlight = useRef(false);
  const queued = useRef(false);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const actualRef = useRef(actual);
  actualRef.current = actual;

  const parsed = (s: string) => {
    try {
      return { min: parseClock(s, crew.night), err: null as string | null };
    } catch (e) {
      return { min: null, err: (e as Error).message };
    }
  };
  const a = parsed(draft.arrive);
  let d: { min: number | null; err: string | null };
  try {
    d = { min: parseLeave(draft.depart, a.min, crew.night), err: null };
  } catch (e) {
    d = { min: null, err: (e as Error).message };
  }
  const mins = onSiteMinutes(a.min, d.min);
  const hours = mins == null ? null : mins / 60;
  // The server counts real hours (the DST night); prefer its number once saved.
  const shownHours = actual && sameAsSaved(draft, actual, crew.night) ? actual.actualHours : hours;
  const diff = diffLabel(stop.estHours, shownHours);

  const doSave = useCallback(async () => {
    const cur = draftRef.current;
    if (sameAsSaved(cur, actualRef.current, crew.night)) return;
    try {
      readTimes(cur, crew.night);
    } catch (e) {
      setSave({ status: "error", message: (e as Error).message });
      return;
    }
    if (inFlight.current) {
      queued.current = true;
      return;
    }
    inFlight.current = true;
    setSave({ status: "saving" });
    try {
      const out = await call<{ actual: Actual; warnings: string[] }>("/api/install-times/actuals", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          dayId: crew.dayId,
          row: stop.row,
          kind: crew.kind,
          arrive: cur.arrive,
          depart: cur.depart,
          peopleCount: cur.people.trim() === "" ? null : Math.max(0, Math.min(40, Math.round(Number(cur.people)) || 0)),
          photosDone: cur.photos,
          scopeNote: cur.note,
          supersedesId: actualRef.current?.id ?? null,
        }),
      });
      setActual(out.actual);
      actualRef.current = out.actual;
      onSaved(crew.dayId, stop.row, out.actual);
      // Show the times as the server read them ("10:15p" -> "10:15 PM").
      setDraft((dr) => ({ ...dr, arrive: out.actual.arrive, depart: out.actual.depart }));
      setSave({ status: "saved", message: out.warnings[0] });
    } catch (e) {
      const err = e as Error & { status?: number; detail?: { current?: Actual | null } };
      if (err.status === 409 && err.detail && typeof err.detail === "object" && "current" in err.detail) {
        const current = err.detail.current ?? null;
        setActual(current);
        actualRef.current = current;
        onSaved(crew.dayId, stop.row, current);
        setDraft(draftOf(current, crew.headcount));
        draftRef.current = draftOf(current, crew.headcount);
        toast.warning(`${stop.name}: someone else just saved this stop. Their times are shown now.`);
        setSave({ status: "idle" });
      } else {
        setSave({ status: "error", message: err.message });
      }
    } finally {
      inFlight.current = false;
      if (queued.current) {
        queued.current = false;
        void doSave();
      }
    }
  }, [crew.dayId, crew.headcount, crew.kind, crew.night, stop.name, stop.row, onSaved]);

  const set = (patch: Partial<Draft>) => setDraft((x) => ({ ...x, ...patch }));
  // Buttons and checkboxes save right away: on iPhone a tap doesn't focus
  // them, so the "save when you leave the stop" rule would never fire.
  const setAndSave = (patch: Partial<Draft>) => {
    draftRef.current = { ...draftRef.current, ...patch };
    setDraft(draftRef.current);
    void doSave();
  };
  const stampNow = (field: "arrive" | "depart") => setAndSave({ [field]: fmtClock(nowClockCT()) });
  // Save when focus leaves the whole stop (not each box), so typing Arrive
  // then Leave is one saved version, not two.
  const rowBlur = (e: React.FocusEvent<HTMLLIElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) void doSave();
  };

  return (
    <li className="px-4 py-3" onBlur={rowBlur}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-stone-900">
            <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-[11px] font-bold text-emerald-800">
              {index}
            </span>
            {stop.name}
          </p>
          <p className="mt-0.5 text-xs text-stone-500">
            {stop.city && <>{stop.city} · </>}
            {stop.estHours != null ? `Estimate ${fmtHours(stop.estHours)}` : "No estimate"}
          </p>
        </div>
        <SavedBadge state={save} />
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_88px_auto]">
        <TimeField
          label="Arrive"
          value={draft.arrive}
          placeholder={crew.night ? "10:15" : "8:30"}
          error={a.err}
          preview={a.min != null ? fmtClock(a.min) : ""}
          disabled={disabled}
          onNow={live ? () => stampNow("arrive") : undefined}
          onChange={(v) => set({ arrive: v })}
        />
        <TimeField
          label="Leave"
          value={draft.depart}
          placeholder={crew.night ? "1:30" : "2:15"}
          error={d.err}
          preview={d.min != null ? fmtClock(d.min) + (a.min != null && d.min <= a.min ? " next day" : "") : ""}
          disabled={disabled}
          onNow={live ? () => stampNow("depart") : undefined}
          onChange={(v) => set({ depart: v })}
        />
        <label className="block">
          <span className="mb-0.5 block text-[11px] font-semibold uppercase tracking-wide text-stone-500">People</span>
          <input
            inputMode="numeric"
            value={draft.people}
            disabled={disabled}
            onChange={(e) => set({ people: e.target.value.replace(/[^\d]/g, "").slice(0, 2) })}
              className={inputBase}
          />
        </label>
        <label className="flex min-h-10 items-center gap-2 self-end rounded-lg px-1 pb-2 text-sm text-stone-700 sm:pb-2.5">
          <input
            type="checkbox"
            checked={draft.photos}
            disabled={disabled}
            onChange={(e) => setAndSave({ photos: e.target.checked })}
            className="h-5 w-5 rounded border-stone-300 accent-emerald-700"
          />
          <Camera size={15} className="text-stone-400" /> Photos done
        </label>
      </div>

      {(showNote || draft.note) ? (
        <label className="mt-2 block">
          <span className="mb-0.5 block text-[11px] font-semibold uppercase tracking-wide text-stone-500">Notes</span>
          <textarea
            rows={2}
            value={draft.note}
            disabled={disabled}
            maxLength={2000}
            placeholder="What changed: added a tree, front door only, came back to finish"
            onChange={(e) => set({ note: e.target.value })}
              className={`${inputBase} resize-y`}
          />
        </label>
      ) : (
        !disabled && (
          <button type="button" onClick={() => setShowNote(true)} className="mt-1 min-h-10 text-xs font-semibold text-emerald-700 hover:underline">
            + Add a note
          </button>
        )
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {hours != null || shownHours != null ? (
          <span className="inline-flex items-center gap-1 font-semibold text-stone-800">
            <Clock size={13} className="text-stone-400" /> On site {fmtDuration(shownHours)}
          </span>
        ) : (
          <span className="text-stone-400">On site: not entered</span>
        )}
        {diff && (
          <span
            className={
              diff.tone === "over" ? "font-semibold text-red-700" : diff.tone === "under" ? "font-semibold text-emerald-700" : "text-stone-500"
            }
          >
            {diff.text}
          </span>
        )}
      </div>

      {actual && (
        <p className="mt-1 text-[11px] text-stone-500">
          Entered by {who(actual.enteredBy)} ({SOURCE_LABEL[actual.source] || actual.source}), {stampCT(actual.createdAt)}
          {actual.corrections > 0 && (
            <>
              {" · "}
              <button type="button" onClick={() => setShowHistory((v) => !v)} className="inline-flex items-center gap-0.5 font-semibold text-emerald-700 hover:underline">
                {actual.corrections} earlier version{actual.corrections === 1 ? "" : "s"}
                {showHistory ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </button>
            </>
          )}
        </p>
      )}
      {showHistory && actual && <History dayId={crew.dayId} row={stop.row} kind={crew.kind} latestId={actual.id} />}
    </li>
  );
}

function TimeField(props: {
  label: string;
  value: string;
  placeholder: string;
  error: string | null;
  preview: string;
  disabled: boolean;
  onNow?: () => void;
  onChange: (v: string) => void;
}) {
  const { label, value, placeholder, error, preview, disabled, onNow, onChange } = props;
  const nextDay = preview.endsWith(" next day");
  const typedSame = value.trim().toUpperCase() === preview.replace(" next day", "");
  // Show how the time was read ("2:05 PM") while it differs from what's typed;
  // "next day" stays up even once the box reads "1:30 AM".
  const hint = !value.trim() || !preview ? "" : !typedSame ? preview : nextDay ? "next day" : "";
  const id = useId();
  return (
    // With a Now button each time gets the full phone width, so "10:59 AM" fits.
    <div className={onNow ? "col-span-2 sm:col-span-1" : ""}>
      <label htmlFor={id} className="mb-0.5 block text-[11px] font-semibold uppercase tracking-wide text-stone-500">
        {label}
      </label>
      <div className="flex gap-1.5">
        <input
          id={id}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          enterKeyHint="done"
          aria-invalid={Boolean(error)}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
          className={`${inputBase} min-w-0 ${error ? "border-red-400" : ""}`}
        />
        {onNow && (
          <button
            type="button"
            onClick={onNow}
            disabled={disabled}
            // Out of the Tab order: typing Arrive, Tab, Leave stays one motion.
            tabIndex={-1}
            aria-label={`${label} now`}
            title={`Set ${label} to the time right now`}
            className="flex min-h-10 w-14 flex-none items-center justify-center rounded-lg border border-emerald-600 bg-emerald-50 text-sm font-semibold text-emerald-800 hover:bg-emerald-100 disabled:opacity-40"
          >
            Now
          </button>
        )}
      </div>
      {error ? (
        <span className="mt-0.5 block text-[11px] text-red-700">{error}</span>
      ) : hint ? (
        <span className="mt-0.5 block text-[11px] text-stone-500">{hint}</span>
      ) : null}
    </div>
  );
}

function SavedBadge({ state }: { state: SaveState }) {
  if (state.status === "saving")
    return (
      <span className="inline-flex flex-none items-center gap-1 text-[11px] text-stone-500">
        <Loader2 size={12} className="animate-spin" /> Saving
      </span>
    );
  if (state.status === "saved")
    return (
      <span className="inline-flex max-w-[50%] flex-none items-center gap-1 text-right text-[11px] font-semibold text-emerald-700" title={state.message}>
        {state.message ? <AlertTriangle size={12} className="text-amber-600" /> : <Check size={12} strokeWidth={3} />}
        {state.message ? <span className="font-normal text-amber-800">{state.message}</span> : "Saved"}
      </span>
    );
  if (state.status === "error")
    return (
      <span className="inline-flex max-w-[55%] flex-none items-center gap-1 text-right text-[11px] text-red-700">
        <AlertTriangle size={12} /> {state.message || "Not saved"}
      </span>
    );
  return null;
}

function History({ dayId, row, kind, latestId }: { dayId: string; row: number; kind: string; latestId: number }) {
  const [versions, setVersions] = useState<Actual[] | null>(null);
  useEffect(() => {
    call<{ versions: Actual[] }>(`/api/install-times/visit?dayId=${encodeURIComponent(dayId)}&row=${row}&kind=${kind}`)
      .then((d) => setVersions(d.versions))
      .catch(() => setVersions([]));
  }, [dayId, row, kind, latestId]);
  if (!versions) return <Loader2 size={14} className="mt-1 animate-spin text-stone-400" />;
  return (
    <ul className="mt-1.5 space-y-1 rounded-lg bg-stone-50 p-2 text-[11px] text-stone-600">
      {versions.map((v) => (
        <li key={v.id} className={v.id === latestId ? "font-semibold text-stone-800" : ""}>
          {v.arrive || "?"} to {v.depart || "?"}
          {v.peopleCount != null ? `, ${v.peopleCount} people` : ""} · {who(v.enteredBy)}, {stampCT(v.createdAt)}
          {v.id === latestId ? " (current)" : ""}
        </li>
      ))}
    </ul>
  );
}

// ─── reports (office only) ───────────────────────────────────────────────────

interface Rollup {
  visits: number;
  compared: number;
  missing: number;
  estHours: number | null;
  actualHours: number | null;
  avgActualHours: number | null;
  diffHours: number | null;
  diffPct: number | null;
}
interface SeasonCell {
  estHours: number | null;
  actualHours: number | null;
  visits: number;
  missing: number;
}
interface ReportsResponse {
  season: string;
  seasons: string[];
  rows: Actual[];
  byLead: (Rollup & { crewLead: string })[];
  byType: (Rollup & { type: string })[];
  byClient: { clientId: number | null; clientName: string; seasons: Record<string, SeasonCell> }[];
}

const NOT_ENTERED = <span className="whitespace-nowrap italic text-stone-400">not entered</span>;

function DiffCell({ hours, pct }: { hours: number | null | undefined; pct: number | null | undefined }) {
  if (hours == null) return NOT_ENTERED;
  const tone = Math.abs(hours) < 0.09 ? "text-stone-500" : hours > 0 ? "text-red-700" : "text-emerald-700";
  return (
    <span className={`whitespace-nowrap font-semibold ${tone}`}>
      {hours > 0 ? "+" : ""}
      {fmtHours(hours)}
      {pct != null && <span className="ml-1 font-normal">({pct > 0 ? "+" : ""}{Math.round(pct)}%)</span>}
    </span>
  );
}

function H({ h }: { h: number | null | undefined }) {
  return h == null ? NOT_ENTERED : <span className="whitespace-nowrap">{fmtHours(h)}</span>;
}

function Reports() {
  const [season, setSeason] = useState<string | null>(null);
  const [data, setData] = useState<ReportsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    call<ReportsResponse>(`/api/install-times/reports${season ? `?season=${season}` : ""}`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  }, [season]);

  if (error) return <p className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>;
  if (!data)
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="animate-spin text-stone-400" />
      </div>
    );

  const yoySeasons = Array.from(new Set(["2024", "2025", ...data.seasons])).sort();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-stone-600" htmlFor="it-season">
          Season
        </label>
        <select
          id="it-season"
          value={data.season}
          onChange={(e) => setSeason(e.target.value)}
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-base sm:text-sm"
        >
          {data.seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <p className="text-xs text-stone-500">Totals count only stops with both an estimate and real times.</p>
      </div>

      <ReportSection title="By type" icon={<TrendingUp size={15} />}>
        <RollupTable rows={data.byType.map((r) => ({ key: r.type, label: TYPE_LABEL[r.type] || r.type, r }))} />
      </ReportSection>

      <ReportSection title="By crew lead" icon={<Users size={15} />}>
        {data.byLead.length ? (
          <RollupTable rows={data.byLead.map((r) => ({ key: r.crewLead, label: r.crewLead, r }))} />
        ) : (
          <p className="p-4 text-sm text-stone-500">No crew leads on entered stops yet.</p>
        )}
      </ReportSection>

      <ReportSection title={`Every stop, ${data.season}`} icon={<Clock size={15} />}>
        {data.rows.length === 0 ? (
          <p className="p-4 text-sm text-stone-500">No times entered for {data.season} yet.</p>
        ) : (
          <>
            <table className="hidden w-full text-sm sm:table">
              <thead className="text-left text-[11px] uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-4 py-2 font-semibold">Date</th>
                  <th className="px-2 py-2 font-semibold">Stop</th>
                  <th className="px-2 py-2 font-semibold">Crew</th>
                  <th className="px-2 py-2 text-right font-semibold">Estimate</th>
                  <th className="px-2 py-2 text-right font-semibold">Actual</th>
                  <th className="px-4 py-2 text-right font-semibold">Difference</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {data.rows.map((r) => (
                  <tr key={r.id}>
                    <td className="whitespace-nowrap px-4 py-2 text-stone-600">
                      {shortDate(r.date)}
                      {r.kind === "takedown" ? " (TD)" : ""}
                    </td>
                    <td className="px-2 py-2 text-stone-900">{r.clientName}</td>
                    <td className="px-2 py-2 text-xs text-stone-600">{r.crewLead || r.crewLabel || ""}</td>
                    <td className="px-2 py-2 text-right">
                      <H h={r.estHours} />
                    </td>
                    <td className="px-2 py-2 text-right">
                      <H h={r.actualHours} />
                    </td>
                    <td className="px-4 py-2 text-right">
                      <DiffCell hours={r.diffHours} pct={r.diffPct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y divide-stone-100 sm:hidden">
              {data.rows.map((r) => (
                <li key={r.id} className="px-4 py-2.5 text-sm">
                  <p className="font-semibold text-stone-900">{r.clientName}</p>
                  <p className="text-xs text-stone-500">
                    {shortDate(r.date)}
                    {r.kind === "takedown" ? " takedown" : ""}
                    {r.crewLead ? ` · ${r.crewLead}` : ""}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-stone-700">
                    <span>
                      Est <H h={r.estHours} />
                    </span>
                    <span>
                      Actual <H h={r.actualHours} />
                    </span>
                    <DiffCell hours={r.diffHours} pct={r.diffPct} />
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </ReportSection>

      <ReportSection title="Clients year over year (install, actual vs estimate)" icon={<CalendarDays size={15} />}>
        {data.byClient.length === 0 ? (
          <p className="p-4 text-sm text-stone-500">No client times yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-4 py-2 font-semibold">Client</th>
                  {yoySeasons.map((s) => (
                    <th key={s} className="px-2 py-2 text-right font-semibold">
                      {s}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {data.byClient.map((c) => (
                  <tr key={`${c.clientId ?? c.clientName}`}>
                    <td className="px-4 py-2 text-stone-900">{c.clientName}</td>
                    {yoySeasons.map((s) => {
                      const cell = c.seasons[s];
                      return (
                        <td key={s} className="whitespace-nowrap px-2 py-2 text-right text-stone-700">
                          {!cell || cell.actualHours == null ? (
                            NOT_ENTERED
                          ) : (
                            <>
                              <span className="font-semibold">{fmtHours(cell.actualHours)}</span>
                              <span className="ml-1 text-xs text-stone-500">
                                {cell.estHours != null ? `est ${fmtHours(cell.estHours)}` : "no est"}
                              </span>
                            </>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ReportSection>
    </div>
  );
}

function ReportSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
      <h2 className="flex items-center gap-1.5 border-b border-stone-100 px-4 py-2.5 text-sm font-semibold text-stone-900">
        <span className="text-emerald-700">{icon}</span> {title}
      </h2>
      {children}
    </section>
  );
}

function RollupTable({ rows }: { rows: { key: string; label: string; r: Rollup }[] }) {
  return (
    <ul className="divide-y divide-stone-100">
      {rows.map(({ key, label, r }) => (
        <li key={key} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 px-4 py-2.5 text-sm sm:grid-cols-[minmax(0,180px)_1fr_170px_140px]">
          <span className="font-semibold text-stone-900">{label}</span>
          <span className="text-right sm:order-last">
            <DiffCell hours={r.diffHours} pct={r.diffPct} />
          </span>
          <span className="text-xs text-stone-500 sm:text-sm sm:text-stone-700">
            {r.compared ? <>Est <H h={r.estHours} /> · Actual <H h={r.actualHours} /></> : <span className="italic text-stone-400">No stops with both times yet</span>}
          </span>
          <span className="text-right text-xs text-stone-500 sm:text-left">
            {r.compared} of {r.visits} stop{r.visits === 1 ? "" : "s"}
            {r.missing ? `, ${r.missing} not entered` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
