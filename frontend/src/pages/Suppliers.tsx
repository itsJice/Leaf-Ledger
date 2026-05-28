import React, { useEffect, useState, useRef, useCallback, useMemo } from "react";
import {
  Plus, Pencil, Trash2, X, ExternalLink, Building2, RefreshCw,
  CheckCircle2, XCircle, Loader2, Eye, Download, AlertTriangle,
  KeyRound, ChevronDown, ChevronUp, Package, ArrowRight, RefreshCcw,
  Circle, BookOpen,
} from "lucide-react";
import Layout from "components/Layout";
import CatalogWizard from "components/CatalogWizard";
import { apiClient } from "app";
import { toast } from "sonner";
import type { ScrapeJobOut, ScrapedProductOut } from "types";

type Supplier = {
  id: number;
  name: string;
  login_url?: string;
  login_username?: string;
  login_password?: string;
  has_credentials?: boolean;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  notes?: string;
  product_count: number;
  last_price_synced_at?: string | null;
  last_full_sync_at?: string | null;
  created_at: string;
};
const SUPPLIERS_CACHE_KEY = "leaf-ledger:suppliers-cache:v1";

function readSuppliersCache(): Supplier[] | null {
  try {
    const raw = localStorage.getItem(SUPPLIERS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function writeSuppliersCache(suppliers: Supplier[]) {
  try {
    localStorage.setItem(SUPPLIERS_CACHE_KEY, JSON.stringify(suppliers));
  } catch {
    // Ignore storage issues.
  }
}

function formatLastSynced(dateStr?: string | null): string {
  if (!dateStr) return "Never synced";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "Never synced";
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

type ScrapeStatus = "idle" | "starting" | "running" | "done" | "failed";
type DetailBackfillStatus = {
  status: "idle" | "running" | "done" | "failed";
  total: number;
  done: number;
  updated: number;
  stored_images: number;
  skipped: number;
  failed: number;
  started_at?: string | null;
  completed_at?: string | null;
  message?: string | null;
  error?: string | null;
};
type DetailBackfillAutoRunStatus = {
  status: "idle" | "running" | "done" | "failed" | "stopping";
  supplier_id?: number | null;
  batch_limit: number;
  max_batches?: number | null;
  batches_run: number;
  total_updated: number;
  total_stored_images: number;
  remaining_pending?: number | null;
  current_batch?: DetailBackfillStatus | null;
  started_at?: string | null;
  completed_at?: string | null;
  message?: string | null;
  error?: string | null;
  stop_requested?: boolean;
};
type EnrichmentStatus = {
  supplier_id: number;
  total_active: number;
  detail_stored: number;
  detail_pending: number;
  detail_failed: number;
  images_stored: number;
  images_external: number;
  images_with_reference?: number;
  images_displayable?: number;
  images_pending: number;
  images_failed: number;
  images_missing: number;
  last_backfill?: DetailBackfillStatus | null;
};

async function fetchFreshJson<T>(url: string): Promise<T> {
  const sep = url.includes("?") ? "&" : "?";
  const res = await fetch(`${url}${sep}_=${Date.now()}`, {
    cache: "no-store",
    headers: { "Cache-Control": "no-cache" },
  });
  if (!res.ok) throw new Error(`${url} failed with ${res.status}`);
  return res.json();
}

function progressKey(auto?: DetailBackfillAutoRunStatus | null, batch?: DetailBackfillStatus | null) {
  const activeBatch = auto?.current_batch || batch;
  return [
    auto?.status || "idle",
    auto?.batches_run ?? 0,
    auto?.remaining_pending ?? 0,
    activeBatch?.status || "idle",
    activeBatch?.done ?? 0,
    activeBatch?.updated ?? 0,
    activeBatch?.stored_images ?? 0,
    activeBatch?.failed ?? 0,
  ].join("|");
}

function formatClock(ts?: number | null) {
  if (!ts) return "Not checked yet";
  return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function formatDuration(minutes?: number | null) {
  if (!minutes || !Number.isFinite(minutes) || minutes <= 0) return "Calculating";
  const rounded = Math.max(1, Math.round(minutes));
  const hours = Math.floor(rounded / 60);
  const mins = rounded % 60;
  if (hours <= 0) return `${mins} min`;
  if (mins === 0) return `${hours} hr`;
  return `${hours} hr ${mins} min`;
}

function parseApiTimestampMs(value?: string | null) {
  if (!value) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const parsed = new Date(hasTimezone ? value : `${value}Z`).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function scrapeJobTimestampMs(job?: ScrapeJobOut | null) {
  const timestamp = job?.completed_at || job?.started_at || job?.created_at;
  return parseApiTimestampMs(timestamp);
}

function estimateAllstateEta(
  auto?: DetailBackfillAutoRunStatus | null,
  batch?: DetailBackfillStatus | null,
  fallbackRemaining?: number,
) {
  const activeBatch = auto?.current_batch || batch || null;
  const now = Date.now();
  const completedRunRemaining = typeof auto?.remaining_pending === "number"
    ? auto.remaining_pending
    : undefined;
  const remaining = completedRunRemaining !== undefined && fallbackRemaining !== undefined
    ? Math.min(completedRunRemaining, fallbackRemaining)
    : completedRunRemaining ?? fallbackRemaining ?? 0;

  let ratePerMinute = 0;
  const runStartedAt = parseApiTimestampMs(auto?.started_at);
  if (runStartedAt && auto) {
    const processed = (auto.total_updated || 0) + (activeBatch?.updated || 0);
    const elapsedMinutes = Math.max(1, (now - runStartedAt) / 60000);
    ratePerMinute = processed / elapsedMinutes;
  }
  if ((!ratePerMinute || !Number.isFinite(ratePerMinute)) && activeBatch?.started_at && (activeBatch.done || 0) > 0) {
    const batchStartedAt = parseApiTimestampMs(activeBatch.started_at);
    if (batchStartedAt) {
      const elapsedMinutes = Math.max(1, (now - batchStartedAt) / 60000);
      ratePerMinute = (activeBatch.done || 0) / elapsedMinutes;
    }
  }

  const minutesRemaining = ratePerMinute > 0 ? remaining / ratePerMinute : null;
  const completionAt = minutesRemaining ? new Date(now + minutesRemaining * 60000) : null;
  return { remaining, ratePerMinute, minutesRemaining, completionAt };
}

function isProgressStale(auto?: DetailBackfillAutoRunStatus | null, lastProgressAt?: number | null) {
  if (auto?.status !== "running" || !lastProgressAt) return false;
  return Date.now() - lastProgressAt > 120000;
}

function statusColor(status: string) {
  if (status === "done") return "text-emerald-600";
  if (status === "failed") return "text-red-500";
  if (status === "running") return "text-amber-600";
  return "text-stone-400";
}

function StatusIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 size={14} className="text-emerald-600" />;
  if (status === "failed") return <XCircle size={14} className="text-red-500" />;
  if (status === "running" || status === "starting") return <Loader2 size={14} className="text-amber-600 animate-spin" />;
  return null;
}

function isPreviewReadyJob(job: ScrapeJobOut) {
  return !!job.result_key && (job.phase === "ready" || (job.status === "done" && (job.products_imported ?? 0) === 0));
}

function isResumableImportJob(job: ScrapeJobOut) {
  const total = job.total_expected ?? job.products_found ?? 0;
  const done = job.products_importing ?? 0;
  return !!job.result_key && job.status === "failed" && done > 0 && total > done;
}

function chooseSupplierJob(jobs: ScrapeJobOut[]) {
  const latest = jobs[0];
  if (!latest) return null;
  if (latest.status === "running" || latest.phase === "importing" || isResumableImportJob(latest)) return latest;
  if (latest.status === "failed" && !isResumableImportJob(latest)) return latest;
  if (latest.phase === "done" && (latest.products_imported ?? 0) > 0) {
    const readyJobs = jobs.filter((job) => isPreviewReadyJob(job) || isResumableImportJob(job));
    if (readyJobs.length > 0) {
      return readyJobs.reduce(
        (best, next) => ((next.products_found ?? 0) > (best.products_found ?? 0) ? next : best),
        readyJobs[0],
      );
    }
  }
  return latest;
}

// ── Supplier Form Modal ──────────────────────────────────────────────────────
function SupplierModal({
  supplier, onClose, onSave,
}: {
  supplier: Partial<Supplier> | null;
  onClose: () => void;
  onSave: (s: Supplier) => void;
}) {
  const [form, setForm] = useState<any>(supplier || { name: "" });
  const [saving, setSaving] = useState(false);
  // Track whether credentials section is locked (true when creds already saved)
  const [credsLocked, setCredsLocked] = useState<boolean>(!!(supplier?.has_credentials));
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const handleSave = async () => {
    if (!form.name) { toast.error("Supplier name is required"); return; }
    setSaving(true);
    try {
      let res;
      if (form.id) {
        res = await apiClient.update_supplier({ supplierId: form.id }, form);
      } else {
        res = await apiClient.create_supplier(form);
      }
      const saved = await res.json();
      onSave(saved);
      onClose();
      toast.success(form.id ? "Supplier updated" : "Supplier added");
    } catch {
      toast.error("Failed to save supplier");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-100">
          <h2 className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            {form.id ? "Edit Supplier" : "Add Supplier"}
          </h2>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600"><X size={18} /></button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Supplier name *</label>
            <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.name || ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Allstate Floral" />
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Portal URL <span className="text-stone-400">(for reference)</span></label>
            <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.login_url || ""} onChange={(e) => set("login_url", e.target.value)} placeholder="https://" />
          </div>

          <div className={`rounded-xl border px-4 py-3 ${credsLocked ? "border-emerald-100 bg-emerald-50" : "border-amber-100 bg-amber-50"}`}>
            <div className="flex items-center justify-between mb-2">
              <p className={`text-xs font-semibold flex items-center gap-1.5 ${credsLocked ? "text-emerald-800" : "text-amber-800"}`}>
                <KeyRound size={12} />
                {credsLocked ? "Login credentials — saved" : "Login credentials — needed for catalog sync"}
              </p>
              {credsLocked && (
                <button
                  type="button"
                  onClick={() => {
                    // Clear fields so user must re-enter — never pre-fill from stored values
                    set("login_username", "");
                    set("login_password", "");
                    setCredsLocked(false);
                  }}
                  className="flex items-center gap-1 text-[11px] font-medium text-emerald-700 hover:text-emerald-900 border border-emerald-200 bg-white rounded-md px-2 py-0.5 transition-colors"
                >
                  <Pencil size={10} /> Edit
                </button>
              )}
            </div>

            {credsLocked ? (
              /* ── Locked / read-only view ── */
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-stone-500 mb-1">Username / account #</label>
                  <div className="w-full border border-emerald-200 rounded-lg px-3 py-2 text-sm bg-white text-stone-700 truncate">
                    {form.login_username || <span className="text-stone-400 italic">saved</span>}
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-stone-500 mb-1">Password / billing zip</label>
                  <div className="w-full border border-emerald-200 rounded-lg px-3 py-2 text-sm bg-white text-stone-500 tracking-widest">
                    ••••••••
                  </div>
                </div>
              </div>
            ) : (
              /* ── Editable view ── */
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-stone-600 mb-1">Username / account #</label>
                  <input
                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 bg-white"
                    value={form.login_username || ""}
                    onChange={(e) => set("login_username", e.target.value)}
                    placeholder="Account number or email"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-xs text-stone-600 mb-1">Password / billing zip</label>
                  <input
                    type="password"
                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 bg-white"
                    value={form.login_password || ""}
                    onChange={(e) => set("login_password", e.target.value)}
                    placeholder="Password or zip code"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1">Contact name</label>
              <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.contact_name || ""} onChange={(e) => set("contact_name", e.target.value)} placeholder="Jane Smith" />
            </div>
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1">Phone</label>
              <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.contact_phone || ""} onChange={(e) => set("contact_phone", e.target.value)} placeholder="(555) 000-0000" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Contact email</label>
            <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.contact_email || ""} onChange={(e) => set("contact_email", e.target.value)} placeholder="orders@supplier.com" />
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Notes</label>
            <textarea rows={2} className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 resize-none" value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} placeholder="Any notes about this supplier..." />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-stone-100">
          <button onClick={onClose} className="text-sm text-stone-500 hover:text-stone-700 px-4 py-2">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="px-5 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-60 hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
            {saving ? "Saving..." : form.id ? "Update Supplier" : "Add Supplier"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Types for milestone_log ─────────────────────────────────────────────────
type MilestoneCat = {
  name: string;
  slug: string;
  total: number;
  collected: number;
  done: boolean;
};

type MilestoneLog = {
  logged_in?: boolean;
  pages_accessible?: boolean;
  categories_discovered?: boolean;
  categories?: MilestoneCat[];
  data_saved?: boolean;
};

// ── Milestone step row ───────────────────────────────────────────────────────
function MilestoneStep({
  done, active, label, detail, last,
}: {
  done: boolean;
  active?: boolean;
  label: string;
  detail?: React.ReactNode;
  last?: boolean;
}) {
  return (
    <div className="flex gap-3">
      {/* Icon + connector line */}
      <div className="flex flex-col items-center">
        <div
          className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300 ${
            done
              ? "bg-emerald-500"
              : active
                ? "bg-amber-400"
                : "bg-stone-200"
          }`}
        >
          {done ? (
            <CheckCircle2 size={14} className="text-white" />
          ) : active ? (
            <Loader2 size={12} className="text-white animate-spin" />
          ) : (
            <Circle size={10} className="text-stone-400" />
          )}
        </div>
        {!last && (
          <div className={`w-0.5 flex-1 mt-1 min-h-[12px] rounded-full transition-colors duration-500 ${
            done ? "bg-emerald-200" : "bg-stone-200"
          }`} />
        )}
      </div>
      {/* Content */}
      <div className={`pb-4 min-w-0 flex-1 ${last ? "pb-0" : ""}` }>
        <p className={`text-sm font-medium leading-tight ${
          done ? "text-emerald-700" : active ? "text-amber-700" : "text-stone-400"
        }`}>
          {label}
        </p>
        {detail && <div className="mt-1">{detail}</div>}
      </div>
    </div>
  );
}

// ── MilestonePanel ───────────────────────────────────────────────────────────
function MilestonePanel({
  job, isRunning, isImporting, elapsed,
}: {
  job: ScrapeJobOut | null;
  isRunning: boolean;
  isImporting: boolean;
  elapsed: number;
}) {
  const ml = (job?.milestone_log ?? {}) as MilestoneLog;
  const cats: MilestoneCat[] = ml.categories ?? [];

  const loggedIn  = !!(ml.logged_in);
  const pagesOk   = !!(ml.pages_accessible);
  const catsDone  = !!(ml.categories_discovered);
  const dataSaved = !!(ml.data_saved);

  const activeStep = !loggedIn
    ? "login"
    : !pagesOk
      ? "pages"
      : !catsDone
        ? "categories"
        : !dataSaved
          ? "scraping"
          : "done";

  const fmtTime = (s: number) => `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;

  const totalProducts = job?.total_expected ?? job?.products_found ?? 0;
  const totalCollected = cats.reduce((sum, c) => sum + c.collected, 0);
  const headerStatus = isRunning || isImporting
    ? "running"
    : job?.status === "failed"
      ? "failed"
      : job?.status === "done"
        ? "done"
        : "idle";

  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">

      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <StatusIcon status={headerStatus} />
          <span className="text-sm font-semibold text-stone-700">
            {isRunning && activeStep === "login"      && "Logging in\u2026"}
            {isRunning && activeStep === "pages"      && "Checking pages\u2026"}
            {isRunning && activeStep === "categories" && "Discovering categories\u2026"}
            {isRunning && activeStep === "scraping"   && "Scraping products\u2026"}
            {isImporting                             && "Uploading to library\u2026"}
            {!isRunning && !isImporting && headerStatus === "done"   && "Ready to import"}
            {!isRunning && !isImporting && headerStatus === "failed" && "Scrape failed"}
          </span>
          {job && <span className="text-xs text-stone-400">Job #{job.id}</span>}
        </div>
        <div className="flex items-center gap-3">
          {totalProducts > 0 && (
            <span className="text-xs font-semibold text-stone-600 tabular-nums">
              {totalCollected > 0
                ? `${totalCollected.toLocaleString()} / ${totalProducts.toLocaleString()}`
                : totalProducts.toLocaleString()} products
            </span>
          )}
          {(isRunning || isImporting) && (
            <span className="text-xs text-stone-400 tabular-nums">{fmtTime(elapsed)}</span>
          )}
          {job?.completed_at && !isRunning && !isImporting && (
            <span className="text-xs text-stone-400">
              {new Date(job.completed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      </div>

      {/* Checklist body */}
      <div className="px-4 py-4">

        {/* Step 1: Logged in */}
        <MilestoneStep
          done={loggedIn}
          active={isRunning && activeStep === "login"}
          label="Logged in"
          detail={
            loggedIn ? (
              <p className="text-xs text-stone-400">Authentication successful</p>
            ) : isRunning && activeStep === "login" ? (
              <p className="text-xs text-amber-600">Connecting to supplier portal\u2026</p>
            ) : null
          }
        />

        {/* Step 2: Pages accessible */}
        <MilestoneStep
          done={pagesOk}
          active={isRunning && activeStep === "pages"}
          label="Product pages accessible"
          detail={
            pagesOk ? (
              <p className="text-xs text-stone-400">Catalog pages confirmed</p>
            ) : isRunning && activeStep === "pages" ? (
              <p className="text-xs text-amber-600">Checking catalog availability\u2026</p>
            ) : null
          }
        />

        {/* Step 3: Categories discovered */}
        <MilestoneStep
          done={catsDone}
          active={isRunning && activeStep === "categories"}
          label={
            catsDone
              ? `Categories discovered \u2014 ${cats.length} found`
              : isRunning && activeStep === "categories" && cats.length > 0
                ? `Discovering categories \u2014 ${cats.length} so far`
                : "Categories discovered"
          }
          detail={null}
        />

        {/* Per-category rows */}
        {cats.length > 0 && (
          <div className="flex gap-3">
            <div className="flex flex-col items-center w-6 flex-shrink-0">
              <div className="w-0.5 flex-1 bg-stone-200 rounded-full" />
            </div>
            <div className="pb-4 flex-1 min-w-0">
              <div className="rounded-lg border border-stone-100 overflow-hidden">
                <div className="grid grid-cols-[1fr_72px_72px] bg-stone-50 border-b border-stone-100 px-3 py-1.5">
                  <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">Category</span>
                  <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide text-right">Total</span>
                  <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide text-right">Collected</span>
                </div>
                <div className="max-h-52 overflow-y-auto divide-y divide-stone-50">
                  {cats.map((cat) => {
                    const pct = cat.total > 0 ? cat.collected / cat.total : 0;
                    return (
                      <div key={cat.slug} className="grid grid-cols-[1fr_72px_72px] px-3 py-2 items-center hover:bg-stone-50 transition-colors">
                        <div className="flex items-center gap-2 min-w-0">
                          {cat.done ? (
                            <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                          ) : cat.collected > 0 ? (
                            <Loader2 size={12} className="text-amber-400 animate-spin flex-shrink-0" />
                          ) : (
                            <Circle size={12} className="text-stone-300 flex-shrink-0" />
                          )}
                          <span className="text-xs text-stone-700 truncate">{cat.name}</span>
                        </div>
                        <span className="text-xs text-stone-400 text-right tabular-nums">
                          {cat.total > 0 ? cat.total.toLocaleString() : "\u2014"}
                        </span>
                        <div className="flex flex-col items-end gap-0.5">
                          <span className={`text-xs font-medium tabular-nums ${
                            cat.done
                              ? "text-emerald-600"
                              : cat.collected > 0
                                ? "text-amber-600"
                                : "text-stone-300"
                          }`}>
                            {cat.collected > 0 ? cat.collected.toLocaleString() : "\u2014"}
                          </span>
                          {cat.total > 0 && cat.collected > 0 && !cat.done && (
                            <div className="w-10 h-1 bg-stone-100 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-amber-400 rounded-full transition-all duration-500"
                                style={{ width: `${Math.min(pct * 100, 100).toFixed(1)}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 5: Data saved */}
        <MilestoneStep
          done={dataSaved}
          active={false}
          last
          label={
            dataSaved
              ? `Data saved \u2014 ${(job?.products_found ?? 0).toLocaleString()} products ready`
              : "Data saved \u2014 ready to import"
          }
          detail={
            dataSaved ? (
              <p className="text-xs text-stone-400">All products cached and ready for import</p>
            ) : null
          }
        />

        {/* Error message */}
        {job?.status === "failed" && job.error_message && (
          <div className="mt-2 rounded-lg border border-red-100 bg-red-50 px-3 py-2">
            <p className="text-xs font-medium text-red-700 mb-0.5">Error</p>
            <p className="text-xs text-red-600">{job.error_message}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Inline Scraper Panel ─────────────────────────────────────────────────────
function ScraperPanel({ supplier, onProductsImported }: { supplier: Supplier; onProductsImported: () => void }) {
  const [job, setJob] = useState<ScrapeJobOut | null>(null);
  const [status, setStatus] = useState<ScrapeStatus>("idle");
  const [maxProducts, setMaxProducts] = useState(""); // blank = full catalog
  const [catalogWizardOpen, setCatalogWizardOpen] = useState(false);
  const [preview, setPreview] = useState<ScrapedProductOut[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ inserted: number; updated: number; completedAt: Date } | null>(null);
  const [detailBackfillLimit] = useState("250");
  const [detailBackfill, setDetailBackfill] = useState<DetailBackfillStatus | null>(null);
  const [detailBackfillRunning, setDetailBackfillRunning] = useState(false);
  const [detailBackfillAuto, setDetailBackfillAuto] = useState<DetailBackfillAutoRunStatus | null>(null);
  const [detailBackfillAutoRunning, setDetailBackfillAutoRunning] = useState(false);
  const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentStatus | null>(null);
  const [progressCheckedAt, setProgressCheckedAt] = useState<number | null>(null);
  const [progressChangedAt, setProgressChangedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const importPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const detailBackfillPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const detailBackfillAutoPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressKeyRef = useRef<string>("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasCredentials = !!(supplier.has_credentials || (supplier.login_username && supplier.login_password));

  const stopTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }, []);

  const startTimer = useCallback((from: Date) => {
    stopTimer();
    setElapsed(Math.floor((Date.now() - from.getTime()) / 1000));
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - from.getTime()) / 1000));
    }, 1000);
  }, [stopTimer]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const stopImportPolling = useCallback(() => {
    if (importPollRef.current) { clearInterval(importPollRef.current); importPollRef.current = null; }
  }, []);

  const stopDetailBackfillPolling = useCallback(() => {
    if (detailBackfillPollRef.current) { clearInterval(detailBackfillPollRef.current); detailBackfillPollRef.current = null; }
  }, []);

  const stopDetailBackfillAutoPolling = useCallback(() => {
    if (detailBackfillAutoPollRef.current) { clearInterval(detailBackfillAutoPollRef.current); detailBackfillAutoPollRef.current = null; }
  }, []);

  const loadEnrichmentStatus = useCallback(async () => {
    if (!supplier.name.toLowerCase().includes("allstate")) return;
    try {
      const data = await fetchFreshJson<EnrichmentStatus>(`/api/scraper/supplier-enrichment-status/${supplier.id}`);
      setEnrichmentStatus(data);
      setProgressCheckedAt(Date.now());
    } catch (e) {
      console.error("Enrichment status error", e);
    }
  }, [supplier.id, supplier.name]);

  const pollDetailBackfillStatus = useCallback(async () => {
    try {
      const data = await fetchFreshJson<DetailBackfillStatus>("/api/scraper/backfill-allstate-details/status");
      setDetailBackfill(data);
      setProgressCheckedAt(Date.now());
      void loadEnrichmentStatus();
      if (data.status === "done" || data.status === "failed") {
        setDetailBackfillRunning(false);
        stopDetailBackfillPolling();
      }
    } catch (e) {
      console.error("Detail backfill poll error", e);
    }
  }, [loadEnrichmentStatus, stopDetailBackfillPolling]);

  const pollDetailBackfillAutoStatus = useCallback(async () => {
    try {
      const data = await fetchFreshJson<DetailBackfillAutoRunStatus>("/api/scraper/backfill-allstate-details/run-until-complete/status");
      setDetailBackfillAuto(data);
      if (data.current_batch) setDetailBackfill(data.current_batch);
      const nextKey = progressKey(data, data.current_batch || null);
      if (nextKey !== progressKeyRef.current) {
        progressKeyRef.current = nextKey;
        setProgressChangedAt(Date.now());
      }
      setProgressCheckedAt(Date.now());
      void loadEnrichmentStatus();
      if (data.status === "done" || data.status === "failed" || data.status === "stopping") {
        setDetailBackfillAutoRunning(false);
        setDetailBackfillRunning(false);
      }
    } catch (e) {
      console.error("Detail backfill autorun poll error", e);
    }
  }, [loadEnrichmentStatus]);

  const pollJob = useCallback(async (jobId: number) => {
    try {
      const data: ScrapeJobOut = await apiClient.get_scrape_job({ jobId }).then((r) => r.json());
      setJob(data);
      // Keep polling through importing phase; stop on terminal states
      const terminal = data.status === "failed" || (data.status === "done" && data.phase === "done");
      if (terminal) {
        stopPolling();
        stopTimer();
        setStatus(data.status as ScrapeStatus);
      } else if (data.status === "done" && data.phase === "ready") {
        // Scrape finished, waiting for import click — stop polling heavy job
        stopPolling();
        stopTimer();
        setStatus("done");
        toast.success(`${(data.products_found ?? 0).toLocaleString()} products ready to import!`);
      }
    } catch (e) { console.error("Poll error", e); }
  }, [stopPolling, stopTimer]);

  // Load most recent job on mount
  useEffect(() => {
    (async () => {
      try {
        const jobs: ScrapeJobOut[] = await apiClient.list_scrape_jobs({ supplierId: supplier.id }).then((r) => r.json());
        if (jobs.length > 0) {
          const selectedJob = chooseSupplierJob(jobs);
          if (!selectedJob) return;
          setJob(selectedJob);
          setStatus(selectedJob.status as ScrapeStatus);
          if (selectedJob.status === "running" || selectedJob.phase === "importing") {
            pollRef.current = setInterval(() => pollJob(selectedJob.id), 2000);
            if (selectedJob.started_at) startTimer(new Date(selectedJob.started_at));
          } else if (isPreviewReadyJob(selectedJob) || isResumableImportJob(selectedJob)) {
            try {
              const data: ScrapedProductOut[] = await apiClient
                .preview_scraped_products({ jobId: selectedJob.id }, { limit: 50 })
                .then((r) => r.json());
              setPreview(data);
              setShowPreview(true);
            } catch {
              setPreview([]);
              setShowPreview(false);
            }
          }
        }
      } catch { /* no jobs yet */ }
    })();
    (async () => {
      try {
        await loadEnrichmentStatus();
        const data = await fetchFreshJson<DetailBackfillStatus>("/api/scraper/backfill-allstate-details/status");
        setDetailBackfill(data);
        if (data.status === "running") {
          setDetailBackfillRunning(true);
          stopDetailBackfillPolling();
          detailBackfillPollRef.current = setInterval(() => { void pollDetailBackfillStatus(); }, 2000);
        }
        const autoData = await fetchFreshJson<DetailBackfillAutoRunStatus>("/api/scraper/backfill-allstate-details/run-until-complete/status");
        setDetailBackfillAuto(autoData);
        const nextKey = progressKey(autoData, autoData.current_batch || data);
        progressKeyRef.current = nextKey;
        setProgressCheckedAt(Date.now());
        setProgressChangedAt(Date.now());
        if (autoData.status === "running") {
          setDetailBackfillAutoRunning(true);
          setDetailBackfillRunning(true);
        }
        if (supplier.name.toLowerCase().includes("allstate")) {
          stopDetailBackfillAutoPolling();
          detailBackfillAutoPollRef.current = setInterval(() => { void pollDetailBackfillAutoStatus(); }, 3000);
        }
      } catch { /* no detail backfill yet */ }
    })();
    return () => { stopPolling(); stopTimer(); stopDetailBackfillPolling(); stopDetailBackfillAutoPolling(); };
  }, [supplier.id, pollJob, pollDetailBackfillStatus, pollDetailBackfillAutoStatus, stopDetailBackfillPolling, stopDetailBackfillAutoPolling, stopPolling, stopTimer, startTimer, loadEnrichmentStatus]);

  const startScrape = async () => {
    if (!hasCredentials) { toast.error("Add login credentials before scraping."); return; }
    setStatus("starting"); setJob(null); setPreview([]); setImportResult(null); setShowPreview(false); setElapsed(0);
    try {
      const body: Record<string, unknown> = { supplier_id: supplier.id };
      if (maxProducts && parseInt(maxProducts) > 0) body.max_products = parseInt(maxProducts);
      const newJob: ScrapeJobOut = await apiClient.start_scrape(body as Parameters<typeof apiClient.start_scrape>[0]).then((r) => r.json());
      setJob(newJob); setStatus("running");
      pollRef.current = setInterval(() => pollJob(newJob.id), 2000);
      startTimer(new Date());
    } catch {
      toast.error("Failed to start scrape"); setStatus("failed");
    }
  };

  const loadPreview = async () => {
    if (!job) return;
    try {
      const data: ScrapedProductOut[] = await apiClient.preview_scraped_products({ jobId: job.id }, { limit: 50 }).then((r) => r.json());
      setPreview(data); setShowPreview(true);
    } catch { toast.error("Could not load preview"); }
  };

  const importAll = async () => {
    if (!job) return;
    setImporting(true);
    stopImportPolling(); // clear any lingering import poll

    const handleImportDone = (data: ScrapeJobOut) => {
      stopImportPolling();
      setImporting(false);
      setJob(data);
      const ins = data.products_imported ?? 0;
      const upd = Math.max(0, ins - (data.products_found ?? 0));
      setImportResult({ inserted: ins, updated: upd, completedAt: new Date() });
      onProductsImported();
      toast.success(`Imported ${ins.toLocaleString()} products into your library!`);
    };

    const handleImportFailed = () => {
      stopImportPolling();
      setImporting(false);
      toast.error("Import failed — check the supplier panel for details.");
    };

    try {
      // Fire the import — it returns immediately with {started: true}
      await apiClient.import_scraped_products({ job_id: job.id, supplier_id: supplier.id });
    } catch {
      toast.error("Could not start import");
      setImporting(false);
      return;
    }

    // Poll on a dedicated ref so it never conflicts with the scrape poll
    importPollRef.current = setInterval(async () => {
      try {
        const data: ScrapeJobOut = await apiClient.get_scrape_job({ jobId: job.id }).then((r) => r.json());
        setJob(data);
        if (data.phase === "done" && data.status === "done") {
          handleImportDone(data);
        } else if (data.phase === "failed" || data.status === "failed") {
          handleImportFailed();
        }
      } catch (e) { console.error("Import poll error", e); }
    }, 2000);
  };

  const startDetailBackfill = async (force = false) => {
    if (!hasCredentials) { toast.error("Add login credentials before backfilling."); return; }
    if (!supplier.name.toLowerCase().includes("allstate")) {
      toast.error("Detail backfill is only available for Allstate suppliers.");
      return;
    }
    setDetailBackfillRunning(true);
    try {
      const limit = detailBackfillLimit ? parseInt(detailBackfillLimit, 10) : NaN;
      const query = new URLSearchParams();
      if (!Number.isNaN(limit) && limit > 0) query.set("limit", String(limit));
      if (force) query.set("force", "true");
      const url = `/api/scraper/backfill-allstate-details/${supplier.id}${query.toString() ? `?${query.toString()}` : ""}`;
      const res = await fetch(url, { method: "POST" });
      const data: DetailBackfillStatus = await res.json();
      setDetailBackfill(data);
      if (!res.ok) {
        setDetailBackfillRunning(false);
        toast.error(data.error || "Could not start detail backfill");
        return;
      }
      toast.success("Detail backfill started");
      void loadEnrichmentStatus();
      stopDetailBackfillPolling();
      detailBackfillPollRef.current = setInterval(() => { void pollDetailBackfillStatus(); }, 2000);
    } catch {
      setDetailBackfillRunning(false);
      toast.error("Could not start detail backfill");
    }
  };

  const runDetailBackfillUntilComplete = async () => {
    if (!hasCredentials) { toast.error("Add login credentials before backfilling."); return; }
    if (!supplier.name.toLowerCase().includes("allstate")) {
      toast.error("Run until complete is only available for Allstate suppliers.");
      return;
    }
    setDetailBackfillAutoRunning(true);
    setDetailBackfillRunning(true);
    try {
      const limit = detailBackfillLimit ? parseInt(detailBackfillLimit, 10) : NaN;
      const query = new URLSearchParams();
      query.set("batch_limit", String(!Number.isNaN(limit) && limit > 0 ? limit : 250));
      const res = await fetch(`/api/scraper/backfill-allstate-details/${supplier.id}/run-until-complete?${query.toString()}`, { method: "POST" });
      const data: DetailBackfillAutoRunStatus = await res.json();
      setDetailBackfillAuto(data);
      if (!res.ok) {
        setDetailBackfillAutoRunning(false);
        setDetailBackfillRunning(false);
        toast.error(data.error || "Could not start run until complete");
        return;
      }
      toast.success("Run until complete started");
      void loadEnrichmentStatus();
      stopDetailBackfillAutoPolling();
      detailBackfillAutoPollRef.current = setInterval(() => { void pollDetailBackfillAutoStatus(); }, 3000);
    } catch {
      setDetailBackfillAutoRunning(false);
      setDetailBackfillRunning(false);
      toast.error("Could not start run until complete");
    }
  };

  const stopDetailBackfillUntilComplete = async () => {
    try {
      const res = await fetch("/api/scraper/backfill-allstate-details/run-until-complete/stop", { method: "POST" });
      const data: DetailBackfillAutoRunStatus = await res.json();
      setDetailBackfillAuto(data);
      if (!res.ok) throw new Error(data.error || "Could not stop run");
      toast.success("Stop requested");
    } catch {
      toast.error("Could not stop run until complete");
    }
  };

  const retryFailedImages = async () => {
    try {
      const res = await fetch("/api/scraper/backfill-images", { method: "POST" });
      if (!res.ok) throw new Error("Could not start image retry");
      toast.success("Image retry started");
      void loadEnrichmentStatus();
    } catch {
      toast.error("Could not start image retry");
    }
  };

  const phase = (job as ScrapeJobOut & { phase?: string })?.phase;
  const isRunning = status === "running" || status === "starting";
  const isImporting = importing || phase === "importing";
  const showMilestones = !!job && (isRunning || isImporting || phase === "discovering" || phase === "scraping" || phase === "importing");
  const canImportOrResume = !!job && (
    job.phase === "ready" ||
    (job.status === "done" && !!job.result_key && (job.products_imported ?? 0) === 0) ||
    isResumableImportJob(job)
  );
  const jobTimestamp = scrapeJobTimestampMs(job);
  const lastImportedAt = parseApiTimestampMs(supplier.last_full_sync_at);
  const staleReadyImport = !!job && canImportOrResume && !isImporting && !isResumableImportJob(job)
    && !!lastImportedAt && !!jobTimestamp && jobTimestamp < lastImportedAt && supplier.product_count > 0;
  const showImportAction = canImportOrResume && !staleReadyImport;
  const staleProgress = isProgressStale(detailBackfillAuto, progressChangedAt);
  const enrichmentEta = estimateAllstateEta(
    detailBackfillAuto,
    detailBackfill,
    enrichmentStatus?.detail_pending,
  );
  const enrichmentRunning = detailBackfillRunning || detailBackfillAutoRunning;
  const currentBatchTotal = detailBackfill?.total || detailBackfillAuto?.current_batch?.total || 0;
  const currentBatchDone = detailBackfill?.done || detailBackfillAuto?.current_batch?.done || 0;
  const currentBatchPct = currentBatchTotal > 0 ? Math.min(100, Math.round((currentBatchDone / currentBatchTotal) * 100)) : 0;
  const readyCount = enrichmentStatus
    ? Math.min(
        enrichmentStatus.detail_stored,
        enrichmentStatus.images_with_reference ?? enrichmentStatus.images_displayable ?? enrichmentStatus.images_stored,
      )
    : 0;
  const readyPct = enrichmentStatus?.total_active
    ? Math.min(100, Math.round((readyCount / enrichmentStatus.total_active) * 100))
    : 0;
  const readyDisplayPct = enrichmentStatus?.total_active && readyCount < enrichmentStatus.total_active
    ? Math.min(99, Math.floor((readyCount / enrichmentStatus.total_active) * 100))
    : readyPct;
  const needsWorkCount = enrichmentStatus?.total_active
    ? Math.max(0, enrichmentStatus.total_active - readyCount)
    : 0;
  const retryableImages = enrichmentStatus && needsWorkCount > 0 ? enrichmentStatus.images_failed : 0;
  const completionButtonText = detailBackfillAuto?.status === "failed"
    ? "Resume catalog completion"
    : needsWorkCount > 0
      ? "Complete missing photos/details"
      : "Catalog photos & details complete";
  const checkpointSize = detailBackfillAuto?.batch_limit || 250;
  const completedCheckpoints = detailBackfillAuto?.batches_run ?? 0;
  const checkpointNumber = enrichmentRunning && currentBatchTotal > 0 ? completedCheckpoints + 1 : completedCheckpoints;
  const currentCheckpointRemaining = enrichmentRunning ? Math.max(0, currentBatchTotal - currentBatchDone) : 0;
  const workAfterCurrentCheckpoint = Math.max(0, needsWorkCount - currentCheckpointRemaining);
  const checkpointsLeft = needsWorkCount === 0
    ? 0
    : enrichmentRunning && currentBatchTotal > currentBatchDone
      ? 1 + Math.ceil(workAfterCurrentCheckpoint / checkpointSize)
      : Math.ceil(needsWorkCount / checkpointSize);
  const estimatedFinalCheckpoint = checkpointNumber > 0 && checkpointsLeft > 0
    ? checkpointNumber + checkpointsLeft - 1
    : checkpointNumber;
  const totalCheckpoints = enrichmentStatus?.total_active
    ? Math.max(1, Math.ceil(enrichmentStatus.total_active / checkpointSize))
    : Math.max(checkpointNumber || 1, estimatedFinalCheckpoint || 1);
  const displayedCheckpoint = needsWorkCount === 0
    ? totalCheckpoints
    : Math.min(Math.max(1, checkpointNumber || 1), totalCheckpoints);

  return (
    <div className="mt-4 space-y-4">

      {/* Credentials warning */}
      {!hasCredentials && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800">Login credentials missing</p>
            <p className="text-xs text-amber-700 mt-0.5">Click <strong>Edit</strong> on this supplier and fill in the username and password so the scraper can log in.</p>
          </div>
        </div>
      )}

      {supplier.name.toLowerCase().includes("allstate") && (
        <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold text-sky-700">Finish catalog photos & details</p>
              {enrichmentStatus ? (
                <p className="text-[11px] text-sky-700 mt-0.5">
                  {readyCount.toLocaleString()} of {enrichmentStatus.total_active.toLocaleString()} products ready
                  {" "}({readyDisplayPct}%). {needsWorkCount.toLocaleString()} still need attention.
                </p>
              ) : (
                <p className="text-[11px] text-sky-600 mt-0.5">
                  Make sure every product has a photo and source-page details.
                </p>
              )}
              {enrichmentRunning && currentBatchTotal > 0 && (
                <p className="text-[10px] text-sky-600 mt-0.5">
                  Working now: {currentBatchDone.toLocaleString()} of {currentBatchTotal.toLocaleString()} in this checkpoint
                  {needsWorkCount <= 1 ? " · almost done" : enrichmentEta.minutesRemaining ? ` · about ${formatDuration(enrichmentEta.minutesRemaining)} left` : ""}
                </p>
              )}
              {(enrichmentRunning || needsWorkCount > 0) && (
                <p className="text-[10px] text-sky-600 mt-0.5">
                  Checkpoint {displayedCheckpoint} of {totalCheckpoints}: a saved batch of up to {checkpointSize} products, so progress is kept if the run stops.
                </p>
              )}
              {!enrichmentRunning && needsWorkCount === 0 && enrichmentStatus && (
                <p className="text-[10px] text-sky-600 mt-0.5">
                  Checkpoints complete: {totalCheckpoints} of {totalCheckpoints} saved batches.
                </p>
              )}
              {detailBackfill?.error && (
                <p className="text-[10px] text-red-500 mt-0.5">{detailBackfill.error}</p>
              )}
              <p className="text-[10px] text-stone-500 mt-0.5">
                Updated {formatClock(progressCheckedAt)}
                {enrichmentEta.completionAt ? ` · Done around ${formatClock(enrichmentEta.completionAt.getTime())}` : ""}
              </p>
              {staleProgress && (
                <p className="text-[10px] font-semibold text-amber-700 mt-0.5">
                  Progress has not changed in over 2 minutes. Stop after this checkpoint if needed, then use Resume catalog completion.
                </p>
              )}
              {detailBackfillAuto?.error && (
                <p className="text-[10px] text-red-500 mt-0.5">{detailBackfillAuto.error}</p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(enrichmentRunning || needsWorkCount > 0 || detailBackfillAuto?.status === "failed") ? (
                <button
                  onClick={runDetailBackfillUntilComplete}
                  disabled={!hasCredentials || enrichmentRunning}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-50 hover:opacity-90 transition-colors"
                  style={{ backgroundColor: "#0f766e" }}
                >
                  {enrichmentRunning ? (
                    <><Loader2 size={14} className="animate-spin" /> Completing catalog…</>
                  ) : (
                    <><RefreshCw size={14} /> {completionButtonText}</>
                  )}
                </button>
              ) : (
                <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm font-semibold text-emerald-700">
                  <CheckCircle2 size={14} /> Photos & details complete
                </div>
              )}
              {detailBackfillAutoRunning && (
                <button
                  onClick={stopDetailBackfillUntilComplete}
                  className="flex items-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-600 hover:bg-red-50"
                >
                  <XCircle size={14} /> Stop after checkpoint
                </button>
              )}
              {retryableImages > 0 && !enrichmentRunning && (
                <button
                  onClick={retryFailedImages}
                  disabled={detailBackfillRunning || detailBackfillAutoRunning}
                  className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-700 disabled:opacity-50 hover:bg-amber-100"
                >
                  <RefreshCw size={14} /> Retry image problems
                </button>
              )}
            </div>
          </div>
          {enrichmentStatus && (
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Ready</p>
                <p className="text-sm font-semibold text-emerald-700">
                  {readyCount.toLocaleString()} / {enrichmentStatus.total_active.toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Photos available</p>
                <p className="text-sm font-semibold text-stone-800">
                  {(enrichmentStatus.images_with_reference ?? enrichmentStatus.images_displayable ?? enrichmentStatus.images_stored).toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Still left</p>
                <p className="text-sm font-semibold text-amber-700">
                  {needsWorkCount.toLocaleString()}
                </p>
              </div>
            </div>
          )}
          {enrichmentRunning && currentBatchTotal > 0 && (
            <div className="mt-3">
              <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wide text-sky-700">
                <span>Current checkpoint</span>
                <span>{currentBatchPct}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-sky-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-sky-500 transition-all duration-500"
                  style={{ width: `${currentBatchPct}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Catalog sync button */}
      <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-stone-700">Catalog</p>
          <p className="text-[11px] text-stone-400 mt-0.5">
            {supplier.last_full_sync_at
              ? `Last synced ${formatLastSynced(supplier.last_full_sync_at)}`
              : "Never synced"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] font-medium text-stone-500">
            Limit
            <input
              value={maxProducts}
              onChange={(e) => setMaxProducts(e.target.value.replace(/[^\d]/g, ""))}
              placeholder="All"
              inputMode="numeric"
              className="w-16 rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-xs text-stone-700 focus:outline-none focus:ring-2 focus:ring-emerald-300"
              disabled={!hasCredentials || isRunning || isImporting}
            />
          </label>
          {/* Configure Catalog — opens the wizard */}
          <button
            onClick={() => setCatalogWizardOpen(true)}
            disabled={!hasCredentials}
            title={hasCredentials ? "Choose which categories to scrape" : "Add credentials first"}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-stone-600 border border-stone-200 rounded-lg hover:bg-stone-100 bg-white disabled:opacity-40 transition-colors"
          >
            <BookOpen size={12} /> Configure Catalog
          </button>
          <button
            onClick={startScrape}
            disabled={!hasCredentials || isRunning || isImporting}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-50 hover:opacity-90 transition-colors"
            style={{ backgroundColor: "#2d5a33" }}
          >
            {isRunning ? (
              <><Loader2 size={14} className="animate-spin" /> Syncing…</>
            ) : (
              <><RefreshCw size={14} /> {job?.status === "done" ? "Update Catalog" : "Sync Catalog"}</>
            )}
          </button>
        </div>
      </div>

      {/* Catalog Wizard Modal */}
      {catalogWizardOpen && (
        <CatalogWizard
          supplierId={supplier.id}
          supplierName={supplier.name}
          onClose={() => setCatalogWizardOpen(false)}
          onSaved={() => { /* filters saved — scraper will pick them up on next run */ }}
        />
      )}

      {/* ── Milestone checklist panel ────────────────────────────────────── */}
      {showMilestones && (
        <MilestonePanel
          job={job}
          isRunning={isRunning}
          isImporting={isImporting}
          elapsed={elapsed}
        />
      )}

      {/* ── Import action (phase ready) ── */}
      {/* Show the already-imported success card if the job is done with products imported and no in-memory result yet */}
      {job?.phase === "done" && job?.status === "done" && (job?.products_imported ?? 0) > 0 && !importResult && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 size={18} className="text-emerald-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-emerald-800">Import complete</p>
                <p className="text-xs text-emerald-700 mt-0.5">Your product library has been updated.</p>
              </div>
            </div>
            {job.completed_at && (
              <div className="text-right flex-shrink-0">
                <p className="text-[11px] font-medium text-emerald-600 uppercase tracking-wide">Imported at</p>
                <p className="text-sm font-semibold text-emerald-800 tabular-nums">
                  {new Date(job.completed_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                </p>
                <p className="text-xs text-emerald-700 tabular-nums">
                  {new Date(job.completed_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true })}
                </p>
              </div>
            )}
          </div>
          <div className="flex items-center gap-4 border-t border-emerald-200 pt-3">
            <div className="flex-1 text-center">
              <p className="text-lg font-bold text-emerald-800 tabular-nums">{(job.products_imported ?? 0).toLocaleString()}</p>
              <p className="text-[11px] text-emerald-600 uppercase tracking-wide">Products imported</p>
            </div>
          </div>
        </div>
      )}

      {staleReadyImport && !importResult && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 size={18} className="mt-0.5 flex-shrink-0 text-emerald-600" />
            <div>
              <p className="text-sm font-semibold text-emerald-800">Catalog is already uploaded</p>
              <p className="mt-0.5 text-xs text-emerald-700">
                The latest imported Product Library catalog is newer than this old preview batch, so there is nothing else to import right now.
              </p>
            </div>
          </div>
        </div>
      )}

      {showImportAction && !importResult && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4">
          {importing ? (
            (() => {
              const done = job?.products_importing ?? 0;
              const total = job?.total_expected ?? job?.products_found ?? 0;
              const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
              return (
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <Loader2 size={16} className="text-emerald-600 animate-spin flex-shrink-0" />
                      <div>
                        <p className="text-sm font-semibold text-emerald-800">Importing to library…</p>
                        <p className="text-xs text-emerald-700 mt-0.5">Adding products — do not close this panel.</p>
                      </div>
                    </div>
                    <span className="text-sm font-semibold text-emerald-700 tabular-nums flex-shrink-0">
                      {done.toLocaleString()} / {total.toLocaleString()}
                    </span>
                  </div>
                  {/* Progress bar */}
                  <div className="h-1.5 w-full rounded-full bg-emerald-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="text-right text-[10px] text-emerald-500 tabular-nums">{pct}% complete</p>
                </div>
              );
            })()
          ) : (
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                  Next step: import scraped catalog
                </p>
                <p className="text-sm font-semibold text-emerald-800">
                  {isResumableImportJob(job)
                    ? `${(job.products_importing ?? 0).toLocaleString()} / ${(job.total_expected ?? job.products_found ?? 0).toLocaleString()} imported — resume available`
                    : `${(job.products_found ?? 0).toLocaleString()} products ready to import`}
                </p>
                <p className="text-xs text-emerald-700 mt-0.5">
                  {isResumableImportJob(job)
                    ? "The previous import stopped safely. Resume from the last saved product."
                    : "These scraped rows are waiting. Preview them, then import them into Product Library."}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={loadPreview}
                  className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-stone-600 border border-stone-200 rounded-lg hover:bg-stone-50 bg-white"
                >
                  <Eye size={13} /> Preview
                </button>
                <button
                  onClick={importAll}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-lg hover:opacity-90"
                  style={{ backgroundColor: "#2d5a33" }}
                >
                  <Download size={13} /> {isResumableImportJob(job) ? "Resume import" : "Import scraped products"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Import success */}
      {importResult && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 size={18} className="text-emerald-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-emerald-800">Import complete</p>
                <p className="text-xs text-emerald-700 mt-0.5">Your product library has been updated.</p>
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-[11px] font-medium text-emerald-600 uppercase tracking-wide">Imported at</p>
              <p className="text-sm font-semibold text-emerald-800 tabular-nums">
                {importResult.completedAt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
              </p>
              <p className="text-xs text-emerald-700 tabular-nums">
                {importResult.completedAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true })}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 border-t border-emerald-200 pt-3">
            <div className="flex-1 text-center">
              <p className="text-lg font-bold text-emerald-800 tabular-nums">{importResult.inserted.toLocaleString()}</p>
              <p className="text-[11px] text-emerald-600 uppercase tracking-wide">New products</p>
            </div>
            <div className="w-px h-8 bg-emerald-200" />
            <div className="flex-1 text-center">
              <p className="text-lg font-bold text-emerald-800 tabular-nums">{importResult.updated.toLocaleString()}</p>
              <p className="text-[11px] text-emerald-600 uppercase tracking-wide">Updated</p>
            </div>
            <div className="w-px h-8 bg-emerald-200" />
            <div className="flex-1 text-center">
              <p className="text-lg font-bold text-emerald-800 tabular-nums">{(importResult.inserted + importResult.updated).toLocaleString()}</p>
              <p className="text-[11px] text-emerald-600 uppercase tracking-wide">Total</p>
            </div>
          </div>
        </div>
      )}

      {/* Preview table */}
      {showPreview && preview.length > 0 && (
        <div className="rounded-xl border border-stone-200 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-stone-50 border-b border-stone-200">
            <p className="text-sm font-medium text-stone-700">Preview — first {preview.length} products</p>
            <button onClick={() => setShowPreview(false)} className="text-stone-400 hover:text-stone-600">
              <ChevronUp size={14} />
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-stone-50 sticky top-0 border-b border-stone-100">
                <tr>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">SKU</th>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">Name</th>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">Price</th>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">UOM</th>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">Min</th>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">Status</th>
                  <th className="text-left px-3 py-2 text-stone-500 font-medium">Photo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {preview.map((p, i) => (
                  <tr key={i} className="hover:bg-stone-50">
                    <td className="px-3 py-2 font-mono text-stone-500 text-[11px]">{p.sku}</td>
                    <td className="px-3 py-2 text-stone-800 max-w-[220px] truncate">{p.name}</td>
                    <td className="px-3 py-2 text-stone-700">{p.base_price != null ? `$${p.base_price.toFixed(2)}` : "—"}</td>
                    <td className="px-3 py-2 text-stone-700">{p.uom || "—"}</td>
                    <td className="px-3 py-2 text-stone-700">{p.min_qty ?? "—"}</td>
                    <td className="px-3 py-2 text-stone-700">{p.availability_note || p.avail_qty || "—"}</td>
                    <td className="px-3 py-2">
                      {p.photo_url
                        ? <img src={p.photo_url} alt="" className="w-8 h-8 object-cover rounded" />
                        : <span className="text-stone-300">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Price Sync Button ────────────────────────────────────────────────────────
function PriceSyncButton({ supplier, onSynced }: { supplier: Supplier; onSynced: (ts: string) => void }) {
  const [syncing, setSyncing] = useState(false);
  const [lastSynced, setLastSynced] = useState<string | null | undefined>(supplier.last_price_synced_at);
  const hasCredentials = !!(supplier.has_credentials || supplier.login_username);

  const handleSync = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!hasCredentials) {
      toast.error("Add login credentials before syncing prices.");
      return;
    }
    setSyncing(true);
    try {
      await apiClient.sync_prices({ supplierId: supplier.id });
      const now = new Date().toISOString();
      setLastSynced(now);
      onSynced(now);
      toast.success("Price sync started in background — prices will update shortly");
    } catch {
      toast.error("Failed to start price sync");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-0.5" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={handleSync}
        disabled={syncing || !hasCredentials}
        title={hasCredentials ? "Sync prices only (fast)" : "Add credentials to enable price sync"}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-stone-200 bg-white text-stone-600 hover:border-emerald-300 hover:text-emerald-700 disabled:opacity-40 transition-all"
      >
        <RefreshCcw size={11} className={syncing ? "animate-spin" : ""} />
        {syncing ? "Syncing…" : "Sync"}
      </button>
      <span className="text-[10px] text-stone-400 pr-0.5">
        {lastSynced ? formatLastSynced(lastSynced) : "Never synced"}
      </span>
    </div>
  );
}

// ── Supplier Card (expandable) ───────────────────────────────────────────────
function SupplierCard({
  supplier, onEdit, onDelete, defaultExpanded, onProductsImported,
}: {
  supplier: Supplier;
  onEdit: () => void;
  onDelete: () => void;
  defaultExpanded?: boolean;
  onProductsImported: () => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const [syncedAt, setSyncedAt] = useState<string | null | undefined>(supplier.last_price_synced_at);
  const hasCredentials = !!(supplier.has_credentials || (supplier.login_username && supplier.login_password));

  return (
    <div className={`bg-white rounded-xl border transition-all ${
      expanded ? "border-emerald-200 shadow-sm" : "border-stone-200"
    }`}>
      {/* Card header row */}
      <div
        className="flex items-center gap-4 px-5 py-4 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: "#e8f0e8" }}>
          <Building2 size={18} className="text-emerald-700" strokeWidth={1.5} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-semibold text-stone-800 text-sm">{supplier.name}</p>
            {supplier.login_url && (
              <a href={supplier.login_url} target="_blank" rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-stone-300 hover:text-emerald-600 transition-colors">
                <ExternalLink size={12} />
              </a>
            )}
            {/* Credentials badge */}
            {hasCredentials
              ? <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 px-1.5 py-0.5 rounded-full"><KeyRound size={9} /> Credentials saved</span>
              : <span className="flex items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded-full"><AlertTriangle size={9} /> No credentials</span>
            }
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-xs text-stone-400">
            {supplier.contact_name && <span>{supplier.contact_name}</span>}
            {supplier.contact_email && <span>{supplier.contact_email}</span>}
            {supplier.contact_phone && <span>{supplier.contact_phone}</span>}
          </div>
        </div>

        {/* Product count */}
        <div className="text-right mr-2 flex-shrink-0">
          <div className="flex items-center gap-1.5 text-stone-500">
            <Package size={13} className="text-stone-400" />
            <span className="text-sm font-semibold">{supplier.product_count.toLocaleString()}</span>
            <span className="text-xs text-stone-400">products</span>
          </div>
        </div>

        {/* Price Sync */}
        <PriceSyncButton supplier={{ ...supplier, last_price_synced_at: syncedAt }} onSynced={(ts) => setSyncedAt(ts)} />

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          <button onClick={onEdit} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-stone-100 text-stone-400 hover:text-stone-600 transition-colors" title="Edit supplier">
            <Pencil size={14} />
          </button>
          <button onClick={onDelete} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-red-50 text-stone-400 hover:text-red-500 transition-colors" title="Delete supplier">
            <Trash2 size={14} />
          </button>
        </div>

        {/* Expand chevron */}
        <div className="text-stone-400 flex-shrink-0">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {/* Expandable scraper panel */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-stone-100">
          <ScraperPanel supplier={supplier} onProductsImported={onProductsImported} />
        </div>
      )}
    </div>
  );
}

// Missing prop in type signature — fix below
function SupplierCardWrapper(props: {
  supplier: Supplier;
  onEdit: () => void;
  onDelete: () => void;
  defaultExpanded?: boolean;
  onProductsImported: () => void;
}) {
  return <SupplierCard {...props} />;
}

function AllstateRunBanner({ supplier }: { supplier?: Supplier }) {
  const [autoStatus, setAutoStatus] = useState<DetailBackfillAutoRunStatus | null>(null);
  const [enrichment, setEnrichment] = useState<EnrichmentStatus | null>(null);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const [changedAt, setChangedAt] = useState<number | null>(null);
  const bannerProgressKeyRef = useRef("");

  const loadStatus = useCallback(async () => {
    if (!supplier) return;
    try {
      const [autoData, enrichmentData] = await Promise.all([
        fetchFreshJson<DetailBackfillAutoRunStatus>("/api/scraper/backfill-allstate-details/run-until-complete/status"),
        fetchFreshJson<EnrichmentStatus>(`/api/scraper/supplier-enrichment-status/${supplier.id}`),
      ]);
      setAutoStatus(autoData);
      setEnrichment(enrichmentData);
      const nextKey = progressKey(autoData, autoData.current_batch || enrichmentData.last_backfill || null);
      if (nextKey !== bannerProgressKeyRef.current) {
        bannerProgressKeyRef.current = nextKey;
        setChangedAt(Date.now());
      }
      setCheckedAt(Date.now());
    } catch (err) {
      console.error("Allstate progress banner error", err);
    }
  }, [supplier]);

  useEffect(() => {
    void loadStatus();
    const interval = setInterval(() => { void loadStatus(); }, 3000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  if (!supplier || !enrichment) return null;

  const batch = autoStatus?.current_batch || enrichment.last_backfill || null;
  const batchTotal = batch?.total || 0;
  const batchDone = batch?.done || 0;
  const isRunning = autoStatus?.status === "running" || batch?.status === "running";
  const staleProgress = isProgressStale(autoStatus, changedAt);
  const enrichmentEta = estimateAllstateEta(autoStatus, batch, enrichment.detail_pending);
  const displayablePhotos = enrichment.images_with_reference ?? enrichment.images_displayable ?? enrichment.images_stored;
  const readyCount = Math.min(enrichment.detail_stored, displayablePhotos);
  const readyPct = enrichment.total_active > 0
    ? Math.min(100, Math.round((readyCount / enrichment.total_active) * 100))
    : 0;
  const readyDisplayPct = enrichment.total_active > 0 && readyCount < enrichment.total_active
    ? Math.min(99, Math.floor((readyCount / enrichment.total_active) * 100))
    : readyPct;
  const needsWork = Math.max(0, enrichment.total_active - readyCount);
  const checkpointSize = autoStatus?.batch_limit || 250;
  const completedCheckpoints = autoStatus?.batches_run ?? 0;
  const checkpointNumber = isRunning && batchTotal > 0 ? completedCheckpoints + 1 : completedCheckpoints;
  const currentCheckpointRemaining = isRunning ? Math.max(0, batchTotal - batchDone) : 0;
  const workAfterCurrentCheckpoint = Math.max(0, needsWork - currentCheckpointRemaining);
  const checkpointsLeft = needsWork === 0
    ? 0
    : isRunning && batchTotal > batchDone
      ? 1 + Math.ceil(workAfterCurrentCheckpoint / checkpointSize)
      : Math.ceil(needsWork / checkpointSize);
  const estimatedFinalCheckpoint = checkpointNumber > 0 && checkpointsLeft > 0
    ? checkpointNumber + checkpointsLeft - 1
    : checkpointNumber;
  const totalCheckpoints = enrichment.total_active > 0
    ? Math.max(1, Math.ceil(enrichment.total_active / checkpointSize))
    : Math.max(checkpointNumber || 1, estimatedFinalCheckpoint || 1);
  const displayedCheckpoint = needsWork === 0
    ? totalCheckpoints
    : Math.min(Math.max(1, checkpointNumber || 1), totalCheckpoints);

  return (
    <div className="mb-5 rounded-xl border border-teal-200 bg-teal-50 px-5 py-4 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            {isRunning ? <Loader2 size={15} className="animate-spin text-teal-700" /> : <CheckCircle2 size={15} className="text-teal-700" />}
            <p className="text-sm font-semibold text-teal-900">
              {needsWork === 0 ? "Allstate catalog is complete" : isRunning ? "Allstate catalog is finishing" : "Allstate catalog status"}
            </p>
          </div>
          <p className="mt-1 text-sm font-semibold text-teal-900">
            {readyCount.toLocaleString()} of {enrichment.total_active.toLocaleString()} products ready ({readyDisplayPct}%)
          </p>
          <p className="mt-1 text-xs text-teal-700">
            {needsWork.toLocaleString()} still need a photo or source detail.
            {needsWork > 0 && isRunning && batchTotal > 0
              ? ` Working now: ${batchDone.toLocaleString()} of ${batchTotal.toLocaleString()} in this checkpoint.`
              : ""}
          </p>
          <p className="mt-1 text-[10px] text-teal-800">
            Updated {formatClock(checkedAt)}
            {needsWork <= 1 ? " · Almost done" : enrichmentEta.minutesRemaining ? ` · About ${formatDuration(enrichmentEta.minutesRemaining)} left` : ""}
            {enrichmentEta.completionAt ? ` · Done around ${formatClock(enrichmentEta.completionAt.getTime())}` : ""}
          </p>
          {(isRunning || needsWork > 0) && (
            <p className="mt-1 text-[10px] text-teal-700">
              Checkpoint {displayedCheckpoint} of {totalCheckpoints}: a saved batch of up to {checkpointSize} products. If this stops, it resumes from unfinished products.
            </p>
          )}
          {!isRunning && needsWork === 0 && (
            <p className="mt-1 text-[10px] text-teal-700">
              Checkpoints complete: {totalCheckpoints} of {totalCheckpoints} saved batches.
            </p>
          )}
          {staleProgress && (
            <p className="mt-1 text-[10px] font-semibold text-amber-700">
              Progress has not changed in over 2 minutes. The resume controls are in the Allstate panel below.
            </p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:min-w-[520px]">
          <div className="rounded-lg bg-white px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Ready</p>
            <p className="text-sm font-semibold text-emerald-700">{readyCount.toLocaleString()}</p>
          </div>
          <div className="rounded-lg bg-white px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Photos</p>
            <p className="text-sm font-semibold text-teal-800">{displayablePhotos.toLocaleString()}</p>
          </div>
          <div className="rounded-lg bg-white px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Details</p>
            <p className="text-sm font-semibold text-teal-800">{enrichment.detail_stored.toLocaleString()}</p>
          </div>
          <div className="rounded-lg bg-white px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Time Left</p>
            <p className="text-sm font-semibold text-teal-800">
              {needsWork <= 1 ? "Almost done" : formatDuration(enrichmentEta.minutesRemaining)}
            </p>
            <p className="text-[10px] text-stone-400">
              {needsWork.toLocaleString()} left
            </p>
          </div>
        </div>
      </div>
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wide text-teal-700">
          <span>Overall catalog readiness</span>
          <span>{readyDisplayPct}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white">
          <div className="h-full rounded-full bg-emerald-600 transition-all duration-500" style={{ width: `${readyPct}%` }} />
        </div>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function Suppliers() {
  const cachedSuppliers = useMemo(() => readSuppliersCache(), []);
  const [suppliers, setSuppliers] = useState<Supplier[]>(cachedSuppliers || []);
  const [loading, setLoading] = useState(!cachedSuppliers);
  const [refreshing, setRefreshing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editSupplier, setEditSupplier] = useState<Partial<Supplier> | null>(null);

  const load = async () => {
    if (suppliers.length === 0) setLoading(true);
    else setRefreshing(true);
    try {
      // Race against a 10-second timeout so the page never hangs forever
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      const res = await fetch("/api/suppliers/list", {
        credentials: "include",
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) throw new Error(`Supplier list failed with ${res.status}`);
      const data = await res.json();
      if (!Array.isArray(data)) throw new Error("Supplier list returned an unexpected shape");
      setSuppliers(data);
      writeSuppliersCache(data);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        toast.error("Suppliers took too long to load — the server may be busy. Try refreshing.");
      } else {
        toast.error("Failed to load suppliers — try refreshing the page.");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  const deleteSupplier = async (id: number) => {
    if (!confirm("Delete this supplier? All associated products will also be removed.")) return;
    try {
      await apiClient.delete_supplier({ supplierId: id });
      setSuppliers((prev) => prev.filter((s) => s.id !== id));
      toast.success("Supplier deleted");
    } catch {
      toast.error("Failed to delete supplier");
    }
  };

  const openEdit = (s: Supplier) => { setEditSupplier(s); setShowModal(true); };
  const openNew = () => { setEditSupplier(null); setShowModal(true); };
  const allstateSupplier = suppliers.find((s) => s.name.toLowerCase().includes("allstate"));

  return (
    <Layout>
      {/* Page header */}
      <header className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200" style={{ backgroundColor: "#f7f4ef" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Suppliers</h1>
          <p className="text-xs text-stone-500 mt-0.5">
            {suppliers.length} supplier{suppliers.length !== 1 ? "s" : ""} · Click a row to sync its product catalog
            {refreshing && <span className="ml-2 text-emerald-700">Refreshing…</span>}
          </p>
        </div>
        <button
          onClick={openNew}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white hover:opacity-90 transition-colors"
          style={{ backgroundColor: "#2d5a33" }}
        >
          <Plus size={15} strokeWidth={2.2} /> Add Supplier
        </button>
      </header>

      <div className="px-10 py-6 max-w-4xl">

        <AllstateRunBanner supplier={allstateSupplier} />


        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : suppliers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "#e8f0e8" }}>
              <Building2 size={28} className="text-emerald-600" strokeWidth={1.5} />
            </div>
            <p className="text-base font-medium text-stone-600 mb-1">No suppliers yet</p>
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed mb-4">Add your first supplier to start syncing product catalogs.</p>
            <button onClick={openNew} className="px-4 py-2 text-sm font-semibold text-white rounded-lg hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>Add First Supplier</button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {suppliers.map((s) => (
              <SupplierCardWrapper
                key={s.id}
                supplier={s}
                onEdit={() => openEdit(s)}
                onDelete={() => deleteSupplier(s.id)}
                defaultExpanded={false}
                onProductsImported={load}
              />
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <SupplierModal
          supplier={editSupplier}
          onClose={() => { setShowModal(false); setEditSupplier(null); }}
          onSave={() => {
            // Reload from server to get fresh has_credentials flag and all fields
            load();
          }}
        />
      )}
    </Layout>
  );
}
