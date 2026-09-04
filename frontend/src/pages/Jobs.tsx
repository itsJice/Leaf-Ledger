import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ClipboardList, Plus, Trash2, Search, PackageCheck, FileSpreadsheet,
  ExternalLink, Check, Package, AlertTriangle, Link2,
} from "lucide-react";
import { toast } from "sonner";
import Layout from "components/Layout";
import CatalogPickPane, { type CatalogPick } from "components/CatalogPickPane";
import { useAuth } from "app/auth/AuthProvider";
import { apiFetch } from "utils/apiFetch";
import {
  listJobs, getJob, createJob, updateJob, deleteJob,
  addNeeds, updateNeed, deleteNeed,
  addSourcing, updateSourcing, deleteSourcing,
  searchOpenOrders, allocateFromOrder, sendToPO, openPOsForVendor, updatePO, poLines, receiveLine,
  addTask, updateTask, deleteTask, downloadExport,
  STAGES, STAGE_LABEL, SOURCING_LABEL,
  type Job, type JobSummary, type Need, type SourcingLine, type Stage,
  type OpenOrderLine, type POLine, type SourcingStatus,
} from "utils/jobs";

// Sourcing: the purchaser's worksheet, one per client job.
//
// The designers keep their paper (the Manufacturing Order and the purple
// "what we still need" sheet). The buyer transcribes the purple sheet's lines
// here, then sources each one: open orders first, then the catalog, with pack
// math, substitutions, follow-ups, and purchase orders with check-in. The
// tracking sheet exports in the binder's column layout with pictures.
//
// See docs/JOBS_SOURCING.md for what is deliberately held back for later.
// The job's stage is derived on the server from its lines.

type Tab = "worksheet" | "orders" | "details";
const TABS: Array<{ id: Tab; label: string }> = [
  { id: "worksheet", label: "Worksheet" },
  { id: "orders", label: "Purchase orders" },
  { id: "details", label: "Job details" },
];
const PO_STATUSES = ["draft", "approved", "placed", "follow_up", "shipped", "arrived", "closed"];

const proxied = (url?: string | null) => (url ? `/api/products/image-proxy?url=${encodeURIComponent(url)}` : undefined);
const money = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);
const qty = (n?: number | null) => (n == null ? "" : Number.isInteger(Number(n)) ? String(n) : Number(n).toFixed(1));
const dateStr = (d?: string | null) => (d ? String(d).slice(0, 10) : "");

const input = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm outline-none focus:border-emerald-500";
const btnPrimary = "inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50";
const btnGhost = "inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700";

type Run = (fn: () => Promise<Job>, ok?: string) => Promise<Job | null>;

