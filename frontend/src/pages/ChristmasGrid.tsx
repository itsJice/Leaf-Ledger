import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Download, Search } from "components/icons";
import { toast } from "sonner";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel } from "utils/season";
import type { ActivityEntry } from "./clients/SeasonHistory";
import { discountLabel, missingLabel, type InventoryLine, type RoleNeed } from "./clients/pricing";

/**
 * The "Christmas grid" tab of the Clients page: every Christmas client for
 * one season on a single grid -- the same shape
 * as the spreadsheet the business ran on (one row per site, the card, the
 * money) and as the scheduler's billing export, so you can see the export
 * before you export it.
 *
 * It is not Excel. It sorts, filters, hides columns, totals the money and
 * downloads a CSV; and a cell you click becomes an input that saves on
 * Enter or blur through the same PUT /clients/{id}/seasons/{season} the
 * Clients tab uses, so an edit here is stamped like any other and the
 * spreadsheet sync leaves it alone. Ideal and discount come back from the
 * server on that same response -- nothing is priced in the browser.
 *
 * "Client" and "Site" are one stored name split at its separator ("M Crowd
 * | Lakewood", "Capital Bank - Deer Park", "Byler, Gary | Home"), so a
 * chain reads as one client with a row per location without any new data.
 *
 * Greenery clients never appear here: the grid is a Christmas-only view of
 * the same client list, fed the rows the Clients page already loaded so an
 * edit in either place shows in both.
 */

type ClientRecord = {
  id?: number | null;
  name: string;
  phone?: string | null;
  email?: string | null;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  activity?: ActivityEntry[];
};

type Row = {
  clientId: number;
  name: string;
  group: string;
  site: string;
  client: ClientRecord;
  entry: ActivityEntry;
  d: Record<string, unknown>;
  prev: Record<string, unknown> | null;
};

type EditKind = "text" | "int" | "number" | "money" | "date" | "storing" | "role";

type Col = {
  key: string;
  label: string;
  width: number;
  money?: boolean;
  get: (r: Row) => string | number | null;
  /** How the cell edits, when it does. `field` is the season key; `role` edits one role_need headcount. */
  edit?: { kind: EditKind; field: string; role?: keyof RoleNeed };
  title?: (r: Row) => string;
  render?: (r: Row) => React.ReactNode;
};

const COLS_KEY = "ll.christmasGrid.cols";

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}
function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/[$,]/g, ""));
  return Number.isFinite(n) ? n : null;
}
function mdy(iso: unknown): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str(iso));
  return m ? `${m[2]}/${m[3]}/${m[1]}` : str(iso);
}

/** "M Crowd | Lakewood" -> ["M Crowd", "Lakewood"]; "Capital Bank - Deer Park" -> ["Capital Bank", "Deer Park"]. */
export function splitName(name: string): [string, string] {
  const n = name.trim();
  const sep = /\s+[|—–]\s+|\s+-\s+|:\s+/;
  const m = sep.exec(n);
  if (!m) return [n, ""];
  return [n.slice(0, m.index).trim(), n.slice(m.index + m[0].length).trim()];
}

function role(d: Record<string, unknown>): RoleNeed {
  return d.role_need && typeof d.role_need === "object" ? (d.role_need as RoleNeed) : {};
}
function inventorySummary(d: Record<string, unknown>): string {
  const raw = d.inventory;
  if (!Array.isArray(raw)) return "";
  return (raw as InventoryLine[]).map((l) => `${l.qty} ${l.type}${l.size ? ` ${l.size}` : ""}`).join(", ");
}
function statusOf(d: Record<string, unknown>): string {
  if (d.not_installing) return "Not installing";
  if (d.hold) return "On hold";
  return "Installing";
}

