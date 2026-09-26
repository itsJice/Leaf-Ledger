import React, { useEffect, useMemo, useState } from "react";
import { Check, Copy, TreePine } from "components/icons";
import { toast } from "sonner";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { currentMe } from "utils/me";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel } from "utils/season";

/**
 * Settings > Christmas rates: the rate card a season's ideal prices are
 * computed from (backend app.libs.pricing, table ll_app.pricing_rates).
 * One set of numbers per season; a season with nothing of its own shows
 * the latest earlier season's, marked inherited, until "Make these
 * <season>'s own" copies them down. Anyone signed in can look; admins edit.
 */

type RatesOut = { season: string; rates: Record<string, number>; own: string[]; seasons: string[] };

const ROWS: Array<{ key: string; label: string; unit: string; help: string; group: "site" | "storage" | "logistics" }> = [
  { key: "crew_lead", label: "Crew lead", unit: "$ / person-hour", help: "On site, per crew lead per install hour. Takedown is charged the same again.", group: "site" },
  { key: "specialty", label: "Specialty install labor", unit: "$ / person-hour", help: "Scaffolding, lifts, extra-tall work.", group: "site" },
  { key: "designer", label: "Designer / art director", unit: "$ / person-hour", help: "", group: "site" },
  { key: "general", label: "General install labor", unit: "$ / person-hour", help: "", group: "site" },
  { key: "storage_box", label: "Storage", unit: "$ / box / season", help: "Flat per box, no uplift.", group: "storage" },
  { key: "van_crew_rate", label: "Van crew", unit: "$ / hour", help: "What the crew in the van costs per hour while nobody is being charged: loading at the warehouse and driving.", group: "logistics" },
  { key: "handling_min_per_box", label: "Handling", unit: "min / box", help: "Minutes to move one box between the storage shelf and the trailer. Only for clients we store for.", group: "logistics" },
  { key: "drive_min_default", label: "Default drive", unit: "min one way", help: "Used for a leg the scheduler has not mapped yet. Mapped clients use their real minutes each way.", group: "logistics" },
];

const GROUP_LABEL = { site: "On-site labor", storage: "Storage", logistics: "Pickup & delivery" };

function seasonChoices(known: string[]): string[] {
  const now = Number(currentSeasonLabel());
  const set = new Set<string>([...known, String(now), String(now + 1)]);
  return [...set].sort((a, b) => b.localeCompare(a));
}

/** The pickup & delivery fee for one client at these rates -- the same
 *  arithmetic as backend pricing.ideal(), shown here only as a live example. */
function logisticsExample(rates: Record<string, number>, boxes: number, storing: boolean, out: number, back: number): number | null {
  const van = rates.van_crew_rate, perBox = rates.handling_min_per_box;
  if (van == null || perBox == null) return null;
  const loading = storing ? 2 * boxes * perBox : 0;
  const driving = 2 * (out + back);
  return Math.round(((loading + driving) / 60) * van * 100) / 100;
}

