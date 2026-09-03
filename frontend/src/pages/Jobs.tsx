import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ClipboardList, Plus, Trash2, Search, PackageCheck, FileSpreadsheet, FileText,
  ExternalLink, Check, Package, AlertTriangle, Printer, Link2,
} from "lucide-react";
import { toast } from "sonner";
import Layout from "components/Layout";
import CatalogPickPane, { type CatalogPick } from "components/CatalogPickPane";
import { useAuth } from "app/auth/AuthProvider";
import { apiFetch } from "utils/apiFetch";
import {
  listJobs, getJob, createJob, updateJob, deleteJob,
  addPiece, updatePiece, deletePiece,
  addNeeds, updateNeed, deleteNeed,
  addSourcing, updateSourcing, deleteSourcing,
  searchOpenOrders, allocateFromOrder, sendToPO, openPOsForVendor, updatePO, poLines, receiveLine,
  addTask, updateTask, deleteTask, downloadExport, fetchJobsMeta,
  STAGE_LABEL, SOURCING_LABEL,
  type Job, type JobSummary, type Need, type SourcingLine, type Piece, type Stage,
  type OpenOrderLine, type POLine, type SourcingStatus, type JobsMeta,
} from "utils/jobs";

// Jobs: one client order carried from intake to the client shelf.
//
//   Order      what the client asked for (the Manufacturing Order header + pieces)
//   Need list  the purple sheet: each material, how many, how many already
//              pulled from inventory onto this client's shelf
//   Sourcing   the buyer's worksheet: catalog pick, pack math, open-order
//              allocation, substitutions, follow-ups, then send to POs
//   Orders     the job's purchase orders and check-in
//   Build      what the builders take to the bench
//
// The job's stage is derived on the server from its lines — nothing here sets it.

type Tab = "order" | "needs" | "sourcing" | "orders" | "build";
const TABS: Array<{ id: Tab; label: string }> = [
  { id: "order", label: "Order" },
  { id: "needs", label: "Need list" },
  { id: "sourcing", label: "Sourcing" },
  { id: "orders", label: "Purchase orders" },
  { id: "build", label: "Build sheet" },
];
const STAGES: Stage[] = ["received", "scoped", "sourcing", "ordered", "receiving", "ready", "built", "installed"];
const PO_STATUSES = ["draft", "approved", "placed", "follow_up", "shipped", "arrived", "closed"];
const DELIVERY = ["Delivery", "Pickup", "Shipping"];

const proxied = (url?: string | null) => (url ? `/api/products/image-proxy?url=${encodeURIComponent(url)}` : undefined);
const money = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);
const qty = (n?: number | null) => (n == null ? "" : Number.isInteger(Number(n)) ? String(n) : Number(n).toFixed(1));
const dateStr = (d?: string | null) => (d ? String(d).slice(0, 10) : "");

const input = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm outline-none focus:border-emerald-500";
const btnPrimary = "inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50";
const btnGhost = "inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700";

function stagePill(stage: Stage) {
  const tone: Record<Stage, string> = {
    received: "bg-stone-100 text-stone-600",
    scoped: "bg-stone-100 text-stone-700",
    sourcing: "bg-amber-50 text-amber-800",
    ordered: "bg-amber-50 text-amber-800",
    receiving: "bg-amber-50 text-amber-800",
    ready: "bg-emerald-50 text-emerald-800",
    built: "bg-emerald-50 text-emerald-800",
    installed: "bg-emerald-100 text-emerald-900",
  };
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${tone[stage]}`}>{STAGE_LABEL[stage]}</span>;
}

function linePill(s: SourcingStatus) {
  const tone: Record<SourcingStatus, string> = {
    proposed: "bg-stone-100 text-stone-700",
    ready: "bg-emerald-50 text-emerald-800",
    ordered: "bg-emerald-50 text-emerald-800",
    follow_up: "bg-amber-50 text-amber-800",
    allocated: "bg-sky-50 text-sky-800",
    sold_out: "bg-rose-50 text-rose-700 line-through",
    on_hold: "bg-stone-100 text-stone-500",
  };
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${tone[s]}`}>{SOURCING_LABEL[s]}</span>;
}

