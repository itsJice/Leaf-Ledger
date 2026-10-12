/**
 * Import clients from a spreadsheet (Comment #11).
 *
 * Three steps in one dialog:
 *   1. pick: download the template or the example, see the columns as a small
 *      table, choose a CSV (or .xlsx) file -- an Odoo export works as is;
 *   2. preview: the server's dry run (POST /api/clients/import/validate), one
 *      line per row with "Will create", "Duplicate (skip)" or "Error: ...";
 *   3. done: the server creates only the new, valid rows
 *      (POST /api/clients/import/commit) and this lists what happened.
 *
 * Existing clients are never changed. The headers, example rows and Odoo
 * mapping come from GET /api/clients/import/template (backend
 * app/libs/client_import.py), so there is one list.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle, Check, ChevronDown, Download, FileSpreadsheet, FileUp, Loader2, X,
} from "components/icons";
import { apiFetch } from "utils/apiFetch";
import { composeClientName } from "./ClientNameFields";

export type ImportStatus = "create" | "duplicate" | "error";

export type ImportRow = {
  row: number;
  status: ImportStatus;
  message: string | null;
  notes: string[];
  name: string;
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  site?: string | null;
  email?: string | null;
  phone?: string | null;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  time_preference?: string | null;
  secondary_contacts?: { label: string; phone?: string | null; email?: string | null }[];
  notes_text?: string | null;
  client_id?: number | null;
};

export type ImportResult = {
  dry_run: boolean;
  counts: { create: number; duplicate: number; error: number; total: number };
  columns: Record<string, string>;
  ignored_columns: string[];
  rows: ImportRow[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  created?: any[];
};

export type ImportTemplate = {
  headers: string[];
  example_rows: string[][];
  odoo_aliases: [string, string][];
  max_rows: number;
};

/** One CSV cell, quoted when it needs to be. */
export function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** The template (headers only) or the example (headers + example rows) as
 *  CSV, with a BOM so Excel opens it as UTF-8. */
export function templateCsv(t: ImportTemplate, withExamples: boolean): string {
  const lines = [t.headers, ...(withExamples ? t.example_rows : [])].map((r) => r.map(csvCell).join(","));
  return "\ufeff" + lines.join("\r\n") + "\r\n";
}

/** What an example row shows as, by the same rule as the New Client form. */
export function exampleShowsAs(t: ImportTemplate, row: string[]): string {
  const at = (h: string) => row[t.headers.indexOf(h)] || "";
  return composeClientName({
    first_name: at("First name"), last_name: at("Last name"), company: at("Business name"), site: at("Location"),
  });
}

