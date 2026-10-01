import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import Layout from "components/Layout";
import { ChevronLeft, ChevronRight, Copy, Download, ExternalLink, Loader2, Search } from "components/icons";
import { apiFetch } from "utils/apiFetch";
import {
  DONE, EMPTY_FILTER, STATUSES, answerText, countBy, exportUrl, filterResponses, fmtDate, fmtTimestamp,
  isUrl, listResponses, setAccepting, shortOption, updateResponse,
  type FormDef, type FormQuestion, type FormResponse, type ResponseFilter, type Status,
} from "utils/forms";

/**
 * The form's responses, for the buyer -- what the Google Sheet was.
 *
 * Table: one row per submission, the Sheet's columns (Requestor moved up next
 * to the Timestamp), oldest first, sortable. Status replaces the Sheet's
 * strikethrough: Ordered / Received / Cancelled rows are drawn struck through,
 * exactly as Cynthia marked them by hand. Buyer notes save on blur.
 * Summary: Google Forms' Responses -> Summary. Individual: one at a time.
 * Export: the Sheet's exact headers and column order (built server-side).
 */

type Tab = "table" | "summary" | "individual";
const STATUS_STYLE: Record<Status, string> = {
  New: "bg-emerald-50 text-emerald-800 border-emerald-200",
  Ordered: "bg-sky-50 text-sky-800 border-sky-200",
  Received: "bg-stone-100 text-stone-700 border-stone-300",
  Cancelled: "bg-red-50 text-red-700 border-red-200",
};

function Cell({ value, q }: { value: FormResponse["answers"][string]; q: FormQuestion }) {
  if (value == null || value === "") return <span className="text-stone-300">—</span>;
  if (q.type === "date") return <>{fmtDate(value)}</>;
  if (q.type === "radio" && typeof value === "string") return <span title={value}>{shortOption(value)}</span>;
  if (q.type === "checkboxes" && Array.isArray(value)) return <span title={value.join("\n")}>{value.map(shortOption).join("; ")}</span>;
  const s = answerText(value);
  if (isUrl(s)) {
    return (
      <a href={s} target="_blank" rel="noreferrer" className="break-all text-emerald-700 underline" onClick={(e) => e.stopPropagation()}>
        {s.replace(/^https?:\/\/(www\.)?/, "").slice(0, 40)}{s.length > 48 ? "…" : ""}
      </a>
    );
  }
  return <>{s}</>;
}

function StatusSelect({ r, onChange }: { r: FormResponse; onChange: (s: Status) => void }) {
  return (
    <select
      value={r.status}
      onChange={(e) => onChange(e.target.value as Status)}
      onClick={(e) => e.stopPropagation()}
      className={`rounded-full border px-2 py-0.5 text-xs font-semibold outline-none ${STATUS_STYLE[r.status]}`}
    >
      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

function NotesInput({ r, onSave }: { r: FormResponse; onSave: (v: string) => void }) {
  const [v, setV] = useState(r.buyer_notes || "");
  useEffect(() => setV(r.buyer_notes || ""), [r.buyer_notes]);
  return (
    <input
      value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={() => { if (v.trim() !== (r.buyer_notes || "")) onSave(v); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      onClick={(e) => e.stopPropagation()}
      placeholder="Add a note"
      className="w-40 rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-xs outline-none hover:border-stone-200 focus:border-emerald-400 focus:bg-white"
    />
  );
}

function Bars({ rows, total }: { rows: { value: string; count: number }[]; total: number }) {
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.value}>
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="text-stone-700" title={r.value}>{shortOption(r.value)}</span>
            <span className="shrink-0 font-semibold text-stone-800">{r.count} <span className="font-normal text-stone-400">({Math.round((r.count / Math.max(total, 1)) * 100)}%)</span></span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-stone-100">
            <div className="h-full rounded-full" style={{ width: `${(r.count / Math.max(total, 1)) * 100}%`, backgroundColor: "rgb(var(--ll-brand))" }} />
          </div>
        </div>
      ))}
      {!rows.length && <p className="text-xs italic text-stone-400">No answers yet.</p>}
    </div>
  );
}