const COLUMNS: Col[] = [
  { key: "group", label: "Client", width: 180, get: (r) => r.group },
  { key: "site", label: "Site", width: 150, get: (r) => r.site },
  { key: "address", label: "Address", width: 180, get: (r) => str(r.client.street) },
  { key: "city", label: "City", width: 110, get: (r) => str(r.client.city) },
  { key: "st", label: "ST", width: 44, get: (r) => str(r.client.state) },
  { key: "zip", label: "Zip", width: 64, get: (r) => str(r.client.zip) },
  { key: "phone", label: "Phone", width: 110, get: (r) => str(r.client.phone) },
  { key: "email", label: "Email", width: 170, get: (r) => str(r.client.email) },
  { key: "status", label: "Status", width: 96, get: (r) => statusOf(r.d) },
  { key: "install_date", label: "Install", width: 92, get: (r) => mdy(r.d.install_date), edit: { kind: "date", field: "install_date" } },
  { key: "takedown_date", label: "Takedown", width: 92, get: (r) => mdy(r.d.takedown_date), edit: { kind: "date", field: "takedown_date" } },
  { key: "storing", label: "Storing", width: 70, get: (r) => (r.d.storing === true ? "Yes" : r.d.storing === false ? "No" : ""), edit: { kind: "storing", field: "storing" } },
  { key: "boxes", label: "Boxes", width: 60, get: (r) => num(r.d.boxes), edit: { kind: "int", field: "boxes" } },
  { key: "leads", label: "Leads", width: 56, get: (r) => num(role(r.d).leads), edit: { kind: "role", field: "role_need", role: "leads" } },
  { key: "specialty", label: "Spec.", width: 56, get: (r) => num(role(r.d).specialty), edit: { kind: "role", field: "role_need", role: "specialty" } },
  { key: "designer", label: "Design.", width: 60, get: (r) => num(role(r.d).designer), edit: { kind: "role", field: "role_need", role: "designer" } },
  { key: "general", label: "General", width: 64, get: (r) => num(role(r.d).general), edit: { kind: "role", field: "role_need", role: "general" } },
  { key: "est_hours", label: "Est. hrs", width: 64, get: (r) => num(r.d.est_hours), edit: { kind: "number", field: "est_hours" } },
  { key: "real_hours", label: "Real hrs", width: 64, get: (r) => num(r.d.real_hours) },
  { key: "inventory", label: "Inventory", width: 200, get: (r) => inventorySummary(r.d) },
  { key: "drive_out", label: "Drive out", width: 70, get: (r) => num(r.d.drive_min_out), edit: { kind: "number", field: "drive_min_out" } },
  { key: "drive_back", label: "Drive back", width: 74, get: (r) => num(r.d.drive_min_back), edit: { kind: "number", field: "drive_min_back" } },
  { key: "install_fee", label: "Install $", width: 90, money: true, get: (r) => num(r.d.install_fee), edit: { kind: "money", field: "install_fee" } },
  { key: "takedown_fee", label: "Takedown $", width: 90, money: true, get: (r) => num(r.d.takedown_fee), edit: { kind: "money", field: "takedown_fee" } },
  { key: "storage_fee", label: "Storage $", width: 90, money: true, get: (r) => num(r.d.storage_fee), edit: { kind: "money", field: "storage_fee" } },
  { key: "total", label: "Total (sent)", width: 96, money: true, get: (r) => num(r.d.total), edit: { kind: "money", field: "total" } },
  {
    key: "ideal", label: "Ideal", width: 96, money: true, get: (r) => r.entry.pricing?.ideal?.total ?? null,
    title: (r) => (r.entry.pricing?.ideal?.total == null ? `Needs ${missingLabel(r.entry.pricing?.ideal?.missing) || "a card"}` : "Christmas card × this season's rates"),
  },
  {
    key: "discount", label: "Discount", width: 80, get: (r) => r.entry.pricing?.discount_pct ?? null,
    render: (r) => {
      const p = r.entry.pricing?.discount_pct;
      if (p == null) return <span className="text-stone-300">–</span>;
      return <span className={p > 0.05 ? "text-amber-700" : p < -0.05 ? "text-emerald-700" : ""}>{discountLabel(p)}</span>;
    },
  },
  { key: "prev_invoice", label: "Prev. invoice", width: 96, money: true, get: (r) => (r.prev ? num(r.prev.invoice_total) : null) },
  { key: "invoice_total", label: "Invoiced", width: 96, money: true, get: (r) => num(r.d.invoice_total), edit: { kind: "money", field: "invoice_total" } },
  { key: "price_basis", label: "Pricing basis", width: 240, get: (r) => str(r.entry.pricing?.basis ?? r.d.price_basis), edit: { kind: "text", field: "price_basis" } },
  { key: "production_notes", label: "Repairs / notes", width: 200, get: (r) => str(r.d.production_notes), edit: { kind: "text", field: "production_notes" } },
  { key: "notes", label: "Notes", width: 200, get: (r) => str(r.d.notes), edit: { kind: "text", field: "notes" } },
];
const FROZEN = 2; // Client + Site stay put while the rest scrolls