export function statusLabel(r: Pick<ImportRow, "status" | "message">, committed = false): string {
  if (r.status === "create") return committed ? "Created" : "Will create";
  if (r.status === "duplicate") return committed ? "Duplicate (skipped)" : "Duplicate (skip)";
  return `Error: ${r.message || "can't import this row"}`;
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function errorText(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch { /* not JSON */ }
  if (res.status === 403) return "This login can view clients but can't import them.";
  return fallback;
}

const TIME_LABEL: Record<string, string> = { morning: "Early morning", afternoon: "Afternoon", late: "Late" };

const btnSecondary =
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-3.5 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-60";
const btnPrimary =
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60";

function StatusBadge({ row, committed }: { row: ImportRow; committed?: boolean }) {
  const tone =
    row.status === "create" ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : row.status === "duplicate" ? "border-amber-200 bg-amber-50 text-amber-900"
    : "border-red-200 bg-red-50 text-red-800";
  const Icon = row.status === "create" ? Check : AlertCircle;
  return (
    <span data-status={row.status} className={`inline-flex max-w-full items-start gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${tone}`}>
      <Icon size={13} className="mt-px shrink-0" />
      <span className="min-w-0 break-words">
        {row.status === "error" ? statusLabel(row, committed) : (
          <>
            {statusLabel(row, committed)}
            {row.status === "duplicate" && row.message && (
              <span className="block font-normal opacity-90">{row.message}</span>
            )}
          </>
        )}
      </span>
    </span>
  );
}

function rowAddress(r: ImportRow): string {
  const cityLine = [r.city, [r.state, r.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return [r.street, cityLine].filter(Boolean).join(", ");
}

function rowContact(r: ImportRow): string {
  if (!r.company) return "";
  return [r.first_name, r.last_name].filter(Boolean).join(" ");
}

/** The columns the template uses, as a small styled table with the example rows. */
function ExampleTable({ template }: { template: ImportTemplate }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-stone-200" data-testid="import-example-table">
      <table className="min-w-max border-collapse text-left text-xs">
        <thead>
          <tr className="bg-stone-50">
            <th className="sticky left-0 z-[1] border-b border-r border-stone-200 bg-emerald-50 px-2.5 py-2 font-semibold text-emerald-800">Shows as</th>
            {template.headers.map((h, i) => (
              <th key={h} className="whitespace-nowrap border-b border-stone-200 px-2.5 py-2 font-semibold text-stone-700">
                {h}{i < 3 && <span className="text-emerald-700">*</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {template.example_rows.map((row, i) => (
            <tr key={i} className="border-b border-stone-100 last:border-0">
              <td className="sticky left-0 z-[1] min-w-[7rem] max-w-[9.5rem] border-r border-stone-200 bg-white px-2.5 py-1.5 font-semibold text-stone-800 sm:max-w-none sm:whitespace-nowrap">{exampleShowsAs(template, row)}</td>
              {row.map((cell, j) => (
                <td key={j} className="max-w-[16rem] truncate whitespace-nowrap px-2.5 py-1.5 text-stone-600" title={cell}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Filter = "all" | ImportStatus;

function PreviewRows({ rows, committed }: { rows: ImportRow[]; committed?: boolean }) {
  return (
    <>
      {/* Phone: one card per row. */}
      <ul className="space-y-2 sm:hidden" data-testid="import-preview-cards">
        {rows.map((r) => (
          <li key={r.row} className="rounded-lg border border-stone-200 bg-white p-3 text-sm">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 break-words font-semibold text-stone-800">{r.name || <span className="text-stone-400">No name</span>}</span>
              <span className="shrink-0 text-xs text-stone-400">Row {r.row}</span>
            </div>
            {rowContact(r) && <div className="text-xs text-stone-500">Contact: {rowContact(r)}</div>}
            {(r.phone || r.email) && <div className="mt-1 break-words text-xs text-stone-600">{[r.phone, r.email].filter(Boolean).join(" · ")}</div>}
            {rowAddress(r) && <div className="break-words text-xs text-stone-600">{rowAddress(r)}</div>}
            <div className="mt-2"><StatusBadge row={r} committed={committed} /></div>
            {r.notes.length > 0 && <div className="mt-1 text-xs text-stone-400">{r.notes.join(". ")}</div>}
          </li>
        ))}
      </ul>
      {/* Tablet and up: a table. */}
      <div className="hidden overflow-hidden rounded-lg border border-stone-200 sm:block">
        <table className="w-full table-fixed border-collapse text-left text-sm" data-testid="import-preview-table">
          <thead className="bg-stone-50 text-xs text-stone-500">
            <tr>
              <th className="w-12 px-3 py-2 font-semibold">Row</th>
              <th className="w-[24%] px-3 py-2 font-semibold">Shows as</th>
              <th className="w-[25%] px-3 py-2 font-semibold">Phone / email</th>
              <th className="px-3 py-2 font-semibold">Address</th>
              <th className="w-[27%] px-3 py-2 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.row} className="border-t border-stone-100 align-top">
                <td className="px-3 py-2 text-xs text-stone-400">{r.row}</td>
                <td className="px-3 py-2">
                  <div className="break-words font-medium text-stone-800">{r.name || <span className="text-stone-400">No name</span>}</div>
                  {rowContact(r) && <div className="text-xs text-stone-500">Contact: {rowContact(r)}</div>}
                  {r.time_preference && <div className="text-xs text-stone-500">{TIME_LABEL[r.time_preference] || r.time_preference}</div>}
                  {r.notes.length > 0 && <div className="mt-0.5 text-xs text-stone-400">{r.notes.join(". ")}</div>}
                </td>
                <td className="break-words px-3 py-2 text-xs text-stone-600">
                  {r.phone && <div>{r.phone}</div>}
                  {r.email && <div className="[overflow-wrap:anywhere]">{r.email}</div>}
                  {(r.secondary_contacts || []).map((c, i) => (
                    <div key={i} className="text-stone-400">{c.label}: {[c.phone, c.email].filter(Boolean).join(", ")}</div>
                  ))}
                </td>
                <td className="break-words px-3 py-2 text-xs text-stone-600">{rowAddress(r)}</td>
                <td className="px-3 py-2"><StatusBadge row={r} committed={committed} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function ClientImportDialog({ onClose, onImported }: {
  onClose: () => void;
  /** The clients the import created, as /clients/create returns them. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onImported: (created: any[]) => void;
}) {
  const [template, setTemplate] = useState<ImportTemplate | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [file, setFile] = useState<{ name: string; base64: string } | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"reading" | "importing" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    apiFetch("/api/clients/import/template")
      .then(async (r) => {
        if (!r.ok) throw new Error(await errorText(r, "Couldn't load the template."));
        return r.json();
      })
      .then((t) => { if (live) setTemplate(t); })
      .catch((e) => { if (live) setTemplateError(String(e?.message || e)); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const step: "pick" | "preview" | "done" = result ? "done" : preview ? "preview" : "pick";
  // Each step starts at its top (the result summary, not the old scroll spot).
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (bodyRef.current) bodyRef.current.scrollTop = 0; }, [step]);

  const chooseFile = async (f: File | null | undefined) => {
    if (!f) return;
    setProblem(null);
    setBusy("reading");
    try {
      const base64 = await readAsBase64(f);
      const res = await apiFetch("/api/clients/import/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: f.name, content_base64: base64 }),
      });
      if (!res.ok) throw new Error(await errorText(res, "Couldn't check that file. Try again in a moment."));
      setFile({ name: f.name, base64 });
      setPreview(await res.json());
      setFilter("all");
    } catch (e) {
      setProblem(String((e as Error)?.message || e));
    } finally {
      setBusy(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const commit = async () => {
    if (!file || !preview || busy) return;
    setBusy("importing");
    setProblem(null);
    try {
      const res = await apiFetch("/api/clients/import/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content_base64: file.base64 }),
      });
      if (!res.ok) throw new Error(await errorText(res, "The import didn't go through, so nothing was added. Try again."));
      const done: ImportResult = await res.json();
      setResult(done);
      onImported(done.created || []);
      const n = done.counts.create;
      toast.success(n ? `Imported ${n} client${n === 1 ? "" : "s"}` : "No new clients to import");
    } catch (e) {
      setProblem(String((e as Error)?.message || e));
    } finally {
      setBusy(null);
    }
  };

  const shown = preview || result;
  const visibleRows = useMemo(
    () => (shown ? shown.rows.filter((r) => filter === "all" || r.status === filter) : []),
    [shown, filter],
  );

  const chips: [Filter, string, string][] = shown ? [
    ["all", `All ${shown.counts.total}`, "border-stone-200 text-stone-700"],
    ["create", `${shown.counts.create} ${step === "done" ? "created" : "will create"}`, "border-emerald-200 text-emerald-800"],
    ["duplicate", `${shown.counts.duplicate} duplicate${shown.counts.duplicate === 1 ? "" : "s"}`, "border-amber-200 text-amber-900"],
    ["error", `${shown.counts.error} error${shown.counts.error === 1 ? "" : "s"}`, "border-red-200 text-red-800"],
  ] : [];

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 ll-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="client-import-title"
        className="mx-3 flex max-h-[calc(100dvh-1.5rem)] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ll-modal sm:mx-4">
        <div className="flex shrink-0 items-center justify-between border-b border-stone-100 px-4 py-3.5 sm:px-6">
          <h2 id="client-import-title" className="font-semibold text-stone-800" style={{ fontFamily: "'Sora', system-ui, sans-serif" }}>
            {step === "done" ? "Import finished" : step === "preview" ? "Check the import" : "Import clients"}
          </h2>
          <button type="button" onClick={onClose} disabled={Boolean(busy)} aria-label="Close" className="-mr-2 rounded-lg p-2 text-stone-400 hover:bg-stone-100 hover:text-stone-600"><X size={18} /></button>
        </div>

        <div ref={bodyRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">
          {step === "pick" && (
            <div className="space-y-5">
              <p className="text-sm text-stone-600">
                Add many clients at once from a spreadsheet. Use the template's column names (an export from Odoo works too).
                Clients already on file are never changed: matching names are skipped.
              </p>

              <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
                <button type="button" className={btnSecondary} disabled={!template} onClick={() => template && download("client-import-template.csv", templateCsv(template, false))}>
                  <Download size={15} /> Download template
                </button>
                <button type="button" className={btnSecondary} disabled={!template} onClick={() => template && download("client-import-example.csv", templateCsv(template, true))}>
                  <FileSpreadsheet size={15} /> Download example
                </button>
              </div>

              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-500">Columns</h3>
                {template ? <ExampleTable template={template} /> : (
                  <div className="rounded-lg border border-dashed border-stone-200 px-3 py-4 text-xs text-stone-500">
                    {templateError || "Loading the columns..."}
                  </div>
                )}
                <p className="text-xs text-stone-500">
                  <span className="text-emerald-700">*</span> Each row needs a First name, Last name or Business name. Everything else is optional.
                  A business shows by its business name, plus " | Location" when there is one; a person with a business is saved as its contact.
                </p>
                {template && (
                  <details className="group rounded-lg border border-stone-200 text-xs">
                    <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 font-medium text-stone-700">
                      Exporting from Odoo?
                      <ChevronDown size={14} className="shrink-0 text-stone-400 transition-transform group-open:rotate-180" />
                    </summary>
                    <div className="space-y-2 border-t border-stone-100 px-3 py-2.5 text-stone-600">
                      <p>In Odoo, export your contacts as CSV or Excel (.xlsx). These Odoo columns are read too:</p>
                      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-[auto_1fr]">
                        {template.odoo_aliases.map(([from, to]) => (
                          <React.Fragment key={from}>
                            <dt className="font-medium text-stone-700">{from}</dt>
                            <dd className="mb-1 text-stone-500 sm:mb-0">{to}</dd>
                          </React.Fragment>
                        ))}
                      </dl>
                      <p className="text-stone-500">Other columns (Country, Tags, Odoo's own Company) are ignored.</p>
                    </div>
                  </details>
                )}
              </section>

              <label
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); void chooseFile(e.dataTransfer.files?.[0]); }}
                className={`flex min-h-[7rem] cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors ${dragging ? "border-emerald-400 bg-emerald-50" : "border-stone-200 hover:border-emerald-300 hover:bg-stone-50"}`}
              >
                <input ref={inputRef} type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only"
                  onChange={(e) => void chooseFile(e.target.files?.[0])} disabled={Boolean(busy)} data-testid="import-file-input" />
                {busy === "reading" ? <Loader2 size={22} className="animate-spin text-emerald-700" /> : <FileUp size={22} className="text-emerald-700" />}
                <span className="text-sm font-semibold text-stone-800">{busy === "reading" ? "Checking the file..." : "Choose a CSV or Excel file"}</span>
                <span className="text-xs text-stone-500">or drop it here. Nothing is saved until you confirm.</span>
              </label>
            </div>
          )}

          {(step === "preview" || step === "done") && shown && (
            <div className="space-y-3">
              {step === "done" ? (
                <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-900" data-testid="import-result-summary">
                  <Check size={18} className="mt-0.5 shrink-0" />
                  <div>
                    <div className="font-semibold">
                      {shown.counts.create ? `Imported ${shown.counts.create} new client${shown.counts.create === 1 ? "" : "s"}` : "No new clients were added"}
                    </div>
                    <div className="text-xs text-emerald-800">
                      {[
                        shown.counts.duplicate ? `${shown.counts.duplicate} duplicate${shown.counts.duplicate === 1 ? "" : "s"} skipped` : "",
                        shown.counts.error ? `${shown.counts.error} row${shown.counts.error === 1 ? "" : "s"} with errors not imported` : "",
                      ].filter(Boolean).join(", ") || "Every row was imported"}. Existing clients were not changed.
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-stone-600">
                  <span className="font-medium text-stone-800">{file?.name}</span>: {shown.counts.total} row{shown.counts.total === 1 ? "" : "s"}.
                  {" "}Only rows marked Will create are added. Duplicates and errors are skipped; fix them in the file and import again.
                </p>
              )}

              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Show rows">
                {chips.map(([value, label, tone]) => (
                  <button key={value} type="button" onClick={() => setFilter(value)} aria-pressed={filter === value}
                    className={`min-h-9 rounded-lg border px-3 py-1.5 text-xs font-semibold ${tone} ${filter === value ? "bg-stone-100 ring-1 ring-stone-300" : "bg-white hover:bg-stone-50"}`}>
                    {label}
                  </button>
                ))}
              </div>

              {step === "preview" && (Object.keys(shown.columns).length > 0) && (
                <p className="text-xs text-stone-500">
                  Read {Object.keys(shown.columns).length} column{Object.keys(shown.columns).length === 1 ? "" : "s"}
                  {shown.ignored_columns.length > 0 && <>; ignored {shown.ignored_columns.join(", ")}</>}.
                </p>
              )}

              {visibleRows.length ? <PreviewRows rows={visibleRows} committed={step === "done"} /> : (
                <p className="rounded-lg border border-dashed border-stone-200 px-3 py-4 text-center text-xs text-stone-500">No rows here.</p>
              )}
            </div>
          )}

          {problem && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
              <AlertCircle size={16} className="mt-0.5 shrink-0" /> <span>{problem}</span>
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-stone-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-end sm:gap-3 sm:px-6">
          {step === "pick" && <button type="button" onClick={onClose} className="min-h-10 px-4 py-2 text-sm text-stone-500 hover:text-stone-700">Cancel</button>}
          {step === "preview" && (
            <>
              <button type="button" disabled={Boolean(busy)} onClick={() => { setPreview(null); setFile(null); setProblem(null); }} className={btnSecondary}>
                Choose a different file
              </button>
              <button type="button" disabled={Boolean(busy) || !preview?.counts.create} onClick={() => void commit()}
                className={btnPrimary} style={{ backgroundColor: "rgb(var(--ll-brand))" }} data-testid="import-confirm">
                {busy === "importing" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
                {busy === "importing" ? "Importing..." : preview?.counts.create
                  ? `Import ${preview.counts.create} client${preview.counts.create === 1 ? "" : "s"}`
                  : "Nothing new to import"}
              </button>
            </>
          )}
          {step === "done" && (
            <button type="button" onClick={onClose} className={btnPrimary} style={{ backgroundColor: "rgb(var(--ll-brand))" }}>Done</button>
          )}
        </div>
      </div>
    </div>
  );
}
