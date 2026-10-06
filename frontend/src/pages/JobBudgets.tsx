import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import Layout from "components/Layout";
import { apiClient } from "app";
import { currentMe } from "utils/me";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel } from "utils/season";

/**
 * Job Budgets (admin only): every install job on the schedule, its season
 * price against what it costs us -- the install as scheduled plus an
 * estimated takedown -- and, the headline, how many crew-hours it can take
 * before it misses the target profit or starts losing money. All arithmetic
 * is server-side (backend app.libs.job_budget, GET /job-budgets) off the
 * same inputs as Crew-Day Profit, so a change to the install cost card in
 * Settings moves every number here too.
 */

type Status = "healthy" | "tight" | "losing" | "unpriced";
type Job = {
  row: number; name: string; client_id: number | null;
  days: Array<{ id: string; date: string; crew: string }>;
  price: {
    total: number | null; install: number | null; takedown: number | null; storage: number | null;
    price_source: "clients" | "schedule" | "no_charge" | "unpriced"; basis: string | null;
  };
  install: {
    onsite_h: number; paid_h: number; labor_cost: number; other_cost: number; cost: number;
    crew_rate: number | null; crew_size: number; crew_basis: string;
  };
  takedown: { factor: number; paid_h: number; labor_cost: number; other_cost: number; cost: number };
  materials: null;
  job_cost: number; overhead: number | null; net: number | null; net_pct: number | null; status: Status;
  budget: {
    vehicle: number; crew_rate: number | null;
    budget_target_h: number | null; budget_breakeven_h: number | null;
    planned_h: number; over_target_h: number | null;
  };
  last_year: { hours: number | null; crew_size: number | null };
  last_year_vs_plan: { plan_onsite_h: number; real25_h: number; diff_h: number; ratio: number } | null;
  missing: string[]; placeholder: boolean;
};
type Out = {
  season: string; overhead_pct: number | null; target_profit_pct: number | null; takedown_time_factor: number;
  summary: {
    jobs: number; priced_jobs: number; revenue: number; cost: number; overhead: number; net: number;
    net_pct: number | null; unpriced_cost: number; planned_h: number;
    counts: Partial<Record<Status, number>>; over_budget: number; over_budget_h: number;
  };
  jobs: Job[];
  missing_card: string[];
};
type Filter = "all" | Status | "over";

const STATUS: Record<Status, { label: string; chip: string; dot: string }> = {
  healthy: { label: "On target", chip: "bg-emerald-50 text-emerald-800 border-emerald-200", dot: "bg-emerald-600" },
  tight: { label: "Under target", chip: "bg-amber-50 text-amber-800 border-amber-200", dot: "bg-amber-500" },
  losing: { label: "Losing money", chip: "bg-red-50 text-red-800 border-red-200", dot: "bg-red-600" },
  unpriced: { label: "No price", chip: "bg-stone-100 text-stone-600 border-stone-200", dot: "bg-stone-400" },
};
const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: "all", label: "All jobs" },
  { id: "over", label: "Over hour budget" },
  { id: "losing", label: "Losing money" },
  { id: "tight", label: "Under target" },
  { id: "healthy", label: "On target" },
  { id: "unpriced", label: "No price" },
];

const money0 = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`);
const hrs = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)} h`);

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function fmtShortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** "Nov 12 · Crew 1, Crew 2" or "Nov 12, Nov 13" -- the job's days, briefly. */
function daysSummary(days: Job["days"]): string {
  const dates = [...new Set(days.map((d) => d.date))];
  if (dates.length === 1) return `${fmtShortDate(dates[0])} · ${days.map((d) => d.crew).join(", ")}`;
  return dates.map(fmtShortDate).join(", ");
}

const SOURCE: Record<Job["price"]["price_source"], string> = {
  clients: "price from Clients",
  schedule: "price from the schedule",
  no_charge: "no charge",
  unpriced: "no price yet",
};

const BASIS: Record<string, string> = {
  "2025 crew": "last year's crew",
  "role needs": "the job's role needs",
  staffed: "the people staffed",
  none: "nobody staffed, no role needs",
};