function stagePill(stage: Stage) {
  const tone: Record<Stage, string> = {
    new: "bg-stone-100 text-stone-600",
    sourcing: "bg-amber-50 text-amber-800",
    ordered: "bg-amber-50 text-amber-800",
    receiving: "bg-amber-50 text-amber-800",
    complete: "bg-emerald-50 text-emerald-800",
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
  const [tab, setTab] = useState<Tab>("worksheet");
  const [loading, setLoading] = useState(false);

  const activeId = jobId ? Number(jobId) : null;

  const refreshList = useCallback(async () => {
    try { setJobs(await listJobs()); } catch { setJobs([]); }
  }, []);
  useEffect(() => { refreshList(); }, [refreshList]);

  const load = useCallback(async (id: number) => {
    setLoading(true);
    try { setJob(await getJob(id)); }
    catch { setJob(null); toast.error("That worksheet could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (activeId) load(activeId); else setJob(null); }, [activeId, load]);

  // Every mutation returns the whole job; apply it and keep the rail in step.
  const apply = useCallback((next: Job) => { setJob(next); refreshList(); }, [refreshList]);
  const run: Run = useCallback(async (fn, ok) => {
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
      const created = await createJob({ name: "New worksheet" });
      await refreshList();
      navigate(`/sourcing/${created.id}`);
      setTab("details");
    } catch (e: any) { toast.error(e?.message || "Could not create a worksheet."); }
  };

  const removeJob = async () => {
    if (!job) return;
    if (!window.confirm(`Delete "${job.name}" and its lines? Purchase orders stay.`)) return;
    await deleteJob(job.id);
    setJob(null);
    await refreshList();
    navigate("/sourcing");
    toast.success("Worksheet deleted");
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-8 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            <ClipboardList size={18} className="text-emerald-700" /> Sourcing
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">The buyer's worksheet: what the designers still need, and where it is coming from.</p>
        </div>
        <button onClick={newJob} className={btnPrimary}><Plus size={15} /> New worksheet</button>
      </header>

      <div className="flex">
        <aside className="w-72 flex-shrink-0 border-r border-stone-200 px-3 py-4" style={{ minHeight: "calc(100vh - 65px)" }}>
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-stone-500">Worksheets ({jobs.length})</p>
          {jobs.length === 0 ? (
            <p className="px-2 text-sm text-stone-400">Nothing yet. Start one when a purple sheet lands on your desk.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {jobs.map((j) => {
                const active = j.id === activeId;
                return (
                  <button key={j.id} onClick={() => navigate(`/sourcing/${j.id}`)}
                    className={`flex flex-col rounded-lg px-3 py-2 text-left ${active ? "bg-emerald-50 ring-1 ring-emerald-200" : "hover:bg-stone-100"}`}>
                    <span className="flex items-center justify-between gap-2">
                      <span className={`truncate text-sm font-medium ${active ? "text-emerald-900" : "text-stone-700"}`}>{j.name}</span>
                      {stagePill(j.stage)}
                    </span>
                    <span className="mt-0.5 truncate text-xs text-stone-400">
                      {j.client_name || "No client"}{j.collection ? ` · ${j.collection}` : ""}
                    </span>
                    <span className="mt-0.5 text-[11px] text-stone-400">
                      {j.summary.ready_count}/{j.summary.need_count} lines covered
                      {j.summary.unsourced_count ? ` · ${j.summary.unsourced_count} to source` : ""}
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
            <p className="py-20 text-center text-sm text-stone-400">Loading…</p>
          ) : !job ? <Empty /> : (
            <>
              <JobHeader job={job} onDelete={removeJob} onChange={(body) => run(() => updateJob(job.id, body))} />
              <nav className="mt-5 flex gap-1 border-b border-stone-200">
                {TABS.map((t) => (
                  <button key={t.id} onClick={() => setTab(t.id)}
                    className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === t.id ? "border-emerald-700 text-emerald-800" : "border-transparent text-stone-500 hover:text-stone-800"}`}>
                    {t.label}
                    {t.id === "worksheet" && job.summary.unsourced_count > 0 && <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-[11px] text-amber-800">{job.summary.unsourced_count}</span>}
                    {t.id === "orders" && job.purchase_orders.length > 0 && <span className="ml-1.5 text-[11px] text-stone-400">{job.purchase_orders.length}</span>}
                  </button>
                ))}
              </nav>
              <div className="mt-5">
                {tab === "worksheet" && <Worksheet job={job} run={run} me={me} />}
                {tab === "orders" && <OrdersTab job={job} run={run} reload={() => load(job.id)} />}
                {tab === "details" && <DetailsTab job={job} run={run} />}
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
      <p className="mb-1 text-base font-medium text-stone-600">No worksheet selected</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">Pick one on the left, or start a new one from the purple sheet.</p>
    </div>
  );
}

// ── Header: name, stage strip, export ───────────────────────────────────────
function JobHeader({ job, onDelete, onChange }: { job: Job; onDelete: () => void; onChange: (b: Record<string, unknown>) => void }) {
  const [name, setName] = useState(job.name);
  useEffect(() => setName(job.name), [job.id, job.name]);
  const idx = STAGES.indexOf(job.stage);
  const exportIt = async () => {
    try { await downloadExport(job.id, job.name); } catch { toast.error("Export failed"); }
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
            {job.summary.buy_cost != null && <> · <span className="font-semibold text-emerald-800">{money(job.summary.buy_cost)}</span> to buy</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={exportIt} className={btnGhost} title="The binder sheet, with pictures"><FileSpreadsheet size={13} /> Tracking sheet</button>
          <button onClick={onDelete} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"><Trash2 size={13} /> Delete</button>
        </div>
      </div>
      <ol className="mt-4 grid grid-cols-5 gap-1">
        {STAGES.map((s, i) => (
          <li key={s} className={`border-t-2 px-1 pt-1.5 text-[11px] font-semibold ${i < idx ? "border-emerald-600 text-emerald-700" : i === idx ? "border-emerald-700 text-emerald-900" : "border-stone-200 text-stone-400"}`}>
            {STAGE_LABEL[s]}
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── Job details: client, project, notes ─────────────────────────────────────
function DetailsTab({ job, run }: { job: Job; run: Run }) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [clients, setClients] = useState<Array<{ id: number; name: string }>>([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setForm({
      client_name: job.client_name || "", collection: job.collection || "", order_no: job.order_no || "",
      season: job.season || "", due_date: dateStr(job.due_date), notes: job.notes || "",
    });
    setDirty(false);
    // Reset only when a different job (or a saved version of it) arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, job.updated_at]);

  useEffect(() => {
    apiFetch("/api/clients/list").then((r) => (r.ok ? r.json() : [])).then((rows: any[]) =>
      setClients(rows.map((c) => ({ id: c.id, name: c.name })))).catch(() => {});
  }, []);

  const set = (k: string, v: string) => { setForm((f) => ({ ...f, [k]: v })); setDirty(true); };
  const save = () => {
    const client = clients.find((c) => c.name.toLowerCase() === (form.client_name || "").trim().toLowerCase());
    run(() => updateJob(job.id, { ...form, due_date: form.due_date || null, client_id: client?.id ?? null }), "Saved").then((j) => j && setDirty(false));
  };
  const F = ({ k, label, type = "text", list, placeholder }: { k: string; label: string; type?: string; list?: string; placeholder?: string }) => (
    <label className="flex flex-col gap-1 text-xs text-stone-500">
      {label}
      <input type={type} list={list} value={form[k] ?? ""} placeholder={placeholder} onChange={(e) => set(k, e.target.value)} className={input} />
    </label>
  );
  return (
    <section className="max-w-3xl">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-stone-600">Client and project, as they appear on the tracking sheet.</p>
        <button onClick={save} disabled={!dirty} className={btnPrimary}><Check size={14} /> Save</button>
      </div>
      <datalist id="job-clients">{clients.map((c) => <option key={c.id} value={c.name} />)}</datalist>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <F k="client_name" label="Client" list="job-clients" placeholder="Hanover" />
        <F k="collection" label="Project / collection" placeholder="Springfield · Natural Evergreen" />
        <F k="order_no" label="MO / order #" />
        <F k="season" label="Season" placeholder="2026" />
        <F k="due_date" label="Needed by" type="date" />
      </div>
      <label className="mt-3 flex flex-col gap-1 text-xs text-stone-500">Notes
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={3} className={input} />
      </label>
      <p className="mt-4 text-xs text-stone-400">The Manufacturing Order and the purple sheet stay on paper for now. This worksheet starts where the buyer does.</p>
    </section>
  );
}

// ── Worksheet: the purple sheet's lines, each with its sourcing ─────────────
type Drawer =
  | { kind: "catalog"; need: Need; substituteFor?: SourcingLine }
  | { kind: "open-orders"; need: Need }
  | { kind: "manual"; need: Need }
  | null;

type PlanRow = { key: string; supplier_id: number | null; vendor: string; options: Array<{ id: number; name: string; status: string; line_count: number }>; choice: number };

function Worksheet({ job, run, me }: { job: Job; run: Run; me?: string }) {
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [sending, setSending] = useState(false);
  const [plan, setPlan] = useState<PlanRow[] | null>(null);
  const [draft, setDraft] = useState({ label: "", spec: "", need_qty: "" });
  const [bulk, setBulk] = useState("");
  const [showBulk, setShowBulk] = useState(false);

  const addLine = () => {
    if (!draft.label.trim()) return;
    run(() => addNeeds(job.id, [{ label: draft.label.trim(), spec: draft.spec || undefined, need_qty: Number(draft.need_qty) || 0 }]))
      .then((j) => j && setDraft({ label: "", spec: "", need_qty: "" }));
  };
  // Paste the purple sheet: one line per row, quantity last.
  const addBulk = () => {
    const rows = bulk.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
      const m = l.match(/^(.*?)\s+(\d+(?:\.\d+)?)\s*$/);
      return m ? { label: m[1].trim(), need_qty: Number(m[2]) } : { label: l, need_qty: 0 };
    });
    if (!rows.length) return;
    run(() => addNeeds(job.id, rows), `${rows.length} line${rows.length === 1 ? "" : "s"} added`).then((j) => { if (j) { setBulk(""); setShowBulk(false); } });
  };

  const sendable = job.needs.flatMap((n) => n.lines).filter((l) => !l.order_item_id && ["proposed", "ready", "follow_up"].includes(l.status) && l.order_qty > 0);
  const doSend = async (append_to: Record<string, number>) => {
    setSending(true);
    setPlan(null);
    const j = await run(() => sendToPO(job.id, { append_to }), "Sent to purchase orders");
    setSending(false);
    if (j?.created_orders?.length) toast.message(`${j.created_orders.length} purchase order${j.created_orders.length === 1 ? "" : "s"} created`, { description: "Open the Purchase orders tab to place them." });
  };
  // Before creating POs, offer any open PO at the same vendor: "add to the
  // existing Impressive Silk order" is an action here, not an email reminder.
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
        {/* Entry: the purple sheet's lines */}
        <div className="mb-4 rounded-xl border border-stone-200 bg-white p-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-xs text-stone-500">Item (from the purple sheet)
              <input value={draft.label} placeholder="cream hydrangeas" onChange={(e) => setDraft({ ...draft, label: e.target.value })} onKeyDown={(e) => e.key === "Enter" && addLine()} className={input} />
            </label>
            <label className="flex w-48 flex-col gap-1 text-xs text-stone-500">Spec / color / size
              <input value={draft.spec} placeholder="white, 26 in" onChange={(e) => setDraft({ ...draft, spec: e.target.value })} onKeyDown={(e) => e.key === "Enter" && addLine()} className={input} />
            </label>
            <label className="flex w-24 flex-col gap-1 text-xs text-stone-500">Need
              <input type="number" min={0} step="any" value={draft.need_qty} onChange={(e) => setDraft({ ...draft, need_qty: e.target.value })} onKeyDown={(e) => e.key === "Enter" && addLine()} className={`${input} text-right`} />
            </label>
            <button onClick={addLine} className={btnPrimary}><Plus size={14} /> Add line</button>
            <button onClick={() => setShowBulk((v) => !v)} className={btnGhost}>{showBulk ? "Close" : "Paste the sheet"}</button>
          </div>
          {showBulk && (
            <div className="mt-3 border-t border-stone-100 pt-3">
              <p className="mb-2 text-xs text-stone-500">One line per item, quantity last, exactly as written. Example: <code>white natural berry 40</code></p>
              <textarea value={bulk} onChange={(e) => setBulk(e.target.value)} rows={6} className={`${input} w-full font-mono text-xs`} placeholder={"sage green ribbon 12\nburlap ribbon 10\nhydrangeas white 40\nchampagne leaves 52\npine cones large 30"} />
              <div className="mt-2 flex justify-end"><button onClick={addBulk} className={btnPrimary}><Plus size={14} /> Add lines</button></div>
            </div>
          )}
        </div>

        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-stone-600">
            {job.needs.length === 0 ? "Add the lines from the purple sheet to begin." : "For each line: check open orders first, then the catalog. Pack math and adjusted cost fill in from the product."}
          </p>
          {sendable.length > 0 && (
            <button onClick={send} disabled={sending} className={btnPrimary}>
              <PackageCheck size={14} /> Send {sendable.length} line{sendable.length === 1 ? "" : "s"} to purchase orders
            </button>
          )}
        </div>
        <div className="flex flex-col gap-4">
          {job.needs.map((n) => (
            <NeedCard key={n.id} need={n} run={run} me={me} jobId={job.id}
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

function NeedCard({ need, run, me, jobId, onCatalog, onOpenOrders, onManual }: {
  need: Need; run: Run; me?: string; jobId: number;
  onCatalog: (substituteFor?: SourcingLine) => void; onOpenOrders: () => void; onManual: () => void;
}) {
  const [v, setV] = useState({ label: need.label, spec: need.spec || "", need_qty: String(need.need_qty) });
  useEffect(() => setV({ label: need.label, spec: need.spec || "", need_qty: String(need.need_qty) }), [need]);
  const commit = (k: "label" | "spec" | "need_qty") => {
    const cur = k === "need_qty" ? Number(v.need_qty) : v[k];
    const was = k === "spec" ? need.spec || "" : need[k];
    if (cur !== was) run(() => updateNeed(need.id, { [k]: cur } as any));
  };
  return (
    <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 bg-stone-50 px-3 py-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <input value={v.label} onChange={(e) => setV({ ...v, label: e.target.value })} onBlur={() => commit("label")} className={`${input} w-56 font-semibold`} />
          <input value={v.spec} placeholder="spec" onChange={(e) => setV({ ...v, spec: e.target.value })} onBlur={() => commit("spec")} className={`${input} w-40`} />
          <span className="text-xs text-stone-500">need</span>
          <input type="number" min={0} step="any" value={v.need_qty} onChange={(e) => setV({ ...v, need_qty: e.target.value })} onBlur={() => commit("need_qty")} className={`${input} w-20 text-right font-semibold`} />
          <span className="text-xs text-stone-500">
            {need.allocated_qty ? <>allocated <b className="tabular-nums">{qty(need.allocated_qty)}</b> · </> : null}
            {need.ordered_qty ? <>on order <b className="tabular-nums">{qty(need.ordered_qty)}</b>{need.received_qty ? ` (${qty(need.received_qty)} in)` : ""} · </> : null}
          </span>
          {need.ready ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">Covered</span>
            : need.unsourced_qty > 0 ? <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900"><AlertTriangle size={11} /> {qty(need.unsourced_qty)} to source</span>
            : need.gap_qty > 0 ? <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-semibold text-stone-700">Proposed, not sent</span>
            : <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800">Coming</span>}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onOpenOrders} className={btnGhost} title="Use something already on order"><Link2 size={12} /> Open orders</button>
          <button onClick={() => onCatalog()} className={btnGhost}><Search size={12} /> Catalog</button>
          <button onClick={onManual} className={btnGhost}><Plus size={12} /> By hand</button>
          <button onClick={() => run(() => deleteNeed(need.id))} className="text-stone-300 hover:text-rose-600" aria-label="Remove line"><Trash2 size={14} /></button>
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
                <th className="px-2 py-2 text-right font-medium">O/O qty</th>
                <th className="px-2 py-2 text-right font-medium">Unit cost</th>
                <th className="px-2 py-2 text-right font-medium">Adj. unit</th>
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
      {need.lines.length === 0 && need.need_qty > 0 && (
        <p className="px-4 py-2.5 text-xs text-stone-400">Nothing sourced yet.</p>
      )}
    </div>
  );
}

function SourcingRow({ line, need, run, me, jobId, onSubstitute }: {
  line: SourcingLine; need: Need; run: Run; me?: string; jobId: number; onSubstitute: () => void;
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
            {line.order_item_id && <p className="text-[11px] text-stone-500">{line.order_name}{line.order_status ? ` · ${line.order_status.replace("_", " ")}` : ""}{line.expected_arrival ? ` · arriving ${dateStr(line.expected_arrival)}` : ""}{line.received_qty ? ` · ${qty(line.received_qty)} checked in` : ""}</p>}
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
            <button disabled={locked} onClick={() => save({ price_per: line.price_per === "pack" ? "each" : "pack" })} className="rounded border border-stone-200 px-1 text-[10px] text-stone-500 hover:border-emerald-400" title="Is the price per pack or per piece?">{line.price_per === "pack" ? "$/pack" : "$/each"}</button>
          </div>
        )}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-stone-600">{line.status === "allocated" ? "—" : line.packs}</td>
      <td className="px-2 py-2 text-right">
        {line.status === "allocated" ? "—" : (
          <div className="flex flex-col items-end">
            <input type="number" min={0} step="any" value={v.order} onChange={(e) => setV({ ...v, order: e.target.value })} onBlur={() => Number(v.order) !== line.order_qty && save({ order_qty: Number(v.order) })} className={`${input} w-16 text-right font-semibold`} />
            {line.overage_qty > 0 && <span className="text-[10px] text-stone-400">+{qty(line.overage_qty)} extra</span>}
          </div>
        )}
      </td>
      <td className="px-2 py-2 text-right"><input type="number" min={0} step="0.01" value={v.cost} disabled={locked} onChange={(e) => setV({ ...v, cost: e.target.value })} onBlur={() => (v.cost === "" ? null : Number(v.cost)) !== (line.unit_cost ?? null) && save({ unit_cost: v.cost === "" ? (null as any) : Number(v.cost) })} className={`${input} w-20 text-right`} /></td>
      <td className="px-2 py-2 text-right tabular-nums text-stone-600">{line.price_per === "pack" ? money(line.adj_unit_cost) : "—"}</td>
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

function OpenOrdersPane({ need, run, onClose }: { need: Need; run: Run; onClose: () => void }) {
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
  const suggested = (r: OpenOrderLine) => Math.min(r.remaining_qty, need.unsourced_qty || need.gap_qty || r.remaining_qty);
  const take = async (r: OpenOrderLine) => {
    const n = Number(amounts[r.order_item_id] ?? suggested(r));
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
                  <input type="number" min={0} max={r.remaining_qty} step="any" value={amounts[r.order_item_id] ?? String(suggested(r))} onChange={(e) => setAmounts({ ...amounts, [r.order_item_id]: e.target.value })} className={`${input} w-20 text-right`} />
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

function ManualLinePane({ need, run, onClose }: { need: Need; run: Run; onClose: () => void }) {
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

function TasksPanel({ job, run, me }: { job: Job; run: Run; me?: string }) {
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
function OrdersTab({ job, run, reload }: { job: Job; run: Run; reload: () => void }) {
  if (job.purchase_orders.length === 0) {
    return <p className="rounded-xl border border-dashed border-stone-300 p-8 text-center text-sm text-stone-400">No purchase orders yet. Send worksheet lines to create them, one per vendor.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      {job.purchase_orders.map((po) => <POCard key={po.id} po={po} run={run} reload={reload} />)}
    </div>
  );
}

function POCard({ po, run, reload }: { po: Job["purchase_orders"][number]; run: Run; reload: () => void }) {
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
        <span className="ml-auto text-xs text-stone-500">{qty(po.received_qty)}/{qty(po.total_qty)} checked in · {pct}%</span>
        <a href="/orders" onClick={() => { try { localStorage.setItem("leaf-ledger:active-order:v1", String(po.id)); } catch {} }} className="inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline"><ExternalLink size={11} /> Open PO</a>
      </div>
      <div className="grid grid-cols-3 gap-3 px-4 py-3">
        <label className="flex flex-col gap-1 text-xs text-stone-500">Vendor order #<input value={meta.vendor_order_no} onChange={(e) => setMeta({ ...meta, vendor_order_no: e.target.value })} onBlur={() => meta.vendor_order_no !== (po.vendor_order_no || "") && savePO({ vendor_order_no: meta.vendor_order_no })} className={input} /></label>
        <label className="flex flex-col gap-1 text-xs text-stone-500">Arrival<input type="date" value={meta.expected_arrival} onChange={(e) => setMeta({ ...meta, expected_arrival: e.target.value })} onBlur={() => meta.expected_arrival !== dateStr(po.expected_arrival) && savePO({ expected_arrival: meta.expected_arrival || null })} className={input} /></label>
        <label className="flex flex-col gap-1 text-xs text-stone-500">Freight<input type="number" step="0.01" value={meta.freight} onChange={(e) => setMeta({ ...meta, freight: e.target.value })} onBlur={() => savePO({ freight: meta.freight === "" ? null : Number(meta.freight) })} className={input} /></label>
      </div>
      {open && (
        <div className="border-t border-stone-100">
          {lines === null ? <p className="px-4 py-3 text-xs text-stone-400">Loading…</p> : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wide text-stone-400"><th className="px-4 py-2 font-medium">Line</th><th className="px-2 py-2 font-medium">For</th><th className="px-2 py-2 text-right font-medium">Ordered</th><th className="px-2 py-2 text-right font-medium">Checked in</th><th className="px-2 py-2 text-right font-medium">Check in</th></tr></thead>
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
