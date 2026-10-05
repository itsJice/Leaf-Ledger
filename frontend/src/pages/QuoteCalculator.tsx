import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "components/Layout";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { currentMe } from "utils/me";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel } from "utils/season";

/**
 * Quote Calculator (admin only): what one job costs us to install and take
 * down, and what it should sell for at each profit level. All arithmetic is
 * server-side (backend app.libs.quote, POST /install-quote/calc) off the saved
 * install cost card, so a change in Settings > Install Costs moves every
 * number here. GET /install-quote/jobs lists the season's scheduled jobs so a
 * quote can start from a real one.
 */

type PayClass = { slug: string; label: string; rate: number | null };
type Trip = {
  trip: "install" | "takedown"; onsite_h: number; pretrip_min: number; drive_min_each_way: number;
  miles_round_trip: number; paid_h: number; day_share: number; crew_pay: number; van: number; trailer: number;
  insurance: number; ancillary: number; tolls: number; parking: number; day_share_cost: number;
  gas: number; wear: number; other: number; total: number;
};
type Level = {
  profit_pct: number; break_even: boolean; target: boolean; cost_share_pct: number; price_needed: number | null;
  max_job_cost?: number; headroom?: number; max_crew_hours?: number | null; max_materials?: number;
  max_designer_hours?: number | null;
};
type Out = {
  season: string; crew_rate: number; crew_size: number; takedown_time_factor: number;
  inputs: {
    install_onsite_h: number; takedown_onsite_h: number; takedown_auto: boolean; include_takedown: boolean;
    drive_min_each_way: number; miles_each_way: number; miles_auto: boolean; boxes: number; stored_with_us: boolean;
    designer_hours: number; materials: number; price: number | null;
  };
  trips: Trip[];
  designer: { hours: number; rate: number | null; cost: number };
  materials: number; crew_pay: number; other: number; crew_hours: number; job_cost: number;
  overhead_pct: number | null; target_profit_pct: number | null;
  price: number | null; overhead: number | null; profit: number | null; profit_pct: number | null;
  levels: Level[]; classes: PayClass[]; missing: string[];
};
type Job = {
  row: number; name: string;
  price: { total: number | null; install: number | null; takedown: number | null; storage: number | null; source: string };
  h26: number | null; boxes: number; size25: number | null; real25: number | null; stored_with_us: boolean;
  drive_min_each_way: number | null; miles_each_way: number | null;
  crew: Record<string, number>; crew_basis: string | null;
};

type Form = {
  price: string; crew: Record<string, string>; installH: string; takedownH: string; includeTakedown: boolean;
  driveMin: string; miles: string; boxes: string; stored: boolean; designerH: string; materials: string;
};

const START: Form = {
  price: "", crew: { lead: "1", general: "3" }, installH: "4", takedownH: "", includeTakedown: true,
  driveMin: "30", miles: "", boxes: "0", stored: true, designerH: "", materials: "",
};

const money0 = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
const hrs = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)} h`);
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`);

/** A typed number, or null for blank/invalid (negative counts as invalid). */
function num(s: string): number | null {
  const t = s.trim().replace(/[$,]/g, "");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

const s = (v: number | null | undefined) => (v == null ? "" : String(v));

async function errorOf(res: Response, fallback: string): Promise<string> {
  try {
    const j = await res.json();
    if (typeof j?.detail === "string") return j.detail;
    if (Array.isArray(j?.detail) && j.detail[0]?.msg) {
      const d = j.detail[0];
      const where = Array.isArray(d.loc) ? d.loc.filter((x: unknown) => x !== "body").join(" ") : "";
      return `${where ? `${where}: ` : ""}${d.msg}`;
    }
  } catch { /* no body */ }
  return fallback;
}

/** The price a job's quote covers: install + takedown (storage pays for the
 *  warehouse, which is overhead). Takedown is priced the same as install. */
function quotePrice(j: Job): number | null {
  const { install, takedown } = j.price;
  if (install == null && takedown == null) return null;
  return (install ?? takedown ?? 0) + (takedown ?? install ?? 0);
}

const MISSING_LABEL: Record<string, string> = {
  van_day: "van rental", trailer_day: "trailer rental", mpg: "fuel economy", gas_per_gallon: "gas price", gas: "gas",
  overhead_pct: "overhead %", target_profit_pct: "target profit %",
};
const missingLabel = (m: string) => (m.startsWith("pay:") ? `a ${m.slice(4).replace(/_/g, " ")} pay rate` : MISSING_LABEL[m] || m);

function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="text-xs font-medium text-stone-600">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-0.5 block text-[11px] leading-snug text-stone-400">{hint}</span>}
    </label>
  );
}