export default function Jobs() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const me = user?.email || undefined;

  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [meta, setMeta] = useState<JobsMeta | null>(null);
  const [tab, setTab] = useState<Tab>("order");
  const [loading, setLoading] = useState(false);

  const activeId = jobId ? Number(jobId) : null;

  const refreshList = useCallback(async () => {
    try { setJobs(await listJobs()); } catch { setJobs([]); }
  }, []);

  useEffect(() => {
    refreshList();
    fetchJobsMeta().then(setMeta).catch(() => {});
  }, [refreshList]);

  const load = useCallback(async (id: number) => {
    setLoading(true);
    try { setJob(await getJob(id)); }
    catch { setJob(null); toast.error("That job could not be loaded."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (activeId) load(activeId); else setJob(null);
  }, [activeId, load]);

  // Every mutation returns the whole job; apply it and keep the rail in step.
  const apply = useCallback((next: Job) => { setJob(next); refreshList(); }, [refreshList]);

  const run = useCallback(async (fn: () => Promise<Job>, ok?: string) => {
    try {
      const next = await fn();
      apply(next);
      if (ok) toast.success(ok);
      return next;
    } catch (e: any) {
      toast.error(e?.message || "That didn't save.");
      return null;
    }
  }, [apply]);

  const newJob = async () => {
    try {
      const created = await createJob({ name: "New job" });
      await refreshList();
      navigate(`/jobs/${created.id}`);
      setTab("order");
    } catch (e: any) { toast.error(e?.message || "Could not create a job."); }
  };

  const removeJob = async () => {
    if (!job) return;
    if (!window.confirm(`Delete "${job.name}" and everything on it? Purchase orders stay.`)) return;
    await deleteJob(job.id);
    setJob(null);
    await refreshList();
    navigate("/jobs");
    toast.success("Job deleted");
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-8 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            <ClipboardList size={18} className="text-emerald-700" /> Jobs
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">A client order, from intake to the shelf.</p>
        </div>
        <button onClick={newJob} className={btnPrimary}><Plus size={15} /> New job</button>
      </header>

      <div className="flex">
        <aside className="w-72 flex-shrink-0 border-r border-stone-200 px-3 py-4" style={{ minHeight: "calc(100vh - 65px)" }}>
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-stone-500">Jobs ({jobs.length})</p>
          {jobs.length === 0 ? (
            <p className="px-2 text-sm text-stone-400">No jobs yet. Start one when an order comes in.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {jobs.map((j) => {
                const active = j.id === activeId;
                return (
                  <button key={j.id} onClick={() => navigate(`/jobs/${j.id}`)}
                    className={`flex flex-col rounded-lg px-3 py-2 text-left ${active ? "bg-emerald-50 ring-1 ring-emerald-200" : "hover:bg-stone-100"}`}>
                    <span className="flex items-center justify-between gap-2">
                      <span className={`truncate text-sm font-medium ${active ? "text-emerald-900" : "text-stone-700"}`}>{j.name}</span>
                      {stagePill(j.stage)}
                    </span>
                    <span className="mt-0.5 truncate text-xs text-stone-400">
                      {j.client_name || "No client"}{j.collection ? ` · ${j.collection}` : ""}
                    </span>
                    <span className="mt-0.5 text-[11px] text-stone-400">
                      {j.summary.ready_count}/{j.summary.need_count} lines on shelf
                      {j.summary.open_tasks ? ` · ${j.summary.open_tasks} follow-up${j.summary.open_tasks === 1 ? "" : "s"}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        <main className="min-w-0 flex-1 px-8 py-6">
          {!activeId ? <Empty /> : loading && !job ? (
            <p className="py-20 text-center text-sm text-stone-400">Loading job…</p>
          ) : !job ? <Empty /> : (
            <>
              <JobHeader job={job} onDelete={removeJob} onChange={(body) => run(() => updateJob(job.id, body))} />
              <nav className="mt-5 flex gap-1 border-b border-stone-200">
                {TABS.map((t) => (
                  <button key={t.id} onClick={() => setTab(t.id)}
                    className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === t.id ? "border-emerald-700 text-emerald-800" : "border-transparent text-stone-500 hover:text-stone-800"}`}>
                    {t.label}
                    {t.id === "needs" && job.summary.need_count > 0 && <span className="ml-1.5 text-[11px] text-stone-400">{job.summary.need_count}</span>}
                    {t.id === "sourcing" && job.summary.unsourced_count > 0 && <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-[11px] text-amber-800">{job.summary.unsourced_count}</span>}
                  </button>
                ))}
              </nav>
              <div className="mt-5">
                {tab === "order" && <OrderTab job={job} meta={meta} run={run} />}
                {tab === "needs" && <NeedsTab job={job} run={run} />}
                {tab === "sourcing" && <SourcingTab job={job} run={run} me={me} />}
                {tab === "orders" && <OrdersTab job={job} run={run} reload={() => load(job.id)} />}
                {tab === "build" && <BuildTab job={job} run={run} />}
              </div>
            </>
          )}
        </main>
      </div>
    </Layout>
  );
}

function Empty() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
        <ClipboardList size={28} className="text-emerald-600" strokeWidth={1.5} />
      </div>
      <p className="mb-1 text-base font-medium text-stone-600">No job selected</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">Pick a job on the left, or start one when a client order comes in.</p>
    </div>
  );
}

// ── Header: name, stage strip, exports ──────────────────────────────────────
function JobHeader({ job, onDelete, onChange }: { job: Job; onDelete: () => void; onChange: (b: Record<string, unknown>) => void }) {
  const [name, setName] = useState(job.name);
  useEffect(() => setName(job.name), [job.id, job.name]);
  const idx = STAGES.indexOf(job.stage);
  const exportIt = async (fmt: "xlsx" | "mo") => {
    try { await downloadExport(job.id, fmt, job.name); } catch { toast.error("Export failed"); }
  };
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <input value={name} onChange={(e) => setName(e.target.value)}
            onBlur={() => name.trim() && name !== job.name && onChange({ name: name.trim() })}
            className="w-full max-w-xl bg-transparent text-lg font-semibold text-stone-800 outline-none focus:border-b focus:border-emerald-500"
            style={{ fontFamily: "Georgia, serif" }} />
          <p className="text-xs text-stone-500">
            {job.client_name || "No client"}{job.collection ? ` · ${job.collection}` : ""}
            {job.install_date ? ` · installs ${dateStr(job.install_date)}` : ""}
            {job.summary.buy_cost != null && <> · <span className="font-semibold text-emerald-800">{money(job.summary.buy_cost)}</span> to buy</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => exportIt("xlsx")} className={btnGhost}><FileSpreadsheet size={13} /> Tracking sheet</button>
          <button onClick={() => exportIt("mo")} className={btnGhost}><FileText size={13} /> Manufacturing order</button>
          <button onClick={onDelete} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"><Trash2 size={13} /> Delete</button>
        </div>
      </div>
      <ol className="mt-4 grid grid-cols-8 gap-1">
        {STAGES.map((s, i) => (
          <li key={s} className={`border-t-2 px-1 pt-1.5 text-[11px] font-semibold ${i < idx ? "border-emerald-600 text-emerald-700" : i === idx ? "border-emerald-700 text-emerald-900" : "border-stone-200 text-stone-400"}`}>
            {STAGE_LABEL[s]}
          </li>
        ))}
      </ol>
      {(job.stage === "ready" || job.stage === "built") && (
        <div className="mt-3 flex items-center gap-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          <PackageCheck size={16} />
          {job.stage === "ready" ? "Every need line is on the shelf." : "Built."}
          {job.stage === "ready" && <button onClick={() => onChange({ built: true })} className="ml-auto text-xs font-semibold underline">Mark built</button>}
          {job.stage === "built" && <button onClick={() => onChange({ installed: true })} className="ml-auto text-xs font-semibold underline">Mark installed</button>}
        </div>
      )}
    </div>
  );
}

// ── Order tab: intake + pieces ──────────────────────────────────────────────
function OrderTab({ job, meta, run }: { job: Job; meta: JobsMeta | null; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null> }) {
  const [form, setForm] = useState<Record<string, any>>({});
  const [intake, setIntake] = useState<Record<string, any>>({});
  const [clients, setClients] = useState<Array<{ id: number; name: string }>>([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setForm({
      order_no: job.order_no || "", client_name: job.client_name || "", collection: job.collection || "",
      color_palette: job.color_palette || "", season: job.season || "", order_date: dateStr(job.order_date),
      install_date: dateStr(job.install_date), due_date: dateStr(job.due_date), designer: job.designer || "",
      sidemark: job.sidemark || "", delivery_method: job.delivery_method || "", notes: job.notes || "",
    });
    setIntake({ ...(job.intake || {}) });
    setDirty(false);
    // Reset the form only when a different job (or a saved version of it) arrives,
    // not on every keystroke elsewhere in the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, job.updated_at]);

  useEffect(() => {
    apiFetch("/api/clients/list").then((r) => (r.ok ? r.json() : [])).then((rows: any[]) =>
      setClients(rows.map((c) => ({ id: c.id, name: c.name })))).catch(() => {});
  }, []);

  const set = (k: string, v: any) => { setForm((f) => ({ ...f, [k]: v })); setDirty(true); };
  const setI = (k: string, v: any) => { setIntake((f) => ({ ...f, [k]: v })); setDirty(true); };

  const save = () => {
    const client = clients.find((c) => c.name.toLowerCase() === String(form.client_name || "").trim().toLowerCase());
    const body: Record<string, unknown> = { ...form, intake, client_id: client?.id ?? null };
    for (const k of ["order_date", "install_date", "due_date"]) if (!body[k]) body[k] = null;
    run(() => updateJob(job.id, body), "Order saved").then((j) => j && setDirty(false));
  };

  const F = ({ k, label, type = "text", list }: { k: string; label: string; type?: string; list?: string }) => (
    <label className="flex flex-col gap-1 text-xs text-stone-500">
      {label}
      <input type={type} list={list} value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} className={input} />
    </label>
  );
  const I = ({ k, label }: { k: string; label: string }) => (
    <label className="flex flex-col gap-1 text-xs text-stone-500">
      {label}
      <input value={intake[k] ?? ""} onChange={(e) => setI(k, e.target.value)} className={input} />
    </label>
  );

  return (
    <div className="flex flex-col gap-8">
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500">Manufacturing order</h3>
          <button onClick={save} disabled={!dirty} className={btnPrimary}><Check size={14} /> Save</button>
        </div>
        <datalist id="job-clients">{clients.map((c) => <option key={c.id} value={c.name} />)}</datalist>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <F k="order_no" label="Order #" />
          <label className="flex flex-col gap-1 text-xs text-stone-500">Design firm / end user
            <select value={intake.client_kind ?? ""} onChange={(e) => setI("client_kind", e.target.value)} className={input}>
              <option value="">—</option><option>Design Firm</option><option>End User</option>
            </select>
          </label>
          <F k="client_name" label="Client name" list="job-clients" />
          <F k="install_date" label="Install date" type="date" />
          <F k="sidemark" label="Sidemark" />
          <F k="designer" label="Designer" />
          <F k="order_date" label="Order date" type="date" />
          <F k="due_date" label="Client due date" type="date" />
          <I k="phone" label="Phone" />
          <I k="email" label="Email" />
          <label className="flex flex-col gap-1 text-xs text-stone-500">Delivery
            <select value={form.delivery_method ?? ""} onChange={(e) => set("delivery_method", e.target.value)} className={input}>
              <option value="">—</option>{DELIVERY.map((d) => <option key={d}>{d}</option>)}
            </select>
          </label>
          <I k="sales" label="Sales" />
          <I k="tbdg_so" label="TBDG SO" />
          <F k="collection" label="Collection / color scheme" />
          <F k="season" label="Season" />
          <F k="color_palette" label="Color palette (as written)" />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <I k="plug_location" label="Electrical plug location" />
          <I k="location_tag" label="Location tag" />
          <I k="quoted_price" label="Quoted price (W / R)" />
          <I k="build_to" label="Build to" />
        </div>
        <div className="mt-3 flex items-center gap-6 text-sm text-stone-600">
          <label className="flex items-center gap-2"><input type="checkbox" checked={!!intake.mirrored} onChange={(e) => setI("mirrored", e.target.checked)} /> Mirrored</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={!!intake.matching} onChange={(e) => setI("matching", e.target.checked)} /> Matching</label>
        </div>
        <label className="mt-3 flex flex-col gap-1 text-xs text-stone-500">Notes on product
          <textarea value={intake.notes_on_product ?? ""} onChange={(e) => setI("notes_on_product", e.target.value)} rows={2} className={input} />
        </label>
        <label className="mt-3 flex flex-col gap-1 text-xs text-stone-500">Internal notes
          <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2} className={input} />
        </label>
      </section>

      <PiecesSection job={job} meta={meta} run={run} />
    </div>
  );
}

