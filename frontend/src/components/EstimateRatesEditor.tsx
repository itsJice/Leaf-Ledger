import { useEffect, useMemo, useState } from "react";
import { Check, Clock } from "components/icons";
import { toast } from "sonner";
import { apiFetch } from "utils/apiFetch";
import { currentMe } from "utils/me";
import { currentSeasonLabel } from "utils/season";

/**
 * Settings > Install Estimates: minutes per item and the night, commercial
 * and first-year factors the client card's suggested hours use when a client
 * has no real on-site time yet (backend app.libs.install_estimate, table
 * ll_app.estimate_rates). A season with nothing of its own uses the latest
 * earlier season's numbers, marked inherited. A blank is NEEDS INPUT: the
 * suggestion then says so instead of guessing. Office staff look; admins edit.
 */

type RateCell = { amount: number | null; fromSeason: string | null; own: boolean };
type RatesOut = {
  season: string;
  rates: Record<string, RateCell>;
  keys: { key: string; unit: string; help: string }[];
  seasons: string[];
};

const LABEL: Record<string, string> = {
  setup: "Setup per visit",
  tree_small: "Tree up to 7.5 ft",
  tree_medium: "Tree 8 to 10 ft",
  tree_large: "Tree 11 to 14 ft",
  tree_xl: "Tree 15 ft and up",
  wreath: "Wreath",
  garland_ft: "Garland",
  spray: "Spray",
  swag: "Swag",
  other: "Other piece",
  box: "Box",
  factor_night: "Dallas night",
  factor_commercial: "Business",
  factor_first_year: "First year",
};

export default function EstimateRatesEditor() {
  const isAdmin = !!currentMe()?.isAdmin;
  const now = Number(currentSeasonLabel());
  const [season, setSeason] = useState(String(now + 1));
  const [data, setData] = useState<RatesOut | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const load = async (s: string) => {
    try {
      const r = await apiFetch(`/api/install-estimate/rates?season=${encodeURIComponent(s)}`);
      if (!r.ok) throw new Error("Couldn't load the estimate rates");
      const j = (await r.json()) as RatesOut;
      setData(j);
      setDraft(Object.fromEntries(Object.entries(j.rates).map(([k, v]) => [k, v.amount == null ? "" : String(v.amount)])));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  useEffect(() => {
    void load(season);
  }, [season]);

  const changed = useMemo(() => {
    if (!data) return {} as Record<string, number | null>;
    const out: Record<string, number | null> = {};
    for (const { key } of data.keys) {
      const cur = data.rates[key]?.amount ?? null;
      const txt = (draft[key] ?? "").trim();
      const val = txt === "" ? null : Number(txt);
      if (txt !== "" && !Number.isFinite(val)) continue;
      if (val !== cur) out[key] = val;
    }
    return out;
  }, [data, draft]);

  const save = async () => {
    setSaving(true);
    try {
      const r = await apiFetch("/api/install-estimate/rates", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ season, rates: changed }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j?.detail || "Couldn't save the estimate rates");
      }
      const j = (await r.json()) as RatesOut;
      setData(j);
      setDraft(Object.fromEntries(Object.entries(j.rates).map(([k, v]) => [k, v.amount == null ? "" : String(v.amount)])));
      toast.success(`${season} estimate rates saved`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const seasons = Array.from(new Set([...(data?.seasons ?? []), String(now), String(now + 1)])).sort().reverse();
  const items = data?.keys.filter((k) => !k.key.startsWith("factor_")) ?? [];
  const factors = data?.keys.filter((k) => k.key.startsWith("factor_")) ?? [];

  const row = ({ key, unit, help }: { key: string; unit: string; help: string }) => {
    const cell = data?.rates[key];
    return (
      <li key={key} className="grid grid-cols-[1fr_120px] items-center gap-3 px-4 py-2.5 sm:grid-cols-[220px_140px_1fr]">
        <div>
          <p className="text-sm font-semibold text-stone-900">{LABEL[key] || key}</p>
          <p className="text-[11px] text-stone-500">{unit}</p>
        </div>
        <div>
          <input
            inputMode="decimal"
            value={draft[key] ?? ""}
            disabled={!isAdmin}
            placeholder="NEEDS INPUT"
            onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-right text-base placeholder:text-[11px] placeholder:text-amber-700 sm:text-sm"
            aria-label={`${LABEL[key] || key} (${unit})`}
          />
          {cell?.amount != null && !cell.own && <p className="mt-0.5 text-right text-[10px] text-stone-400">from {cell.fromSeason}</p>}
        </div>
        <p className="col-span-2 text-xs text-stone-500 sm:col-span-1">{help}</p>
      </li>
    );
  };

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-1.5 text-lg font-semibold text-stone-900">
            <Clock size={17} className="text-emerald-700" /> Install estimate rates
          </h2>
          <p className="text-sm text-stone-500">
            Used for a client's suggested hours only when there's no real on-site time yet. Blank means NEEDS INPUT; the
            suggestion won't guess.
          </p>
        </div>
        <select
          value={season}
          onChange={(e) => setSeason(e.target.value)}
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-base sm:text-sm"
          aria-label="Season"
        >
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {data && (
        <>
          <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
            <h3 className="border-b border-stone-100 px-4 py-2.5 text-sm font-semibold text-stone-900">Minutes on site</h3>
            <ul className="divide-y divide-stone-100">{items.map(row)}</ul>
          </section>
          <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
            <h3 className="border-b border-stone-100 px-4 py-2.5 text-sm font-semibold text-stone-900">Factors (multipliers)</h3>
            <ul className="divide-y divide-stone-100">{factors.map(row)}</ul>
          </section>
          {isAdmin && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving || Object.keys(changed).length === 0}
                className="flex min-h-10 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                <Check size={14} strokeWidth={3} /> {saving ? "Saving" : `Save ${season} rates`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
