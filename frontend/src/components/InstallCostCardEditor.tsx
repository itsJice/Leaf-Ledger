import React, { useEffect, useMemo, useState } from "react";
import { Calculator, Check, Copy, Plus, Trash2 } from "components/icons";
import { toast } from "sonner";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel } from "utils/season";

/**
 * Settings > Install Costs: what a Christmas install costs US to run (backend
 * app.libs.install_costs, table ll_app.install_cost_rates) -- the other side
 * of the Christmas rate card. Pay is by class; each installer is assigned a
 * class in the Roster pay classes table below (ll_app.install_pay_assignments), and
 * anyone not assigned is paid as their roster title. Admin-only: pay is
 * private, so the whole tab is hidden from everyone else.
 */

type PayClass = { slug: string; label: string; rate: number | null };
type CardOut = {
  season: string;
  costs: Record<string, number>;
  classes: PayClass[];
  own: string[];
  seasons: string[];
  missing: string[];
  derived: { gas_per_mile: number | null; break_even_pct: number | null; target_spend_pct: number | null };
};
type PersonPay = {
  person_id: string; name: string; title: string; pay_class: string; pay_label: string;
  assigned: boolean; rate_override: number | null; rate: number | null; source: string;
};

type Group = "vehicles" | "day" | "warehouse" | "company";
const ROWS: Array<{ key: string; label: string; unit: string; help: string; group: Group; required?: boolean }> = [
  { key: "van_day", label: "Van rental", unit: "$ / van / day", help: "Every day a crew goes out.", group: "vehicles", required: true },
  { key: "trailer_day", label: "Trailer rental", unit: "$ / trailer / day", help: "", group: "vehicles", required: true },
  { key: "vans_per_crew", label: "Vans per crew", unit: "vans", help: "", group: "vehicles" },
  { key: "trailers_per_crew", label: "Trailers per crew", unit: "trailers", help: "", group: "vehicles" },
  { key: "rental_insurance_day", label: "Rental insurance", unit: "$ / vehicle / day", help: "Damage waiver, if you take it. Blank counts as $0.", group: "vehicles" },
  { key: "mpg", label: "Van fuel economy", unit: "miles / gallon", help: "", group: "vehicles", required: true },
  { key: "gas_per_gallon", label: "Gas", unit: "$ / gallon", help: "Gas = the day's route miles ÷ MPG × this.", group: "vehicles", required: true },
  { key: "wear_per_mile", label: "Wear & maintenance", unit: "$ / mile", help: "Tires and routine repairs. Blank counts as $0.", group: "vehicles" },
  { key: "ancillary_day", label: "Ancillary", unit: "$ / crew / day", help: "The things that just come up.", group: "day" },
  { key: "tolls_day", label: "Tolls", unit: "$ / crew / day", help: "Blank counts as $0.", group: "day" },
  { key: "parking_day", label: "Parking", unit: "$ / crew / day", help: "Blank counts as $0.", group: "day" },
  { key: "load_min_per_box", label: "Loading", unit: "min / box", help: "Pull from the shelf and load the trailer, each way. Paid at the crew's own rates.", group: "warehouse" },
  { key: "prep_min_per_job", label: "Job prep", unit: "min / job", help: "Staging and checking lights before the trip. Blank counts as none.", group: "warehouse" },
  { key: "takedown_time_factor", label: "Takedown time", unit: "× install time", help: "How long takedown takes next to install. Blank uses 0.6, your sheet's estimate. Only time: the takedown price always equals the install price.", group: "warehouse" },
  { key: "overhead_pct", label: "Overhead", unit: "% of revenue", help: "Operating costs not charged to any one job: warehouse, software, insurance, admin.", group: "company", required: true },
  { key: "target_profit_pct", label: "Target profit", unit: "% of revenue", help: "What a job should leave after its own costs and its share of overhead.", group: "company", required: true },
];
const GROUP_LABEL: Record<Group, string> = {
  vehicles: "Vans, trailers & gas",
  day: "Every crew-day",
  warehouse: "Warehouse time",
  company: "Overhead & profit",
};