export default function ChristmasRatesEditor() {
  const isAdmin = !!currentMe()?.isAdmin;
  const [season, setSeason] = useState(currentSeasonLabel());
  const [data, setData] = useState<RatesOut | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exBoxes, setExBoxes] = useState("20");
  const [exOut, setExOut] = useState("25");
  const [exBack, setExBack] = useState("30");

  const load = async (s: string) => {
    setLoading(true);
    try {
      const res = await apiClient.request({ path: `/routes/pricing/rates?season=${encodeURIComponent(s)}`, method: "GET" });
      if (!res.ok) throw new Error("Couldn't load the rate card");
      const j = (await res.json()) as RatesOut;
      setData(j);
      setDraft(Object.fromEntries(Object.entries(j.rates).map(([k, v]) => [k, String(v)])));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't load the rate card");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(season); }, [season]);

  const changed = useMemo(() => {
    if (!data) return {};
    const out: Record<string, number> = {};
    ROWS.forEach(({ key }) => {
      const s = (draft[key] ?? "").trim();
      if (s === "") return;
      const n = Number(s);
      if (!Number.isFinite(n) || n < 0) return;
      if (data.rates[key] !== n || !data.own.includes(key)) out[key] = n;
    });
    return out;
  }, [data, draft]);

  const put = async (rates: Record<string, number>, copy: boolean) => {
    setSaving(true);
    try {
      const res = await apiClient.request({
        path: "/routes/pricing/rates",
        method: "PUT",
        body: { season, rates, copy_from_inherited: copy },
        type: ContentType.Json,
      });
      if (!res.ok) {
        let why = "Couldn't save the rate card";
        try { const j = await res.json(); if (j?.detail) why = String(j.detail); } catch { /* no body */ }
        throw new Error(why);
      }
      const j = (await res.json()) as RatesOut;
      setData(j);
      setDraft(Object.fromEntries(Object.entries(j.rates).map(([k, v]) => [k, String(v)])));
      toast.success(copy ? `${season} now has its own rate card` : `${season} rates saved`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save the rate card");
    } finally {
      setSaving(false);
    }
  };

  const rates = data?.rates || {};
  const inherited = data ? ROWS.filter(({ key }) => rates[key] != null && !data.own.includes(key)).length : 0;
  const example = (boxes: number, storing: boolean) =>
    logisticsExample(rates, boxes, storing, Number(exOut) || 0, Number(exBack) || 0);

  return (
    <div className="max-w-5xl space-y-6">
      <div className="rounded-xl border border-stone-200 bg-white p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
              <TreePine size={15} className="text-emerald-700" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-stone-800">Christmas install rates</h2>
              <p className="text-xs text-stone-500">What a job should cost, per season. Every client's ideal price on the Clients tab is their Christmas card × these.</p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-stone-600">
            Season
            <select className="rounded-lg border border-stone-200 px-2 py-1.5 text-sm" value={season} onChange={(e) => setSeason(e.target.value)}>
              {seasonChoices(data?.seasons || []).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>

        {loading || !data ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
          </div>
        ) : (
          <>
            {inherited > 0 && (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <span>{season} has no rate card of its own{data.own.length ? " for every rate" : ""} — the values marked <em>inherited</em> come from the latest earlier season.</span>
                {isAdmin && (
                  <button type="button" disabled={saving} onClick={() => void put({}, true)} className="flex items-center gap-1 rounded-md border border-amber-300 bg-white px-2 py-1 font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-60">
                    <Copy size={12} /> Make these {season}'s own
                  </button>
                )}
              </div>
            )}
            {(["site", "storage", "logistics"] as const).map((g) => (
              <div key={g} className="mb-4">
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">{GROUP_LABEL[g]}</p>
                <div className="divide-y divide-stone-100 rounded-lg border border-stone-200">
                  {ROWS.filter((r) => r.group === g).map(({ key, label, unit, help }) => {
                    const own = data.own.includes(key);
                    return (
                      <div key={key} className="grid items-center gap-3 px-3 py-2 text-xs sm:grid-cols-[180px_190px_1fr]">
                        <div>
                          <span className="font-medium text-stone-800">{label}</span>
                          {rates[key] != null && !own && <span className="ml-1.5 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">inherited</span>}
                          {rates[key] == null && <span className="ml-1.5 rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] text-red-700">not set</span>}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <input
                            inputMode="decimal"
                            disabled={!isAdmin}
                            className="w-20 rounded-lg border border-stone-200 px-2 py-1 text-right text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 disabled:bg-stone-50 disabled:text-stone-500"
                            value={draft[key] ?? ""}
                            onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                          />
                          <span className="whitespace-nowrap text-[10px] text-stone-400">{unit}</span>
                        </div>
                        <p className="text-stone-500">{help}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
            {isAdmin ? (
              <div className="flex items-center justify-end gap-2">
                <span className="text-xs text-stone-400">{Object.keys(changed).length ? `${Object.keys(changed).length} change(s) for ${season}` : "No changes"}</span>
                <button
                  type="button"
                  disabled={saving || Object.keys(changed).length === 0}
                  onClick={() => void put(changed, false)}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                  style={{ backgroundColor: "rgb(var(--ll-brand))" }}
                >
                  <Check size={12} strokeWidth={3} />
                  {saving ? "Saving…" : `Save ${season} rates`}
                </button>
              </div>
            ) : (
              <p className="text-right text-xs text-stone-400">Only an admin can change rates.</p>
            )}
          </>
        )}
      </div>

      {data && (
        <div className="rounded-xl border border-stone-200 bg-white p-6">
          <h2 className="text-sm font-semibold text-stone-800">How pickup &amp; delivery is priced</h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-stone-500">
            A client only pays from the moment the crew arrives to the moment they leave. Each season has two van trips
            that nobody was being charged for: the install trip (pull the boxes off the shelf, load the trailer, drive out,
            drive back) and the takedown trip (drive out, load the trailer, drive back, unload and shelve). The fee is that
            unpaid time at the van crew rate. Loading scales with the box count and only applies when we store the boxes;
            driving uses the client's real minutes each way, mapped by the scheduler.
          </p>
          <pre className="mt-3 rounded-lg bg-stone-50 px-3 py-2 text-[11px] text-stone-700">{`loading  = 2 × boxes × ${rates.handling_min_per_box ?? "?"} min          (only if stored with us)
driving  = 2 × (out + back) minutes
fee      = (loading + driving) ÷ 60 × ${rates.van_crew_rate != null ? formatCurrency(rates.van_crew_rate) : "?"} / hour`}</pre>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-stone-600">
            <label className="flex items-center gap-1.5">Boxes <input inputMode="numeric" className="w-14 rounded-lg border border-stone-200 px-2 py-1 text-right" value={exBoxes} onChange={(e) => setExBoxes(e.target.value)} /></label>
            <label className="flex items-center gap-1.5">Drive out <input inputMode="numeric" className="w-14 rounded-lg border border-stone-200 px-2 py-1 text-right" value={exOut} onChange={(e) => setExOut(e.target.value)} /> min</label>
            <label className="flex items-center gap-1.5">back <input inputMode="numeric" className="w-14 rounded-lg border border-stone-200 px-2 py-1 text-right" value={exBack} onChange={(e) => setExBack(e.target.value)} /> min</label>
            <span className="ml-auto">
              stored with us: <b className="text-stone-800">{formatCurrency(example(Number(exBoxes) || 0, true))}</b>
              <span className="mx-2 text-stone-300">|</span>
              kept at the client: <b className="text-stone-800">{formatCurrency(example(0, false))}</b>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