function readCols(): Set<string> {
  try {
    const raw = JSON.parse(localStorage.getItem(COLS_KEY) || "null");
    if (Array.isArray(raw) && raw.length) return new Set(raw.filter((k) => COLUMNS.some((c) => c.key === k)));
  } catch { /* fresh */ }
  return new Set(COLUMNS.map((c) => c.key));
}

function csvCell(v: unknown): string {
  const s = str(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function CellEditor({ col, row, onDone }: { col: Col; row: Row; onDone: (saved?: ActivityEntry) => void }) {
  const edit = col.edit!;
  const initial = edit.kind === "storing"
    ? (row.d.storing === true ? "yes" : row.d.storing === false ? "no" : "")
    : edit.kind === "date" ? str(row.d[edit.field]).slice(0, 10)
    : edit.kind === "role" ? str(role(row.d)[edit.role!])
    : str(row.d[edit.field]);
  const [v, setV] = useState(initial);
  const ref = useRef<HTMLInputElement | HTMLSelectElement>(null);
  useEffect(() => { ref.current?.focus(); if (ref.current instanceof HTMLInputElement) ref.current.select(); }, []);

  const save = async () => {
    if (v === initial) { onDone(); return; }
    let fields: Record<string, unknown>;
    if (edit.kind === "storing") fields = { storing: v === "" ? null : v === "yes" };
    else if (edit.kind === "role") {
      const next: RoleNeed = { ...role(row.d) };
      if (v.trim() === "") delete next[edit.role!]; else next[edit.role!] = Number(v);
      fields = { role_need: Object.keys(next).length ? next : null };
    } else fields = { [edit.field]: v.trim() === "" ? null : v.trim() };
    try {
      const res = await apiClient.request<ActivityEntry>({
        path: `/routes/clients/${row.clientId}/seasons/${row.entry.season}`,
        method: "PUT", body: { fields }, type: ContentType.Json,
      });
      if (!res.ok) {
        let why = "Couldn't save";
        try { const j = await res.json(); if (j?.detail) why = String(j.detail); } catch { /* no body */ }
        throw new Error(why);
      }
      onDone(await res.json());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save");
      onDone();
    }
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); void save(); }
    if (e.key === "Escape") onDone();
  };
  const cls = "h-7 w-full rounded border border-emerald-400 bg-white px-1.5 text-xs text-stone-800 outline-none ring-2 ring-emerald-200";
  if (edit.kind === "storing") {
    return (
      <select ref={ref as React.RefObject<HTMLSelectElement>} className={cls} value={v} onChange={(e) => setV(e.target.value)} onBlur={() => void save()} onKeyDown={onKey}>
        <option value="">?</option><option value="yes">Yes</option><option value="no">No</option>
      </select>
    );
  }
  return (
    <input
      ref={ref as React.RefObject<HTMLInputElement>}
      type={edit.kind === "date" ? "date" : "text"}
      inputMode={edit.kind === "text" || edit.kind === "date" ? undefined : "decimal"}
      className={`${cls} ${edit.kind === "text" ? "" : "text-right"}`}
      value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={() => void save()}
      onKeyDown={onKey}
    />
  );
}

