import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import Layout from "components/Layout";
import { apiClient } from "app";
import { currentMe } from "utils/me";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel } from "utils/season";

/**
 * Install & Takedown Profit (admin only): every install and takedown
 * crew-day, its jobs' revenue against what the day costs to run -- crew pay,
 * van, trailer, gas, the day's extras -- and the overhead share, as a net
 * profit percentage. The season on the install board is the plan (installs
 * plus the takedown each implies, backend app.libs.crew_day_profit); an
 * earlier season is what actually happened, rebuilt from real clock times,
 * real crews and real invoices (app.libs.season_history). All arithmetic is
 * server-side (GET /install-costs/crew-days) off the saved install cost card.
 */

type CrewSeat = { name: string | null; pay_class: string | null; label: string; rate: number | null; half?: boolean; temp?: boolean };
type Cost = {
  labor: number; van: number; trailer: number; insurance: number; gas: number; wear: number;
  ancillary: number; tolls: number; parking: number; total: number; missing: string[];
};
type Stop = {
  row: number; name: string; client_id: number | null; onsite_h: number; share: number; boxes: number;
  price: number | null; revenue: number | null; source: string; basis: string | null;
  cost: number; net: number | null; net_pct: number | null;
  start?: number | null; end?: number | null; real_times?: boolean; invoice?: number | null; storage?: number | null;
};
type Kind = "install" | "takedown";
type Status = "healthy" | "tight" | "losing" | "unpriced";
type Day = {
  id: string; date: string; crew: string; night: boolean; anchored: boolean;
  kind: Kind; times?: "real" | "mixed" | "estimated" | "planned"; crew_source?: string; takedown_of?: string;
  clock_out_min?: number | null; drive_min?: number;
  staffed: boolean; staffed_count: number; estimated_count: number; crew_basis: string | null; crew_people: CrewSeat[];
  paid_hours: number; pretrip_min: number; lunch_min: number; boxes: number; miles: number;
  cost: Cost; revenue: number | null; overhead: number | null; net: number | null; net_pct: number | null;
  priced_cost: number; unpriced_cost: number; status: Status; placeholder: boolean;
  stops: Stop[]; notes: string[];
};
type Totals = {
  days: number; staffed_days: number; revenue: number; cost: number; priced_cost: number; unpriced_cost: number;
  labor?: number; person_hours?: number;
  overhead: number; net: number; net_pct: number | null; counts: Partial<Record<Status, number>>; missing: string[];
};
type Out = {
  season: string; overhead_pct: number | null; target_profit_pct: number | null;
  mode?: "plan" | "actual"; card_season?: string; history_source?: string; takedown_time_factor?: number;
  summary: Totals;
  by_kind?: Record<Kind, Totals>;
  days: Day[];
  missing_card: string[];
};

const STATUS: Record<Status, { label: string; chip: string; dot: string }> = {
  healthy: { label: "On target", chip: "bg-emerald-50 text-emerald-800 border-emerald-200", dot: "bg-emerald-600" },
  tight: { label: "Under target", chip: "bg-amber-50 text-amber-800 border-amber-200", dot: "bg-amber-500" },
  losing: { label: "Losing money", chip: "bg-red-50 text-red-800 border-red-200", dot: "bg-red-600" },
  unpriced: { label: "No price", chip: "bg-stone-100 text-stone-600 border-stone-200", dot: "bg-stone-400" },
};
const FILTERS: Array<{ id: "all" | Status; label: string }> = [
  { id: "all", label: "All days" },
  { id: "losing", label: "Losing money" },
  { id: "tight", label: "Under target" },
  { id: "healthy", label: "On target" },
  { id: "unpriced", label: "No price" },
];

const KINDS: Array<{ id: "all" | Kind; label: string }> = [
  { id: "all", label: "Installs + takedowns" },
  { id: "install", label: "Installs" },
  { id: "takedown", label: "Takedowns" },
];
const TIMES: Record<string, string> = {
  real: "real clock times", mixed: "some real times", estimated: "estimated times", planned: "planned",
};
const clock = (m: number | null | undefined) => {
  if (m == null) return "—";
  const h = Math.floor(m / 60) % 24, mm = Math.round(m % 60);
  return `${((h + 11) % 12) + 1}:${String(mm).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};

const money0 = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`);
const hrs = (v: number) => `${v.toFixed(1)} h`;

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