export default function FormResponses() {
  const { slug = "product-request" } = useParams();
  const [form, setForm] = useState<FormDef | null>(null);
  const [responses, setResponses] = useState<FormResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("table");
  const [filter, setFilter] = useState<ResponseFilter>(EMPTY_FILTER);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: "submitted_at", dir: 1 });
  const [idx, setIdx] = useState(0);

  const load = useCallback(async () => {
    try {
      const r = await listResponses(slug);
      setForm(r.form);
      setResponses(r.responses);
    } catch (e) {
      toast.error((e as Error).message || "Could not load responses");
    } finally {
      setLoading(false);
    }
  }, [slug]);
  useEffect(() => { void load(); }, [load]);

  const q = useMemo(() => Object.fromEntries((form?.questions || []).map((x) => [x.key, x])), [form]);
  // The Sheet's columns, with Requestor moved up next to the Timestamp.
  const columns = useMemo(() => {
    const cols = [...(form?.questions || [])].filter((x) => x.export_position).sort((a, b) => a.export_position! - b.export_position!);
    const req = cols.find((c) => c.key === "requestor");
    return req ? [req, ...cols.filter((c) => c !== req)] : cols;
  }, [form]);

  const filtered = useMemo(() => filterResponses(responses, filter), [responses, filter]);
  const sorted = useMemo(() => {
    const val = (r: FormResponse) =>
      sort.key === "submitted_at" ? r.submitted_at : sort.key === "status" ? r.status : answerText(r.answers[sort.key]).toLowerCase();
    return [...filtered].sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : a.id - b.id) * sort.dir);
  }, [filtered, sort]);

  const distinct = (key: string) =>
    [...new Map(responses.map((r) => answerText(r.answers[key]).trim()).filter(Boolean).map((v) => [v.toLowerCase(), v])).values()]
      .sort((a, b) => a.localeCompare(b));

  const patch = async (r: FormResponse, p: { status?: Status; buyer_notes?: string }) => {
    const prev = responses;
    setResponses((rs) => rs.map((x) => (x.id === r.id ? { ...x, ...p } as FormResponse : x)));
    try {
      const saved = await updateResponse(r.id, p);
      setResponses((rs) => rs.map((x) => (x.id === r.id ? { ...x, ...saved } : x)));
    } catch {
      setResponses(prev);
      toast.error("Couldn't save that -- try again.");
    }
  };

  const toggleAccepting = async () => {
    if (!form) return;
    try {
      const r = await setAccepting(slug, !form.is_accepting);
      setForm({ ...form, is_accepting: r.is_accepting });
      toast.success(r.is_accepting ? "Accepting responses" : "No longer accepting responses");
    } catch {
      toast.error("Couldn't change that -- try again.");
    }
  };

  const download = async () => {
    try {
      const res = await apiFetch(exportUrl(slug));
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${form?.title || "Responses"} (Responses).csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch {
      toast.error("Export failed -- try again.");
    }
  };

  const formLink = `${window.location.origin}/forms/${slug}`;
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(formLink); toast.success("Form link copied"); }
    catch { toast.error(formLink); }
  };

  const sortBy = (key: string) => setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: 1 }));
  const th = (key: string, label: string, title?: string) => (
    <th key={key} title={title || label} onClick={() => sortBy(key)}
      className="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap border-b border-stone-200 px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-white"
      style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
      {label}{sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
    </th>
  );
  const shortLabel = (c: FormQuestion) => c.label.split(/[/?:]/)[0].replace(/\s+/g, " ").trim().slice(0, 28);

  const cur = filtered[Math.min(idx, Math.max(filtered.length - 1, 0))];
  const statusCounts = STATUSES.map((s) => ({ value: s, count: responses.filter((r) => r.status === s).length }));
  const selectCls = "rounded-md border border-stone-300 bg-white px-2 py-1.5 text-xs outline-none focus:border-emerald-500";

  return (
    <Layout>
      <header className="sticky top-0 z-20 border-b border-stone-200 px-4 py-4 sm:px-8" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-emerald-700">Product Requests</p>
            <h1 className="truncate text-xl font-semibold text-stone-800" style={{ fontFamily: "'Sora', system-ui, sans-serif" }}>
              {form?.title || "Responses"}
            </h1>
            <p className="text-xs text-stone-500">
              {responses.length} response{responses.length === 1 ? "" : "s"} · {responses.filter((r) => r.status === "New").length} new
            </p>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-stone-700">
            <span>Accepting responses</span>
            <button type="button" role="switch" aria-checked={Boolean(form?.is_accepting)} onClick={() => void toggleAccepting()}
              className={`relative h-5 w-9 rounded-full transition-colors ${form?.is_accepting ? "bg-emerald-600" : "bg-stone-300"}`}>
              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${form?.is_accepting ? "left-4" : "left-0.5"}`} />
            </button>
          </label>
          <Link to={`/forms/${slug}`} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 hover:border-emerald-400">
            <ExternalLink size={13} /> Open form
          </Link>
          <button type="button" onClick={() => void copyLink()} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 hover:border-emerald-400">
            <Copy size={13} /> Copy link
          </button>
          <button type="button" onClick={() => void download()} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
            <Download size={13} /> Export CSV
          </button>
        </div>
        <div className="mt-3 flex gap-1 border-b border-transparent">
          {(["table", "summary", "individual"] as Tab[]).map((t) => (
            <button key={t} type="button" onClick={() => setTab(t)}
              className={`rounded-t-md px-3 py-1.5 text-xs font-semibold capitalize ${tab === t ? "border-b-2 border-emerald-700 text-emerald-800" : "text-stone-500 hover:text-stone-800"}`}>
              {t}
            </button>
          ))}
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b border-stone-100 px-4 py-2.5 sm:px-8" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <label className="relative flex min-w-[200px] flex-1 items-center sm:max-w-xs">
          <Search size={13} className="pointer-events-none absolute left-2.5 text-stone-400" />
          <input value={filter.text} onChange={(e) => setFilter({ ...filter, text: e.target.value })} placeholder="Search responses"
            className="w-full rounded-full border border-stone-300 bg-white py-1.5 pl-7 pr-3 text-xs outline-none focus:border-emerald-500" />
        </label>
        {([["client", "client_name", "Client"], ["project", "project_name", "Project"], ["requestor", "requestor", "Requestor"]] as const).map(([fk, key, label]) => (
          <select key={fk} value={filter[fk]} onChange={(e) => setFilter({ ...filter, [fk]: e.target.value })} className={selectCls}>
            <option value="">{label}: all</option>
            {distinct(key).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        ))}
        <select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })} className={selectCls}>
          <option value="">Status: all</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="flex items-center gap-1 text-xs text-stone-500">
          Install
          <input type="date" value={filter.from} onChange={(e) => setFilter({ ...filter, from: e.target.value })} className={selectCls} />
          –
          <input type="date" value={filter.to} onChange={(e) => setFilter({ ...filter, to: e.target.value })} className={selectCls} />
        </span>
        {JSON.stringify(filter) !== JSON.stringify(EMPTY_FILTER) && (
          <button type="button" onClick={() => setFilter(EMPTY_FILTER)} className="text-xs font-medium text-stone-400 hover:text-stone-700">
            Reset · {filtered.length} of {responses.length}
          </button>
        )}
      </div>

      <main className="px-4 py-4 sm:px-8">
        {loading ? (
          <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin text-emerald-700" /></div>
        ) : tab === "table" ? (
          <div className="overflow-auto rounded-lg border border-stone-200 bg-white" style={{ maxHeight: "calc(100vh - 220px)" }}>
            <table className="min-w-[1800px] border-collapse text-xs">
              <thead>
                <tr>
                  {th("submitted_at", "Timestamp")}
                  {columns.map((c) => th(c.key, shortLabel(c), c.label + (c.helper_text ? ` ${c.helper_text}` : "")))}
                  {th("status", "Status")}
                  <th className="sticky top-0 z-10 border-b border-stone-200 px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-white" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>Buyer notes</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => {
                  const done = DONE.has(r.status);
                  return (
                    <tr key={r.id} onClick={() => { setIdx(filtered.indexOf(r)); setTab("individual"); }}
                      className={`cursor-pointer border-b border-stone-100 align-top hover:bg-emerald-50/40 ${done ? "text-stone-400" : "text-stone-800"}`}>
                      <td className={`whitespace-nowrap px-3 py-2 ${done ? "line-through" : ""}`}>{fmtTimestamp(r.submitted_at)}</td>
                      {columns.map((c) => (
                        <td key={c.key} className={`max-w-[260px] px-3 py-2 ${done ? "line-through" : ""} ${c.type === "long_text" ? "whitespace-pre-line" : ""}`}>
                          <Cell value={r.answers[c.key]} q={c} />
                        </td>
                      ))}
                      <td className="px-3 py-2"><StatusSelect r={r} onChange={(s) => void patch(r, { status: s })} /></td>
                      <td className="px-2 py-1.5"><NotesInput r={r} onSave={(v) => void patch(r, { buyer_notes: v })} /></td>
                    </tr>
                  );
                })}
                {!sorted.length && (
                  <tr><td colSpan={columns.length + 3} className="px-3 py-10 text-center text-sm text-stone-400">No responses match.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        ) : tab === "summary" ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-lg border border-stone-200 bg-white p-5">
              <p className="text-3xl font-semibold text-stone-800">{filtered.length}</p>
              <p className="text-xs text-stone-500">response{filtered.length === 1 ? "" : "s"}{filtered.length !== responses.length ? ` (filtered from ${responses.length})` : ""}</p>
              <div className="mt-4"><Bars rows={statusCounts.filter((s) => s.count)} total={responses.length} /></div>
            </section>
            {["requestor", "match_existing", "samples_pictures", "preferred_vendor", "client_name", "project_name"].map((key) => q[key] && (
              <section key={key} className="rounded-lg border border-stone-200 bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold text-stone-800" title={q[key].label}>{shortLabel(q[key])}</h3>
                <Bars rows={countBy(filtered, q[key]).slice(0, 12)} total={filtered.length} />
              </section>
            ))}
          </div>
        ) : cur ? (
          <div className="mx-auto max-w-2xl">
            <div className="mb-3 flex items-center justify-between">
              <button type="button" disabled={idx <= 0} onClick={() => setIdx((i) => Math.max(0, i - 1))}
                className="inline-flex items-center gap-1 rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs disabled:opacity-40"><ChevronLeft size={13} /> Previous</button>
              <span className="text-xs text-stone-600">{Math.min(idx, filtered.length - 1) + 1} of {filtered.length}</span>
              <button type="button" disabled={idx >= filtered.length - 1} onClick={() => setIdx((i) => Math.min(filtered.length - 1, i + 1))}
                className="inline-flex items-center gap-1 rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs disabled:opacity-40">Next <ChevronRight size={13} /></button>
            </div>
            <section className="rounded-lg border border-stone-200 bg-white p-5">
              <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-stone-100 pb-3">
                <span className="text-xs text-stone-500">{fmtTimestamp(cur.submitted_at)}</span>
                <StatusSelect r={cur} onChange={(s) => void patch(cur, { status: s })} />
                <NotesInput r={cur} onSave={(v) => void patch(cur, { buyer_notes: v })} />
                {cur.source === "sheet" && <span className="text-[10px] text-stone-400">imported from the Google Sheet</span>}
              </div>
              <dl className={`space-y-4 ${DONE.has(cur.status) ? "text-stone-400 line-through" : ""}`}>
                {(form?.questions || []).map((c) => (
                  <div key={c.key}>
                    <dt className="whitespace-pre-line text-xs text-stone-500">{c.label}</dt>
                    <dd className="mt-1 whitespace-pre-line text-sm text-stone-800">
                      {Array.isArray(cur.answers[c.key])
                        ? (cur.answers[c.key] as string[]).map((v) => <span key={v} className="block">{v}</span>)
                        : <Cell value={cur.answers[c.key]} q={{ ...c, type: c.type === "radio" ? "short_text" : c.type }} />}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        ) : (
          <p className="py-20 text-center text-sm text-stone-400">No responses yet.</p>
        )}
      </main>
    </Layout>
  );
}