/** Net % as a bar on a fixed −50%…+75% track with the target marked. */
function NetBar({ value, target }: { value: number | null; target: number | null }) {
  const lo = -50, hi = 75, span = hi - lo;
  const x = (v: number) => `${((Math.min(hi, Math.max(lo, v)) - lo) / span) * 100}%`;
  const zero = x(0);
  if (value == null) return <div className="h-2 w-24 rounded-full bg-stone-100" />;
  const pos = value >= 0;
  const color = value < 0 ? "bg-red-500" : target != null && value < target ? "bg-amber-400" : "bg-emerald-600";
  return (
    <div className="relative h-2 w-24 rounded-full bg-stone-100" aria-hidden>
      <div
        className={`absolute top-0 h-2 ${color} ${pos ? "rounded-r-full" : "rounded-l-full"}`}
        style={pos ? { left: zero, width: `calc(${x(value)} - ${zero})` } : { left: x(value), width: `calc(${zero} - ${x(value)})` }}
      />
      <div className="absolute -top-0.5 h-3 w-px bg-stone-400" style={{ left: zero }} />
      {target != null && <div className="absolute -top-1 h-4 w-0.5 rounded bg-stone-700" style={{ left: x(target) }} title={`Target ${target}%`} />}
    </div>
  );
}

function Tile({ label, value, detail, hero, className = "" }: { label: string; value: string; detail?: React.ReactNode; hero?: boolean; className?: string }) {
  return (
    <div className={`min-w-0 px-4 py-3 sm:px-5 sm:py-4 ${className}`}>
      <p className="text-xs text-stone-500">{label}</p>
      <p className={`font-semibold tabular-nums text-stone-900 ${hero ? "text-4xl tracking-tight" : "text-lg sm:text-xl"}`}>{value}</p>
      {detail && <div className="mt-0.5 text-xs text-stone-500">{detail}</div>}
    </div>
  );
}

/** The headline: crew-hours the job can take at target and at break-even. */
function HourBudget({ j }: { j: Job }) {
  const b = j.budget;
  if (b.budget_target_h == null || b.budget_breakeven_h == null) {
    return (
      <span className="text-xs text-stone-400">
        {j.price.total == null ? "no price, no budget" : !b.crew_rate ? "no crew rate" : "card incomplete"}
      </span>
    );
  }
  if (b.budget_breakeven_h <= 0) {
    return (
      <span className="whitespace-nowrap text-xs font-semibold text-red-700" title="Vans, gas and overhead alone use up the price, even before any crew time">
        No hours left
      </span>
    );
  }
  return (
    <div className="leading-tight">
      <div className="font-semibold tabular-nums text-stone-900">
        {b.budget_target_h > 0 ? `${hrs(b.budget_target_h)} at target` : "0 h at target"}
      </div>
      <div className="text-xs tabular-nums text-stone-500">{hrs(b.budget_breakeven_h)} break-even</div>
    </div>
  );
}

function Planned({ j }: { j: Job }) {
  const over = j.budget.over_target_h;
  return (
    <div className="leading-tight">
      <div className="tabular-nums text-stone-800">{hrs(j.budget.planned_h)}</div>
      {over != null && (
        <div className={`text-xs tabular-nums ${over > 0 ? "font-semibold text-red-700" : "text-emerald-700"}`}>
          {over > 0 ? `${hrs(over)} over` : `${hrs(-over)} to spare`}
        </div>
      )}
    </div>
  );
}

