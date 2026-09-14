import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ClipboardList, Plus, Trash2, Search, Star, ExternalLink, Package, FolderPlus, Layers, GripVertical } from "lucide-react";
import { toast } from "sonner";
import Layout from "components/Layout";
import { ProductDetailModal, ProxiedImage } from "./Library";
import { apiFetch } from "utils/apiFetch";
import {
  listBoards, getBoard, createJob, updateJob, deleteJob, touchJob,
  addGroup, updateGroup, deleteGroup, updatePin, removePin, writeWorkingJob,
  type Board, type BoardJob, type BoardItem, type PinGroup,
} from "utils/jobs";
import { formatMoney as money } from "utils/money";

// Jobs: a pinboard per client job, compared side by side.
//
// Products are pinned from Catalog Search (the + on every card, aimed by the
// "Pinning to" picker in its header) into groups such as Ornaments or
// Garland. This page lays each group out like a spec comparison: one column
// per candidate, one row per attribute, so the team can pick.
//
// The purchaser's full worksheet still exists at /sourcing/:id (no sidebar
// entry) for when a job moves from choosing to buying.

const inch = (n?: number | null) => (n == null ? null : `${Number.isInteger(Number(n)) ? n : Number(n).toFixed(1)}"`);
const input = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm outline-none focus:border-emerald-500";
const btnPrimary = "inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50";
const btnGhost = "inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700";

type Run = (fn: () => Promise<Board>, ok?: string) => Promise<Board | null>;

function sizeText(it: BoardItem): string {
  const parts: string[] = [];
  if (it.height_in != null) parts.push(`${inch(it.height_in)} H`);
  if (it.width_in != null) parts.push(`${inch(it.width_in)} W`);
  if (it.length_in != null) parts.push(`${inch(it.length_in)} L`);
  if (it.diameter_in != null) parts.push(`${inch(it.diameter_in)} dia`);
  if (parts.length) return parts.join(" × ");
  if (it.norm_size_in != null) return `${inch(it.norm_size_in)}`;
  return "—";
}
function packText(it: BoardItem): string {
  const parts: string[] = [];
  if (it.box_qty) parts.push(`${it.box_qty}/box`);
  if (it.case_qty) parts.push(`${it.case_qty}/case`);
  if (it.moq) parts.push(`min ${it.moq}`);
  if (it.uom || it.unit) parts.push(String(it.uom || it.unit));
  return parts.join(" · ") || "—";
}
function availText(it: BoardItem): { text: string; tone: string } {
  const a = (it.availability || "").trim();
  if (!a) return { text: "—", tone: "text-stone-400" };
  if (/^\d+(\.\d+)?$/.test(a)) return Number(a) > 0 ? { text: `${a} in stock`, tone: "text-emerald-700" } : { text: "Out of stock", tone: "text-rose-600" };
  const low = a.toLowerCase();
  if (["in_stock", "available", "in stock", "today", "yes", "active", "instock"].includes(low)) return { text: "In stock", tone: "text-emerald-700" };
  if (["out_of_stock", "sold out", "unavailable", "no"].includes(low)) return { text: "Sold out", tone: "text-rose-600" };
  return { text: a, tone: "text-stone-600" };
}