const inputCls = "w-full rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-sm tabular-nums text-stone-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500";

function NumInput({ value, onChange, placeholder, step = "any", prefix, suffix }: {
  value: string; onChange: (v: string) => void; placeholder?: string; step?: string; prefix?: string; suffix?: string;
}) {
  return (
    <div className="relative">
      {prefix && <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-stone-400">{prefix}</span>}
      <input type="number" inputMode="decimal" min={0} step={step} value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputCls} ${prefix ? "pl-6" : ""} ${suffix ? "pr-10" : ""}`} />
      {suffix && <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-stone-400">{suffix}</span>}
    </div>
  );
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)}
      className="flex min-h-[36px] items-center gap-2 text-xs text-stone-700 sm:min-h-0">
      <span className={`relative inline-block h-4 w-7 rounded-full transition-colors ${on ? "bg-emerald-600" : "bg-stone-300"}`}>
        <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all ${on ? "left-3.5" : "left-0.5"}`} />
      </span>
      {label}
    </button>
  );
}

function JobPicker({ jobs, loading, picked, onPick, onClear }: {
  jobs: Job[]; loading: boolean; picked: Job | null; onPick: (j: Job) => void; onClear: () => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (t ? jobs.filter((j) => j.name.toLowerCase().includes(t)) : jobs).slice(0, 60);
  }, [jobs, q]);
  return (
    <div className="relative">
      <input
        type="search" value={open ? q : picked?.name || q} placeholder={loading ? "Loading jobs…" : `Search ${jobs.length} scheduled jobs`}
        onFocus={() => { setOpen(true); setQ(""); }} onBlur={() => setOpen(false)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { onPick(hits[0]); setOpen(false); (e.target as HTMLInputElement).blur(); } }}
        className={inputCls} aria-label="Start from a scheduled job" />
      {open && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-stone-200 bg-white py-1 text-sm shadow-lg">
          {hits.map((j) => (
            <li key={j.row}>
              <button type="button" onMouseDown={(e) => { e.preventDefault(); onPick(j); setOpen(false); }}
                className="flex w-full items-baseline justify-between gap-2 px-3 py-1.5 text-left hover:bg-stone-50">
                <span className="truncate text-stone-800">{j.name}</span>
                <span className="shrink-0 text-xs tabular-nums text-stone-500">{hrs(j.h26)} · {money0(quotePrice(j))}</span>
              </button>
            </li>
          ))}
          {hits.length === 0 && <li className="px-3 py-2 text-xs text-stone-500">{loading ? "Loading…" : "No scheduled job by that name."}</li>}
        </ul>
      )}
      {picked && !open && (
        <button type="button" onClick={onClear} className="mt-1 text-[11px] font-semibold text-emerald-700 hover:underline">Clear the job</button>
      )}
    </div>
  );
}