export function ChristmasGridView({ clients, loading, onSaved }: {
  clients: ClientRecord[];
  loading: boolean;
  /** A season row saved from a cell; the page swaps it into its own list. */
  onSaved: (clientId: number, entry: ActivityEntry) => void;
}) {
  const [season, setSeason] = useState(currentSeasonLabel());
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: "group", dir: 1 });
  const [cols, setCols] = useState<Set<string>>(readCols);
  const [colsOpen, setColsOpen] = useState(false);
  const [editing, setEditing] = useState<{ id: number; key: string } | null>(null);

  useEffect(() => {
    try { localStorage.setItem(COLS_KEY, JSON.stringify([...cols])); } catch { /* fine */ }
  }, [cols]);

  const seasons = useMemo(() => {
    const s = new Set<string>([currentSeasonLabel()]);
    clients.forEach((c) => (c.activity || []).forEach((a) => { if (a.kind === "christmas_install") s.add(a.season); }));
    return [...s].sort((a, b) => b.localeCompare(a));
  }, [clients]);

  const rows = useMemo<Row[]>(() => {
    const prevSeason = String(Number(season) - 1);
    const out: Row[] = [];
    clients.forEach((c) => {
      if (c.id == null) return;
      const entry = (c.activity || []).find((a) => a.kind === "christmas_install" && a.season === season);
      if (!entry) return;
      const prev = (c.activity || []).find((a) => a.kind === "christmas_install" && a.season === prevSeason);
      const [group, site] = splitName(c.name);
      out.push({
        clientId: c.id, name: c.name, group, site, client: c, entry,
        d: (entry.detail && typeof entry.detail === "object" ? entry.detail : {}) as Record<string, unknown>,
        prev: prev?.detail && typeof prev.detail === "object" ? (prev.detail as Record<string, unknown>) : null,
      });
    });
    return out;
  }, [clients, season]);

  const active = useMemo(() => COLUMNS.filter((c) => cols.has(c.key) || c.key === "group"), [cols]);

  const visible = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    let list = rows;
    if (words.length) {
      list = rows.filter((r) => {
        const hay = active.map((c) => str(c.get(r))).join(" ").toLowerCase();
        return words.every((w) => hay.includes(w));
      });
    }
    const col = COLUMNS.find((c) => c.key === sort.key) || COLUMNS[0];
    return [...list].sort((a, b) => {
      const x = col.get(a), y = col.get(b);
      if (x === null || x === "") return y === null || y === "" ? 0 : 1;
      if (y === null || y === "") return -1;
      if (typeof x === "number" && typeof y === "number") return (x - y) * sort.dir;
      return String(x).localeCompare(String(y), undefined, { numeric: true }) * sort.dir || a.site.localeCompare(b.site);
    });
  }, [rows, query, sort, active]);

  const totals = useMemo(() => {
    const t: Record<string, number> = {};
    active.forEach((c) => {
      if (!c.money) return;
      t[c.key] = visible.reduce((s, r) => s + (num(c.get(r)) || 0), 0);
    });
    return t;
  }, [visible, active]);
  const priced = visible.filter((r) => num(r.d.total) !== null).length;

  const download = () => {
    const head = active.map((c) => c.label);
    const body = visible.map((r) => active.map((c) => c.get(r)));
    const foot: (string | number)[] = active.map((c) => (c.money ? Math.round(totals[c.key] * 100) / 100 : ""));
    foot[0] = `TOTAL — ${visible.length} clients (${priced} priced)`;
    const csv = [head, ...body, active.map(() => ""), foot].map((r) => r.map(csvCell).join(",")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `christmas-${season}-grid.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };

  const toggleSort = (key: string) => setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));

  let left = 0;
  const frozenLeft = active.slice(0, FROZEN).map((c) => { const l = left; left += c.width; return l; });

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 px-4 py-3 sm:px-10" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <p className="text-xs text-stone-500">
          {loading ? "Loading…" : `${visible.length} of ${rows.length} Christmas clients for ${season} · ${priced} priced · click a cell to edit, Enter or click away to save`}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select value={season} onChange={(e) => setSeason(e.target.value)} className="rounded-lg border border-stone-200 bg-white px-2.5 py-2 text-sm">
            {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="relative flex items-center">
            <Search size={13} className="pointer-events-none absolute left-2.5 text-stone-400" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter…" className="w-44 rounded-lg border border-stone-200 bg-white py-2 pl-8 pr-2 text-sm" />
          </label>
          <div className="relative">
            <button type="button" onClick={() => setColsOpen((v) => !v)} className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600 hover:bg-stone-50">
              Columns <ChevronDown size={13} />
            </button>
            {colsOpen && (
              <div className="absolute right-0 z-30 mt-1 max-h-80 w-56 overflow-y-auto rounded-lg border border-stone-200 bg-white p-2 text-xs shadow-lg">
                <div className="mb-1 flex justify-between px-1 text-[10px] uppercase tracking-wide text-stone-400">
                  <button type="button" onClick={() => setCols(new Set(COLUMNS.map((c) => c.key)))}>all</button>
                  <button type="button" onClick={() => setCols(new Set(["group", "site"]))}>none</button>
                </div>
                {COLUMNS.map((c) => (
                  <label key={c.key} className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-stone-50">
                    <input type="checkbox" disabled={c.key === "group"} checked={cols.has(c.key)} onChange={(e) => setCols((s) => { const n = new Set(s); if (e.target.checked) n.add(c.key); else n.delete(c.key); return n; })} />
                    {c.label}
                  </label>
                ))}
              </div>
            )}
          </div>
          <button type="button" onClick={download} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
            <Download size={14} /> CSV
          </button>
        </div>
      </div>

      <div className="overflow-auto" style={{ maxHeight: "calc(100vh - 190px)" }} onClick={() => colsOpen && setColsOpen(false)}>
        <table className="border-separate border-spacing-0 text-xs text-stone-700" style={{ minWidth: active.reduce((s, c) => s + c.width, 0) }}>
          <thead className="sticky top-0 z-20">
            <tr>
              {active.map((c, i) => (
                <th
                  key={c.key}
                  onClick={() => toggleSort(c.key)}
                  className={`cursor-pointer select-none whitespace-nowrap border-b border-r border-stone-200 bg-stone-100 px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-stone-500 hover:bg-stone-200 ${i < FROZEN ? "sticky z-30" : ""} ${c.money ? "text-right" : ""}`}
                  style={{ width: c.width, minWidth: c.width, left: i < FROZEN ? frozenLeft[i] : undefined }}
                >
                  {c.label}{sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r, ri) => (
              <tr key={r.clientId} className={ri % 2 ? "bg-stone-50/60" : "bg-white"}>
                {active.map((c, i) => {
                  const isEditing = editing && editing.id === r.clientId && editing.key === c.key;
                  const v = c.get(r);
                  const stamped = c.edit && r.d.app_edits && typeof r.d.app_edits === "object" && (r.d.app_edits as Record<string, unknown>)[c.edit.field];
                  return (
                    <td
                      key={c.key}
                      onClick={() => c.edit && !isEditing && setEditing({ id: r.clientId, key: c.key })}
                      title={c.title ? c.title(r) : stamped ? "Set in Leaf & Ledger — the spreadsheet sync keeps it" : undefined}
                      className={`whitespace-nowrap border-b border-r border-stone-100 px-2 py-1 ${i < FROZEN ? "sticky z-10 font-medium" : ""} ${ri % 2 ? "bg-stone-50" : "bg-white"} ${c.money || typeof v === "number" ? "text-right tabular-nums" : ""} ${c.edit ? "cursor-text hover:bg-emerald-50" : ""} ${i === 0 ? "text-stone-900" : ""}`}
                      style={{ width: c.width, minWidth: c.width, maxWidth: c.width, left: i < FROZEN ? frozenLeft[i] : undefined, overflow: "hidden", textOverflow: "ellipsis" }}
                    >
                      {isEditing ? (
                        <CellEditor col={c} row={r} onDone={(saved) => { setEditing(null); if (saved) onSaved(r.clientId, saved); }} />
                      ) : c.render ? c.render(r) : c.money ? (
                        v === null || v === "" ? <span className="text-stone-300">–</span> : formatCurrency(num(v))
                      ) : (
                        <>{v === null || v === "" ? <span className="text-stone-300">–</span> : v}{stamped ? <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 align-middle" /> : null}</>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!loading && visible.length === 0 && (
              <tr><td colSpan={active.length} className="px-3 py-8 text-center text-stone-400">No Christmas clients for {season}{query ? " match that filter" : ""}.</td></tr>
            )}
          </tbody>
          <tfoot className="sticky bottom-0 z-20">
            <tr>
              {active.map((c, i) => (
                <td key={c.key} className={`whitespace-nowrap border-t-2 border-r border-stone-200 bg-stone-100 px-2 py-1.5 font-semibold ${i < FROZEN ? "sticky z-30" : ""} ${c.money ? "text-right tabular-nums" : ""}`} style={{ left: i < FROZEN ? frozenLeft[i] : undefined }}>
                  {i === 0 ? `TOTAL — ${visible.length} clients (${priced} priced)` : c.money ? formatCurrency(totals[c.key]) : ""}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  );
}