const SPEC_KEYS = ["height", "width", "length", "diameter", "style", "notes"];

function PiecesSection({ job, meta, run }: { job: Job; meta: JobsMeta | null; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null> }) {
  const types = meta?.piece_types || ["Tree", "Garland", "Wreath", "Vertical Spray", "Horizontal Swag", "Low Arrangement", "Tall Arrangement", "Other"];
  const [draft, setDraft] = useState<{ piece_type: string; qty: number; spec: Record<string, string> }>({ piece_type: types[0], qty: 1, spec: {} });

  const add = () => {
    run(() => addPiece(job.id, { piece_type: draft.piece_type, qty: draft.qty, spec: clean(draft.spec) }))
      .then((j) => j && setDraft({ piece_type: draft.piece_type, qty: 1, spec: {} }));
  };

  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-widest text-stone-500">Pieces ordered</h3>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-stone-400">
              <th className="px-3 py-2 font-medium">Piece</th>
              <th className="px-2 py-2 font-medium">Qty</th>
              {SPEC_KEYS.map((k) => <th key={k} className="px-2 py-2 font-medium">{k}</th>)}
              <th />
            </tr>
          </thead>
          <tbody>
            {job.pieces.map((p) => <PieceRow key={p.id} piece={p} types={types} run={run} />)}
            <tr className="border-t border-stone-200 bg-stone-50">
              <td className="px-3 py-2">
                <select value={draft.piece_type} onChange={(e) => setDraft({ ...draft, piece_type: e.target.value })} className={input}>
                  {types.map((t) => <option key={t}>{t}</option>)}
                </select>
              </td>
              <td className="px-2 py-2"><input type="number" min={0} step="any" value={draft.qty} onChange={(e) => setDraft({ ...draft, qty: Number(e.target.value) })} className={`${input} w-16`} /></td>
              {SPEC_KEYS.map((k) => (
                <td key={k} className="px-2 py-2">
                  <input value={draft.spec[k] || ""} placeholder={k === "height" ? "12 ft" : k === "length" ? "24 ft" : ""} onChange={(e) => setDraft({ ...draft, spec: { ...draft.spec, [k]: e.target.value } })} className={`${input} w-24`} />
                </td>
              ))}
              <td className="px-2 py-2 text-right"><button onClick={add} className={btnPrimary}><Plus size={14} /> Add</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      {job.pieces.length === 0 && <p className="mt-2 text-xs text-stone-400">Add each piece the client ordered: 12 ft tree × 1, vertical spray × 2, garland 24 ft × 1.</p>}
    </section>
  );
}

function PieceRow({ piece, types, run }: { piece: Piece; types: string[]; run: (fn: () => Promise<Job>) => Promise<Job | null> }) {
  const [spec, setSpec] = useState<Record<string, string>>(Object.fromEntries(Object.entries(piece.spec || {}).map(([k, v]) => [k, v == null ? "" : String(v)])));
  const [q, setQ] = useState(piece.qty);
  useEffect(() => { setQ(piece.qty); }, [piece.qty]);
  const saveSpec = () => {
    const next = clean(spec);
    if (JSON.stringify(next) !== JSON.stringify(clean(piece.spec as any))) run(() => updatePiece(piece.id, { spec: next }));
  };
  return (
    <tr className="border-t border-stone-100">
      <td className="px-3 py-2">
        <select value={piece.piece_type} onChange={(e) => run(() => updatePiece(piece.id, { piece_type: e.target.value }))} className={input}>
          {[...new Set([piece.piece_type, ...types])].map((t) => <option key={t}>{t}</option>)}
        </select>
      </td>
      <td className="px-2 py-2"><input type="number" min={0} step="any" value={q} onChange={(e) => setQ(Number(e.target.value))} onBlur={() => q !== piece.qty && run(() => updatePiece(piece.id, { qty: q }))} className={`${input} w-16`} /></td>
      {SPEC_KEYS.map((k) => (
        <td key={k} className="px-2 py-2">
          <input value={spec[k] || ""} onChange={(e) => setSpec({ ...spec, [k]: e.target.value })} onBlur={saveSpec} className={`${input} w-24`} />
        </td>
      ))}
      <td className="px-2 py-2 text-right"><button onClick={() => run(() => deletePiece(piece.id))} className="text-stone-300 hover:text-rose-600" aria-label="Remove"><Trash2 size={15} /></button></td>
    </tr>
  );
}

function clean(spec: Record<string, any>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(spec || {})) if (v != null && String(v).trim()) out[k] = String(v).trim();
  return out;
}