export default function QuoteCalculator() {
  const isAdmin = !!currentMe()?.isAdmin;
  const [season, setSeason] = useState(currentSeasonLabel());
  const [form, setForm] = useState<Form>(START);
  const [classes, setClasses] = useState<PayClass[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [picked, setPicked] = useState<Job | null>(null);
  const [out, setOut] = useState<Out | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setCrew = (slug: string, v: string) => setForm((f) => ({ ...f, crew: { ...f.crew, [slug]: v } }));

  useEffect(() => {
    if (!isAdmin) return;
    let live = true;
    setJobsLoading(true);
    (async () => {
      try {
        const res = await apiClient.request({ path: `/routes/install-quote/jobs?season=${encodeURIComponent(season)}`, method: "GET" });
        if (!res.ok) throw new Error(await errorOf(res, "Couldn't load the scheduled jobs"));
        const j = (await res.json()) as { jobs: Job[] };
        if (live) setJobs(j.jobs);
      } catch {
        if (live) setJobs([]);
      } finally {
        if (live) setJobsLoading(false);
      }
    })();
    return () => { live = false; };
  }, [season, isAdmin]);

  const body = useMemo(() => {
    const crew: Record<string, number> = {};
    Object.entries(form.crew).forEach(([slug, v]) => {
      const n = num(v);
      if (n) crew[slug] = Math.floor(n);
    });
    return {
      season, crew,
      price: num(form.price),
      install_onsite_h: num(form.installH) ?? 0,
      takedown_onsite_h: num(form.takedownH),
      include_takedown: form.includeTakedown,
      drive_min_each_way: num(form.driveMin),
      miles_each_way: num(form.miles),
      boxes: Math.floor(num(form.boxes) ?? 0),
      stored_with_us: form.stored,
      designer_hours: num(form.designerH) ?? 0,
      materials: num(form.materials) ?? 0,
    };
  }, [form, season]);
  const bodyKey = JSON.stringify(body);

  useEffect(() => {
    if (!isAdmin) return;
    const mine = ++seq.current;
    setBusy(true);
    const t = window.setTimeout(async () => {
      try {
        const res = await apiClient.request({
          path: "/routes/install-quote/calc", method: "POST", body: JSON.parse(bodyKey), type: ContentType.Json,
        });
        if (!res.ok) throw new Error(await errorOf(res, "Couldn't work out the quote"));
        const j = (await res.json()) as Out;
        if (mine !== seq.current) return;
        setOut(j);
        setClasses(j.classes);
        setError(null);
      } catch (e) {
        if (mine === seq.current) setError(e instanceof Error ? e.message : "Couldn't work out the quote");
      } finally {
        if (mine === seq.current) setBusy(false);
      }
    }, 300);
    return () => window.clearTimeout(t);
  }, [bodyKey, isAdmin]);

  const pick = (j: Job) => {
    setPicked(j);
    const crew: Record<string, string> = {};
    classes.forEach((c) => { crew[c.slug] = ""; });
    Object.entries(j.crew).forEach(([slug, n]) => { crew[slug] = String(n); });
    setForm({
      price: s(quotePrice(j)), crew, installH: s(j.h26), takedownH: "", includeTakedown: true,
      driveMin: s(j.drive_min_each_way ?? 30), miles: s(j.miles_each_way), boxes: String(j.boxes || 0),
      stored: j.stored_with_us, designerH: "", materials: "",
    });
  };

  if (!isAdmin) {
    return (
      <Layout>
        <div className="p-8 text-sm text-stone-600">The quote calculator is for admins only.</div>
      </Layout>
    );
  }

  const target = out?.target_profit_pct ?? null;
  const hasPrice = out?.price != null;
  const targetLevel = out?.levels.find((l) => l.target) || null;
  const knownSlugs = new Set(classes.map((c) => c.slug));
  const strayCrew = Object.keys(form.crew).filter((k) => !knownSlugs.has(k) && num(form.crew[k]));

  return (
    <Layout>
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-stone-900">Quote Calculator</h1>
            <p className="mt-1 max-w-2xl text-sm text-stone-500">
              What a job costs us to install and take down, and what to charge for each profit level. Only admins see this page.
            </p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-x-3 gap-y-2 text-xs text-stone-600 sm:w-auto">
            {out && (
              <span>
                Overhead <b className="text-stone-800">{out.overhead_pct ?? "—"}%</b> · Target profit <b className="text-stone-800">{target ?? "—"}%</b>
                {" · "}<Link to="/settings" className="font-semibold text-emerald-700 hover:underline">Install Costs</Link>
              </span>
            )}
            <label className="flex items-center gap-2">
              Season
              <select className="rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm" value={season} onChange={(e) => { setSeason(e.target.value); setPicked(null); }}>
                {[Number(currentSeasonLabel()) + 1, Number(currentSeasonLabel()), Number(currentSeasonLabel()) - 1].map((y) => (
                  <option key={y} value={String(y)}>{y}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          {/* ---------- inputs ---------- */}
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white p-4">
            <Field label="Start from a scheduled job" hint={picked ? <JobHint j={picked} /> : "Fills in the price, crew, hours, drive and boxes from the schedule."}>
              <JobPicker jobs={jobs} loading={jobsLoading} picked={picked} onPick={pick} onClear={() => setPicked(null)} />
            </Field>

            <Field label="Price" hint="Install and takedown together. Takedown is priced the same as install; leave storage out.">
              <NumInput value={form.price} onChange={(v) => set("price", v)} prefix="$" step="50" placeholder="Leave blank to see the price needed" />
            </Field>

            <div>
              <p className="text-xs font-medium text-stone-600">Crew</p>
              <div className="mt-1 grid grid-cols-2 gap-2">
                {classes.map((c) => (
                  <Field key={c.slug} label={c.label} hint={c.rate == null ? <span className="text-red-600">no rate on the card</span> : `${formatCurrency(c.rate)}/h`}>
                    <NumInput value={form.crew[c.slug] ?? ""} onChange={(v) => setCrew(c.slug, v)} step="1" placeholder="0" />
                  </Field>
                ))}
              </div>
              {out && (
                <p className="mt-1.5 text-[11px] text-stone-500">
                  {out.crew_size} {out.crew_size === 1 ? "person" : "people"}, {formatCurrency(out.crew_rate)} an hour together.
                  {strayCrew.length > 0 && <span className="text-red-600"> {strayCrew.join(", ")} is not a class on this season's card.</span>}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Install, on site">
                <NumInput value={form.installH} onChange={(v) => set("installH", v)} step="0.25" suffix="h" />
              </Field>
              <Field label="Takedown, on site" hint={form.takedownH === "" && out ? `Auto: install × ${out.takedown_time_factor}` : form.takedownH !== "" ? <button type="button" className="font-semibold text-emerald-700 hover:underline" onClick={() => set("takedownH", "")}>Back to auto</button> : undefined}>
                <NumInput value={form.takedownH} onChange={(v) => set("takedownH", v)} step="0.25" suffix="h"
                  placeholder={out && form.includeTakedown ? String(out.inputs.takedown_onsite_h) : ""} />
              </Field>
            </div>
            <Toggle on={form.includeTakedown} onChange={(v) => set("includeTakedown", v)} label="Include the takedown trip" />

            <div className="grid grid-cols-2 gap-2">
              <Field label="Drive, each way">
                <NumInput value={form.driveMin} onChange={(v) => set("driveMin", v)} step="5" suffix="min" placeholder="30" />
              </Field>
              <Field label="Miles, each way" hint={form.miles === "" ? "Auto: drive time at 27 mph" : undefined}>
                <NumInput value={form.miles} onChange={(v) => set("miles", v)} step="1" suffix="mi"
                  placeholder={out ? String(out.inputs.miles_each_way) : ""} />
              </Field>
            </div>

            <div className="grid grid-cols-2 items-end gap-2">
              <Field label="Boxes">
                <NumInput value={form.boxes} onChange={(v) => set("boxes", v)} step="1" />
              </Field>
              <div className="pb-2">
                <Toggle on={form.stored} onChange={(v) => set("stored", v)} label="Stored with us" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Designer hours" hint={out?.designer.rate != null ? `${formatCurrency(out.designer.rate)}/h` : undefined}>
                <NumInput value={form.designerH} onChange={(v) => set("designerH", v)} step="0.5" suffix="h" placeholder="0" />
              </Field>
              <Field label="Materials">
                <NumInput value={form.materials} onChange={(v) => set("materials", v)} prefix="$" step="10" placeholder="0" />
              </Field>
            </div>
          </div>

          {/* ---------- results ---------- */}
          <div className="min-w-0 space-y-4">
            {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">{error}</div>}
            {out && out.missing.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                Some numbers are placeholders: the install cost card still needs {out.missing.map(missingLabel).join(", ")}.{" "}
                <Link to="/settings" className="font-semibold underline">Fill it in</Link>
              </div>
            )}
            {!out ? (
              <div className="flex items-center justify-center rounded-xl border border-stone-200 bg-white py-24">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
              </div>
            ) : (
              <div className={`space-y-4 transition-opacity ${busy ? "opacity-70" : ""}`}>
                <Headline out={out} target={target} targetLevel={targetLevel} />
                <Breakdown out={out} />
                <Levels out={out} hasPrice={hasPrice} />
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}

function JobHint({ j }: { j: Job }) {
  const p = j.price;
  return (
    <>
      {j.price.source === "unpriced" ? "No price yet. " : (
        <>Price: install {money0(p.install)} + takedown {money0(p.takedown)}{p.storage ? `, storage ${money0(p.storage)} left out` : ""}. </>
      )}
      {j.size25 ? `2025 crew of ${j.size25}` : j.crew_basis === "role needs" ? "Crew from its role needs" : "No crew on record"}
      {j.real25 != null ? `, 2025 real hours ${j.real25}` : ""}.
    </>
  );
}

function Headline({ out, target, targetLevel }: { out: Out; target: number | null; targetLevel: Level | null }) {
  if (out.price == null) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white px-5 py-4">
        <p className="text-xs text-stone-500">Price needed for the {target ?? "—"}% target</p>
        <p className="text-4xl font-semibold tracking-tight tabular-nums text-stone-900">{money0(targetLevel?.price_needed)}</p>
        <p className="mt-0.5 text-xs text-stone-500">
          The job costs {money0(out.job_cost)}; break-even is {money0(out.levels.find((l) => l.break_even)?.price_needed)}. Enter a price to see the profit.
        </p>
      </div>
    );
  }
  const p = out.profit_pct;
  const chip = p == null ? null
    : p < 0 ? { t: "Losing money", c: "bg-red-50 text-red-800 border-red-200" }
      : target != null && p < target ? { t: `${(target - p).toFixed(1)} pts under the ${target}% target`, c: "bg-amber-50 text-amber-800 border-amber-200" }
        : { t: target != null ? `At or above the ${target}% target` : "Profitable", c: "bg-emerald-50 text-emerald-800 border-emerald-200" };
  return (
    <div className="rounded-xl border border-stone-200 bg-white px-5 py-4">
      <p className="text-xs text-stone-500">Profit at {money0(out.price)}</p>
      <div className="flex flex-wrap items-center gap-3">
        <p className={`text-4xl font-semibold tracking-tight tabular-nums ${p != null && p < 0 ? "text-red-700" : "text-stone-900"}`}>{pct(p)}</p>
        {chip && <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${chip.c}`}>{chip.t}</span>}
      </div>
      <p className="mt-0.5 text-xs tabular-nums text-stone-500">
        {money0(out.price)} − {money0(out.job_cost)} job cost − {money0(out.overhead)} overhead ({out.overhead_pct}%) = <b className="text-stone-700">{money0(out.profit)}</b>
        {targetLevel?.price_needed != null && <> · the {target}% target needs {money0(targetLevel.price_needed)}</>}
      </p>
    </div>
  );
}

function Breakdown({ out }: { out: Out }) {
  const trips = out.trips;
  const title = (t: Trip) => (t.trip === "install" ? "Install" : "Takedown");
  const rows: Array<{ label: React.ReactNode; cells: React.ReactNode[]; bold?: boolean }> = [
    { label: "On site", cells: trips.map((t) => hrs(t.onsite_h)) },
    {
      label: "Paid hours, depot to depot",
      cells: trips.map((t) => (
        <span key={t.trip} title={`${t.pretrip_min} min before the trip + ${t.drive_min_each_way} min each way + on site`}>{hrs(t.paid_h)}</span>
      )),
    },
    { label: `Crew pay · ${out.crew_size} × paid hours`, cells: trips.map((t) => formatCurrency(t.crew_pay)) },
    {
      label: <>Share of the crew-day's van, trailer and extras<span className="block text-[10px] text-stone-400">paid hours ÷ 10, at most a whole day</span></>,
      cells: trips.map((t) => <span key={t.trip}>{formatCurrency(t.day_share_cost)}<span className="block text-[10px] text-stone-400">{Math.round(t.day_share * 100)}% of a day</span></span>),
    },
    {
      label: "Gas and wear",
      cells: trips.map((t) => <span key={t.trip}>{formatCurrency(t.gas + t.wear)}<span className="block text-[10px] text-stone-400">{t.miles_round_trip} mi round trip</span></span>),
    },
    { label: "Trip cost", cells: trips.map((t) => formatCurrency(t.total)), bold: true },
  ];
  return (
    <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
      <div className="flex items-baseline justify-between gap-2 border-b border-stone-100 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-stone-900">Job cost</h2>
        <span className="text-lg font-semibold tabular-nums text-stone-900">{formatCurrency(out.job_cost)}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-xs">
          <thead>
            <tr className="border-b border-stone-100 text-left text-[10px] uppercase tracking-wide text-stone-400">
              <th className="px-4 py-1.5 font-semibold" />
              {trips.map((t) => <th key={t.trip} className="px-4 py-1.5 text-right font-semibold">{title(t)}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.map((r, i) => (
              <tr key={i} className={r.bold ? "bg-stone-50 font-semibold text-stone-900" : "text-stone-700"}>
                <td className="px-4 py-1.5 text-stone-600">{r.label}</td>
                {r.cells.map((c, j) => <td key={j} className="px-4 py-1.5 text-right align-top tabular-nums">{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-stone-100 border-t border-stone-200 text-xs">
        {out.designer.hours > 0 && (
          <div className="flex justify-between px-4 py-1.5 text-stone-700">
            <span className="text-stone-600">Designer · {out.designer.hours} h × {formatCurrency(out.designer.rate)}</span>
            <span className="tabular-nums">{formatCurrency(out.designer.cost)}</span>
          </div>
        )}
        {out.materials > 0 && (
          <div className="flex justify-between px-4 py-1.5 text-stone-700">
            <span className="text-stone-600">Materials</span><span className="tabular-nums">{formatCurrency(out.materials)}</span>
          </div>
        )}
        <div className="flex justify-between px-4 py-1.5 font-semibold text-stone-900">
          <span>Job cost</span><span className="tabular-nums">{formatCurrency(out.job_cost)}</span>
        </div>
      </div>
    </div>
  );
}

function Levels({ out, hasPrice }: { out: Out; hasPrice: boolean }) {
  const neg = (v: number | null | undefined) => (v != null && v < 0 ? "text-red-700" : "");
  const hoursCell = (v: number | null | undefined) => (v == null ? "—" : v <= 0 ? "none" : hrs(v));
  return (
    <div className="rounded-xl border border-stone-200 bg-white">
      <div className="border-b border-stone-100 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-stone-900">Profit levels</h2>
        <p className="text-xs text-stone-500">
          {hasPrice
            ? `At ${money0(out.price)}: the most the job can cost for each profit level, and how much of it could go to crew time, materials or a designer.`
            : "The price the job needs for each profit level. Enter a price to see how much room it leaves."}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className={`w-full text-sm ${hasPrice ? "min-w-[760px]" : "min-w-[320px]"}`}>
          <thead>
            <tr className="border-b border-stone-200 text-left text-[10px] uppercase tracking-wide text-stone-400">
              {/* First column stays put while a phone scrolls the figures sideways. */}
              <th className="sticky left-0 z-[1] bg-white px-4 py-2 font-semibold sm:static">Profit</th>
              <th className="px-2 py-2 text-right font-semibold">Price needed</th>
              {hasPrice && (
                <>
                  <th className="px-2 py-2 text-right font-semibold">Most the job can cost</th>
                  <th className="px-2 py-2 text-right font-semibold">Headroom</th>
                  <th className="px-2 py-2 text-right font-semibold">Crew-hours you can afford</th>
                  <th className="px-2 py-2 text-right font-semibold">Most on materials</th>
                  <th className="px-4 py-2 text-right font-semibold">Designer hours you can afford</th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {out.levels.map((l) => (
              <tr key={l.profit_pct} className={l.target ? "bg-emerald-50/70 font-semibold" : ""}>
                <td className={`sticky left-0 z-[1] whitespace-nowrap px-4 py-2 tabular-nums text-stone-900 sm:static sm:bg-transparent ${l.target ? "bg-emerald-50" : "bg-white"}`}>
                  {l.profit_pct}%
                  {l.break_even && <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-stone-400">break-even</span>}
                  {l.target && <span className="ml-2 rounded-full border border-emerald-200 bg-white px-1.5 py-px text-[10px] font-semibold text-emerald-800">target</span>}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-stone-900">{l.price_needed == null ? "out of reach" : money0(l.price_needed)}</td>
                {hasPrice && (
                  <>
                    <td className="px-2 py-2 text-right tabular-nums text-stone-700">{money0(l.max_job_cost)}</td>
                    <td className={`px-2 py-2 text-right tabular-nums ${neg(l.headroom) || "text-emerald-700"}`}>
                      {l.headroom == null ? "—" : `${l.headroom >= 0 ? "+" : "−"}${money0(Math.abs(l.headroom))}`}
                    </td>
                    <td className={`px-2 py-2 text-right tabular-nums ${l.max_crew_hours != null && l.max_crew_hours < out.crew_hours ? "text-red-700" : "text-stone-700"}`}>
                      {hoursCell(l.max_crew_hours)}
                    </td>
                    <td className={`px-2 py-2 text-right tabular-nums ${neg(l.max_materials) || "text-stone-700"}`}>
                      {l.max_materials == null ? "—" : l.max_materials < 0 ? "none" : money0(l.max_materials)}
                    </td>
                    <td className={`px-4 py-2 text-right tabular-nums ${neg(l.max_designer_hours) || "text-stone-700"}`}>{hoursCell(l.max_designer_hours)}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-1 border-t border-stone-100 px-4 py-2.5 text-xs leading-relaxed text-stone-500">
        {hasPrice && (
          <p>
            A crew-hour is one hour of this whole crew ({out.crew_size} {out.crew_size === 1 ? "person" : "people"}, {formatCurrency(out.crew_rate)} an hour together) on the clock, depot to depot, install and takedown added up. This quote uses {hrs(out.crew_hours)}; red means it needs more than the price allows.
          </p>
        )}
        <p>
          Paid hours start with the longer of the 30-minute early arrival and loading the boxes (for jobs stored with us), then the drive out and back and the time on site.
          Van, trailer, insurance, ancillary, tolls and parking are charged per crew-day, so each trip carries its paid hours ÷ 10 of them. Overhead is {out.overhead_pct ?? "—"}% of the price.
        </p>
      </div>
    </div>
  );
}
