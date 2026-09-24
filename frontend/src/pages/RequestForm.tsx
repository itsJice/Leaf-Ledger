import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NotebookPen, Plus, Trash2, Check } from "components/icons";
import { toast } from "sonner";
import Layout from "components/Layout";
import {
  listRequests, getRequest, createRequest, updateRequest, saveRequest, deleteRequest,
  addRequestItem, updateRequestItem, deleteRequestItem, fetchRequestsMeta,
  type ProductRequest, type RequestSummary, type RequestItem, type RequestsMeta,
} from "utils/requests";

// Request Form: how a design order enters Leaf & Ledger, replacing Charles's
// bilingual Google Form. Client and project are asked once; everything below
// is one spreadsheet — type into the blank row at the bottom and it becomes
// a real row, the same draft-row pattern the sourcing worksheet uses. Every
// field autosaves on blur; Save just confirms nothing was lost.
//
// Same visual language as Catalog Search and Jobs on purpose — Charles
// already knows this UI. Labels stay bilingual (English / Español) inline
// rather than behind a toggle, matching Charles's own form.
//
// Once saved, a request sits open until Charles loads it into a job from
// the Jobs page's "Load a request" picker (Jobs.tsx) — that's the link this
// tab has to the Jobs board.

const input = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm outline-none focus:border-emerald-500";
const btnPrimary = "inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50";
const btnGhost = "inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700";

const dateStr = (d?: string | null) => (d ? String(d).slice(0, 10) : "");

type Run = (fn: () => Promise<ProductRequest>, ok?: string) => Promise<ProductRequest | null>;