/** "1 Lead · 7 General Installer" from the crew seats. */
function crewSummary(seats: CrewSeat[]): string {
  const counts = new Map<string, number>();
  seats.forEach((s) => counts.set(s.label, (counts.get(s.label) || 0) + 1));
  return [...counts.entries()].map(([l, n]) => `${n} ${l}`).join(" · ") || "No crew";
}

/** Net % as a bar on a fixed −50%…+75% track with the target marked. */
function NetBar({ value, target }: { value: number | null; target: number | null }) {
  const lo = -50, hi = 75, span = hi - lo;
  const x = (v: number) => `${((Math.min(hi, Math.max(lo, v)) - lo) / span) * 100}%`;
  const zero = x(0);
  if (value == null) return <div className="h-2 w-28 rounded-full bg-stone-100" />;
  const pos = value >= 0;
  const color = value < 0 ? "bg-red-500" : target != null && value < target ? "bg-amber-400" : "bg-emerald-600";
  return (
    <div className="relative h-2 w-28 rounded-full bg-stone-100" aria-hidden>
      <div
        className={`absolute top-0 h-2 ${color} ${pos ? "rounded-r-full" : "rounded-l-full"}`}
        style={pos ? { left: zero, width: `calc(${x(value)} - ${zero})` } : { left: x(value), width: `calc(${zero} - ${x(value)})` }}
      />
      <div className="absolute -top-0.5 h-3 w-px bg-stone-400" style={{ left: zero }} />
      {target != null && <div className="absolute -top-1 h-4 w-0.5 rounded bg-stone-700" style={{ left: x(target) }} title={`Target ${target}%`} />}
    </div>
  );
}

function Tile({ label, value, detail, hero }: { label: string; value: string; detail?: React.ReactNode; hero?: boolean }) {
  return (
    <div className="min-w-0 px-5 py-4">
      <p className="text-xs text-stone-500">{label}</p>
      <p className={`font-semibold tabular-nums text-stone-900 ${hero ? "text-4xl tracking-tight" : "text-xl"}`}>{value}</p>
      {detail && <div className="mt-0.5 text-xs text-stone-500">{detail}</div>}
    </div>
  );
}