// ── Need list tab: the purple sheet ─────────────────────────────────────────
function NeedsTab({ job, run }: { job: Job; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null> }) {
  const [draft, setDraft] = useState({ label: "", spec: "", need_qty: "", shelf_qty: "" });
  const [bulk, setBulk] = useState("");
  const [showBulk, setShowBulk] = useState(false);

  const add = () => {
    if (!draft.label.trim()) return;
    run(() => addNeeds(job.id, [{ label: draft.label.trim(), spec: draft.spec || undefined, need_qty: Number(draft.need_qty) || 0, shelf_qty: Number(draft.shelf_qty) || 0 }]))
      .then((j) => j && setDraft({ label: "", spec: "", need_qty: "", shelf_qty: "" }));
  };
  // Paste the purple sheet: one line per row, "label  qty" or "label qty / shelf".
  const addBulk = () => {
    const rows = bulk.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
      const m = l.match(/^(.*?)\s+(\d+(?:\.\d+)?)(?:\s*[/|]\s*(\d+(?:\.\d+)?))?\s*$/);
      return m ? { label: m[1].trim(), need_qty: Number(m[2]), shelf_qty: Number(m[3] || 0) } : { label: l, need_qty: 0, shelf_qty: 0 };
    });
    if (!rows.length) return;
    run(() => addNeeds(job.id, rows), `${rows.length} line${rows.length === 1 ? "" : "s"} added`).then((j) => { if (j) { setBulk(""); setShowBulk(false); } });
  };

  const ready = job.needs.filter((n) => n.ready).length;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-stone-600">
          What the pieces need, and how much is already pulled onto <b>{job.client_name || "the client"}'s shelf</b>. The gap goes to the buyer.
          {job.needs.length > 0 && <span className="ml-2 text-xs text-stone-400">{ready}/{job.needs.length} lines on the shelf</span>}
        </p>
        <button onClick={() => setShowBulk((v) => !v)} className={btnGhost}>{showBulk ? "Close" : "Paste a list"}</button>
      </div>
      {showBulk && (
        <div className="mb-4 rounded-xl border border-stone-200 bg-stone-50 p-3">
          <p className="mb-2 text-xs text-stone-500">One line per material, quantity last. Add <code>/ shelf qty</code> if some is already pulled. Example: <code>white natural berry 40</code>, <code>pine cones large 30 / 10</code></p>
          <textarea value={bulk} onChange={(e) => setBulk(e.target.value)} rows={6} className={`${input} w-full font-mono text-xs`} placeholder={"sage green ribbon 12\nburlap ribbon 10\nhydrangeas white 40\nchampagne leaves 52\npine cones large 30"} />
          <div className="mt-2 flex justify-end"><button onClick={addBulk} className={btnPrimary}><Plus size={14} /> Add lines</button></div>
        </div>
      )}
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-stone-400">
              <th className="px-3 py-2 font-medium">Material</th>
              <th className="px-2 py-2 font-medium">Spec / color / size</th>
              <th className="px-2 py-2 text-right font-medium">Need</th>
              <th className="px-2 py-2 text-right font-medium">On shelf</th>
              <th className="px-2 py-2 text-right font-medium">Allocated</th>
              <th className="px-2 py-2 text-right font-medium">On order</th>
              <th className="px-2 py-2 text-right font-medium">Gap</th>
              <th className="px-2 py-2 font-medium">Status</th>
              <th className="px-2 py-2 font-medium">Notes</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {job.needs.map((n) => <NeedRow key={n.id} need={n} run={run} />)}
            <tr className="border-t border-stone-200 bg-stone-50">
              <td className="px-3 py-2"><input value={draft.label} placeholder="cream hydrangeas" onChange={(e) => setDraft({ ...draft, label: e.target.value })} onKeyDown={(e) => e.key === "Enter" && add()} className={`${input} w-full`} /></td>
              <td className="px-2 py-2"><input value={draft.spec} placeholder="white, 26 in" onChange={(e) => setDraft({ ...draft, spec: e.target.value })} className={`${input} w-full`} /></td>
              <td className="px-2 py-2"><input type="number" min={0} step="any" value={draft.need_qty} onChange={(e) => setDraft({ ...draft, need_qty: e.target.value })} onKeyDown={(e) => e.key === "Enter" && add()} className={`${input} w-20 text-right`} /></td>
              <td className="px-2 py-2"><input type="number" min={0} step="any" value={draft.shelf_qty} onChange={(e) => setDraft({ ...draft, shelf_qty: e.target.value })} onKeyDown={(e) => e.key === "Enter" && add()} className={`${input} w-20 text-right`} /></td>
              <td colSpan={5} className="px-2 py-2 text-right"><button onClick={add} className={btnPrimary}><Plus size={14} /> Add line</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NeedRow({ need, run }: { need: Need; run: (fn: () => Promise<Job>) => Promise<Job | null> }) {
  const [v, setV] = useState({ label: need.label, spec: need.spec || "", need_qty: String(need.need_qty), shelf_qty: String(need.shelf_qty), notes: need.notes || "" });
  useEffect(() => setV({ label: need.label, spec: need.spec || "", need_qty: String(need.need_qty), shelf_qty: String(need.shelf_qty), notes: need.notes || "" }), [need]);
  const commit = (k: keyof typeof v) => {
    const cur = k === "need_qty" || k === "shelf_qty" ? Number(v[k]) : v[k];
    const was = k === "spec" ? need.spec || "" : k === "notes" ? need.notes || "" : (need as any)[k];
    if (cur !== was) run(() => updateNeed(need.id, { [k]: cur } as any));
  };
  const status = need.ready ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">On shelf</span>
    : need.gap_qty <= 0 ? <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800">Coming</span>
    : need.unsourced_qty <= 0 ? <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-semibold text-stone-700">Sourced</span>
    : <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900">Needs sourcing</span>;
  return (
    <tr className="border-t border-stone-100 align-middle">
      <td className="px-3 py-1.5"><input value={v.label} onChange={(e) => setV({ ...v, label: e.target.value })} onBlur={() => commit("label")} className={`${input} w-full font-medium`} /></td>
      <td className="px-2 py-1.5"><input value={v.spec} onChange={(e) => setV({ ...v, spec: e.target.value })} onBlur={() => commit("spec")} className={`${input} w-full`} /></td>
      <td className="px-2 py-1.5"><input type="number" min={0} step="any" value={v.need_qty} onChange={(e) => setV({ ...v, need_qty: e.target.value })} onBlur={() => commit("need_qty")} className={`${input} w-20 text-right`} /></td>
      <td className="px-2 py-1.5"><input type="number" min={0} step="any" value={v.shelf_qty} onChange={(e) => setV({ ...v, shelf_qty: e.target.value })} onBlur={() => commit("shelf_qty")} className={`${input} w-20 text-right`} /></td>
      <td className="px-2 py-1.5 text-right tabular-nums text-stone-600">{need.allocated_qty ? qty(need.allocated_qty) : "—"}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-stone-600">{need.ordered_qty ? `${qty(need.ordered_qty)}${need.received_qty ? ` (${qty(need.received_qty)} in)` : ""}` : "—"}</td>
      <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${need.gap_qty > 0 ? "text-amber-800" : "text-stone-400"}`}>{qty(need.gap_qty)}</td>
      <td className="px-2 py-1.5">{status}</td>
      <td className="px-2 py-1.5"><input value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} onBlur={() => commit("notes")} className={`${input} w-full`} /></td>
      <td className="px-2 py-1.5 text-right"><button onClick={() => run(() => deleteNeed(need.id))} className="text-stone-300 hover:text-rose-600" aria-label="Remove"><Trash2 size={15} /></button></td>
    </tr>
  );
}

// ── Sourcing tab: the buyer's worksheet ─────────────────────────────────────
type Drawer =
  | { kind: "catalog"; need: Need; substituteFor?: SourcingLine }
  | { kind: "open-orders"; need: Need }
  | { kind: "manual"; need: Need }
  | null;

function SourcingTab({ job, run, me }: { job: Job; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; me?: string }) {
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [sending, setSending] = useState(false);

  const sendable = job.needs.flatMap((n) => n.lines).filter((l) => !l.order_item_id && ["proposed", "ready", "follow_up"].includes(l.status) && l.order_qty > 0);
  // Before creating POs, offer any open PO at the same vendor: "add to the
  // existing Impressive Silk order" is an action here, not an email reminder.
  type PlanRow = { key: string; supplier_id: number | null; vendor: string; options: Array<{ id: number; name: string; status: string; line_count: number }>; choice: number };
  const [plan, setPlan] = useState<PlanRow[] | null>(null);
  const doSend = async (append_to: Record<string, number>) => {
    setSending(true);
    setPlan(null);
    const j = await run(() => sendToPO(job.id, { append_to }), "Sent to purchase orders");
    setSending(false);
    if (j?.created_orders?.length) toast.message(`${j.created_orders.length} purchase order${j.created_orders.length === 1 ? "" : "s"} created`, { description: "Open the Purchase orders tab to place them." });
  };
  const send = async () => {
    const vendors = new Map<string, { supplier_id: number | null; vendor: string }>();
    for (const l of sendable) {
      const key = l.supplier_id ? String(l.supplier_id) : `v:${l.vendor_name || "unknown"}`;
      if (!vendors.has(key)) vendors.set(key, { supplier_id: l.supplier_id ?? null, vendor: l.vendor_name || "Unknown vendor" });
    }
    const rows: PlanRow[] = await Promise.all([...vendors.entries()].map(async ([key, v]) => {
      let options: PlanRow["options"] = [];
      if (v.supplier_id) { try { options = await openPOsForVendor(v.supplier_id); } catch {} }
      return { key, supplier_id: v.supplier_id, vendor: v.vendor, options, choice: 0 };
    }));
    if (rows.some((r) => r.options.length)) setPlan(rows); else doSend({});
  };

  const pick = async (need: Need, p: CatalogPick, substituteFor?: SourcingLine) => {
    const j = await run(() => addSourcing(need.id, { product_id: p.id, substitute_for: substituteFor?.id }), `${p.name} added`);
    if (j) setDrawer(null);
  };

  return (
    <div className="flex gap-6">
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-stone-600">For each gap: check open orders first, then pick from the catalog. Pack math and adjusted cost fill in from the product.</p>
          <button onClick={send} disabled={!sendable.length || sending} className={btnPrimary}>
            <PackageCheck size={14} /> Send {sendable.length || ""} line{sendable.length === 1 ? "" : "s"} to purchase orders
          </button>
        </div>
        {job.needs.length === 0 && <p className="rounded-xl border border-dashed border-stone-300 p-8 text-center text-sm text-stone-400">Add the need list first.</p>}
        <div className="flex flex-col gap-4">
          {job.needs.map((n) => (
            <NeedSourcing key={n.id} need={n} run={run} me={me} jobId={job.id}
              onCatalog={(sub) => setDrawer({ kind: "catalog", need: n, substituteFor: sub })}
              onOpenOrders={() => setDrawer({ kind: "open-orders", need: n })}
              onManual={() => setDrawer({ kind: "manual", need: n })} />
          ))}
        </div>
        <TasksPanel job={job} run={run} me={me} />
      </div>
      {plan && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4" onClick={() => setPlan(null)}>
          <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-stone-800">Where should these lines go?</h3>
            <p className="mt-1 text-xs text-stone-500">Some vendors already have an open purchase order. Add to it, or start a new one.</p>
            <div className="mt-4 flex flex-col gap-3">
              {plan.map((r, i) => (
                <label key={r.key} className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-stone-700">{r.vendor}</span>
                  <select value={r.choice} onChange={(e) => setPlan(plan.map((x, j) => (j === i ? { ...x, choice: Number(e.target.value) } : x)))} className={`${input} w-64`}>
                    <option value={0}>New purchase order</option>
                    {r.options.map((o) => <option key={o.id} value={o.id}>Add to: {o.name} ({o.status.replace("_", " ")}, {o.line_count} line{o.line_count === 1 ? "" : "s"})</option>)}
                  </select>
                </label>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setPlan(null)} className={btnGhost}>Cancel</button>
              <button onClick={() => doSend(Object.fromEntries(plan.filter((r) => r.choice).map((r) => [r.key, r.choice])))} className={btnPrimary}><PackageCheck size={14} /> Send</button>
            </div>
          </div>
        </div>
      )}
      {drawer && (
        <aside className="sticky top-[81px] h-[calc(100vh-100px)] w-[380px] shrink-0 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
          {drawer.kind === "catalog" && (
            <CatalogPickPane title={`${drawer.substituteFor ? "Substitute for " + (drawer.substituteFor.description || "line") : drawer.need.label}${drawer.need.spec ? ` · ${drawer.need.spec}` : ""}`}
              initialQuery={drawer.need.label} onClose={() => setDrawer(null)} onPick={(p) => pick(drawer.need, p, drawer.substituteFor)} />
          )}
          {drawer.kind === "open-orders" && <OpenOrdersPane need={drawer.need} run={run} onClose={() => setDrawer(null)} />}
          {drawer.kind === "manual" && <ManualLinePane need={drawer.need} run={run} onClose={() => setDrawer(null)} />}
        </aside>
      )}
    </div>
  );
}

function NeedSourcing({ need, run, me, jobId, onCatalog, onOpenOrders, onManual }: {
  need: Need; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; me?: string; jobId: number;
  onCatalog: (substituteFor?: SourcingLine) => void; onOpenOrders: () => void; onManual: () => void;
}) {
  const buying = need.need_qty - need.shelf_qty;
  return (
    <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 bg-stone-50 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-semibold text-stone-800">{need.label}{need.spec ? <span className="ml-1 font-normal text-stone-500">· {need.spec}</span> : null}</span>
          <span className="text-xs text-stone-500">need <b className="tabular-nums">{qty(need.need_qty)}</b> · shelf <b className="tabular-nums">{qty(need.shelf_qty)}</b>{need.allocated_qty ? <> · allocated <b className="tabular-nums">{qty(need.allocated_qty)}</b></> : null}{need.ordered_qty ? <> · on order <b className="tabular-nums">{qty(need.ordered_qty)}</b></> : null}</span>
          {need.ready ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">On shelf</span>
            : need.unsourced_qty > 0 ? <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900"><AlertTriangle size={11} /> {qty(need.unsourced_qty)} unsourced</span>
            : <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-semibold text-stone-700">Gap covered</span>}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onOpenOrders} className={btnGhost} title="Use something already on order"><Link2 size={12} /> Open orders</button>
          <button onClick={() => onCatalog()} className={btnGhost}><Search size={12} /> Catalog</button>
          <button onClick={onManual} className={btnGhost}><Plus size={12} /> By hand</button>
        </div>
      </div>
      {need.lines.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-stone-400">
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-2 py-2 font-medium">Vendor · SKU</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 text-right font-medium" title="How much of the need this line is for">Covers</th>
                <th className="px-2 py-2 text-right font-medium">Pack</th>
                <th className="px-2 py-2 text-right font-medium">Packs</th>
                <th className="px-2 py-2 text-right font-medium">Order</th>
                <th className="px-2 py-2 text-right font-medium">Cost</th>
                <th className="px-2 py-2 text-right font-medium">Each</th>
                <th className="px-2 py-2 text-right font-medium">Line</th>
                <th className="px-2 py-2 font-medium">Notes</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {need.lines.map((l) => <SourcingRow key={l.id} line={l} need={need} run={run} me={me} jobId={jobId} onSubstitute={() => onCatalog(l)} />)}
            </tbody>
          </table>
        </div>
      )}
      {need.lines.length === 0 && buying > 0 && (
        <p className="px-4 py-3 text-xs text-stone-400">Nothing sourced yet for the {qty(buying)} not on the shelf.</p>
      )}
    </div>
  );
}

function SourcingRow({ line, need, run, me, jobId, onSubstitute }: {
  line: SourcingLine; need: Need; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; me?: string; jobId: number; onSubstitute: () => void;
}) {
  const [v, setV] = useState({ covers: String(line.covers_qty), pack: String(line.pack_qty), order: String(line.order_qty), cost: line.unit_cost == null ? "" : String(line.unit_cost), notes: line.notes || "" });
  useEffect(() => setV({ covers: String(line.covers_qty), pack: String(line.pack_qty), order: String(line.order_qty), cost: line.unit_cost == null ? "" : String(line.unit_cost), notes: line.notes || "" }), [line]);
  const locked = !!line.order_item_id || line.status === "allocated";
  const save = (body: Partial<SourcingLine>) => run(() => updateSourcing(line.id, body));
  const img = proxied(line.image_url);
  const followUp = async () => {
    const title = window.prompt("Follow-up", `Email ${line.vendor_name || "vendor"} about ${line.description || need.label}`);
    if (!title) return;
    await run(() => addTask(jobId, { title, assignee: me, sourcing_line_id: line.id }), "Follow-up added");
    if (line.status !== "follow_up" && !line.order_item_id) save({ status: "follow_up" });
  };
  const dim = line.status === "sold_out" || line.status === "on_hold";
  return (
    <tr className={`border-t border-stone-100 align-middle ${dim ? "opacity-60" : ""}`}>
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border border-stone-200 bg-stone-50">
            {img ? <img src={img} alt="" className="h-full w-full object-contain" /> : <Package size={18} className="text-stone-300" />}
          </div>
          <div className="min-w-0">
            <p className={`max-w-[16rem] truncate font-medium text-stone-800 ${line.status === "sold_out" ? "line-through" : ""}`} title={line.description || ""}>{line.description || "—"}</p>
            {line.status === "allocated" && <p className="text-[11px] text-sky-700">{qty(line.allocated_qty)} from {line.allocated_order_name}</p>}
            {line.order_item_id && <p className="text-[11px] text-stone-500">{line.order_name}{line.order_status ? ` · ${line.order_status.replace("_", " ")}` : ""}{line.received_qty ? ` · ${qty(line.received_qty)} received` : ""}</p>}
          </div>
        </div>
      </td>
      <td className="px-2 py-2 text-xs text-stone-600">{line.vendor_name || "—"}<br /><span className="font-mono text-[11px] text-stone-400">{line.sku || ""}</span></td>
      <td className="px-2 py-2">
        {locked ? linePill(line.status) : (
          <select value={line.status} onChange={(e) => save({ status: e.target.value as SourcingStatus })} className={`${input} text-xs`}>
            {(["proposed", "ready", "follow_up", "sold_out", "on_hold"] as SourcingStatus[]).map((s) => <option key={s} value={s}>{SOURCING_LABEL[s]}</option>)}
          </select>
        )}
      </td>
      <td className="px-2 py-2 text-right">
        {line.status === "allocated" ? <span className="tabular-nums">{qty(line.allocated_qty)}</span>
          : <input type="number" min={0} step="any" value={v.covers} disabled={locked} onChange={(e) => setV({ ...v, covers: e.target.value })} onBlur={() => Number(v.covers) !== line.covers_qty && save({ covers_qty: Number(v.covers) })} className={`${input} w-16 text-right`} />}
      </td>
      <td className="px-2 py-2 text-right">
        {line.status === "allocated" ? "—" : (
          <div className="flex items-center justify-end gap-1">
            <input type="number" min={1} value={v.pack} disabled={locked} onChange={(e) => setV({ ...v, pack: e.target.value })} onBlur={() => Number(v.pack) !== line.pack_qty && save({ pack_qty: Math.max(1, Number(v.pack)) })} className={`${input} w-14 text-right`} />
            <button disabled={locked} onClick={() => save({ price_per: line.price_per === "pack" ? "each" : "pack" })} className="rounded border border-stone-200 px-1 text-[10px] text-stone-500 hover:border-emerald-400" title="Is the catalog price per pack or per piece?">{line.price_per === "pack" ? "$/pack" : "$/each"}</button>
          </div>
        )}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-stone-600">{line.status === "allocated" ? "—" : line.packs}</td>
      <td className="px-2 py-2 text-right">
        {line.status === "allocated" ? "—" : (
          <div className="flex flex-col items-end">
            <input type="number" min={0} step="any" value={v.order} onChange={(e) => setV({ ...v, order: e.target.value })} onBlur={() => Number(v.order) !== line.order_qty && save({ order_qty: Number(v.order) })} className={`${input} w-16 text-right font-semibold`} />
            {line.overage_qty > 0 && <span className="text-[10px] text-stone-400">+{qty(line.overage_qty)} to stock</span>}
          </div>
        )}
      </td>
      <td className="px-2 py-2 text-right"><input type="number" min={0} step="0.01" value={v.cost} disabled={locked} onChange={(e) => setV({ ...v, cost: e.target.value })} onBlur={() => (v.cost === "" ? null : Number(v.cost)) !== (line.unit_cost ?? null) && save({ unit_cost: v.cost === "" ? (null as any) : Number(v.cost) })} className={`${input} w-20 text-right`} /></td>
      <td className="px-2 py-2 text-right tabular-nums text-stone-600">{line.price_per === "pack" ? money(line.adj_unit_cost) : money(line.unit_cost)}</td>
      <td className="px-2 py-2 text-right font-medium tabular-nums text-stone-800">{line.status === "allocated" ? "—" : money(line.line_cost)}</td>
      <td className="px-2 py-2"><input value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} onBlur={() => v.notes !== (line.notes || "") && save({ notes: v.notes })} className={`${input} w-40`} /></td>
      <td className="px-2 py-2">
        <div className="flex items-center justify-end gap-1.5">
          {!locked && <button onClick={onSubstitute} className="text-[11px] text-stone-500 hover:text-emerald-700" title="Sold out? Pick a substitute and keep the history">Substitute</button>}
          <button onClick={followUp} className="text-[11px] text-stone-500 hover:text-amber-700">Follow-up</button>
          {!line.order_item_id && <button onClick={() => run(() => deleteSourcing(line.id))} className="text-stone-300 hover:text-rose-600" aria-label="Remove"><Trash2 size={14} /></button>}
        </div>
      </td>
    </tr>
  );
}

function OpenOrdersPane({ need, run, onClose }: { need: Need; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; onClose: () => void }) {
  const [q, setQ] = useState(need.label);
  const [rows, setRows] = useState<OpenOrderLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  useEffect(() => {
    const t = window.setTimeout(async () => {
      if (!q.trim()) { setRows([]); return; }
      setLoading(true);
      try { setRows(await searchOpenOrders({ q })); } catch { setRows([]); } finally { setLoading(false); }
    }, 250);
    return () => window.clearTimeout(t);
  }, [q]);
  const take = async (r: OpenOrderLine) => {
    const n = Number(amounts[r.order_item_id] ?? Math.min(r.remaining_qty, need.unsourced_qty || need.gap_qty || r.remaining_qty));
    if (!n || n <= 0) return;
    const j = await run(() => allocateFromOrder(need.id, { order_item_id: r.order_item_id, qty: n }), `Allocated ${qty(n)} from ${r.order_name}`);
    if (j) onClose();
  };
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-500">Already on order</p>
          <p className="text-sm font-medium text-stone-800">{need.label}</p>
        </div>
        <button onClick={onClose} className="rounded p-1 text-stone-400 hover:bg-stone-100" aria-label="Close">✕</button>
      </div>
      <div className="px-4 py-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} className={`${input} w-full`} placeholder="hydrangea" />
        <p className="mt-1.5 text-[11px] text-stone-400">{loading ? "Looking…" : "Lines on open purchase orders, including market buys, with what is still unallocated."}</p>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <div className="flex flex-col gap-2">
          {rows.map((r) => (
            <div key={r.order_item_id} className="rounded-lg border border-stone-200 p-2.5">
              <p className="truncate text-sm font-medium text-stone-800" title={r.name}>{r.name}</p>
              <p className="text-[11px] text-stone-500">{r.supplier_name || "—"}{r.sku ? ` · ${r.sku}` : ""} · {r.order_name}{r.job_name ? ` (for ${r.job_name})` : ""}</p>
              <p className="mt-1 text-xs text-stone-600">{qty(r.quantity)} ordered · <b>{qty(r.remaining_qty)}</b> unallocated{r.received_qty ? ` · ${qty(r.received_qty)} received` : ""}</p>
              {r.remaining_qty > 0 && (
                <div className="mt-2 flex items-center gap-2">
                  <input type="number" min={0} max={r.remaining_qty} step="any" value={amounts[r.order_item_id] ?? String(Math.min(r.remaining_qty, need.unsourced_qty || need.gap_qty || r.remaining_qty))} onChange={(e) => setAmounts({ ...amounts, [r.order_item_id]: e.target.value })} className={`${input} w-20 text-right`} />
                  <button onClick={() => take(r)} className={btnPrimary}>Allocate to this job</button>
                </div>
              )}
            </div>
          ))}
          {!loading && q.trim() && rows.length === 0 && <p className="py-8 text-center text-sm text-stone-400">Nothing on open orders matches. Market buys must be entered as purchase orders to show here.</p>}
        </div>
      </div>
    </div>
  );
}

function ManualLinePane({ need, run, onClose }: { need: Need; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; onClose: () => void }) {
  const [v, setV] = useState({ vendor_name: "", sku: "", description: need.label, unit_cost: "", pack_qty: "1", price_per: "each" as "each" | "pack", covers_qty: String(need.unsourced_qty || need.gap_qty) });
  const add = async () => {
    const j = await run(() => addSourcing(need.id, {
      vendor_name: v.vendor_name || undefined, sku: v.sku || undefined, description: v.description || undefined,
      unit_cost: v.unit_cost === "" ? undefined : Number(v.unit_cost), pack_qty: Math.max(1, Number(v.pack_qty) || 1),
      price_per: v.price_per, covers_qty: Number(v.covers_qty) || 0,
    }), "Line added");
    if (j) onClose();
  };
  const L = ({ k, label, type = "text" }: { k: keyof typeof v; label: string; type?: string }) => (
    <label className="flex flex-col gap-1 text-xs text-stone-500">{label}<input type={type} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} className={input} /></label>
  );
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <div><p className="text-xs font-semibold uppercase tracking-widest text-stone-500">Add by hand</p><p className="text-sm font-medium text-stone-800">{need.label}</p></div>
        <button onClick={onClose} className="rounded p-1 text-stone-400 hover:bg-stone-100" aria-label="Close">✕</button>
      </div>
      <div className="flex flex-col gap-3 px-4 py-3">
        <p className="text-[11px] text-stone-400">For items not in the catalog: a market buy, a local store, a vendor not imported yet.</p>
        <L k="vendor_name" label="Vendor" />
        <L k="sku" label="SKU / item number" />
        <L k="description" label="Description" />
        <div className="grid grid-cols-2 gap-3">
          <L k="unit_cost" label="Price" type="number" />
          <label className="flex flex-col gap-1 text-xs text-stone-500">Price is per
            <select value={v.price_per} onChange={(e) => setV({ ...v, price_per: e.target.value as any })} className={input}><option value="each">each</option><option value="pack">pack</option></select>
          </label>
          <L k="pack_qty" label="Pack size" type="number" />
          <L k="covers_qty" label="Covers (of the need)" type="number" />
        </div>
        <button onClick={add} className={btnPrimary}><Plus size={14} /> Add line</button>
      </div>
    </div>
  );
}

function TasksPanel({ job, run, me }: { job: Job; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; me?: string }) {
  const [title, setTitle] = useState("");
  const open = job.tasks.filter((t) => !t.done_at);
  const done = job.tasks.filter((t) => t.done_at);
  const add = () => { if (title.trim()) run(() => addTask(job.id, { title: title.trim(), assignee: me })).then((j) => j && setTitle("")); };
  return (
    <section className="mt-8">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-widest text-stone-500">Follow-ups {open.length ? `(${open.length})` : ""}</h3>
      <div className="rounded-xl border border-stone-200 bg-white p-3">
        <div className="flex gap-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Email Jason to add the champagne leaves to the open order" className={`${input} flex-1`} />
          <button onClick={add} className={btnPrimary}><Plus size={14} /> Add</button>
        </div>
        <ul className="mt-3 flex flex-col gap-1.5">
          {open.map((t) => (
            <li key={t.id} className="flex items-center gap-3 text-sm">
              <input type="checkbox" checked={false} onChange={() => run(() => updateTask(t.id, { done: true }))} />
              <span className="flex-1 text-stone-800">{t.title}</span>
              <span className="text-[11px] text-stone-400">{t.assignee || ""}{t.due ? ` · due ${dateStr(t.due)}` : ""}</span>
              <button onClick={() => run(() => deleteTask(t.id))} className="text-stone-300 hover:text-rose-600" aria-label="Remove"><Trash2 size={13} /></button>
            </li>
          ))}
          {done.map((t) => (
            <li key={t.id} className="flex items-center gap-3 text-sm text-stone-400">
              <input type="checkbox" checked onChange={() => run(() => updateTask(t.id, { done: false }))} />
              <span className="flex-1 line-through">{t.title}</span>
            </li>
          ))}
          {job.tasks.length === 0 && <li className="text-xs text-stone-400">No follow-ups. Add one from a sourcing line or here.</li>}
        </ul>
      </div>
    </section>
  );
}

// ── Purchase orders tab: status, arrival, check-in ─────────────────────────
function OrdersTab({ job, run, reload }: { job: Job; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; reload: () => void }) {
  if (job.purchase_orders.length === 0) {
    return <p className="rounded-xl border border-dashed border-stone-300 p-8 text-center text-sm text-stone-400">No purchase orders yet. Send sourcing lines to create them, one per vendor.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      {job.purchase_orders.map((po) => <POCard key={po.id} po={po} run={run} reload={reload} />)}
    </div>
  );
}

function POCard({ po, run, reload }: { po: Job["purchase_orders"][number]; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>; reload: () => void }) {
  const [lines, setLines] = useState<POLine[] | null>(null);
  const [open, setOpen] = useState(false);
  const [recv, setRecv] = useState<Record<number, string>>({});
  const [meta, setMeta] = useState({ vendor_order_no: po.vendor_order_no || "", expected_arrival: dateStr(po.expected_arrival), freight: po.freight == null ? "" : String(po.freight) });
  useEffect(() => setMeta({ vendor_order_no: po.vendor_order_no || "", expected_arrival: dateStr(po.expected_arrival), freight: po.freight == null ? "" : String(po.freight) }), [po]);

  const loadLines = useCallback(async () => { try { setLines(await poLines(po.id)); } catch { setLines([]); } }, [po.id]);
  useEffect(() => { if (open && lines === null) loadLines(); }, [open, lines, loadLines]);

  const savePO = async (body: Record<string, unknown>) => {
    try { await updatePO(po.id, body); reload(); } catch (e: any) { toast.error(e?.message || "Could not update the order"); }
  };
  const receive = async (l: POLine) => {
    const n = Number(recv[l.id] ?? (l.quantity - l.received_qty));
    if (!n || n <= 0) return;
    const j = await run(() => receiveLine(l.id, n), `${qty(n)} × ${l.name} checked in`);
    if (j) { setRecv({ ...recv, [l.id]: "" }); loadLines(); }
  };
  const pct = po.total_qty ? Math.round((po.received_qty / po.total_qty) * 100) : 0;
  return (
    <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
      <div className="flex flex-wrap items-center gap-3 border-b border-stone-100 bg-stone-50 px-4 py-2.5">
        <button onClick={() => setOpen((v) => !v)} className="font-semibold text-stone-800 hover:text-emerald-800">{po.name}</button>
        <span className="text-xs text-stone-400">{po.supplier_name || "—"} · {po.line_count} line{po.line_count === 1 ? "" : "s"}</span>
        <select value={po.status || "draft"} onChange={(e) => savePO({ status: e.target.value })} className={`${input} text-xs`}>
          {PO_STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </select>
        {!po.placed_at && <button onClick={() => savePO({ placed: true })} className={btnGhost}><Check size={12} /> Mark placed</button>}
        <span className="ml-auto text-xs text-stone-500">{qty(po.received_qty)}/{qty(po.total_qty)} received · {pct}%</span>
        <a href={`/orders`} onClick={() => { try { localStorage.setItem("leaf-ledger:active-order:v1", String(po.id)); } catch {} }} className="inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline"><ExternalLink size={11} /> Open PO</a>
      </div>
      <div className="grid grid-cols-3 gap-3 px-4 py-3">
        <label className="flex flex-col gap-1 text-xs text-stone-500">Vendor order #<input value={meta.vendor_order_no} onChange={(e) => setMeta({ ...meta, vendor_order_no: e.target.value })} onBlur={() => meta.vendor_order_no !== (po.vendor_order_no || "") && savePO({ vendor_order_no: meta.vendor_order_no })} className={input} /></label>
        <label className="flex flex-col gap-1 text-xs text-stone-500">Expected arrival<input type="date" value={meta.expected_arrival} onChange={(e) => setMeta({ ...meta, expected_arrival: e.target.value })} onBlur={() => meta.expected_arrival !== dateStr(po.expected_arrival) && savePO({ expected_arrival: meta.expected_arrival || null })} className={input} /></label>
        <label className="flex flex-col gap-1 text-xs text-stone-500">Freight<input type="number" step="0.01" value={meta.freight} onChange={(e) => setMeta({ ...meta, freight: e.target.value })} onBlur={() => savePO({ freight: meta.freight === "" ? null : Number(meta.freight) })} className={input} /></label>
      </div>
      {open && (
        <div className="border-t border-stone-100">
          {lines === null ? <p className="px-4 py-3 text-xs text-stone-400">Loading…</p> : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wide text-stone-400"><th className="px-4 py-2 font-medium">Line</th><th className="px-2 py-2 font-medium">For</th><th className="px-2 py-2 text-right font-medium">Ordered</th><th className="px-2 py-2 text-right font-medium">Received</th><th className="px-2 py-2 text-right font-medium">Check in</th></tr></thead>
              <tbody>
                {lines.map((l) => {
                  const left = l.quantity - l.received_qty;
                  return (
                    <tr key={l.id} className="border-t border-stone-100">
                      <td className="px-4 py-2"><span className="font-medium text-stone-800">{l.name}</span>{l.sku && <span className="ml-2 font-mono text-[11px] text-stone-400">{l.sku}</span>}</td>
                      <td className="px-2 py-2 text-xs text-stone-500">{l.need_label || "—"}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{qty(l.quantity)}</td>
                      <td className={`px-2 py-2 text-right tabular-nums ${left <= 0 ? "text-emerald-700" : ""}`}>{qty(l.received_qty)}</td>
                      <td className="px-2 py-2 text-right">
                        {left > 0 ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <input type="number" min={0} step="any" value={recv[l.id] ?? String(left)} onChange={(e) => setRecv({ ...recv, [l.id]: e.target.value })} className={`${input} w-16 text-right`} />
                            <button onClick={() => receive(l)} className={btnGhost}><PackageCheck size={12} /> Receive</button>
                          </div>
                        ) : <span className="text-[11px] font-semibold text-emerald-700">All in</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ── Build sheet: what the builders take to the bench ────────────────────────
function BuildTab({ job, run }: { job: Job; run: (fn: () => Promise<Job>, ok?: string) => Promise<Job | null> }) {
  const byPiece = useMemo(() => {
    const m = new Map<number | null, Need[]>();
    for (const n of job.needs) { const k = n.piece_id ?? null; m.set(k, [...(m.get(k) || []), n]); }
    return m;
  }, [job.needs]);
  return (
    <div className="print:px-0">
      <div className="mb-4 flex items-center justify-between print:hidden">
        <p className="text-sm text-stone-600">The green folder: what each piece needs, what is on the shelf, what is still coming, and what was actually ordered.</p>
        <button onClick={() => window.print()} className={btnGhost}><Printer size={13} /> Print</button>
      </div>
      <div className="rounded-xl border border-stone-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{job.name}</h2>
        <p className="text-xs text-stone-500">{job.client_name || ""}{job.collection ? ` · ${job.collection}` : ""}{job.install_date ? ` · installs ${dateStr(job.install_date)}` : ""}{job.color_palette ? ` · ${job.color_palette}` : ""}</p>
        {job.intake?.notes_on_product && <p className="mt-2 text-sm text-stone-700">{String(job.intake.notes_on_product)}</p>}
        <div className="mt-4 flex flex-wrap gap-2">
          {job.pieces.map((p) => (
            <span key={p.id} className="rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">{qty(p.qty)} × {p.piece_type}{Object.entries(p.spec || {}).filter(([, v]) => v).map(([k, v]) => ` · ${k} ${v}`).join("")}</span>
          ))}
        </div>
        <table className="mt-5 w-full text-sm">
          <thead><tr className="text-left text-[11px] uppercase tracking-wide text-stone-400"><th className="py-2 font-medium">Material</th><th className="py-2 text-right font-medium">Need</th><th className="py-2 text-right font-medium">On shelf</th><th className="py-2 font-medium">Still coming</th><th className="py-2 font-medium">What was ordered</th></tr></thead>
          <tbody>
            {job.needs.map((n) => {
              const shown = n.lines.filter((l) => l.status !== "sold_out" && l.status !== "on_hold");
              return (
                <tr key={n.id} className="border-t border-stone-100 align-top">
                  <td className="py-2 font-medium text-stone-800">{n.label}{n.spec && <span className="ml-1 font-normal text-stone-500">· {n.spec}</span>}</td>
                  <td className="py-2 text-right tabular-nums">{qty(n.need_qty)}</td>
                  <td className={`py-2 text-right tabular-nums ${n.ready ? "text-emerald-700 font-semibold" : ""}`}>{qty(n.on_shelf_qty)}</td>
                  <td className="py-2 text-xs text-stone-600">
                    {n.ready ? <span className="inline-flex items-center gap-1 text-emerald-700"><Check size={12} /> ready</span>
                      : n.ordered_qty - n.received_qty > 0 ? `${qty(n.ordered_qty - n.received_qty)} on order${shown.find((l) => l.expected_arrival) ? `, due ${dateStr(shown.find((l) => l.expected_arrival)!.expected_arrival)}` : ""}`
                      : n.unsourced_qty > 0 ? <span className="text-amber-800">{qty(n.unsourced_qty)} not yet sourced</span> : "sourced, not ordered"}
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-2">
                      {shown.map((l) => {
                        const img = proxied(l.image_url);
                        return (
                          <div key={l.id} className="flex items-center gap-2 rounded-md border border-stone-200 p-1 pr-2">
                            <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded bg-stone-50">{img ? <img src={img} alt="" className="h-full w-full object-contain" /> : <Package size={14} className="text-stone-300" />}</div>
                            <div className="text-[11px] leading-tight text-stone-600"><p className="max-w-[12rem] truncate font-medium text-stone-800">{l.description}</p><p>{l.vendor_name}{l.sku ? ` · ${l.sku}` : ""}</p></div>
                          </div>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {byPiece.size === 0 && <p className="mt-4 text-xs text-stone-400">The need list is empty.</p>}
      </div>
    </div>
  );
}