export default function RequestForm() {
  const { requestId } = useParams();
  const navigate = useNavigate();
  const [list, setList] = useState<RequestSummary[]>([]);
  const [req, setReq] = useState<ProductRequest | null>(null);
  const [meta, setMeta] = useState<RequestsMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const activeId = requestId ? Number(requestId) : null;

  const refreshList = useCallback(async () => {
    try { setList(await listRequests()); } catch { setList([]); }
  }, []);
  useEffect(() => { refreshList(); fetchRequestsMeta().then(setMeta).catch(() => {}); }, [refreshList]);

  const load = useCallback(async (id: number) => {
    setLoading(true);
    try { setReq(await getRequest(id)); }
    catch { setReq(null); toast.error("That request could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (activeId) load(activeId); else setReq(null); }, [activeId, load]);

  const apply = useCallback((next: ProductRequest) => { setReq(next); refreshList(); }, [refreshList]);
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

  const newRequest = async () => {
    try {
      const created = await createRequest({});
      await refreshList();
      navigate(`/requests/${created.id}`);
    } catch (e: any) { toast.error(e?.message || "Could not start a request."); }
  };

  const removeRequest = async () => {
    if (!req) return;
    if (!window.confirm(`Delete this request for ${req.client_name || "(no client)"}? This can't be undone.`)) return;
    await deleteRequest(req.id);
    setReq(null);
    await refreshList();
    navigate("/requests");
    toast.success("Request deleted");
  };

  const save = async () => {
    if (!req) return;
    setSaving(true);
    await run(() => saveRequest(req.id), "Saved — Charles will see this on the Jobs board.");
    setSaving(false);
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-8 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            <NotebookPen size={18} className="text-emerald-700" /> Request Form
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">One request per project — every item, in one sitting.</p>
        </div>
        <button onClick={newRequest} className={btnPrimary}><Plus size={15} /> New request</button>
      </header>

      <div className="flex">
        <aside className="w-72 flex-shrink-0 border-r border-stone-200 px-3 py-4" style={{ minHeight: "calc(100vh - 65px)" }}>
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-stone-500">Requests ({list.length})</p>
          {list.length === 0 ? (
            <p className="px-2 text-sm text-stone-400">Nothing yet. Start one for a client's project.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {list.map((r) => {
                const active = r.id === activeId;
                const label = [r.client_name, r.project_name].filter(Boolean).join(" · ") || "Untitled request";
                return (
                  <button key={r.id} onClick={() => navigate(`/requests/${r.id}`)}
                    className={`flex flex-col rounded-lg px-3 py-2 text-left ${active ? "bg-emerald-50 ring-1 ring-emerald-200" : "hover:bg-stone-100"}`}>
                    <span className="flex items-center justify-between gap-2">
                      <span className={`truncate text-sm font-medium ${active ? "text-emerald-900" : "text-stone-700"}`}>{label}</span>
                      {r.job_id && <span className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">on Jobs</span>}
                    </span>
                    <span className="mt-0.5 text-[11px] text-stone-400">
                      {r.item_count} item{r.item_count === 1 ? "" : "s"}{r.deadline ? ` · due ${dateStr(r.deadline)}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        <main className="min-w-0 flex-1 px-8 py-6">
          {!activeId ? <Empty onNew={newRequest} /> : loading && !req ? (
            <p className="py-20 text-center text-sm text-stone-400">Loading…</p>
          ) : !req ? <Empty onNew={newRequest} /> : (
            <RequestPanel req={req} meta={meta} run={run} onDelete={removeRequest} onSave={save} saving={saving} />
          )}
        </main>
      </div>
    </Layout>
  );
}

function Empty({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
        <NotebookPen size={28} className="text-emerald-600" strokeWidth={1.5} />
      </div>
      <p className="mb-1 text-base font-medium text-stone-600">No request selected</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">Pick one on the left, or start a new one for a client's project.</p>
      <button onClick={onNew} className={`${btnPrimary} mt-4`}><Plus size={15} /> New request</button>
    </div>
  );
}

// ── The header fields (client, project, deadline, samples) ─────────────────
function RequestPanel({ req, meta, run, onDelete, onSave, saving }: {
  req: ProductRequest; meta: RequestsMeta | null; run: Run; onDelete: () => void; onSave: () => void; saving: boolean;
}) {
  const [v, setV] = useState({
    client_name: req.client_name, project_name: req.project_name, deadline: dateStr(req.deadline),
  });
  useEffect(() => {
    setV({ client_name: req.client_name, project_name: req.project_name, deadline: dateStr(req.deadline) });
    // Reset only when a different request (or a saved version of it) arrives,
    // not on every keystroke elsewhere on the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [req.id, req.updated_at]);

  const commit = (k: "client_name" | "project_name" | "deadline") => {
    const was = k === "deadline" ? dateStr(req.deadline) : req[k];
    if (v[k] !== was) run(() => updateRequest(req.id, { [k]: v[k] || (k === "deadline" ? null : "") }));
  };

  const samplesOptions: Array<{ key: string; en: string; es: string }> = [
    { key: "photos", en: "Photos sent", es: "Fotos enviadas" },
    { key: "samples", en: "Samples at buyer's desk", es: "Muestras en el escritorio" },
    { key: "new", en: "New project — nothing existing", es: "Proyecto nuevo — nada existente" },
  ];
  const toggleSample = (key: string) => {
    const current = (req.samples_note || "").split(",").map((s) => s.trim()).filter(Boolean);
    const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
    run(() => updateRequest(req.id, { samples_note: next.join(",") }));
  };
  const samplesOn = new Set((req.samples_note || "").split(",").map((s) => s.trim()));

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            {[req.client_name, req.project_name].filter(Boolean).join(" · ") || "New request"}
          </h2>
          {req.job_name && <p className="text-xs text-emerald-700">Loaded onto the job: {req.job_name}</p>}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onSave} disabled={saving} className={btnPrimary}><Check size={14} /> Save</button>
          <button onClick={onDelete} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"><Trash2 size={13} /> Delete</button>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1 text-xs text-stone-500">Client / Cliente
          <input value={v.client_name} onChange={(e) => setV({ ...v, client_name: e.target.value })} onBlur={() => commit("client_name")} className={input} placeholder="Smith, John" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-stone-500">Project / Proyecto
          <input value={v.project_name} onChange={(e) => setV({ ...v, project_name: e.target.value })} onBlur={() => commit("project_name")} className={input} placeholder="Outdoor" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-stone-500">Deadline / Fecha límite
          <input type="date" value={v.deadline} onChange={(e) => setV({ ...v, deadline: e.target.value })} onBlur={() => commit("deadline")} className={input} />
        </label>
      </div>

      <div className="mt-3">
        <p className="mb-1.5 text-xs text-stone-500">Samples &amp; pictures / Muestras y fotos</p>
        <div className="flex flex-wrap gap-2">
          {samplesOptions.map((o) => {
            const on = samplesOn.has(o.key);
            return (
              <button key={o.key} onClick={() => toggleSample(o.key)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${on ? "border-emerald-400 bg-emerald-50 text-emerald-800" : "border-stone-300 text-stone-600 hover:border-emerald-300"}`}>
                {o.en} <span className="text-stone-400">/ {o.es}</span>
              </button>
            );
          })}
        </div>
      </div>

      <ItemsSheet req={req} meta={meta} run={run} />
    </div>
  );
}

// ── The Excel-style items sheet ─────────────────────────────────────────────
type Col = { key: keyof RequestItem; en: string; es: string; width: string; kind: "text" | "used_on" | "match" };
const COLS: Col[] = [
  { key: "item", en: "Item", es: "Artículo", width: "w-48", kind: "text" },
  { key: "used_on", en: "Used on", es: "Dónde se usa", width: "w-32", kind: "used_on" },
  { key: "qty", en: "Qty needed", es: "Cantidad", width: "w-28", kind: "text" },
  { key: "match_rule", en: "Match existing?", es: "¿Debe coincidir?", width: "w-36", kind: "match" },
  { key: "description", en: "Description", es: "Descripción", width: "w-56", kind: "text" },
  { key: "quality", en: "Most important quality", es: "Cualidad más importante", width: "w-56", kind: "text" },
  { key: "preferred_vendor", en: "Preferred vendor", es: "Proveedor", width: "w-36", kind: "text" },
  { key: "style_color", en: "Style # & color", es: "Estilo y color", width: "w-36", kind: "text" },
  { key: "catalog_page", en: "Catalog page", es: "Página del catálogo", width: "w-28", kind: "text" },
];

function ItemsSheet({ req, meta, run }: { req: ProductRequest; meta: RequestsMeta | null; run: Run }) {
  const matchLabels = meta?.match_labels || {};
  const usedOnOptions = meta?.used_on_options || ["Tree", "Garland", "Wreath", "Swag", "Enhancer", "Table/Mantel", "Other"];

  return (
    <section className="mt-8">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500">Your request so far</h3>
        <span className="text-xs text-stone-400">{req.items.filter((i) => i.item).length} item{req.items.filter((i) => i.item).length === 1 ? "" : "s"} · type into the last row to add another</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-stone-400">
              {COLS.map((c) => (
                <th key={String(c.key)} className={`px-2.5 py-2 font-medium ${c.width}`}>{c.en} <span className="font-normal normal-case text-stone-300">/ {c.es}</span></th>
              ))}
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {req.items.map((it) => (
              <ItemRow key={it.id} item={it} run={run} matchLabels={matchLabels} usedOnOptions={usedOnOptions} />
            ))}
            <DraftRow requestId={req.id} run={run} matchLabels={matchLabels} usedOnOptions={usedOnOptions} />
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Cell({ col, value, onCommit, matchLabels, usedOnOptions }: {
  col: Col; value: string; onCommit: (v: string) => void;
  matchLabels: Record<string, string>; usedOnOptions: string[];
}) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);

  if (col.kind === "used_on") {
    return (
      <select value={v} onChange={(e) => { setV(e.target.value); onCommit(e.target.value); }} className={`${input} w-full`}>
        <option value="">—</option>
        {usedOnOptions.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  if (col.kind === "match") {
    return (
      <select value={v} onChange={(e) => { setV(e.target.value); onCommit(e.target.value); }} className={`${input} w-full`}>
        <option value="">—</option>
        {Object.entries(matchLabels).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </select>
    );
  }
  return (
    <input value={v} onChange={(e) => setV(e.target.value)} onBlur={() => onCommit(v)}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      className={`${input} w-full`} />
  );
}

function ItemRow({ item, run, matchLabels, usedOnOptions }: {
  item: RequestItem; run: Run; matchLabels: Record<string, string>; usedOnOptions: string[];
}) {
  const commit = (key: keyof RequestItem, val: string) => {
    if ((item[key] || "") === val) return;
    run(() => updateRequestItem(item.id, { [key]: val } as any));
  };
  return (
    <tr className="border-t border-stone-100 align-middle">
      {COLS.map((c) => (
        <td key={String(c.key)} className="px-2.5 py-1.5">
          <Cell col={c} value={(item[c.key] as string) || ""} onCommit={(v) => commit(c.key, v)} matchLabels={matchLabels} usedOnOptions={usedOnOptions} />
        </td>
      ))}
      <td className="px-2 py-1.5 text-right">
        <button onClick={() => run(() => deleteRequestItem(item.id))} className="text-stone-300 hover:text-rose-600" aria-label="Remove row"><Trash2 size={13} /></button>
      </td>
    </tr>
  );
}

// The always-present blank row at the bottom. Typing into Item and leaving
// the cell creates the row for real — there is no separate "add item" click.
function DraftRow({ requestId, run, matchLabels, usedOnOptions }: {
  requestId: number; run: Run; matchLabels: Record<string, string>; usedOnOptions: string[];
}) {
  const [draft, setDraft] = useState<Partial<RequestItem>>({});
  const creating = useRef(false);

  // Promotes with the field value passed in directly, not read back off
  // state — setDraft above hasn't necessarily committed yet when this runs,
  // so closing over `draft` here would create the row with the value one
  // keystroke behind (or blank, on the very first cell typed).
  const promote = async (next: Partial<RequestItem>) => {
    const item = (next.item || "").trim();
    if (!item || creating.current) return;
    creating.current = true;
    await run(() => addRequestItem(requestId, { ...next, item }));
    creating.current = false;
    setDraft({});
  };

  return (
    <tr className="border-t border-stone-100 align-middle bg-stone-50/60">
      {COLS.map((c) => (
        <td key={String(c.key)} className="px-2.5 py-1.5">
          <Cell col={c} value={(draft[c.key] as string) || ""}
            onCommit={(v) => {
              const next = { ...draft, [c.key]: v };
              setDraft(next);
              if (c.key === "item" && v.trim()) promote(next);
            }}
            matchLabels={matchLabels} usedOnOptions={usedOnOptions} />
        </td>
      ))}
      <td />
    </tr>
  );
}