export default function JobBudgets() {
  const isAdmin = !!currentMe()?.isAdmin;
  const [season, setSeason] = useState(currentSeasonLabel());
  const [data, setData] = useState<Out | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!isAdmin) return;
    let live = true;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await apiClient.request({ path: `/routes/job-budgets?season=${encodeURIComponent(season)}`, method: "GET" });
        if (!res.ok) {
          let why = "Couldn't load the job budgets";
          try { const j = await res.json(); if (j?.detail) why = String(j.detail); } catch { /* no body */ }
          throw new Error(why);
        }
        const j = (await res.json()) as Out;
        if (live) setData(j);
      } catch (e) {
        const why = e instanceof Error ? e.message : "Couldn't load the job budgets";
        if (live) { setError(why); setData(null); }
        toast.error(why);
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [season, isAdmin]);

  const jobs = useMemo(
    () => (data?.jobs || []).filter((j) =>
      filter === "all" ? true : filter === "over" ? (j.budget.over_target_h ?? 0) > 0 : j.status === filter),
    [data, filter],
  );
  const toggle = (row: number) => setOpen((s) => { const n = new Set(s); if (n.has(row)) n.delete(row); else n.add(row); return n; });

  if (!isAdmin) {
    return (
      <Layout>
        <div className="p-8 text-sm text-stone-600">Job Budgets is for admins only.</div>
      </Layout>
    );
  }

  const s = data?.summary;
  const target = data?.target_profit_pct ?? null;
  const filterCount = (f: Filter) => (f === "all" ? s?.jobs : f === "over" ? s?.over_budget : s?.counts[f]) || 0;

  return (
    <Layout>
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-stone-900">Job Budgets</h1>
            <p className="mt-1 max-w-2xl text-sm text-stone-500">
              How many crew-hours each install job can take, install and takedown, before it misses the target profit or starts losing money. Only admins see this page.
            </p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-x-3 gap-y-2 text-xs text-stone-600 sm:w-auto">
            {data && (
              <span>
                Overhead <b className="text-stone-800">{data.overhead_pct ?? "—"}%</b> · Target <b className="text-stone-800">{target ?? "—"}%</b>
                {" · "}<Link to="/settings" className="font-semibold text-emerald-700 hover:underline">Install Costs</Link>
              </span>
            )}
            <label className="flex items-center gap-2">
              Season
              <select className="rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm" value={season} onChange={(e) => setSeason(e.target.value)}>
                {[Number(currentSeasonLabel()) + 1, Number(currentSeasonLabel()), Number(currentSeasonLabel()) - 1].map((y) => (
                  <option key={y} value={String(y)}>{y}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
          </div>
        ) : error || !data || !s ? (
          <div className="rounded-xl border border-stone-200 bg-white p-8 text-center text-sm text-stone-500">{error || "Nothing to show."}</div>
        ) : (
          <>
            {data.missing_card.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                Some numbers are placeholders: the install cost card still needs {data.missing_card.join(", ")}.{" "}
                <Link to="/settings" className="font-semibold underline">Fill it in</Link>
              </div>
            )}

            {/* Two across below lg with the net-profit hero on its own row, so a
                phone shows the four figures in two short rows, not five tall ones. */}
            <div className="grid grid-cols-2 overflow-hidden rounded-xl border border-stone-200 bg-white lg:grid-cols-[1.4fr_1fr_1fr_1fr_1fr] lg:divide-x lg:divide-stone-100">
              <Tile hero className="col-span-2 lg:col-span-1" label={`Net profit, ${s.priced_jobs} priced jobs`} value={pct(s.net_pct)}
                detail={<>{money0(s.net)} after install, takedown and {data.overhead_pct}% overhead</>} />
              <Tile label="Season price" value={money0(s.revenue)} detail="install, takedown and storage" />
              <Tile label="Job costs" value={money0(s.cost)}
                detail={s.unpriced_cost ? `plus ${money0(s.unpriced_cost)} on jobs with no price` : "crew, vans, gas, extras"} />
              <Tile label="Over hour budget" value={String(s.over_budget)}
                detail={s.over_budget ? `${hrs(s.over_budget_h)} over target in all` : "every job fits its budget"} />
              <Tile label="Jobs" value={String(s.jobs)}
                detail={
                  <span className="flex flex-wrap gap-x-2">
                    {(["healthy", "tight", "losing", "unpriced"] as Status[]).filter((k) => s.counts[k]).map((k) => (
                      <span key={k} className="flex items-center gap-1"><i className={`inline-block h-2 w-2 rounded-full ${STATUS[k].dot}`} />{s.counts[k]} {STATUS[k].label.toLowerCase()}</span>
                    ))}
                  </span>
                } />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {FILTERS.filter((f) => f.id === "all" || filterCount(f.id)).map((f) => (
                <button key={f.id} type="button" onClick={() => setFilter(f.id)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold sm:py-1 ${filter === f.id ? "border-stone-900 bg-stone-900 text-white" : "border-stone-200 bg-white text-stone-600 hover:bg-stone-50"}`}>
                  {f.label}{f.id !== "all" && <span className="ml-1 opacity-70">{filterCount(f.id)}</span>}
                </button>
              ))}
              <span className="w-full text-xs text-stone-500 sm:ml-auto sm:w-auto">
                Crew-hours are hours the whole crew is on the clock, depot to depot. Bar: net % on a −50% to +75% scale; the dark tick is the {target}% target.
              </span>
            </div>

            {/* Phones and tablets: one card per job (tap to open its breakdown;
                an open card spans both columns). The 980px table below takes
                over from xl, the first width it fits beside the sidebar
                without a sideways scroll. */}
            <div className="grid gap-2 md:grid-cols-2 xl:hidden">
              {jobs.map((j) => (
                <JobCard key={j.row} j={j} data={data} target={target} isOpen={open.has(j.row)} onToggle={() => toggle(j.row)} />
              ))}
              {jobs.length === 0 && (
                <p className="rounded-xl border border-stone-200 bg-white px-4 py-10 text-center text-sm text-stone-500 md:col-span-2">No jobs match that filter.</p>
              )}
            </div>

            <div className="hidden overflow-x-auto rounded-xl border border-stone-200 bg-white xl:block">
              <table className="w-full min-w-[980px] text-sm">
                <thead>
                  <tr className="border-b border-stone-200 text-left text-[10px] uppercase tracking-wide text-stone-400">
                    <th className="px-4 py-2 font-semibold">Job</th>
                    <th className="px-2 py-2 text-right font-semibold">Price</th>
                    <th className="px-2 py-2 text-right font-semibold">Job cost</th>
                    <th className="px-2 py-2 text-right font-semibold">Net</th>
                    <th className="px-2 py-2 font-semibold">Net %</th>
                    <th className="px-2 py-2 font-semibold">Hour budget</th>
                    <th className="px-2 py-2 text-right font-semibold">Planned</th>
                    <th className="px-4 py-2 font-semibold">Last year</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => {
                    const isOpen = open.has(j.row);
                    const p = j.price;
                    return (
                      <React.Fragment key={j.row}>
                        <tr onClick={() => toggle(j.row)} className={`cursor-pointer border-b border-stone-100 hover:bg-stone-50 ${isOpen ? "bg-stone-50" : ""}`}>
                          <td className="max-w-[240px] px-4 py-2.5 align-top">
                            <div className="truncate font-medium text-stone-900" title={j.name}>{j.name}</div>
                            <div className="text-xs text-stone-500">{daysSummary(j.days)}</div>
                          </td>
                          <td className="px-2 py-2.5 text-right align-top">
                            <div className="tabular-nums text-stone-800">{money0(p.total)}</div>
                            {p.total != null && p.price_source !== "no_charge" ? (
                              <div className="whitespace-nowrap text-[10px] tabular-nums text-stone-500">
                                {money0(p.install)} in · {money0(p.takedown)} out · {money0(p.storage)} storage
                              </div>
                            ) : (
                              <div className="text-[10px] text-stone-500">{SOURCE[p.price_source]}</div>
                            )}
                          </td>
                          <td className="px-2 py-2.5 text-right align-top tabular-nums text-stone-700">
                            {money0(j.job_cost)}{j.placeholder && <span className="ml-1 text-[10px] text-red-700">*</span>}
                          </td>
                          <td className={`px-2 py-2.5 text-right align-top font-semibold tabular-nums ${j.net != null && j.net < 0 ? "text-red-700" : "text-stone-900"}`}>{money0(j.net)}</td>
                          <td className="px-2 py-2.5 align-top">
                            <div className="flex items-center gap-2">
                              <span className="w-14 text-right font-semibold tabular-nums text-stone-900">{pct(j.net_pct)}</span>
                              <NetBar value={j.net_pct} target={target} />
                            </div>
                            <span className={`mt-1 inline-block rounded-full border px-1.5 py-px text-[10px] font-semibold ${STATUS[j.status].chip}`}>{STATUS[j.status].label}</span>
                          </td>
                          <td className="max-w-[190px] px-2 py-2.5 align-top"><HourBudget j={j} /></td>
                          <td className="px-2 py-2.5 text-right align-top"><Planned j={j} /></td>
                          <td className="px-4 py-2.5 align-top text-xs text-stone-600">
                            <div className="tabular-nums">{j.last_year.hours != null ? hrs(j.last_year.hours) : <span className="text-stone-400">no hours</span>}</div>
                            <div className="text-stone-500">{j.last_year.crew_size ? `crew of ${j.last_year.crew_size}` : "no crew on record"}</div>
                          </td>
                        </tr>
                        {isOpen && <JobDetail j={j} data={data} />}
                      </React.Fragment>
                    );
                  })}
                  {jobs.length === 0 && (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-stone-500">No jobs match that filter.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="text-xs leading-relaxed text-stone-500">
              Price is the job's whole season price from Clients (install, takedown and storage), falling back to the fees the schedule was built with.
              Install cost is the job's share of its crew-days on the schedule: crew pay for every paid hour depot to depot, split by on-site time, plus vans,
              trailer, gas and extras. Takedown isn't scheduled yet, so it's estimated: {Math.round(data.takedown_time_factor * 100)}% of the install hours,
              with the same trip costs. Hour budget = (price after overhead and target profit, less vans and gas) ÷ the crew's hourly pay. Materials aren't tracked per job yet.
            </p>
          </>
        )}
      </div>
    </Layout>
  );
}

function Line({ label, value, strong, muted }: { label: React.ReactNode; value: React.ReactNode; strong?: boolean; muted?: boolean }) {
  return (
    <div className={`flex justify-between gap-3 px-3 py-1.5 ${strong ? "bg-stone-50 font-semibold" : ""}`}>
      <span className={muted ? "text-stone-400" : "text-stone-600"}>{label}</span>
      <span className={`tabular-nums ${muted ? "text-stone-400" : "text-stone-800"}`}>{value}</span>
    </div>
  );
}

/** The phone layout of one table row: same figures, stacked. */
function JobCard({ j, data, target, isOpen, onToggle }: { j: Job; data: Out; target: number | null; isOpen: boolean; onToggle: () => void }) {
  const p = j.price;
  return (
    <div className={`overflow-hidden rounded-xl border border-stone-200 bg-white ${isOpen ? "md:col-span-2" : ""}`}>
      <button type="button" onClick={onToggle} aria-expanded={isOpen}
        className={`block w-full px-4 py-3 text-left ${isOpen ? "bg-stone-50" : ""}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium text-stone-900">{j.name}</div>
            <div className="text-xs text-stone-500">{daysSummary(j.days)}</div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-lg font-semibold tabular-nums text-stone-900">{pct(j.net_pct)}</div>
            <span className={`inline-block rounded-full border px-1.5 py-px text-[10px] font-semibold ${STATUS[j.status].chip}`}>{STATUS[j.status].label}</span>
          </div>
        </div>
        <div className="mt-2"><NetBar value={j.net_pct} target={target} /></div>
        <dl className="mt-2 grid grid-cols-3 gap-2 border-t border-stone-100 pt-2 text-xs">
          <div className="min-w-0">
            <dt className="text-[10px] uppercase tracking-wide text-stone-400">Price</dt>
            <dd className="tabular-nums text-stone-700">{money0(p.total)}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[10px] uppercase tracking-wide text-stone-400">Job cost</dt>
            <dd className="tabular-nums text-stone-700">{money0(j.job_cost)}{j.placeholder && <span className="ml-0.5 text-[10px] text-red-700">*</span>}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[10px] uppercase tracking-wide text-stone-400">Net</dt>
            <dd className={`font-semibold tabular-nums ${j.net != null && j.net < 0 ? "text-red-700" : "text-stone-900"}`}>{money0(j.net)}</dd>
          </div>
        </dl>
        <div className="mt-1 text-[10px] tabular-nums text-stone-500">
          {p.total != null && p.price_source !== "no_charge"
            ? `${money0(p.install)} in · ${money0(p.takedown)} out · ${money0(p.storage)} storage`
            : SOURCE[p.price_source]}
        </div>
        <dl className="mt-2 grid grid-cols-3 gap-2 border-t border-stone-100 pt-2 text-xs">
          <div className="min-w-0">
            <dt className="text-[10px] uppercase tracking-wide text-stone-400">Hour budget</dt>
            <dd><HourBudget j={j} /></dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[10px] uppercase tracking-wide text-stone-400">Planned</dt>
            <dd><Planned j={j} /></dd>
          </div>
          <div className="min-w-0 text-stone-600">
            <dt className="text-[10px] uppercase tracking-wide text-stone-400">Last year</dt>
            <dd className="tabular-nums">{j.last_year.hours != null ? hrs(j.last_year.hours) : <span className="text-stone-400">no hours</span>}</dd>
            <dd className="text-stone-500">{j.last_year.crew_size ? `crew of ${j.last_year.crew_size}` : "no crew on record"}</dd>
          </div>
        </dl>
      </button>
      {isOpen && (
        <div className="border-t border-stone-200 bg-stone-50/70 p-3">
          <JobDetailBody j={j} data={data} />
        </div>
      )}
    </div>
  );
}

function JobDetail({ j, data }: { j: Job; data: Out }) {
  return (
    <tr className="border-b border-stone-200 bg-stone-50/70">
      <td colSpan={8} className="px-4 pb-4 pt-1">
        <JobDetailBody j={j} data={data} />
      </td>
    </tr>
  );
}

function JobDetailBody({ j, data }: { j: Job; data: Out }) {
  const i = j.install, t = j.takedown, b = j.budget;
  const vs = j.last_year_vs_plan;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white text-xs">
        <p className="px-3 py-1.5 font-semibold text-stone-700">Install · as scheduled</p>
        <Line label="On site" value={hrs(i.onsite_h)} />
        <Line label="Paid crew-hours, depot to depot" value={hrs(i.paid_h)} />
        <Line label="Crew pay" value={formatCurrency(i.labor_cost)} />
        <Line label="Vans, trailer, gas, extras" value={formatCurrency(i.other_cost)} />
        <Line strong label="Install cost" value={formatCurrency(i.cost)} />
        <p className="px-3 py-1.5 font-semibold text-stone-700">Takedown · estimate</p>
        <Line label={`Paid crew-hours · ${Math.round(t.factor * 100)}% of install`} value={hrs(t.paid_h)} />
        <Line label="Crew pay" value={formatCurrency(t.labor_cost)} />
        <Line label="Vans, trailer, gas, extras · same trip" value={formatCurrency(t.other_cost)} />
        <Line strong label="Takedown cost" value={formatCurrency(t.cost)} />
      </div>

      <div className="divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white text-xs">
        <p className="px-3 py-1.5 font-semibold text-stone-700">The job</p>
        <Line label="Price" value={money0(j.price.total)} />
        <Line label="Install + takedown" value={formatCurrency(j.job_cost)} />
        <Line label="Materials" value="not tracked yet" muted />
        <Line label={`Overhead · ${data.overhead_pct ?? "—"}% of the price`} value={j.overhead == null ? "—" : formatCurrency(j.overhead)} />
        <Line strong label={`Net · ${pct(j.net_pct)}`} value={j.net == null ? "—" : formatCurrency(j.net)} />
        <p className="px-3 py-1.5 font-semibold text-stone-700">Hour budget</p>
        <Line label="Crew pay per crew-hour" value={b.crew_rate == null ? "—" : `${formatCurrency(b.crew_rate)}/h`} />
        <Line label="Vans and gas, both trips" value={formatCurrency(b.vehicle)} />
        <Line label={`At the ${target(data)}% target`} value={hrs(b.budget_target_h)} />
        <Line label="Break-even" value={hrs(b.budget_breakeven_h)} />
        <Line strong label="Planned, install + takedown" value={hrs(b.planned_h)} />
        {j.missing.length > 0 && <p className="px-3 py-1.5 text-red-700">* placeholder: still needs {j.missing.join(", ")}</p>}
      </div>

      <div className="space-y-3 text-xs">
        <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-stone-600">
          <p className="mb-1 font-semibold text-stone-700">Crew</p>
          <p>
            {i.crew_size} {i.crew_size === 1 ? "person" : "people"}, sized from {BASIS[i.crew_basis] || i.crew_basis}.
            Everyone on the day is paid for every stop, so the biggest job on a day sets the crew.
          </p>
        </div>
        <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-stone-600">
          <p className="mb-1 font-semibold text-stone-700">On the schedule</p>
          <ul className="space-y-0.5">
            {j.days.map((d) => (
              <li key={d.id} className="flex justify-between gap-2"><span>{fmtDate(d.date)}</span><span className="text-stone-500">{d.crew}</span></li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-stone-600">
          <p className="mb-1 font-semibold text-stone-700">Last year</p>
          {vs ? (
            <p>
              {hrs(vs.real25_h)} on the job in 2025; {hrs(vs.plan_onsite_h)} on site this year
              ({vs.diff_h > 0 ? `${hrs(vs.diff_h)} more` : vs.diff_h < 0 ? `${hrs(-vs.diff_h)} less` : "the same"}).
            </p>
          ) : (
            <p>No 2025 hours on record for this job.</p>
          )}
          {j.last_year.crew_size != null && <p>2025 crew: {j.last_year.crew_size} people.</p>}
        </div>
        <p className="text-stone-500">
          Takedown is an estimate until it's scheduled: {Math.round(t.factor * 100)}% of the install crew-hours, same crew, and the same vans and gas as the install trip.
          The takedown price always equals the install price.
        </p>
        <p className="text-stone-500">
          {SOURCE[j.price.price_source]}{j.price.basis ? ` · ${j.price.basis}` : ""}
        </p>
      </div>
    </div>
  );
}

function target(data: Out): string {
  return data.target_profit_pct == null ? "—" : String(data.target_profit_pct);
}