export default function Jobs() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<BoardJob[]>([]);
  const [board, setBoard] = useState<Board | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any | null>(null);
  const activeId = jobId ? Number(jobId) : null;

  const refreshList = useCallback(async () => {
    try { setJobs(await listBoards()); } catch { setJobs([]); }
  }, []);
  useEffect(() => { refreshList(); }, [refreshList]);

  // Opening a job (sidebar or grid) counts as "working in it" even before
  // anything gets pinned or edited — bump it to the top right away instead
  // of waiting for the next mutation and a full list refetch to notice.
  const selectJob = useCallback((id: number) => {
    setJobs((cur) => {
      const hit = cur.find((j) => j.id === id);
      if (!hit) return cur;
      return [{ ...hit, updated_at: new Date().toISOString() }, ...cur.filter((j) => j.id !== id)];
    });
    navigate(`/jobs/${id}`);
    touchJob(id).catch(() => {});
  }, [navigate]);

  const load = useCallback(async (id: number) => {
    setLoading(true);
    try { setBoard(await getBoard(id)); }
    catch { setBoard(null); toast.error("That job could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (activeId) load(activeId); else setBoard(null); }, [activeId, load]);

  const apply = useCallback((next: Board) => { setBoard(next); refreshList(); }, [refreshList]);
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
    const name = window.prompt("New job", "Client · project");
    if (!name?.trim()) return;
    try {
      const created = await createJob({ name: name.trim() });
      await refreshList();
      navigate(`/jobs/${created.id}`);
      // No need to touch() — creating already stamped updated_at, so it's
      // already first; this only exists so refreshList's fetch can't put it
      // anywhere but first if something else was touched in the same beat.
      const summary: BoardJob = {
        id: created.id, name: created.name, client_name: created.client_name,
        collection: created.collection, season: created.season,
        updated_at: created.updated_at, created_at: created.created_at,
        item_count: 0, group_count: 0, chosen_count: 0,
      };
      setJobs((cur) => [summary, ...cur.filter((j) => j.id !== created.id)]);
    } catch (e: any) { toast.error(e?.message || "Could not create a job."); }
  };

  const removeJob = async () => {
    if (!board) return;
    if (!window.confirm(`Delete "${board.name}" and everything pinned to it?`)) return;
    await deleteJob(board.id);
    setBoard(null);
    await refreshList();
    navigate("/jobs");
    toast.success("Job deleted");
  };

  const openDetail = (productId: number) => {
    apiFetch(`/api/products/detail/${productId}`).then((r) => (r.ok ? r.json() : Promise.reject())).then(setDetail).catch(() => toast.error("Could not open that product"));
  };

  const pinMore = (groupId: number | null = null) => {
    if (!board) return;
    writeWorkingJob({ jobId: board.id, groupId });
    navigate("/search");
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-8 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            <ClipboardList size={18} className="text-emerald-700" /> Jobs
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">Pin from the catalog, compare side by side, pick.</p>
        </div>
        <button onClick={newJob} className={btnPrimary}><Plus size={15} /> New job</button>
      </header>

      <div className="flex">
        <aside className="w-72 flex-shrink-0 border-r border-stone-200 px-3 py-4" style={{ minHeight: "calc(100vh - 65px)" }}>
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-stone-500">Jobs ({jobs.length})</p>
          {jobs.length === 0 ? (
            <p className="px-2 text-sm text-stone-400">No jobs yet. Start one here, or from the “Pinning to” picker in Catalog Search.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {jobs.map((j) => {
                const active = j.id === activeId;
                return (
                  <button key={j.id} onClick={() => selectJob(j.id)}
                    className={`flex flex-col rounded-lg px-3 py-2 text-left ${active ? "bg-emerald-50 ring-1 ring-emerald-200" : "hover:bg-stone-100"}`}>
                    <span className={`truncate text-sm font-medium ${active ? "text-emerald-900" : "text-stone-700"}`}>{j.name}</span>
                    <span className="mt-0.5 truncate text-xs text-stone-400">{j.client_name || ""}{j.client_name && j.collection ? " · " : ""}{j.collection || ""}</span>
                    <span className="mt-0.5 text-[11px] text-stone-400">
                      {j.item_count} pinned{j.group_count ? ` · ${j.group_count} group${j.group_count === 1 ? "" : "s"}` : ""}{j.chosen_count ? ` · ${j.chosen_count} picked` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        <main className="min-w-0 flex-1 px-8 py-6">
          {!activeId ? <JobGrid jobs={jobs} onOpen={selectJob} onNew={newJob} /> : loading && !board ? (
            <p className="py-20 text-center text-sm text-stone-400">Loading…</p>
          ) : !board ? <JobGrid jobs={jobs} onOpen={selectJob} onNew={newJob} /> : (
            <BoardView board={board} run={run} onDelete={removeJob} onPinMore={pinMore} onOpen={openDetail}
              onRename={(name) => updateJob(board.id, { name }).then(() => { load(board.id); refreshList(); }).catch(() => toast.error("Could not rename"))} />
          )}
        </main>
      </div>

      {detail && <ProductDetailModal product={detail} onClose={() => setDetail(null)} />}
    </Layout>
  );
}

// The landing view when no specific job is open: every job as a tile,
// newest-worked-in first (selecting any job — here or in the rail — bumps it
// to the front; see selectJob above). Double-click/double-tap a tile to open
// it, the same gesture as a file browser, rather than overloading a single
// click that the rail already uses for a one-click select.
function JobGrid({ jobs, onOpen, onNew }: { jobs: BoardJob[]; onOpen: (id: number) => void; onNew: () => void }) {
  if (jobs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
          <ClipboardList size={28} className="text-emerald-600" strokeWidth={1.5} />
        </div>
        <p className="mb-1 text-base font-medium text-stone-600">No jobs yet</p>
        <p className="max-w-sm text-sm leading-relaxed text-stone-400">Start one here, or from the “Pinning to” picker in Catalog Search.</p>
        <button onClick={onNew} className={`${btnPrimary} mt-4`}><Plus size={14} /> New job</button>
      </div>
    );
  }
  return (
    <div>
      <p className="mb-4 text-sm text-stone-500">Double-click a job to open its board.</p>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {jobs.map((j) => <JobTile key={j.id} job={j} onOpen={() => onOpen(j.id)} />)}
        <button
          onClick={onNew}
          className="flex min-h-[168px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 text-stone-400 hover:border-emerald-400 hover:text-emerald-700"
        >
          <Plus size={20} />
          <span className="text-sm font-medium">New job</span>
        </button>
      </div>
    </div>
  );
}

function JobTile({ job, onOpen }: { job: BoardJob; onOpen: () => void }) {
  return (
    <button
      onDoubleClick={onOpen}
      title="Double-click to open"
      className="flex min-h-[168px] flex-col rounded-xl border border-stone-200 bg-white p-4 text-left shadow-sm transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-emerald-400"
    >
      <div className="flex items-start justify-between gap-2">
        <ClipboardList size={16} className="mt-0.5 shrink-0 text-emerald-600" />
        {job.chosen_count > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800"><Star size={9} fill="currentColor" /> {job.chosen_count} picked</span>
        )}
      </div>
      <p className="mt-2 line-clamp-2 text-sm font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{job.name}</p>
      <p className="mt-0.5 truncate text-xs text-stone-500">{job.client_name || "No client"}{job.collection ? ` · ${job.collection}` : ""}</p>
      <div className="mt-auto flex items-center gap-1.5 pt-3 text-xs text-stone-400">
        <Layers size={12} />
        {job.item_count} pinned{job.group_count ? ` · ${job.group_count} group${job.group_count === 1 ? "" : "s"}` : ""}
      </div>
    </button>
  );
}

// ── The board ───────────────────────────────────────────────────────────────
function BoardView({ board, run, onDelete, onPinMore, onOpen, onRename }: {
  board: Board; run: Run; onDelete: () => void; onPinMore: (groupId?: number | null) => void; onOpen: (productId: number) => void; onRename: (name: string) => void;
}) {
  const [name, setName] = useState(board.name);
  useEffect(() => setName(board.name), [board.id, board.name]);

  const byGroup = useMemo(() => {
    const m = new Map<number | null, BoardItem[]>();
    for (const it of board.items) {
      const k = it.group_id ?? null;
      m.set(k, [...(m.get(k) || []), it]);
    }
    return m;
  }, [board.items]);
  const ungrouped = byGroup.get(null) || [];

  const newGroup = async () => {
    const n = window.prompt("New group", "Ornaments");
    if (!n?.trim()) return;
    run(() => addGroup(board.id, n.trim()));
  };

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <input value={name} onChange={(e) => setName(e.target.value)}
            onBlur={() => name.trim() && name !== board.name && onRename(name.trim())}
            className="w-full max-w-xl bg-transparent text-lg font-semibold text-stone-800 outline-none focus:border-b focus:border-emerald-500"
            style={{ fontFamily: "Georgia, serif" }} />
          <p className="text-xs text-stone-500">
            {board.client_name || "No client"}{board.collection ? ` · ${board.collection}` : ""} · {board.items.length} pinned
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => onPinMore(null)} className={btnPrimary}><Search size={14} /> Pin and search more from the catalog</button>
          <button onClick={newGroup} className={btnGhost}><FolderPlus size={13} /> New group</button>
          <a href={`/sourcing/${board.id}`} className="text-[11px] text-stone-400 hover:text-emerald-700" title="The purchaser's full worksheet for this job">Worksheet</a>
          <button onClick={onDelete} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"><Trash2 size={13} /> Delete</button>
        </div>
      </div>

      {board.items.length === 0 && board.groups.length === 0 && (
        <div className="mt-8 rounded-xl border border-dashed border-stone-300 p-10 text-center">
          <p className="text-sm font-medium text-stone-600">Nothing pinned yet.</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-stone-400">Go to Catalog Search, choose this job in “Pinning to” at the top, and hit + on anything you're considering. Make groups like Ornaments or Garland to compare like with like.</p>
          <button onClick={() => onPinMore(null)} className={`${btnPrimary} mt-4`}><Search size={14} /> Pin and search more from the catalog</button>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-8">
        {board.groups.map((g) => (
          <GroupSection key={g.id} group={g} items={byGroup.get(g.id) || []} groups={board.groups} run={run} onPinMore={() => onPinMore(g.id)} onOpen={onOpen} />
        ))}
        {ungrouped.length > 0 && (
          <GroupSection group={null} items={ungrouped} groups={board.groups} run={run} onPinMore={() => onPinMore(null)} onOpen={onOpen} />
        )}
      </div>
    </div>
  );
}

function GroupSection({ group, items, groups, run, onPinMore, onOpen }: {
  group: PinGroup | null; items: BoardItem[]; groups: PinGroup[]; run: Run; onPinMore: () => void; onOpen: (productId: number) => void;
}) {
  const [gname, setGname] = useState(group?.name || "");
  useEffect(() => setGname(group?.name || ""), [group?.id, group?.name]);

  // Column order, dragged by the header. Mirrors `items` but reorders ahead
  // of the server round trip so a drag feels immediate; syncs back to props
  // whenever the underlying set changes (an option added/removed/moved
  // group elsewhere on the page) so this never drifts from reality.
  const [order, setOrder] = useState(items);
  useEffect(() => setOrder(items), [items]);
  const [dragId, setDragId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);

  const dropOn = async (targetId: number) => {
    const fromId = dragId;
    setDragId(null);
    setOverId(null);
    if (fromId == null || fromId === targetId) return;
    const fromIdx = order.findIndex((i) => i.item_id === fromId);
    const toIdx = order.findIndex((i) => i.item_id === targetId);
    if (fromIdx === -1 || toIdx === -1) return;
    const next = [...order];
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    setOrder(next); // optimistic — feels instant, corrected below if the save fails
    const changed = next.map((it, i) => ({ it, i })).filter(({ it, i }) => it.sort_order !== i);
    if (!changed.length) return;
    // Persist in order so each write's response reflects every earlier one;
    // only the last goes through run() — that's the single re-render/refresh,
    // the rest would just be redundant toasts and board reloads mid-drag.
    for (let k = 0; k < changed.length - 1; k++) {
      await updatePin(changed[k].it.item_id, { sort_order: changed[k].i }).catch(() => {});
    }
    const last = changed[changed.length - 1];
    const applied = await run(() => updatePin(last.it.item_id, { sort_order: last.i }));
    if (!applied) setOrder(items); // save failed — snap back to last-known-good
  };

  const chosen = order.find((i) => i.chosen);
  const prices = order.map((i) => i.current_price).filter((p): p is number => p != null);
  const cheapest = prices.length > 1 ? Math.min(...prices) : null;

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        {group ? (
          <input value={gname} onChange={(e) => setGname(e.target.value)}
            onBlur={() => gname.trim() && gname !== group.name && run(() => updateGroup(group.id, { name: gname.trim() }))}
            className="bg-transparent text-base font-semibold text-stone-800 outline-none focus:border-b focus:border-emerald-500" style={{ fontFamily: "Georgia, serif" }} />
        ) : (
          <h3 className="text-base font-semibold text-stone-500" style={{ fontFamily: "Georgia, serif" }}>Not in a group</h3>
        )}
        <span className="text-xs text-stone-400">{order.length} option{order.length === 1 ? "" : "s"}{chosen ? ` · picked: ${chosen.name}` : ""}{order.length > 1 ? " · drag a column to reorder" : ""}</span>
        <button onClick={onPinMore} className={btnGhost}><Plus size={12} /> Add options</button>
        {group && (
          <button onClick={() => { if (window.confirm(`Remove the group "${group.name}"? Its pins stay on the job.`)) run(() => deleteGroup(group.id)); }} className="ml-auto text-stone-300 hover:text-rose-600" aria-label="Remove group"><Trash2 size={14} /></button>
        )}
      </div>

      {order.length === 0 ? (
        <p className="rounded-xl border border-dashed border-stone-300 px-4 py-6 text-center text-sm text-stone-400">Nothing here yet. Pin options from the catalog into this group.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
          <table className="border-separate border-spacing-0 text-sm" style={{ minWidth: `${160 + order.length * 230}px` }}>
            <thead>
              <tr>
                <th className="sticky left-0 z-10 w-40 bg-white px-3 py-3 text-left align-bottom text-[11px] font-medium uppercase tracking-wide text-stone-400">Option</th>
                {order.map((it) => (
                  <th key={it.item_id}
                    draggable={order.length > 1}
                    onDragStart={(e) => { setDragId(it.item_id); e.dataTransfer.effectAllowed = "move"; }}
                    onDragEnd={() => { setDragId(null); setOverId(null); }}
                    onDragOver={(e) => { e.preventDefault(); if (dragId != null && overId !== it.item_id) setOverId(it.item_id); }}
                    onDragLeave={() => setOverId((cur) => (cur === it.item_id ? null : cur))}
                    onDrop={(e) => { e.preventDefault(); dropOn(it.item_id); }}
                    className={`w-[230px] min-w-[230px] px-3 py-3 text-left align-top transition-opacity ${it.chosen ? "bg-emerald-50/70" : ""} ${order.length > 1 ? "cursor-grab active:cursor-grabbing" : ""} ${dragId === it.item_id ? "opacity-40" : ""} ${overId === it.item_id && dragId !== it.item_id ? "ring-2 ring-inset ring-emerald-400" : ""}`}
                  >
                    {order.length > 1 && (
                      <div className="mb-1 flex items-center justify-center text-stone-300" title="Drag to reorder"><GripVertical size={13} /></div>
                    )}
                    <div className={`relative overflow-hidden rounded-lg bg-stone-50 ${it.chosen ? "ring-2 ring-emerald-500" : "ring-1 ring-stone-200"}`}>
                      <button onClick={() => onOpen(it.product_id)} className="flex h-44 w-full items-center justify-center" title="Open product">
                        {it.image_urls.length ? <ProxiedImage src={it.image_urls[0]} fallbacks={it.image_urls.slice(1)} alt={it.name || ""} className="h-full w-full object-contain" /> : <Package size={28} className="text-stone-300" />}
                      </button>
                      {it.chosen && <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-emerald-700 px-2 py-0.5 text-[10px] font-semibold text-white"><Star size={10} fill="currentColor" /> Picked</span>}
                    </div>
                    <p className="mt-2 line-clamp-2 font-medium normal-case leading-snug text-stone-800" title={it.name || ""}>{it.missing ? <span className="text-rose-600">Product no longer in catalog</span> : it.name}</p>
                    <p className="text-[11px] font-normal normal-case tracking-normal text-stone-500">{it.supplier_name || "—"}{it.supplier_sku ? <span className="ml-1 font-mono text-stone-400">{it.supplier_sku}</span> : null}</p>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <Row label="Link to product" items={order} render={(it) => it.product_url ? (
                <a href={it.product_url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-1.5 rounded-md bg-emerald-700 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-800">
                  <ExternalLink size={12} /> Link to product
                </a>
              ) : <span className="text-stone-300">—</span>} />
              <Row label="Price" items={order} render={(it) => <span className={`font-semibold ${cheapest != null && it.current_price === cheapest ? "text-emerald-800" : "text-stone-800"}`}>{money(it.current_price)}</span>} />
              <Row label="Size" items={order} render={(it) => sizeText(it)} />
              <Row label="Color" items={order} render={(it) => it.color || it.norm_color || "—"} />
              <Row label="Finish" items={order} render={(it) => it.finish || it.norm_finish || "—"} />
              <Row label="Material" items={order} render={(it) => it.material || "—"} />
              <Row label="Type" items={order} render={(it) => it.product_type || it.category || "—"} />
              <Row label="Pack" items={order} render={(it) => packText(it)} />
              <Row label="Availability" items={order} render={(it) => { const a = availText(it); return <span className={a.tone}>{a.text}</span>; }} />
              <Row label="Note" items={order} render={(it) => <NoteCell item={it} run={run} />} />
              <Row label="Qty needed" items={order} render={(it) => <QtyCell item={it} run={run} />} />
              <Row label="" items={order} render={(it) => (
                <div className="flex flex-wrap items-center gap-1.5">
                  <button onClick={() => run(() => updatePin(it.item_id, { chosen: !it.chosen }))}
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${it.chosen ? "bg-emerald-700 text-white" : "border border-stone-300 text-stone-600 hover:border-emerald-400 hover:text-emerald-700"}`}>
                    <Star size={11} fill={it.chosen ? "currentColor" : "none"} /> {it.chosen ? "Picked" : "Pick"}
                  </button>
                  <select value={it.group_id ?? ""} onChange={(e) => run(() => e.target.value ? updatePin(it.item_id, { group_id: Number(e.target.value) }) : updatePin(it.item_id, { clear_group: true }))}
                    className={`${input} text-xs`} title="Move to a group">
                    <option value="">No group</option>
                    {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                  <button onClick={() => run(() => removePin(it.item_id))} className="text-stone-300 hover:text-rose-600" aria-label="Unpin"><Trash2 size={13} /></button>
                </div>
              )} />
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Row({ label, items, render }: { label: string; items: BoardItem[]; render: (it: BoardItem) => React.ReactNode }) {
  return (
    <tr className="border-t border-stone-100">
      <td className="sticky left-0 z-10 w-40 border-t border-stone-100 bg-white px-3 py-2 align-top text-[11px] font-medium uppercase tracking-wide text-stone-400">{label}</td>
      {items.map((it) => (
        <td key={it.item_id} className={`border-t border-stone-100 px-3 py-2 align-top text-stone-700 ${it.chosen ? "bg-emerald-50/70" : ""}`}>{render(it)}</td>
      ))}
    </tr>
  );
}

function NoteCell({ item, run }: { item: BoardItem; run: Run }) {
  const [v, setV] = useState(item.note || "");
  useEffect(() => setV(item.note || ""), [item.note]);
  return (
    <input value={v} placeholder="why this one…" onChange={(e) => setV(e.target.value)}
      onBlur={() => v !== (item.note || "") && run(() => updatePin(item.item_id, { note: v }))}
      className={`${input} w-full text-xs`} />
  );
}

// How many of this candidate, per row — kept on every option, not only the
// pick, so a comparison already carries what a real order would need by the
// time you've filtered it down to a winner.
function QtyCell({ item, run }: { item: BoardItem; run: Run }) {
  const [v, setV] = useState(item.qty_needed == null ? "" : String(item.qty_needed));
  useEffect(() => setV(item.qty_needed == null ? "" : String(item.qty_needed)), [item.qty_needed]);
  const commit = () => {
    const next = v.trim() === "" ? null : Number(v);
    if (next !== (item.qty_needed ?? null)) run(() => updatePin(item.item_id, { qty_needed: next }));
  };
  return (
    <input type="number" min={0} step="any" value={v} placeholder="0" onChange={(e) => setV(e.target.value)}
      onBlur={commit} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      className={`${input} w-20 text-xs`} />
  );
}
