import React, { useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Copy, Loader2, Scale, Trash2, TreePine } from "lucide-react";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import { toast } from "sonner";
import { coverageDensity, defaultWidthForHeight } from "utils/ornamentRecipe";
import {
  COUNT_SIZES,
  HEIGHT_TOLERANCE_FT,
  compareToTable,
  countsFromForm,
  summariseCounts,
  totalPieces,
} from "utils/treeCounts";
import type { TableComparisonRow, TreeCountInput, TreeCountKind, TreeCountRecord } from "utils/treeCounts";

// The calibration loop behind the ornament calculator's golden table: crews
// record what was actually on a tree at install / teardown, the page averages
// those per golden height and shows drift against the approved row. Nothing
// here writes GOLDEN_RECIPES -- a designer copies an approved average across by
// hand. See utils/treeCounts.md and backend/app/apis/tree_counts.

const INPUT_CLASS =
  "rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600";
const PRIMARY_BUTTON =
  "flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-40";

const DEFAULT_HEIGHT_FT = 9;

function emptyGrid(): Record<string, string> {
  const grid: Record<string, string> = {};
  COUNT_SIZES.forEach((o) => {
    grid[o.display] = "";
  });
  return grid;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatAvg(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function KindBadge({ kind }: { kind: TreeCountKind }) {
  const cls =
    kind === "install"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : "bg-amber-50 text-amber-700 border-amber-200";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}>
      {kind}
    </span>
  );
}

// ─── Count this tree ──────────────────────────────────────────────────────────