function seasonChoices(known: string[]): string[] {
  const now = Number(currentSeasonLabel());
  const set = new Set<string>([...known, String(now), String(now + 1)]);
  return [...set].sort((a, b) => b.localeCompare(a));
}

function num(s: string | undefined): number | null {
  const t = (s ?? "").trim().replace(/[$,]/g, "");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

async function errorOf(res: Response, fallback: string): Promise<string> {
  try { const j = await res.json(); if (j?.detail) return String(j.detail); } catch { /* no body */ }
  return fallback;
}

/** One crew-day at these numbers -- the same arithmetic as backend
 *  install_costs.crew_day_cost(), shown here only as a live example. */
function dayExample(card: Record<string, number | null>, crew: Array<number | null>, hours: number, miles: number) {
  const v = (k: string, d = 0) => card[k] ?? d;
  const vans = v("vans_per_crew", 1), trailers = v("trailers_per_crew", 1);
  const known = crew.filter((r): r is number => r != null);
  const labor = known.reduce((a, b) => a + b, 0) * hours;
  const van = card.van_day != null ? card.van_day * vans : null;
  const trailer = card.trailer_day != null ? card.trailer_day * trailers : null;
  const insurance = v("rental_insurance_day") * (vans + trailers);
  const gas = card.mpg && card.gas_per_gallon != null ? (miles / card.mpg) * card.gas_per_gallon * vans : null;
  const wear = v("wear_per_mile") * miles * vans;
  const fixed = v("ancillary_day") + v("tolls_day") + v("parking_day");
  const lines = [
    { label: `Crew pay (${known.length} people × ${hours} h)`, value: labor },
    { label: `Van${vans === 1 ? "" : "s"}`, value: van },
    { label: `Trailer${trailers === 1 ? "" : "s"}`, value: trailer },
    { label: `Gas (${miles} mi)`, value: gas },
    { label: "Insurance, wear", value: insurance + wear },
    { label: "Ancillary, tolls, parking", value: fixed },
  ];
  const missing = lines.some((l) => l.value == null) || known.length < crew.length;
  const total = lines.reduce((a, l) => a + (l.value ?? 0), 0);
  return { lines, total, missing };
}

const input = "w-20 rounded-lg border border-stone-200 px-2 py-1 text-right text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300";

export default function InstallCostCardEditor() {
  const [season, setSeason] = useState(currentSeasonLabel());
  const [data, setData] = useState<CardOut | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [classDraft, setClassDraft] = useState<Record<string, { label: string; rate: string }>>({});
  const [newClass, setNewClass] = useState({ label: "", rate: "" });
  const [removed, setRemoved] = useState<string[]>([]);
  const [people, setPeople] = useState<PersonPay[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [ex, setEx] = useState({ lead: "1", general: "4", hours: "10", miles: "60" });

  const adopt = (j: CardOut) => {
    setData(j);
    setDraft(Object.fromEntries(Object.entries(j.costs).map(([k, v]) => [k, String(v)])));
    setClassDraft(Object.fromEntries(j.classes.map((c) => [c.slug, { label: c.label, rate: c.rate == null ? "" : String(c.rate) }])));
    setRemoved([]);
    setNewClass({ label: "", rate: "" });
  };

  const loadPeople = async (s: string) => {
    try {
      const res = await apiClient.request({ path: `/routes/install-costs/people?season=${encodeURIComponent(s)}`, method: "GET" });
      if (!res.ok) throw new Error(await errorOf(res, "Couldn't load the crew"));
      setPeople(((await res.json()) as { people: PersonPay[] }).people);
    } catch (e) {
      setPeople([]);
      toast.error(e instanceof Error ? e.message : "Couldn't load the crew");
    }
  };

  const load = async (s: string) => {
    setLoading(true);
    try {
      const res = await apiClient.request({ path: `/routes/install-costs/card?season=${encodeURIComponent(s)}`, method: "GET" });
      if (!res.ok) throw new Error(await errorOf(res, "Couldn't load the cost card"));
      adopt((await res.json()) as CardOut);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't load the cost card");
    } finally {
      setLoading(false);
    }
    void loadPeople(s);
  };

  useEffect(() => { void load(season); }, [season]);

  const costChanges = useMemo(() => {
    if (!data) return {} as Record<string, number | null>;
    const out: Record<string, number | null> = {};
    ROWS.forEach(({ key }) => {
      const raw = (draft[key] ?? "").trim();
      const n = num(raw);
      if (raw !== "" && n == null) return; // not a number yet; don't send
      const had = data.costs[key] ?? null;
      if (n !== had || (n != null && !data.own.includes(key))) out[key] = n;
    });
    return out;
  }, [data, draft]);

  const classChanges = useMemo(() => {
    if (!data) return [] as Array<{ slug?: string; label: string; rate: number | null }>;
    const out: Array<{ slug?: string; label: string; rate: number | null }> = [];
    data.classes.forEach((c) => {
      if (removed.includes(c.slug)) return;
      const d = classDraft[c.slug];
      if (!d) return;
      const rate = num(d.rate);
      if (d.rate.trim() !== "" && rate == null) return;
      const label = d.label.trim() || c.label;
      if (label !== c.label || rate !== c.rate || !data.own.includes(`pay:${c.slug}`)) out.push({ slug: c.slug, label, rate });
    });
    if (newClass.label.trim()) out.push({ label: newClass.label.trim(), rate: num(newClass.rate) });
    return out;
  }, [data, classDraft, newClass, removed]);

  const changeCount = Object.keys(costChanges).length + classChanges.length + removed.length;

  const save = async (copy: boolean) => {
    setSaving(true);
    try {
      const res = await apiClient.request({
        path: "/routes/install-costs/card",
        method: "PUT",
        body: copy
          ? { season, copy_from_inherited: true }
          : { season, costs: costChanges, classes: classChanges, remove_classes: removed },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await errorOf(res, "Couldn't save the cost card"));
      adopt((await res.json()) as CardOut);
      toast.success(copy ? `${season} now has its own cost card` : `${season} costs saved`);
      void loadPeople(season);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save the cost card");
    } finally {
      setSaving(false);
    }
  };

  const assign = async (p: PersonPay, payClass: string | null, override: number | null) => {
    try {
      const res = await apiClient.request({
        path: `/routes/install-costs/people/${encodeURIComponent(p.person_id)}`,
        method: "PUT",
        body: { name: p.name, pay_class: payClass, rate_override: override },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await errorOf(res, "Couldn't save that"));
      toast.success(`${p.name} saved`);
      void loadPeople(season);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save that");
    }
  };

  const liveCard = useMemo(() => {
    const out: Record<string, number | null> = {};
    ROWS.forEach(({ key }) => { out[key] = num(draft[key]); });
    return out;
  }, [draft]);
  const rateOf = (slug: string) => num(classDraft[slug]?.rate);
  const example = dayExample(
    liveCard,
    [...Array(Math.max(0, Math.floor(Number(ex.lead) || 0))).fill(rateOf("lead")),
     ...Array(Math.max(0, Math.floor(Number(ex.general) || 0))).fill(rateOf("general"))],
    Number(ex.hours) || 0,
    Number(ex.miles) || 0,
  );
  const oh = liveCard.overhead_pct, profit = liveCard.target_profit_pct;

  const inherited = data ? ROWS.filter(({ key }) => data.costs[key] != null && !data.own.includes(key)).length
    + data.classes.filter((c) => !data.own.includes(`pay:${c.slug}`)).length : 0;

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
      </div>
    );
  }

  const needs = (
    <span className="ml-1.5 rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">NEEDS INPUT</span>
  );
  const inheritedChip = <span className="ml-1.5 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">inherited</span>;

  return (
    <div className="max-w-5xl space-y-6">
      <div className="rounded-xl border border-stone-200 bg-white p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
              <Calculator size={15} className="text-emerald-700" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-stone-800">Install cost card</h2>
              <p className="text-xs text-stone-500">What an install costs us to run, per season. Only admins see this page.</p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-stone-600">
            Season
            <select className="rounded-lg border border-stone-200 px-2 py-1.5 text-sm" value={season} onChange={(e) => setSeason(e.target.value)}>
              {seasonChoices(data.seasons).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>

        {inherited > 0 && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <span>{season} has no cost card of its own yet. The values marked <em>inherited</em> come from the latest earlier season.</span>
            <button type="button" disabled={saving} onClick={() => void save(true)} className="flex items-center gap-1 rounded-md border border-amber-300 bg-white px-2 py-2 font-semibold text-amber-800 sm:py-1 hover:bg-amber-100 disabled:opacity-60">
              <Copy size={12} /> Make these {season}'s own
            </button>
          </div>
        )}
        {data.missing.length > 0 && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
            {data.missing.length} number{data.missing.length === 1 ? "" : "s"} still needed. Any cost built on them is a placeholder until they are filled in.
          </div>
        )}

        <div className="mb-4">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">Crew pay by class</p>
          <div className="divide-y divide-stone-100 rounded-lg border border-stone-200">
            {data.classes.filter((c) => !removed.includes(c.slug)).map((c) => {
              const d = classDraft[c.slug] || { label: c.label, rate: "" };
              const own = data.own.includes(`pay:${c.slug}`);
              return (
                <div key={c.slug} className="grid items-center gap-3 px-3 py-2 text-xs sm:grid-cols-[220px_190px_1fr]">
                  <div className="flex items-center">
                    <input
                      aria-label="Class name"
                      className="w-40 rounded-lg border border-transparent px-1.5 py-1 text-sm font-medium text-stone-800 hover:border-stone-200 focus:border-stone-300 focus:outline-none"
                      value={d.label}
                      onChange={(e) => setClassDraft((s) => ({ ...s, [c.slug]: { ...d, label: e.target.value } }))}
                    />
                    {c.rate != null && !own && inheritedChip}
                    {(d.rate.trim() === "") && needs}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <input inputMode="decimal" aria-label={`${c.label} hourly pay`} className={input} value={d.rate}
                      onChange={(e) => setClassDraft((s) => ({ ...s, [c.slug]: { ...d, rate: e.target.value } }))} />
                    <span className="whitespace-nowrap text-[10px] text-stone-400">$ / hour</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-stone-500">
                    <span>{people ? `${people.filter((p) => p.pay_class === c.slug).length} on the roster` : ""}</span>
                    <button type="button" title={`Remove ${c.label}`} onClick={() => setRemoved((r) => [...r, c.slug])}
                      className="rounded-md p-2 text-stone-400 sm:p-1 hover:bg-red-50 hover:text-red-600">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              );
            })}
            <div className="grid items-center gap-3 bg-stone-50/60 px-3 py-2 text-xs sm:grid-cols-[220px_190px_1fr]">
              <input placeholder="Add a class, e.g. Trainee" aria-label="New class name"
                className="w-44 rounded-lg border border-stone-200 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                value={newClass.label} onChange={(e) => setNewClass((n) => ({ ...n, label: e.target.value }))} />
              <div className="flex items-center gap-1.5">
                <input inputMode="decimal" aria-label="New class hourly pay" className={input} value={newClass.rate}
                  onChange={(e) => setNewClass((n) => ({ ...n, rate: e.target.value }))} />
                <span className="whitespace-nowrap text-[10px] text-stone-400">$ / hour</span>
              </div>
              <p className="flex items-center gap-1 text-stone-500"><Plus size={12} /> Saved with the rest of the card.</p>
            </div>
          </div>
          <p className="mt-1.5 text-[11px] text-stone-500">
            1099, paid hourly for the whole shift, depot to depot. Lunch, driving and loading are paid. No overtime, burden or minimum.
          </p>
        </div>

        {(["vehicles", "day", "warehouse", "company"] as const).map((g) => (
          <div key={g} className="mb-4">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">{GROUP_LABEL[g]}</p>
            <div className="divide-y divide-stone-100 rounded-lg border border-stone-200">
              {ROWS.filter((r) => r.group === g).map(({ key, label, unit, help, required }) => {
                const own = data.own.includes(key);
                const blank = (draft[key] ?? "").trim() === "";
                return (
                  <div key={key} className="grid items-center gap-3 px-3 py-2 text-xs sm:grid-cols-[220px_190px_1fr]">
                    <div>
                      <span className="font-medium text-stone-800">{label}</span>
                      {data.costs[key] != null && !own && inheritedChip}
                      {required && blank && needs}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <input inputMode="decimal" aria-label={label} className={input} value={draft[key] ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />
                      <span className="whitespace-nowrap text-[10px] text-stone-400">{unit}</span>
                    </div>
                    <p className="text-stone-500">
                      {key === "gas_per_gallon" && liveCard.mpg && liveCard.gas_per_gallon != null
                        ? `${help} That's ${formatCurrency(liveCard.gas_per_gallon / liveCard.mpg)} a mile.`
                        : help}
                    </p>
                  </div>
                );
              })}
            </div>
            {g === "company" && oh != null && (
              <p className="mt-1.5 text-[11px] leading-relaxed text-stone-500">
                A job breaks even when its crew, vans and materials stay under <b className="text-stone-700">{(100 - oh).toFixed(1)}%</b> of its price.
                {profit != null && <> To hit the target, keep them under <b className="text-stone-700">{(100 - oh - profit).toFixed(1)}%</b>.</>}
              </p>
            )}
          </div>
        ))}

        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-stone-400">{changeCount ? `${changeCount} change(s) for ${season}` : "No changes"}</span>
          <button
            type="button"
            disabled={saving || changeCount === 0}
            onClick={() => void save(false)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
          >
            <Check size={12} strokeWidth={3} />
            {saving ? "Saving…" : `Save ${season} costs`}
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-4 sm:p-6">
        <h2 className="text-sm font-semibold text-stone-800">What one crew-day costs</h2>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-stone-500">
          A live example at the numbers above, before you save. The crew-day view on the schedule will use each day's real crew, hours and route miles.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-stone-600">
          <label className="flex items-center gap-1.5">Leads <input inputMode="numeric" className="w-12 rounded-lg border border-stone-200 px-2 py-1 text-right" value={ex.lead} onChange={(e) => setEx((s) => ({ ...s, lead: e.target.value }))} /></label>
          <label className="flex items-center gap-1.5">General <input inputMode="numeric" className="w-12 rounded-lg border border-stone-200 px-2 py-1 text-right" value={ex.general} onChange={(e) => setEx((s) => ({ ...s, general: e.target.value }))} /></label>
          <label className="flex items-center gap-1.5">Shift <input inputMode="decimal" className="w-14 rounded-lg border border-stone-200 px-2 py-1 text-right" value={ex.hours} onChange={(e) => setEx((s) => ({ ...s, hours: e.target.value }))} /> h</label>
          <label className="flex items-center gap-1.5">Route <input inputMode="numeric" className="w-14 rounded-lg border border-stone-200 px-2 py-1 text-right" value={ex.miles} onChange={(e) => setEx((s) => ({ ...s, miles: e.target.value }))} /> mi</label>
        </div>
        <div className="mt-3 max-w-md divide-y divide-stone-100 rounded-lg border border-stone-200 text-xs">
          {example.lines.map((l) => (
            <div key={l.label} className="flex justify-between px-3 py-1.5">
              <span className="text-stone-600">{l.label}</span>
              <span className="tabular-nums text-stone-800">{l.value == null ? <span className="text-red-700">needs input</span> : formatCurrency(l.value)}</span>
            </div>
          ))}
          <div className="flex justify-between bg-stone-50 px-3 py-2 font-semibold">
            <span>Crew-day cost{example.missing ? " (placeholder)" : ""}</span>
            <span className="tabular-nums">{formatCurrency(example.total)}</span>
          </div>
          {oh != null && liveCard.target_profit_pct != null && 100 - oh - liveCard.target_profit_pct > 0 && (
            <div className="flex justify-between px-3 py-2 text-stone-600">
              <span>Billing needed that day at {liveCard.target_profit_pct}% profit</span>
              <span className="tabular-nums font-semibold text-stone-800">{formatCurrency(example.total / ((100 - oh - liveCard.target_profit_pct) / 100))}</span>
            </div>
          )}
          {oh != null && (
            <div className="flex justify-between px-3 py-2 text-stone-600">
              <span>Billing needed to break even</span>
              <span className="tabular-nums text-stone-800">{formatCurrency(example.total / ((100 - oh) / 100))}</span>
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-4 sm:p-6">
        <h2 className="text-sm font-semibold text-stone-800">Roster pay classes</h2>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-stone-500">
          Everyone on the install roster and the class they're paid as. Pick a class here; it never shows on the schedule, the warehouse iPad or the crew leads' pages. Someone with no class picked is paid as their roster title.
          A personal rate beats the class rate. Leave it blank unless they're the exception.
        </p>
        {people == null ? (
          <p className="mt-3 text-xs text-stone-400">Loading the roster…</p>
        ) : people.length === 0 ? (
          <p className="mt-3 text-xs text-stone-500">No one is on the roster yet. Add installers from the schedule's Staffing tab.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-xs">
              <thead>
                <tr className="border-b border-stone-200 text-left text-[10px] uppercase tracking-wide text-stone-400">
                  <th className="py-1.5 pr-3 font-semibold">Installer</th>
                  <th className="py-1.5 pr-3 font-semibold">Roster title</th>
                  <th className="py-1.5 pr-3 font-semibold">Paid as</th>
                  <th className="py-1.5 pr-3 font-semibold">Personal rate</th>
                  <th className="py-1.5 text-right font-semibold">Per hour</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {people.map((p) => (
                  <PersonRow key={p.person_id} p={p} classes={data.classes} onSave={assign} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function PersonRow({ p, classes, onSave }: {
  p: PersonPay; classes: PayClass[];
  onSave: (p: PersonPay, payClass: string | null, override: number | null) => Promise<void>;
}) {
  const [over, setOver] = useState(p.rate_override == null ? "" : String(p.rate_override));
  useEffect(() => { setOver(p.rate_override == null ? "" : String(p.rate_override)); }, [p.rate_override]);
  const cls = p.assigned ? p.pay_class : "";
  const commitOverride = () => {
    const n = num(over);
    if (over.trim() !== "" && n == null) { setOver(p.rate_override == null ? "" : String(p.rate_override)); return; }
    if (n !== p.rate_override) void onSave(p, p.assigned ? p.pay_class : null, n);
  };
  return (
    <tr>
      <td className="whitespace-nowrap py-1.5 pr-3 font-medium text-stone-800">{p.name}</td>
      <td className="min-w-[7rem] py-1.5 pr-3 text-stone-500">{p.title}</td>
      <td className="py-1.5 pr-3">
        <select className="rounded-lg border border-stone-200 px-2 py-1 text-xs" value={cls}
          onChange={(e) => void onSave(p, e.target.value || null, p.rate_override)}>
          <option value="">As title ({p.assigned ? p.title : p.pay_label})</option>
          {classes.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
        </select>
      </td>
      <td className="py-1.5 pr-3">
        <input inputMode="decimal" placeholder="—" aria-label={`${p.name} personal rate`}
          className="w-20 rounded-lg border border-stone-200 px-2 py-1 text-right text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
          value={over} onChange={(e) => setOver(e.target.value)} onBlur={commitOverride}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
      </td>
      <td className="py-1.5 text-right tabular-nums">
        {p.rate == null
          ? <span className="rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">NEEDS INPUT</span>
          : <span className="text-stone-800">{formatCurrency(p.rate)}{p.source === "override" ? <span className="ml-1 text-[10px] text-stone-400">personal</span> : null}</span>}
      </td>
    </tr>
  );
}