export default function CrewDayProfit() {
  const isAdmin = !!currentMe()?.isAdmin;
  const [season, setSeason] = useState(currentSeasonLabel());
  const [data, setData] = useState<Out | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | Status>("all");
  const [kind, setKind] = useState<"all" | Kind>("all");
  const [open, setOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!isAdmin) return;
    let live = true;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await apiClient.request({ path: `/routes/install-costs/crew-days?season=${encodeURIComponent(season)}`, method: "GET" });
        if (!res.ok) {
          let why = "Couldn't load the crew-days";
          try { const j = await res.json(); if (j?.detail) why = String(j.detail); } catch { /* no body */ }
          throw new Error(why);
        }
        const j = (await res.json()) as Out;
        if (live) setData(j);
      } catch (e) {
        const why = e instanceof Error ? e.message : "Couldn't load the crew-days";
        if (live) { setError(why); setData(null); }
        toast.error(why);
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [season, isAdmin]);

  const days = useMemo(() => (data?.days || []).filter((d) => (filter === "all" || d.status === filter)
    && (kind === "all" || d.kind === kind)), [data, filter, kind]);
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  if (!isAdmin) {
    return (
      <Layout>
        <div className="p-8 text-sm text-stone-600">Install &amp; Takedown Profit is for admins only.</div>
      </Layout>
    );
  }

  const s = kind === "all" ? data?.summary : data?.by_kind?.[kind] ?? data?.summary;
  const actual = data?.mode === "actual";
  const target = data?.target_profit_pct ?? null;

  return (
    <Layout>
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-stone-900">Install &amp; Takedown Profit</h1>
            <p className="mt-1 max-w-2xl text-sm text-stone-500">
              {actual
                ? `What ${data?.season}'s installs and takedowns really cost and earned: real clock times, real crews, real invoices. Only admins see this page.`
                : "Every install and takedown crew-day: what its jobs bring in against crew pay, van, trailer, gas and overhead. Only admins see this page."}
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-stone-600">
            {data && (
              <span>
                Overhead <b className="text-stone-800">{data.overhead_pct ?? "—"}%</b> · Target profit <b className="text-stone-800">{target ?? "—"}%</b>
                {" · "}<Link to="/settings" className="font-semibold text-emerald-700 hover:underline">Install Costs</Link>
              </span>
            )}
            <label className="flex items-center gap-2">
              Season
              <select className="rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm" value={season} onChange={(e) => setSeason(e.target.value)}>
                {[Number(currentSeasonLabel()) + 1, Number(currentSeasonLabel()), Number(currentSeasonLabel()) - 1].map((y) => (
                  <option key={y} value={String(y)}>{y}{y < Number(currentSeasonLabel()) ? " · what happened" : y === Number(currentSeasonLabel()) ? " · plan" : ""}</option>
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
            {actual && (
              <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
                Built from the {data.season} client sheet{data.history_source ? ` (${data.history_source})` : ""}: real start and end times, the crews written
                on each job and the day-by-day crew lists, and each job's invoice. Every crew is paid from 8:00 am at the warehouse until it gets back.
                {data.card_season && data.card_season !== data.season ? ` Priced at the ${data.card_season} cost card (same rates in ${data.season}).` : ""}
              </div>
            )}
            {data.missing_card.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                Some numbers are placeholders: the install cost card still needs {data.missing_card.join(", ")}.{" "}
                <Link to="/settings" className="font-semibold underline">Fill it in</Link>
              </div>
            )}
            {(() => {
              const crewless = data.days.filter((d) => d.cost.missing.includes("crew")).length;
              const noRate = data.days.filter((d) => d.cost.missing.includes("pay rate")).length;
              if (!crewless && !noRate) return null;
              return (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  {crewless > 0 && <>{crewless} day{crewless === 1 ? " has" : "s have"} nobody staffed and no role needs on {crewless === 1 ? "its" : "their"} jobs, so crew pay is missing from {crewless === 1 ? "it" : "them"}. </>}
                  {noRate > 0 && <>{noRate} day{noRate === 1 ? " has" : "s have"} someone whose pay class has no rate. </>}
                  Those days are marked *.
                </div>
              );
            })()}

            <div className="grid overflow-hidden rounded-xl border border-stone-200 bg-white sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr_1fr] lg:divide-x lg:divide-stone-100">
              <Tile hero label={`Net profit, ${s.days} crew-days`} value={pct(s.net_pct)}
                detail={<>{money0(s.net)} after every day's costs and {data.overhead_pct}% overhead</>} />
              <Tile label="Revenue" value={money0(s.revenue)}
                detail={actual ? "(invoice − storage) ÷ 2 for the install, the same for the takedown" : "install price on install days, takedown price on takedown days"} />
              <Tile label="Crew-day costs" value={money0(s.cost)}
                detail={<>{s.labor != null ? `${money0(s.labor)} crew pay · ` : ""}{actual ? `${s.staffed_days} of ${s.days} with a real crew` : `${s.staffed_days} of ${s.days} days staffed`}
                  {s.unpriced_cost > 0 && <span className="block">{money0(s.unpriced_cost)} on jobs with no price</span>}</>} />
              <Tile label="Overhead share" value={money0(s.overhead)} detail={`${data.overhead_pct}% of revenue`} />
              <Tile label="Days" value={String(s.days)}
                detail={
                  <span className="flex flex-wrap gap-x-2">
                    {(["healthy", "tight", "losing", "unpriced"] as Status[]).filter((k) => s.counts[k]).map((k) => (
                      <span key={k} className="flex items-center gap-1"><i className={`inline-block h-2 w-2 rounded-full ${STATUS[k].dot}`} />{s.counts[k]} {STATUS[k].label.toLowerCase()}</span>
                    ))}
                  </span>
                } />
            </div>

            {data.by_kind && (
              <div className="grid gap-3 sm:grid-cols-2">
                {(["install", "takedown"] as Kind[]).map((k) => {
                  const t = data.by_kind![k];
                  return (
                    <button key={k} type="button" onClick={() => setKind(kind === k ? "all" : k)}
                      className={`flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border bg-white px-4 py-3 text-left text-xs ${kind === k ? "border-stone-900" : "border-stone-200 hover:border-stone-300"}`}>
                      <span className="text-sm font-semibold text-stone-900">{k === "install" ? "Installs" : "Takedowns"}</span>
                      <span className="text-stone-500">{t.days} crew-days · {money0(t.revenue)} in · {money0(t.cost)} cost</span>
                      <span className="text-base font-semibold tabular-nums text-stone-900">{pct(t.net_pct)}</span>
                    </button>
                  );
                })}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              {KINDS.map((k) => (
                <button key={k.id} type="button" onClick={() => setKind(k.id)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${kind === k.id ? "border-emerald-800 bg-emerald-800 text-white" : "border-stone-200 bg-white text-stone-600 hover:bg-stone-50"}`}>
                  {k.label}
                </button>
              ))}
              <span className="mx-1 h-4 w-px bg-stone-200" />
              {FILTERS.filter((f) => f.id === "all" || s.counts[f.id as Status]).map((f) => (
                <button key={f.id} type="button" onClick={() => setFilter(f.id)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${filter === f.id ? "border-stone-900 bg-stone-900 text-white" : "border-stone-200 bg-white text-stone-600 hover:bg-stone-50"}`}>
                  {f.label}{f.id !== "all" && <span className="ml-1 opacity-70">{s.counts[f.id as Status]}</span>}
                </button>
              ))}
              <span className="ml-auto text-xs text-stone-500">
                Bar: net % on a −50% to +75% scale; the dark tick is the {target}% target.
              </span>
            </div>

            <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
              <table className="w-full min-w-[920px] text-sm">
                <thead>
                  <tr className="border-b border-stone-200 text-left text-[10px] uppercase tracking-wide text-stone-400">
                    <th className="px-4 py-2 font-semibold">Day</th>
                    <th className="px-2 py-2 font-semibold">Jobs</th>
                    <th className="px-2 py-2 font-semibold">Crew</th>
                    <th className="px-2 py-2 text-right font-semibold">Paid</th>
                    <th className="px-2 py-2 text-right font-semibold">Day cost</th>
                    <th className="px-2 py-2 text-right font-semibold">Revenue</th>
                    <th className="px-2 py-2 text-right font-semibold">Net</th>
                    <th className="px-4 py-2 font-semibold">Net %</th>
                  </tr>
                </thead>
                <tbody>
                  {days.map((d) => {
                    const isOpen = open.has(d.id);
                    return (
                      <React.Fragment key={d.id}>
                        <tr onClick={() => toggle(d.id)} className={`cursor-pointer border-b border-stone-100 hover:bg-stone-50 ${isOpen ? "bg-stone-50" : ""}`}>
                          <td className="whitespace-nowrap px-4 py-2.5 align-top">
                            <div className="flex items-center gap-1.5 font-medium text-stone-900">
                              {d.kind === "takedown" && !actual ? "January" : fmtDate(d.date)}
                              <span className={`rounded px-1 py-px text-[9px] font-bold uppercase tracking-wide ${d.kind === "takedown" ? "bg-violet-50 text-violet-700" : "bg-sky-50 text-sky-700"}`}>
                                {d.kind === "takedown" ? "Takedown" : "Install"}
                              </span>
                            </div>
                            <div className="text-xs text-stone-500">
                              {d.crew}{d.night ? " · night" : ""}
                              {d.kind === "takedown" && !actual && d.takedown_of ? ` · installed ${fmtDate(d.takedown_of)}` : ""}
                            </div>
                            {d.times && <div className="text-[10px] text-stone-400">{TIMES[d.times]}</div>}
                          </td>
                          <td className="max-w-[260px] px-2 py-2.5 align-top">
                            <div className="truncate text-stone-800" title={d.stops.map((x) => x.name).join(", ")}>
                              {d.stops.map((x) => x.name).join(", ")}
                            </div>
                            <div className="text-xs text-stone-500">{d.stops.length} job{d.stops.length === 1 ? "" : "s"} · {d.miles} mi</div>
                          </td>
                          <td className="px-2 py-2.5 align-top text-xs">
                            <div className="text-stone-700">{d.crew_people.length} people</div>
                            <div className="text-stone-500">
                              {actual
                                ? (d.crew_source || "")
                                : d.staffed_count === 0 ? "estimated" : d.estimated_count ? `${d.staffed_count} staffed + ${d.estimated_count} est.` : "staffed"}
                              {!actual && d.crew_basis && <span className="block text-[10px] text-stone-400">from {d.crew_basis === "2025 crew" ? "last year's crew" : "role needs"}</span>}
                            </div>
                          </td>
                          <td className="px-2 py-2.5 text-right align-top tabular-nums text-stone-700">{hrs(d.paid_hours)}</td>
                          <td className="px-2 py-2.5 text-right align-top tabular-nums text-stone-700">{money0(d.cost.total)}{d.placeholder && <span className="ml-1 text-[10px] text-red-700">*</span>}</td>
                          <td className="px-2 py-2.5 text-right align-top tabular-nums text-stone-700">{money0(d.revenue)}</td>
                          <td className={`px-2 py-2.5 text-right align-top font-semibold tabular-nums ${d.net != null && d.net < 0 ? "text-red-700" : "text-stone-900"}`}>{money0(d.net)}</td>
                          <td className="px-4 py-2.5 align-top">
                            <div className="flex items-center gap-2">
                              <span className="w-14 text-right font-semibold tabular-nums text-stone-900">{pct(d.net_pct)}</span>
                              <NetBar value={d.net_pct} target={target} />
                            </div>
                            <span className={`mt-1 inline-block rounded-full border px-1.5 py-px text-[10px] font-semibold ${STATUS[d.status].chip}`}>{STATUS[d.status].label}</span>
                          </td>
                        </tr>
                        {isOpen && <DayDetail d={d} overheadPct={data.overhead_pct} />}
                      </React.Fragment>
                    );
                  })}
                  {days.length === 0 && (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-stone-500">No crew-days match that filter.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {actual ? (
            <p className="text-xs leading-relaxed text-stone-500">
              Each crew is paid from 8:00 am at the warehouse until it is back: loading (2 min a box), the drive out, every job from its real start to its
              real end, the drives between, and the drive back. A job with no real times takes its estimate, after the crew's last timed job. A takedown with
              no written time takes {data.takedown_time_factor ?? 0.6} x its real install time. The crew is, most specific first: the names written on the job,
              the job's head count ("Crew A (6)"), the day's crew list from the crew schedule tabs, then the job's role needs. Revenue is (invoice − boxes × $75
              storage) ÷ 2 for the install and the same for the takedown. Dallas nights are costed from the first job to the last; the drive to Dallas and the
              hotel are not included.
            </p>
            ) : (
            <p className="text-xs leading-relaxed text-stone-500">
              Takedown days are estimates: each install crew-day's crew and route in January, with on-site time × the takedown factor, earning the takedown price.
              Revenue on install days is each job's install price (takedown is earned on the takedown trip; storage covers the warehouse, which is in overhead).
              A job worked over several days is split across them by on-site time. Paid hours run depot to depot: the longer of the 30-minute early
              arrival and the warehouse loading, then drives, on-site time and lunch. Until a day is fully staffed, the rest of the crew is estimated from last year's real crew on those jobs (one lead, the rest general), or from the jobs' role needs when there's no 2025 crew on record.
              Miles are straight-line between stops times the scheduler's road factor.
            </p>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}

const actualStop = (x: Stop) => x.invoice !== undefined;

function DayDetail({ d, overheadPct }: { d: Day; overheadPct: number | null }) {
  const c = d.cost;
  const lines: Array<[string, number]> = [
    [`Crew pay · ${d.crew_people.length} people × ${hrs(d.paid_hours)}`, c.labor],
    ["Van", c.van], ["Trailer", c.trailer], [`Gas · ${d.miles} mi`, c.gas],
    ...(c.insurance ? [["Rental insurance", c.insurance] as [string, number]] : []),
    ...(c.wear ? [["Wear", c.wear] as [string, number]] : []),
    ["Ancillary", c.ancillary],
    ...(c.tolls ? [["Tolls", c.tolls] as [string, number]] : []),
    ...(c.parking ? [["Parking", c.parking] as [string, number]] : []),
  ];
  return (
    <tr className="border-b border-stone-200 bg-stone-50/70">
      <td colSpan={8} className="px-4 pb-4 pt-1">
        <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
          <div className="space-y-3">
            <div className="divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white text-xs">
              {lines.map(([l, v]) => (
                <div key={l} className="flex justify-between px-3 py-1.5"><span className="text-stone-600">{l}</span><span className="tabular-nums text-stone-800">{formatCurrency(v)}</span></div>
              ))}
              <div className="flex justify-between bg-stone-50 px-3 py-1.5 font-semibold"><span>Day cost</span><span className="tabular-nums">{formatCurrency(c.total)}</span></div>
              {d.overhead != null && (
                <div className="flex justify-between px-3 py-1.5"><span className="text-stone-600">Overhead · {overheadPct}% of {money0(d.revenue)}</span><span className="tabular-nums text-stone-800">{formatCurrency(d.overhead)}</span></div>
              )}
              {c.missing.length > 0 && <div className="px-3 py-1.5 text-red-700">* placeholder: still needs {c.missing.join(", ")}</div>}
            </div>
            <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-600">
              <p className="mb-1 font-semibold text-stone-700">Crew{d.crew_source ? ` · ${d.crew_source}` : ""}</p>
              {d.clock_out_min != null && d.anchored && (
                <p className="mb-1 text-stone-500">On the clock 8:00 am → {clock(d.clock_out_min)} back at the warehouse.</p>
              )}
              {d.crew_basis && !d.crew_source && (
                <p className="mb-1 text-stone-500">
                  {d.crew_basis === "2025 crew"
                    ? "Estimated seats: last year's real crew on these jobs (the largest), one lead and the rest general."
                    : "Estimated seats: these jobs have no 2025 crew on record, so the crew comes from their role needs."}
                </p>
              )}
              <ul className="space-y-0.5">
                {d.crew_people.map((p, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span className={p.name ? "text-stone-800" : "italic text-stone-500"}>
                      {p.name || `${p.label} (estimated)`}{p.half ? " · half day" : ""}{p.temp ? " · Xclusive temp" : ""}
                    </span>
                    <span className="tabular-nums">{p.name ? `${p.label} · ` : ""}{p.rate == null ? "no rate" : `${formatCurrency(p.rate)}/h`}</span>
                  </li>
                ))}
                {d.crew_people.length === 0 && <li>No one staffed and no role needs on these jobs.</li>}
              </ul>
              <p className="mt-2 text-stone-500">
                {d.anchored ? `${d.pretrip_min} min before the trip (${d.boxes} boxes to load), ` : ""}
                {d.lunch_min ? `${d.lunch_min} min lunch, ` : ""}all paid.
              </p>
            </div>
            {d.notes.map((n) => <p key={n} className="text-xs text-stone-500">{n}</p>)}
          </div>
          <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-stone-200 text-left text-[10px] uppercase tracking-wide text-stone-400">
                  <th className="px-3 py-1.5 font-semibold">Job</th>
                  {d.stops.some((x) => x.start != null) && <th className="px-2 py-1.5 font-semibold">Clock</th>}
                  <th className="px-2 py-1.5 text-right font-semibold">On site</th>
                  <th className="px-2 py-1.5 text-right font-semibold">{d.kind === "takedown" ? "Takedown price" : "Install price"}</th>
                  <th className="px-2 py-1.5 text-right font-semibold">Share of day cost</th>
                  <th className="px-2 py-1.5 text-right font-semibold">Net</th>
                  <th className="px-3 py-1.5 text-right font-semibold">Net %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {d.stops.map((x, i) => (
                  <tr key={`${x.row}-${i}`}>
                    <td className="px-3 py-1.5">
                      <div className="text-stone-800">{x.name}</div>
                      <div className="text-[10px] text-stone-500">
                        {x.source === "unpriced" ? (actualStop(x) ? "no invoice on file" : "no price yet") : x.source === "no_charge" ? "no charge"
                          : x.source === "schedule" ? "price from the schedule"
                          : x.source === "invoice" ? `invoice ${money0(x.invoice)} − ${money0(x.storage)} storage, half` : "price from Clients"}
                        {x.share < 0.999 ? ` · ${Math.round(x.share * 100)}% of the job today` : ""}
                        {x.basis ? ` · ${x.basis}` : ""}
                      </div>
                    </td>
                    {d.stops.some((y) => y.start != null) && (
                      <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">
                        {x.start != null ? `${clock(x.start)}–${clock(x.end)}` : "—"}
                        <span className="block text-[10px] text-stone-400">{x.real_times ? "real" : "estimated"}</span>
                      </td>
                    )}
                    <td className="px-2 py-1.5 text-right tabular-nums">{hrs(x.onsite_h)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{x.revenue == null ? "—" : money0(x.revenue)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{money0(x.cost)}</td>
                    <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${x.net != null && x.net < 0 ? "text-red-700" : "text-stone-900"}`}>{money0(x.net)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{pct(x.net_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </td>
    </tr>
  );
}