function CountForm({ onSaved }: { onSaved: (record: TreeCountRecord) => void }) {
  const [kind, setKind] = useState<TreeCountKind>("install");
  const [heightFt, setHeightFt] = useState<number | "">(DEFAULT_HEIGHT_FT);
  const [widthIn, setWidthIn] = useState<number | "">(defaultWidthForHeight(DEFAULT_HEIGHT_FT));
  // Width follows height until someone types a width of their own.
  const [widthTouched, setWidthTouched] = useState(false);
  const [label, setLabel] = useState("");
  const [profile, setProfile] = useState("");
  const [style, setStyle] = useState("");
  const [grid, setGrid] = useState<Record<string, string>>(emptyGrid);
  const [enhancers, setEnhancers] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const counts = useMemo(() => countsFromForm(grid), [grid]);
  const pieces = totalPieces(counts);
  const enhancerCount = Math.max(0, Math.round(Number(enhancers)) || 0);
  const dimsValid = typeof heightFt === "number" && heightFt > 0 && typeof widthIn === "number" && widthIn > 0;
  const coverage = useMemo(() => {
    if (!dimsValid) return null;
    const map = new Map<number, number>();
    Object.entries(counts).forEach(([size, n]) => map.set(Number(size), n));
    return coverageDensity(heightFt as number, widthIn as number, map);
  }, [counts, dimsValid, heightFt, widthIn]);

  const changeHeight = (value: string) => {
    const next = value === "" ? "" : Number(value);
    setHeightFt(next);
    if (!widthTouched && typeof next === "number" && next > 0) setWidthIn(defaultWidthForHeight(next));
  };

  const reset = () => {
    setKind("install");
    setHeightFt(DEFAULT_HEIGHT_FT);
    setWidthIn(defaultWidthForHeight(DEFAULT_HEIGHT_FT));
    setWidthTouched(false);
    setLabel("");
    setProfile("");
    setStyle("");
    setGrid(emptyGrid());
    setEnhancers("");
    setNotes("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dimsValid) return toast.error("Enter the tree's height and width first.");
    if (pieces === 0 && enhancerCount === 0) return toast.error("Count at least one ornament size or the enhancers.");
    const body: TreeCountInput = {
      kind,
      height_ft: heightFt as number,
      width_in: widthIn as number,
      label: label.trim() || null,
      profile: profile.trim() || null,
      style: style.trim() || null,
      counts,
      enhancers: enhancerCount,
      notes: notes.trim() || null,
    };
    setSaving(true);
    try {
      const res = await apiFetch("/api/tree-counts", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().then((d) => d?.detail).catch(() => null);
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }
      const saved: TreeCountRecord = await res.json();
      toast.success(`Recorded ${saved.height_ft} ft ${saved.kind} — ${totalPieces(saved.counts)} pieces`);
      onSaved(saved);
      reset();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save that tree — try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
        <TreePine size={15} className="text-emerald-700" />
        Count this tree
      </h2>
      <form onSubmit={submit} className="space-y-5">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Install or teardown</span>
            <div className="flex overflow-hidden rounded-lg border border-stone-300">
              {(["install", "teardown"] as TreeCountKind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
                    kind === k ? "bg-emerald-700 text-white" : "text-stone-600 hover:bg-stone-100"
                  }`}
                >
                  {k}
                </button>
              ))}
            </div>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Tree Height (ft)</span>
            <input
              type="number"
              min={0}
              step={0.5}
              value={heightFt}
              onChange={(e) => changeHeight(e.target.value)}
              className={`w-28 ${INPUT_CLASS}`}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Tree Width (in)</span>
            <input
              type="number"
              min={0}
              step={1}
              value={widthIn}
              onChange={(e) => {
                setWidthTouched(true);
                setWidthIn(e.target.value === "" ? "" : Number(e.target.value));
              }}
              className={`w-28 ${INPUT_CLASS}`}
            />
          </label>
          <label className="flex min-w-[14rem] flex-1 flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Client / site (optional)</span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Smith foyer"
              className={INPUT_CLASS}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Profile (optional)</span>
            <input
              type="text"
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              placeholder="slim / full"
              className={`w-40 ${INPUT_CLASS}`}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Style (optional)</span>
            <input
              type="text"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              placeholder="e.g. red & gold"
              className={`w-48 ${INPUT_CLASS}`}
            />
          </label>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">
            Pieces per size (leave blank for none)
          </p>
          <div className="grid grid-cols-4 gap-3 sm:grid-cols-5 lg:grid-cols-9">
            {COUNT_SIZES.map((o) => (
              <label key={o.display} className="flex flex-col gap-1">
                <span className="text-xs font-medium text-stone-500">{o.display}"</span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  inputMode="numeric"
                  value={grid[o.display]}
                  onChange={(e) => setGrid((g) => ({ ...g, [o.display]: e.target.value }))}
                  placeholder="0"
                  className={`w-full ${INPUT_CLASS}`}
                />
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Enhancers</span>
            <input
              type="number"
              min={0}
              step={1}
              inputMode="numeric"
              value={enhancers}
              onChange={(e) => setEnhancers(e.target.value)}
              placeholder="0"
              className={`w-28 ${INPUT_CLASS}`}
            />
          </label>
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1">
            <span className="text-xs font-medium text-stone-500">Notes</span>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything the designer should know — looked thin at the top, client asked for more gold…"
              className={INPUT_CLASS}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-stone-100 pt-4">
          <button type="submit" disabled={saving || !dimsValid} className={PRIMARY_BUTTON}>
            {saving ? <Loader2 size={15} className="animate-spin" /> : <ClipboardCheck size={15} />}
            Record tree
          </button>
          <p className="text-sm text-stone-500">
            <span className="font-semibold text-stone-700">{pieces}</span> pieces
            {enhancerCount > 0 && (
              <>
                {" "}+ <span className="font-semibold text-stone-700">{enhancerCount}</span> enhancers
              </>
            )}
            {coverage !== null && pieces > 0 && (
              <>
                {" "}· <span className="font-semibold text-stone-700">{coverage}%</span> coverage
              </>
            )}
          </p>
        </div>
      </form>
    </section>
  );
}

// ─── Recorded trees ───────────────────────────────────────────────────────────

function RecordedList({
  records,
  loading,
  onDelete,
}: {
  records: TreeCountRecord[];
  loading: boolean;
  onDelete: (record: TreeCountRecord) => void;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">Recorded trees</h2>
        <span className="text-xs text-stone-400">{records.length} on file</span>
      </div>
      {loading ? (
        <p className="px-6 py-10 text-center text-sm text-stone-400">Loading…</p>
      ) : records.length === 0 ? (
        <p className="px-6 py-10 text-center text-sm text-stone-400">
          Nothing counted yet. Next time a tree goes up or comes down, take note above.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500">
                <th className="px-6 py-2 font-medium">Kind</th>
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Tree</th>
                <th className="px-3 py-2 text-right font-medium">Pieces</th>
                <th className="px-3 py-2 text-right font-medium">Enhancers</th>
                <th className="px-3 py-2 font-medium">Client / site</th>
                <th className="px-3 py-2 font-medium">Counts</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-stone-100 last:border-0 hover:bg-stone-50">
                  <td className="px-6 py-2.5">
                    <KindBadge kind={r.kind} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-stone-600">{formatDate(r.recorded_at)}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-stone-800">
                    {r.height_ft} ft × {r.width_in} in
                    {(r.profile || r.style) && (
                      <span className="block text-xs text-stone-400">{[r.profile, r.style].filter(Boolean).join(" · ")}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right font-semibold text-stone-800">{totalPieces(r.counts)}</td>
                  <td className="px-3 py-2.5 text-right text-stone-600">{r.enhancers}</td>
                  <td className="px-3 py-2.5 text-stone-600">
                    {r.label || <span className="text-stone-300">—</span>}
                    {r.created_name && <span className="block text-xs text-stone-400">by {r.created_name}</span>}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-stone-500" title={r.notes || undefined}>
                    {summariseCounts(r.counts) || "—"}
                    {r.notes && <span className="block italic text-stone-400">{r.notes}</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      type="button"
                      onClick={() => onDelete(r)}
                      className="rounded-md p-1.5 text-stone-400 transition-colors hover:bg-red-50 hover:text-red-600"
                      aria-label="Delete this record"
                      title="Delete this record"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ─── Table vs reality ─────────────────────────────────────────────────────────

function ComparisonCard({ row }: { row: TableComparisonRow }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(row.snippet);
      toast.success(`Golden row for ${row.heightFt} ft copied — paste it into GOLDEN_RECIPES`);
    } catch {
      toast.error("Copy failed — select the snippet below and copy it by hand.");
    }
  };

  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-stone-800">{row.heightFt} ft</span>
          <span className="text-xs text-stone-500">approved at {row.approved.widthIn} in</span>
          {row.average ? (
            row.drifted ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-700">
                drift
              </span>
            ) : (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                on recipe
              </span>
            )
          ) : (
            <span className="rounded-full border border-stone-200 bg-white px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
              no counts yet
            </span>
          )}
        </div>
        <button type="button" onClick={copy} disabled={!row.average} className={PRIMARY_BUTTON}>
          <Copy size={14} />
          Copy as golden row
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500">
              <th className="px-4 py-2 font-medium">Size</th>
              {row.sizes.map((s) => (
                <th key={s} className="px-3 py-2 text-right font-medium">
                  {s}"
                </th>
              ))}
              <th className="px-3 py-2 text-right font-medium">Total</th>
              <th className="px-3 py-2 text-right font-medium">Width</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-stone-100">
              <td className="px-4 py-2 font-medium text-stone-700">Approved</td>
              {row.sizes.map((s) => (
                <td key={s} className="px-3 py-2 text-right text-stone-800">
                  {row.approved.quantities[s] ?? <span className="text-stone-300">—</span>}
                </td>
              ))}
              <td className="px-3 py-2 text-right font-semibold text-stone-800">
                {Object.values(row.approved.quantities).reduce((a, b) => a + b, 0)}
              </td>
              <td className="px-3 py-2 text-right text-stone-600">{row.approved.widthIn} in</td>
            </tr>
            <tr className="border-b border-stone-100">
              <td className="px-4 py-2 font-medium text-stone-700">
                Recorded avg
                {row.average && (
                  <span className="ml-1 text-xs font-normal text-stone-400">
                    (n={row.average.n}, ±{HEIGHT_TOLERANCE_FT} ft)
                  </span>
                )}
              </td>
              {row.sizes.map((s) => {
                const cell = row.cells[s];
                return (
                  <td
                    key={s}
                    className={`px-3 py-2 text-right ${
                      cell?.flagged ? "bg-amber-50 font-semibold text-amber-800" : "text-stone-800"
                    }`}
                  >
                    {row.average ? formatAvg(row.average.counts[s] ?? 0) : <span className="text-stone-300">—</span>}
                  </td>
                );
              })}
              <td className="px-3 py-2 text-right font-semibold text-stone-800">
                {row.average ? formatAvg(Object.values(row.average.counts).reduce((a, b) => a + b, 0)) : "—"}
              </td>
              <td className="px-3 py-2 text-right text-stone-600">
                {row.average ? `${formatAvg(row.average.widthIn)} in` : "—"}
              </td>
            </tr>
            <tr>
              <td className="px-4 py-2 text-xs font-medium uppercase tracking-wide text-stone-500">Difference</td>
              {row.sizes.map((s) => {
                const cell = row.cells[s];
                if (!cell) {
                  return (
                    <td key={s} className="px-3 py-2 text-right text-stone-300">
                      —
                    </td>
                  );
                }
                const sign = cell.diff > 0 ? "+" : "";
                return (
                  <td
                    key={s}
                    className={`px-3 py-2 text-right text-xs ${cell.flagged ? "bg-amber-50 font-semibold text-amber-800" : "text-stone-500"}`}
                    title={cell.pct !== null ? `${Math.round(cell.pct * 100)}% of approved` : "not in the approved row"}
                  >
                    {sign}
                    {formatAvg(cell.diff)}
                    {cell.pct !== null && <span className="ml-1 text-[10px] text-stone-400">({sign}{Math.round(cell.pct * 100)}%)</span>}
                  </td>
                );
              })}
              <td className="px-3 py-2" />
              <td className="px-3 py-2 text-right text-xs text-stone-500">
                {row.average ? `enhancers avg ${formatAvg(row.average.enhancers)}` : ""}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {row.average && (
        <pre className="mt-3 select-all overflow-x-auto rounded-lg bg-stone-800 px-4 py-2.5 font-mono text-xs text-stone-100">
          {row.snippet}
        </pre>
      )}
    </div>
  );
}

function TableVsReality({ records }: { records: TreeCountRecord[] }) {
  const rows = useMemo(() => compareToTable(records), [records]);
  return (
    <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
        <Scale size={15} className="text-emerald-700" />
        Table vs reality
      </h2>
      <p className="mb-4 text-xs text-stone-500">
        The approved golden row beside the average of everything counted at that height. A size is flagged when it is off by
        4+ pieces or 20%+. “Copy as golden row” gives a paste-ready line for <code className="rounded bg-stone-100 px-1">GOLDEN_RECIPES</code>{" "}
        (averages rounded to even) — the table is only ever updated by hand, after the designer has signed off.
      </p>
      <div className="space-y-4">
        {rows.map((row) => (
          <ComparisonCard key={row.heightFt} row={row} />
        ))}
      </div>
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TreeCounts() {
  const [records, setRecords] = useState<TreeCountRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    apiFetch("/api/tree-counts", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setRecords(Array.isArray(data) ? data : []))
      .catch(() => toast.error("Couldn't load tree counts"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // A teammate's count should show up without a manual refresh -- refetch on
    // focus, same as the Comments page, no polling loop.
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const remove = async (record: TreeCountRecord) => {
    const what = `${record.height_ft} ft ${record.kind}${record.label ? ` (${record.label})` : ""} from ${formatDate(record.recorded_at)}`;
    if (!confirm(`Delete the ${what}? This removes it from the averages for everyone.`)) return;
    const before = records;
    setRecords((prev) => prev.filter((r) => r.id !== record.id));
    try {
      const res = await apiFetch(`/api/tree-counts/${record.id}`, { method: "DELETE", credentials: "include" });
      if (!res.ok) throw new Error(String(res.status));
      toast.success("Record deleted");
    } catch {
      setRecords(before);
      toast.error("Couldn't delete that — try again.");
    }
  };

  return (
    <Layout>
      <header className="border-b border-stone-200 px-10 py-5">
        <h1
          className="flex items-center gap-2 text-xl font-semibold text-stone-800"
          style={{ fontFamily: "Georgia, serif" }}
        >
          <ClipboardCheck size={18} className="text-emerald-700" />
          Tree Counts
        </h1>
        <p className="mt-0.5 text-xs text-stone-500">
          What was actually on the tree at install and teardown. Every count is a candidate golden-table row — next time we
          take one down, take note.
        </p>
      </header>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
        <CountForm onSaved={(saved) => setRecords((prev) => [saved, ...prev])} />
        <RecordedList records={records} loading={loading} onDelete={remove} />
        <TableVsReality records={records} />
      </div>
    </Layout>
  );
}
