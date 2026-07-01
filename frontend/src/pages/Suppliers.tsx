import React, { useEffect, useState, useRef, useCallback } from "react";
import {
  Plus, Pencil, Trash2, X, ExternalLink, Building2, RefreshCw,
  CheckCircle2, XCircle, Loader2, Eye, EyeOff, Download, AlertTriangle,
  KeyRound, ChevronDown, ChevronUp, Package, ArrowRight, RefreshCcw,
  Circle, BookOpen, FileUp, Database,
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
  credential_status?: string | null;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  notes?: string;
  product_count: number;
  last_price_synced_at?: string | null;
  last_full_sync_at?: string | null;
  created_at: string;
};
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
type ImageBackfillStatus = {
  status: "idle" | "running" | "done" | "failed";
  supplier_id?: number | null;
  total: number;
  done: number;
  stored: number;
  skipped: number;
  failed: number;
  started_at?: string | null;
  completed_at?: string | null;
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
type VickermanFullSyncStatus = {
  status: "idle" | "running" | "done" | "failed" | "stopping" | "stopped";
  supplier_id?: number | null;
  batch_limit: number;
  max_batches?: number | null;
  max_products?: number | null;
  batches_run: number;
  total_scraped: number;
  total_imported: number;
  total_active?: number | null;
  current_job_id?: number | null;
  current_batch?: {
    batch_number?: number;
    excluded_skus?: number;
    limit?: number;
    scraped?: number;
    queued_or_scraped?: number;
    target?: number;
    job_id?: number;
    phase?: string;
    imported?: number;
  } | null;
  last_backfill?: ImageBackfillStatus | null;
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
  images_no_supplier_image?: number;
  images_resolved?: number;
  images_pending: number;
  images_failed: number;
  images_missing: number;
  last_backfill?: DetailBackfillStatus | null;
};
type ReadinessStepStatus = "done" | "partial" | "missing" | "warning" | "working";
type AllstateReadiness = {
  supplier_id: number;
  supplier_name: string;
  scraper_key: string;
  has_credentials: boolean;
  credential_status?: string | null;
  category_index_count: number;
  selected_category_count: number;
  selected_category_mode: "none" | "all" | "selected";
  estimated_selected_products: number;
  product_count: number;
  standardized_count: number;
  photo_ready_count: number;
  internal_photo_count: number;
  supplier_hosted_photo_count: number;
  photo_problem_count: number;
  placeholder_image_count: number;
  no_supplier_image_count: number;
  retryable_image_problem_count: number;
  detail_ready_count: number;
  fully_ready_count: number;
  builder_item_count: number;
  ready_percent: number;
  storage_percent: number;
  image_problem_samples: Array<{
    product_id: number;
    supplier_sku: string;
    name: string;
    photo_url?: string | null;
    source_photo_url?: string | null;
    image_status?: string | null;
    problem_type?: "placeholder" | "retryable" | string;
  }>;
  next_action: string;
  steps: Array<{
    key: string;
    label: string;
    status: ReadinessStepStatus;
    detail: string;
    action?: string | null;
  }>;
};
type CatalogImport = {
  id: number;
  supplier_id: number;
  source_type: string;
  parser_key?: string | null;
  catalog_name: string;
  original_filename: string;
  status: string;
  row_count: number;
  staged_count: number;
  duplicate_count: number;
  inserted_count: number;
  updated_count: number;
  error_count: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  committed_at?: string | null;
};
type CatalogImportRow = {
  id: number;
  import_id: number;
  row_index: number;
  supplier_sku: string;
  name: string;
  upc?: string | null;
  current_price?: number | null;
  unit: string;
  category: string;
  moq?: number | null;
  box_qty?: number | null;
  case_qty?: number | null;
  source_page?: number | null;
  source_section?: string | null;
  status: string;
  error_message?: string | null;
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

function readinessTone(status: ReadinessStepStatus) {
  if (status === "done") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "partial" || status === "working") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "warning") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-stone-200 bg-white text-stone-500";
}

function readinessDot(status: ReadinessStepStatus) {
  if (status === "done") return <CheckCircle2 size={13} className="text-emerald-600" />;
  if (status === "partial" || status === "working") return <Circle size={13} className="fill-amber-400 text-amber-400" />;
  if (status === "warning") return <Circle size={13} className="fill-sky-400 text-sky-400" />;
  return <Circle size={13} className="text-stone-300" />;
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
  const productsFound = job.products_found ?? 0;
  const productsImported = job.products_imported ?? 0;
  const hasUnimportedProducts = productsFound > productsImported;
  return !!job.result_key && hasUnimportedProducts && (job.phase === "ready" || job.status === "done");
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
  const [showPassword, setShowPassword] = useState(false);
  const [showSavedPassword, setShowSavedPassword] = useState(false);
  const [savedPassword, setSavedPassword] = useState<string | null>(null);
  const [revealingSavedPassword, setRevealingSavedPassword] = useState(false);
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));
  const scraperKey = String(form.scraper_key || "").toLowerCase();
  const isAccentDecor = scraperKey === "accent" || scraperKey === "accent_decor" || /accent decor/i.test(String(form.name || ""));
  const isRegency = scraperKey === "regency" || /regency/i.test(String(form.name || ""));
  const isVickerman = scraperKey === "vickerman" || /vickerman/i.test(String(form.name || ""));
  const usernameLabel = isAccentDecor ? "Accent email" : isRegency ? "Regency email" : isVickerman ? "Vickerman email" : "Username / account #";
  const passwordLabel = isAccentDecor ? "Accent password" : isRegency ? "Regency password" : isVickerman ? "Vickerman password" : "Password / billing zip";
  const usernamePlaceholder = isAccentDecor || isRegency || isVickerman ? "customer@email.com" : "Account number or email";
  const passwordPlaceholder = isAccentDecor || isRegency || isVickerman ? "Password" : "Password or zip code";

  const toggleSavedPassword = async () => {
    if (showSavedPassword) {
      setShowSavedPassword(false);
      return;
    }
    if (savedPassword !== null) {
      setShowSavedPassword(true);
      return;
    }
    if (!form.id) return;
    setRevealingSavedPassword(true);
    try {
      const data = await fetchFreshJson<{ login_username?: string | null; login_password?: string | null }>(
        `/api/suppliers/${form.id}/credentials`,
      );
      if (data.login_username && !form.login_username) {
        set("login_username", data.login_username);
      }
      setSavedPassword(data.login_password || "");
      setShowSavedPassword(true);
    } catch {
      toast.error("Could not reveal saved password.");
    } finally {
      setRevealingSavedPassword(false);
    }
  };

  const handleSave = async () => {
    if (!form.name) { toast.error("Supplier name is required"); return; }
    setSaving(true);
    try {
      let res;
      const payload = { ...form };
      if (form.id && credsLocked) {
        delete payload.login_username;
        delete payload.login_password;
      }
      if (form.id) {
        res = await apiClient.update_supplier({ supplierId: form.id }, payload);
      } else {
        res = await apiClient.create_supplier(payload);
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
                {credsLocked ? "Login credentials — saved" : "Login credentials — optional for external extraction"}
              </p>
              {credsLocked && (
                <button
                  type="button"
                  onClick={() => {
                    // Clear fields so user must re-enter — never pre-fill from stored values
                    set("login_username", "");
                    set("login_password", "");
                    setShowPassword(false);
                    setShowSavedPassword(false);
                    setSavedPassword(null);
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
                  <label className="block text-xs text-stone-500 mb-1">{usernameLabel}</label>
                  <div className="w-full border border-emerald-200 rounded-lg px-3 py-2 text-sm bg-white text-stone-700 truncate">
                    {form.login_username || (
                      <span className="text-stone-400 italic">
                        {isAccentDecor ? "email saved" : "username saved"}
                      </span>
                    )}
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-stone-500 mb-1">{passwordLabel}</label>
                  <div className="relative w-full border border-emerald-200 rounded-lg bg-white">
                    <div className={`px-3 py-2 pr-10 text-sm text-stone-700 ${showSavedPassword ? "break-all" : "text-stone-500 tracking-widest"}`}>
                      {showSavedPassword ? savedPassword : "••••••••"}
                    </div>
                    <button
                      type="button"
                      onClick={toggleSavedPassword}
                      disabled={revealingSavedPassword}
                      aria-label={showSavedPassword ? "Hide saved password" : "Show saved password"}
                      title={showSavedPassword ? "Hide password" : "Show password"}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 disabled:opacity-50"
                    >
                      {showSavedPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              /* ── Editable view ── */
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-stone-600 mb-1">{usernameLabel}</label>
                  <input
                    type={isAccentDecor ? "email" : "text"}
                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 bg-white"
                    value={form.login_username || ""}
                    onChange={(e) => set("login_username", e.target.value)}
                    placeholder={usernamePlaceholder}
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-xs text-stone-600 mb-1">{passwordLabel}</label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      className="w-full border border-stone-200 rounded-lg px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 bg-white"
                      value={form.login_password || ""}
                      onChange={(e) => set("login_password", e.target.value)}
                      placeholder={passwordPlaceholder}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      title={showPassword ? "Hide password" : "Show password"}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700"
                    >
                      {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
              </div>
            )}
            {isAccentDecor && (
              <p className="mt-2 text-[11px] leading-relaxed text-stone-600">
                Use the activated Accent Decor customer login from the Customer Login form. The account number and billing zip are only for Accent's one-time online access activation.
              </p>
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
function ScraperPanel({
  supplier,
  onProductsImported,
  onEditCredentials,
}: {
  supplier: Supplier;
  onProductsImported: () => void;
  onEditCredentials: () => void;
}) {
  const [job, setJob] = useState<ScrapeJobOut | null>(null);
  const [status, setStatus] = useState<ScrapeStatus>("idle");
  const [maxProducts, setMaxProducts] = useState(""); // blank = full catalog
  const [catalogWizardOpen, setCatalogWizardOpen] = useState(false);
  const [preview, setPreview] = useState<ScrapedProductOut[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ inserted: number; updated: number; completedAt: Date } | null>(null);
  const [catalogImports, setCatalogImports] = useState<CatalogImport[]>([]);
  const [catalogFiles, setCatalogFiles] = useState<File[]>([]);
  const [catalogName, setCatalogName] = useState("");
  const [catalogRows, setCatalogRows] = useState<CatalogImportRow[]>([]);
  const [selectedCatalogImportId, setSelectedCatalogImportId] = useState<number | null>(null);
  const [catalogUploading, setCatalogUploading] = useState(false);
  const [catalogUploadProgress, setCatalogUploadProgress] = useState<string | null>(null);
  const [catalogUploadResult, setCatalogUploadResult] = useState<{ tone: "info" | "success" | "error"; message: string } | null>(null);
  const [catalogCommitting, setCatalogCommitting] = useState(false);
  const [showAdvancedTools, setShowAdvancedTools] = useState(false);
  const [detailBackfillLimit] = useState("250");
  const [detailBackfill, setDetailBackfill] = useState<DetailBackfillStatus | null>(null);
  const [detailBackfillRunning, setDetailBackfillRunning] = useState(false);
  const [detailBackfillAuto, setDetailBackfillAuto] = useState<DetailBackfillAutoRunStatus | null>(null);
  const [detailBackfillAutoRunning, setDetailBackfillAutoRunning] = useState(false);
  const [imageBackfill, setImageBackfill] = useState<ImageBackfillStatus | null>(null);
  const [imageBackfillRunning, setImageBackfillRunning] = useState(false);
  const [vickermanFullSync, setVickermanFullSync] = useState<VickermanFullSyncStatus | null>(null);
  const [vickermanFullSyncRunning, setVickermanFullSyncRunning] = useState(false);
  const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentStatus | null>(null);
  const [readiness, setReadiness] = useState<AllstateReadiness | null>(null);
  const [readinessCheckedAt, setReadinessCheckedAt] = useState<number | null>(null);
  const [placeholderReviewing, setPlaceholderReviewing] = useState(false);
  const [progressCheckedAt, setProgressCheckedAt] = useState<number | null>(null);
  const [progressChangedAt, setProgressChangedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const importPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const detailBackfillPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const detailBackfillAutoPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const imageBackfillPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const vickermanFullSyncPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressKeyRef = useRef<string>("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasCredentials = !!(supplier.has_credentials || (supplier.login_username && supplier.login_password));
  const credentialStatus = (supplier.credential_status || "").toLowerCase();
  const credentialsFailed = credentialStatus === "failed" || credentialStatus === "error";
  const credentialsUntested = credentialStatus === "untested";
  const normalizedScraperKey = (supplier.scraper_key || "").toLowerCase() === "accent" ? "accent_decor" : (supplier.scraper_key || "").toLowerCase();
  const supportsReadiness = normalizedScraperKey === "allstate" || normalizedScraperKey === "accent_decor" || normalizedScraperKey === "regency" || normalizedScraperKey === "select_artificial" || normalizedScraperKey === "vickerman" || /allstate|accent|regency|select artificial|vickerman/i.test(supplier.name);
  const isAllstateSupplier = normalizedScraperKey === "allstate" || supplier.name.toLowerCase().includes("allstate");
  const isAccentSupplier = normalizedScraperKey === "accent_decor" || supplier.name.toLowerCase().includes("accent");
  const isRegencySupplier = normalizedScraperKey === "regency" || supplier.name.toLowerCase().includes("regency");
  const isSelectSupplier = normalizedScraperKey === "select_artificial" || supplier.name.toLowerCase().includes("select artificial");
  const isVickermanSupplier = normalizedScraperKey === "vickerman" || supplier.name.toLowerCase().includes("vickerman");
  const credentialsNeedValidation = supportsReadiness && hasCredentials && (credentialsFailed || credentialsUntested);
  const failedCredentialDetail = isAccentSupplier
    ? `${supplier.name} rejected the saved Accent email/password.`
    : isRegencySupplier
    ? `${supplier.name} rejected the saved Regency email/password.`
    : isSelectSupplier
    ? `${supplier.name} rejected the saved Select customer number/billing zip.`
    : isVickermanSupplier
    ? `${supplier.name} rejected the saved Vickerman email/password.`
    : `${supplier.name} rejected the saved login credentials.`;
  const failedCredentialAction = isAccentSupplier
    ? "Update the Accent email/password, then run Configure Catalog again."
    : isRegencySupplier
    ? "Update the Regency email/password, then run Configure Catalog again."
    : isSelectSupplier
    ? "Update the Select customer number/billing zip, then run Configure Catalog again."
    : isVickermanSupplier
    ? "Update the Vickerman email/password, then run Configure Catalog again."
    : "Update the login credentials, then run Configure Catalog again.";
  const missingCredentialDetail = isAccentSupplier
    ? "Click Edit on this supplier and fill in the activated Accent email and password only if this supplier needs portal extraction."
    : isRegencySupplier
    ? "Click Edit on this supplier and fill in the Regency email and password only if this supplier needs portal extraction."
    : isSelectSupplier
    ? "Click Edit on this supplier and fill in the Select customer number and billing zip only if this supplier needs portal extraction."
    : isVickermanSupplier
    ? "Click Edit on this supplier and fill in the Vickerman email and password only if this supplier needs portal extraction."
    : "Click Edit on this supplier and fill in credentials only if this supplier needs portal extraction.";
  const untestedCredentialAction = isAccentSupplier
    ? "Run Configure Catalog to test the Accent email/password before syncing products."
    : isRegencySupplier
    ? "Run Configure Catalog to test the Regency email/password before syncing products."
    : isSelectSupplier
    ? "Run Configure Catalog to test the Select customer number/billing zip before syncing products."
    : isVickermanSupplier
    ? "Run Configure Catalog to test the Vickerman email/password before syncing products."
    : "Run Configure Catalog to test these credentials before syncing products.";

  const loadReadiness = useCallback(async () => {
    if (!supportsReadiness) return;
    try {
      const data = await fetchFreshJson<AllstateReadiness>(`/api/scraper/supplier-readiness/${supplier.id}`);
      setReadiness(data);
      setReadinessCheckedAt(Date.now());
    } catch (e) {
      console.error("Supplier readiness error", e);
    }
  }, [supplier.id, supportsReadiness]);

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

  const stopImageBackfillPolling = useCallback(() => {
    if (imageBackfillPollRef.current) { clearInterval(imageBackfillPollRef.current); imageBackfillPollRef.current = null; }
  }, []);

  const stopVickermanFullSyncPolling = useCallback(() => {
    if (vickermanFullSyncPollRef.current) { clearInterval(vickermanFullSyncPollRef.current); vickermanFullSyncPollRef.current = null; }
  }, []);

  const loadEnrichmentStatus = useCallback(async () => {
    if (!supportsReadiness) return;
    try {
      const data = await fetchFreshJson<EnrichmentStatus>(`/api/scraper/supplier-enrichment-status/${supplier.id}`);
      setEnrichmentStatus(data);
      setProgressCheckedAt(Date.now());
      void loadReadiness();
    } catch (e) {
      console.error("Enrichment status error", e);
    }
  }, [loadReadiness, supplier.id, supportsReadiness]);

  const loadCatalogImports = useCallback(async () => {
    try {
      const imports = await fetchFreshJson<CatalogImport[]>(`/api/suppliers/${supplier.id}/catalog-imports`);
      setCatalogImports(imports);
      const latest = imports[0];
      if (latest && !selectedCatalogImportId) {
        setSelectedCatalogImportId(latest.id);
      }
    } catch (e) {
      console.error("Catalog imports error", e);
    }
  }, [selectedCatalogImportId, supplier.id]);

  const loadCatalogRows = useCallback(async (importId: number) => {
    try {
      const data = await fetchFreshJson<{ items: CatalogImportRow[] }>(`/api/suppliers/catalog-imports/${importId}/rows?limit=25`);
      setCatalogRows(data.items || []);
      setSelectedCatalogImportId(importId);
    } catch {
      toast.error("Could not load catalog row preview.");
    }
  }, []);

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

  const pollImageBackfillStatus = useCallback(async () => {
    try {
      const data = await fetchFreshJson<ImageBackfillStatus>("/api/scraper/backfill-images/status");
      setImageBackfill(data);
      const appliesToSupplier = data.supplier_id == null || data.supplier_id === supplier.id;
      setProgressCheckedAt(Date.now());
      if (appliesToSupplier) {
        void loadEnrichmentStatus();
        void loadReadiness();
      }
      if (data.status === "running" && appliesToSupplier) {
        setImageBackfillRunning(true);
      } else {
        setImageBackfillRunning(false);
        stopImageBackfillPolling();
      }
    } catch (e) {
      console.error("Image backfill poll error", e);
    }
  }, [loadEnrichmentStatus, loadReadiness, stopImageBackfillPolling, supplier.id]);

  const pollVickermanFullSyncStatus = useCallback(async () => {
    if (!isVickermanSupplier) return;
    try {
      const data = await fetchFreshJson<VickermanFullSyncStatus>("/api/scraper/vickerman/run-until-complete/status");
      setVickermanFullSync(data);
      const appliesToSupplier = data.supplier_id == null || data.supplier_id === supplier.id;
      const running = appliesToSupplier && data.status === "running";
      setVickermanFullSyncRunning(running);
      setProgressCheckedAt(Date.now());
      if (appliesToSupplier) {
        void loadEnrichmentStatus();
        void loadReadiness();
      }
      if (!running) {
        stopVickermanFullSyncPolling();
      }
    } catch (e) {
      console.error("Vickerman full sync poll error", e);
    }
  }, [isVickermanSupplier, loadEnrichmentStatus, loadReadiness, stopVickermanFullSyncPolling, supplier.id]);

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
        await loadCatalogImports();
        await loadReadiness();
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
        if (isAllstateSupplier) {
          stopDetailBackfillAutoPolling();
          detailBackfillAutoPollRef.current = setInterval(() => { void pollDetailBackfillAutoStatus(); }, 3000);
        }
        const imageData = await fetchFreshJson<ImageBackfillStatus>("/api/scraper/backfill-images/status");
        setImageBackfill(imageData);
        if (imageData.status === "running" && (imageData.supplier_id == null || imageData.supplier_id === supplier.id)) {
          setImageBackfillRunning(true);
          stopImageBackfillPolling();
          imageBackfillPollRef.current = setInterval(() => { void pollImageBackfillStatus(); }, 2000);
        }
        if (isVickermanSupplier) {
          const vickermanData = await fetchFreshJson<VickermanFullSyncStatus>("/api/scraper/vickerman/run-until-complete/status");
          setVickermanFullSync(vickermanData);
          if (vickermanData.status === "running" && (vickermanData.supplier_id == null || vickermanData.supplier_id === supplier.id)) {
            setVickermanFullSyncRunning(true);
            stopVickermanFullSyncPolling();
            vickermanFullSyncPollRef.current = setInterval(() => { void pollVickermanFullSyncStatus(); }, 3000);
          }
        }
      } catch { /* no detail backfill yet */ }
    })();
    return () => { stopPolling(); stopTimer(); stopDetailBackfillPolling(); stopDetailBackfillAutoPolling(); stopImageBackfillPolling(); stopVickermanFullSyncPolling(); };
  }, [supplier.id, pollJob, pollDetailBackfillStatus, pollDetailBackfillAutoStatus, pollImageBackfillStatus, pollVickermanFullSyncStatus, stopDetailBackfillPolling, stopDetailBackfillAutoPolling, stopImageBackfillPolling, stopVickermanFullSyncPolling, stopPolling, stopTimer, startTimer, loadEnrichmentStatus, loadReadiness, loadCatalogImports, isAllstateSupplier, isVickermanSupplier]);

  const startScrape = async () => {
    if (!hasCredentials) { toast.error("Add login credentials before scraping."); return; }
    if (credentialsFailed) { toast.error(failedCredentialAction); return; }
    if (credentialsUntested) { toast.error(untestedCredentialAction); return; }
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
      void loadReadiness();
      void loadEnrichmentStatus();
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

  const uploadCatalogFiles = async (filesOverride?: File[]) => {
    const filesToUpload = filesOverride ?? catalogFiles;
    if (filesToUpload.length === 0) {
      toast.error("Choose one or more catalog exports, spreadsheets, or PDFs first.");
      return;
    }
    setCatalogUploading(true);
    setCatalogCommitting(true);
    setCatalogFiles(filesToUpload);
    setCatalogUploadProgress(`Preparing ${filesToUpload.length.toLocaleString()} file${filesToUpload.length === 1 ? "" : "s"}...`);
    setCatalogUploadResult({
      tone: "info",
      message: `Importing ${filesToUpload.length.toLocaleString()} catalog source${filesToUpload.length === 1 ? "" : "s"} into the Product Library.`,
    });
    try {
      const parsedImports: CatalogImport[] = [];
      const failedImports: string[] = [];
      const importTotals = { inserted: 0, updated: 0, errors: 0 };
      for (const [index, file] of filesToUpload.entries()) {
        const progressMessage = `Reading ${index + 1} of ${filesToUpload.length}: ${file.name}`;
        setCatalogUploadProgress(progressMessage);
        setCatalogUploadResult({ tone: "info", message: progressMessage });
        try {
          const body = new FormData();
          body.append("file", file);
          body.append("catalog_name", filesToUpload.length === 1 && catalogName ? catalogName : file.name);
          if (isAllstateSupplier && file.name.toLowerCase().endsWith(".pdf")) {
            body.append("parser_key", "allstate_pdf");
          }
          const res = await fetch(`/api/suppliers/${supplier.id}/catalog-imports/upload`, {
            method: "POST",
            body,
          });
          const data: CatalogImport & { detail?: string } = await res.json().catch(() => ({
            detail: `Server returned ${res.status}`,
          } as CatalogImport & { detail: string }));
          if (!res.ok || data.status === "failed") {
            failedImports.push(`${file.name}: ${data.error_message || data.detail || "Catalog parsing failed."}`);
            continue;
          }
          parsedImports.push(data);
          setCatalogUploadProgress(`Standardizing ${data.row_count.toLocaleString()} products from ${file.name}`);
          const commitRes = await fetch(`/api/suppliers/catalog-imports/${data.id}/commit?include_duplicates=true`, {
            method: "POST",
          });
          const commitData: { inserted?: number; updated?: number; errors?: number; detail?: string } = await commitRes.json().catch(() => ({
            detail: `Server returned ${commitRes.status}`,
          }));
          if (!commitRes.ok) {
            failedImports.push(`${file.name}: ${commitData.detail || "Products were parsed but could not be imported."}`);
            continue;
          }
          importTotals.inserted += commitData.inserted || 0;
          importTotals.updated += commitData.updated || 0;
          importTotals.errors += commitData.errors || 0;
        } catch (err) {
          failedImports.push(`${file.name}: ${err instanceof Error ? err.message : "Catalog parsing failed."}`);
        }
      }
      const latest = parsedImports[parsedImports.length - 1];
      await loadCatalogImports();
      if (latest) await loadCatalogRows(latest.id);
      onProductsImported();
      void loadReadiness();
      void loadEnrichmentStatus();
      const totalRows = parsedImports.reduce((sum, item) => sum + (item.row_count || 0), 0);
      const successMessage = `Imported ${importTotals.inserted.toLocaleString()} new and updated ${importTotals.updated.toLocaleString()} products from ${totalRows.toLocaleString()} parsed rows.`;
      if (failedImports.length === 0) {
        setCatalogFiles([]);
        setCatalogName("");
        setCatalogUploadResult({ tone: "success", message: successMessage });
        toast.success(successMessage);
      } else if (parsedImports.length > 0) {
        setCatalogFiles([]);
        setCatalogName("");
        setCatalogUploadResult({
          tone: "error",
          message: `${successMessage} ${failedImports.length.toLocaleString()} file${failedImports.length === 1 ? "" : "s"} need review: ${failedImports.join(" | ")}`,
        });
        toast.error(`${parsedImports.length.toLocaleString()} imported, ${failedImports.length.toLocaleString()} need review.`);
      } else {
        setCatalogUploadResult({
          tone: "error",
          message: `No products could be imported: ${failedImports.join(" | ")}`,
        });
        toast.error("No products could be imported from those files.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not upload catalog.";
      setCatalogUploadResult({ tone: "error", message });
      toast.error(message);
    } finally {
      setCatalogUploading(false);
      setCatalogCommitting(false);
      setCatalogUploadProgress(null);
    }
  };

  const commitCatalogImport = async (importId: number) => {
    setCatalogCommitting(true);
    try {
      const res = await fetch(`/api/suppliers/catalog-imports/${importId}/commit?include_duplicates=true`, {
        method: "POST",
      });
      const data: { inserted?: number; updated?: number; errors?: number; detail?: string } = await res.json();
      if (!res.ok) throw new Error(data.detail || "Catalog import failed.");
      await loadCatalogImports();
      await loadCatalogRows(importId);
      onProductsImported();
      void loadReadiness();
      void loadEnrichmentStatus();
      toast.success(`Imported ${(data.inserted || 0).toLocaleString()} new and updated ${(data.updated || 0).toLocaleString()} products.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not import catalog rows.");
    } finally {
      setCatalogCommitting(false);
    }
  };

  const retryCatalogImport = async (importId: number) => {
    setCatalogCommitting(true);
    setCatalogUploadResult({ tone: "info", message: "Retrying this stored catalog with the latest parser." });
    try {
      const retryRes = await fetch(`/api/suppliers/catalog-imports/${importId}/reprocess`, {
        method: "POST",
      });
      const retryData: (CatalogImport & { detail?: string }) = await retryRes.json();
      if (!retryRes.ok || retryData.status === "failed" || retryData.row_count === 0) {
        throw new Error(retryData.error_message || retryData.detail || "No product rows could be imported from this file.");
      }
      const commitRes = await fetch(`/api/suppliers/catalog-imports/${importId}/commit?include_duplicates=true`, {
        method: "POST",
      });
      const commitData: { inserted?: number; updated?: number; errors?: number; detail?: string } = await commitRes.json();
      if (!commitRes.ok) throw new Error(commitData.detail || "Catalog import failed.");
      await loadCatalogImports();
      await loadCatalogRows(importId);
      onProductsImported();
      void loadReadiness();
      void loadEnrichmentStatus();
      const message = `Imported ${(commitData.inserted || 0).toLocaleString()} new and updated ${(commitData.updated || 0).toLocaleString()} products.`;
      setCatalogUploadResult({ tone: "success", message });
      toast.success(message);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not retry catalog import.";
      setCatalogUploadResult({ tone: "error", message });
      toast.error(message);
    } finally {
      setCatalogCommitting(false);
    }
  };

  const startDetailBackfill = async (force = false) => {
    if (!hasCredentials) { toast.error("Add login credentials before backfilling."); return; }
    if (!isAllstateSupplier) {
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
      void loadReadiness();
      stopDetailBackfillPolling();
      detailBackfillPollRef.current = setInterval(() => { void pollDetailBackfillStatus(); }, 2000);
    } catch {
      setDetailBackfillRunning(false);
      toast.error("Could not start detail backfill");
    }
  };

  const runDetailBackfillUntilComplete = async () => {
    if (!hasCredentials) { toast.error("Add login credentials before backfilling."); return; }
    if (!isAllstateSupplier) {
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
      void loadReadiness();
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

  const retryFailedImages = async (scopeToSupplier = false) => {
    try {
      const scoped = scopeToSupplier === true;
      const url = scoped ? `/api/scraper/backfill-images/${supplier.id}` : "/api/scraper/backfill-images";
      const res = await fetch(url, { method: "POST" });
      const data: (ImageBackfillStatus & { detail?: string }) = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Could not start image retry");
      setImageBackfill(data);
      if (data.status === "running" && (data.supplier_id == null || data.supplier_id === supplier.id)) {
        setImageBackfillRunning(true);
        stopImageBackfillPolling();
        imageBackfillPollRef.current = setInterval(() => { void pollImageBackfillStatus(); }, 2000);
      }
      toast.success(scoped ? "Supplier photo storage started" : "Image retry started");
      void loadEnrichmentStatus();
      void loadReadiness();
    } catch (err) {
      setImageBackfillRunning(false);
      toast.error(err instanceof Error ? err.message : "Could not start image retry");
    }
  };

  const markPlaceholderImagesReviewed = async () => {
    if (!isAllstateSupplier) return;
    setPlaceholderReviewing(true);
    try {
      const res = await fetch(`/api/scraper/allstate-placeholder-images/${supplier.id}/mark-reviewed`, { method: "POST" });
      const data: { reviewed_count?: number; message?: string; detail?: string } = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || "Could not mark placeholders reviewed");
      toast.success(data.message || "Placeholder images marked reviewed");
      await loadReadiness();
      await loadEnrichmentStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not mark placeholders reviewed";
      toast.error(message);
    } finally {
      setPlaceholderReviewing(false);
    }
  };

  const phase = (job as ScrapeJobOut & { phase?: string })?.phase;
  const isRunning = status === "running" || status === "starting";
  const isImporting = importing || phase === "importing";
  const showMilestones = !!job && (isRunning || isImporting || phase === "discovering" || phase === "scraping" || phase === "importing");
  const productsFound = job?.products_found ?? 0;
  const productsImported = job?.products_imported ?? 0;
  const hasUnimportedProducts = productsFound > productsImported;
  const canImportOrResume = !!job && (
    (!!job.result_key && hasUnimportedProducts && (job.phase === "ready" || job.status === "done")) ||
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
        enrichmentStatus.images_resolved ?? enrichmentStatus.images_with_reference ?? enrichmentStatus.images_displayable ?? enrichmentStatus.images_stored,
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
  const displayablePhotoCount = enrichmentStatus
    ? (enrichmentStatus.images_with_reference ?? enrichmentStatus.images_displayable ?? enrichmentStatus.images_stored)
    : 0;
  const storedPhotoCount = enrichmentStatus?.images_stored ?? 0;
  const supplierHostedPhotoCount = enrichmentStatus?.images_external ?? 0;
  const imageStorageWorkCount = enrichmentStatus
    ? Math.max(
        0,
        supplierHostedPhotoCount +
          enrichmentStatus.images_failed +
          enrichmentStatus.images_pending +
          enrichmentStatus.images_missing,
      )
    : 0;
  const supplierDetailsReadyCount = enrichmentStatus ? Math.min(enrichmentStatus.detail_stored, enrichmentStatus.total_active) : 0;
  const imageBackfillAppliesToSupplier = !!imageBackfill && (imageBackfill.supplier_id == null || imageBackfill.supplier_id === supplier.id);
  const supplierImageBackfillRunning = imageBackfillRunning && imageBackfillAppliesToSupplier && imageBackfill?.status === "running";
  const imageBackfillPct = imageBackfill && imageBackfill.total > 0
    ? Math.min(100, Math.round((imageBackfill.done / imageBackfill.total) * 100))
    : 0;
  const vickermanSyncAppliesToSupplier = isVickermanSupplier && !!vickermanFullSync && (vickermanFullSync.supplier_id == null || vickermanFullSync.supplier_id === supplier.id);
  const vickermanBatch = vickermanSyncAppliesToSupplier ? vickermanFullSync?.current_batch || null : null;
  const vickermanBatchDone = Number(vickermanBatch?.queued_or_scraped ?? vickermanBatch?.scraped ?? 0);
  const vickermanBatchTotal = Number(vickermanBatch?.target ?? vickermanBatch?.limit ?? 0);
  const vickermanBatchPct = vickermanBatchTotal > 0 ? Math.min(100, Math.round((vickermanBatchDone / vickermanBatchTotal) * 100)) : 0;
  const vickermanBatchLabel = vickermanBatch?.batch_number
    ? `Batch ${vickermanBatch.batch_number}${vickermanFullSync?.max_batches ? ` of ${vickermanFullSync.max_batches}` : ""}`
    : "Current batch";
  const vickermanPhase = String(vickermanBatch?.phase || (vickermanFullSyncRunning ? "scraping" : vickermanFullSync?.status || "idle")).replace(/_/g, " ");
  const vickermanActiveCount = Math.max(
    vickermanFullSync?.total_active ?? 0,
    enrichmentStatus?.total_active ?? 0,
    readiness?.product_count ?? 0,
    supplier.product_count ?? 0,
  );
  const readinessAttentionSteps = readiness?.steps.filter((step) => step.status !== "done") ?? [];
  const readinessDoneSteps = readiness?.steps.filter((step) => step.status === "done") ?? [];
  const showSupplierImageStoragePanel = supportsReadiness && !isAllstateSupplier && !!enrichmentStatus && enrichmentStatus.total_active > 0;
  const selectedCatalogImport = catalogImports.find((item) => item.id === selectedCatalogImportId) || catalogImports[0] || null;
  const catalogCanCommit = !!selectedCatalogImport && selectedCatalogImport.status !== "committed" && selectedCatalogImport.status !== "committed_with_errors" && selectedCatalogImport.row_count > 0;
  const latestCatalogImport = catalogImports[0] || null;
  const successfulCatalogs = catalogImports.filter((item) => item.row_count > 0 && !item.status.includes("failed")).length;
  const failedCatalogs = catalogImports.filter((item) => item.status.includes("failed")).length;
  const catalogStatusLabel = latestCatalogImport
    ? latestCatalogImport.status.includes("failed")
      ? "Needs a better catalog file"
      : latestCatalogImport.status.includes("committed")
        ? "Imported to library"
        : "Ready to import"
    : "Waiting for catalog";
  const catalogStatusTone = latestCatalogImport
    ? latestCatalogImport.status.includes("failed")
      ? "text-rose-700 bg-rose-50 border-rose-100"
      : latestCatalogImport.status.includes("committed")
        ? "text-emerald-700 bg-emerald-50 border-emerald-100"
        : "text-amber-700 bg-amber-50 border-amber-100"
    : "text-stone-600 bg-stone-50 border-stone-200";
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
      <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-stone-800">Catalog data intake</p>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${catalogStatusTone}`}>
                {catalogStatusLabel}
              </span>
            </div>
            <p className="mt-1 max-w-2xl text-xs text-stone-500">
              Leaf & Ledger receives catalog data from supplier files, external scrape exports, PDFs, or cleaned spreadsheets, then standardizes it into the Product Library.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 md:min-w-[330px]">
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Products</p>
              <p className="text-sm font-semibold text-stone-800">{supplier.product_count.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Catalogs</p>
              <p className="text-sm font-semibold text-stone-800">{successfulCatalogs.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Needs review</p>
              <p className="text-sm font-semibold text-amber-700">{failedCatalogs.toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Credentials warning */}
      {showAdvancedTools && !hasCredentials && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
	          <div>
	            <p className="text-sm font-medium text-amber-800">Login credentials missing</p>
	            <p className="text-xs text-amber-700 mt-0.5">{missingCredentialDetail}</p>
	          </div>
	        </div>
	      )}

      {showAdvancedTools && credentialsFailed && (
        <div className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 md:flex-row md:items-start md:justify-between">
          <div className="flex items-start gap-3">
          <AlertTriangle size={15} className="text-red-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800">Login credentials failed</p>
            <p className="text-xs text-red-700 mt-0.5">
              {failedCredentialDetail} Click <strong>Edit credentials</strong>. {failedCredentialAction}
            </p>
          </div>
          </div>
          <button
            type="button"
            onClick={onEditCredentials}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100"
          >
            <Pencil size={12} /> Edit credentials
          </button>
        </div>
      )}

      {showAdvancedTools && credentialsUntested && !credentialsFailed && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800">Login credentials need testing</p>
            <p className="text-xs text-amber-700 mt-0.5">{untestedCredentialAction}</p>
          </div>
        </div>
      )}

      {showAdvancedTools && supportsReadiness && (
        <div className="rounded-xl border border-emerald-200 bg-white px-4 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold text-emerald-700">{supplier.name} readiness</p>
              {readiness ? (
                <>
                  <p className="mt-0.5 text-[11px] text-stone-600">
                    {readiness.fully_ready_count.toLocaleString()} of {readiness.product_count.toLocaleString()} products resolved
                    {readiness.product_count > 0 ? ` (${readiness.ready_percent}%).` : "."}
                  </p>
                  <p className="mt-1 text-xs font-semibold text-stone-800">
                    Next: {readiness.next_action}
                  </p>
                </>
              ) : (
                <p className="mt-0.5 text-[11px] text-stone-500">Checking configuration, catalog upload, photos, details, and builder use.</p>
              )}
              <p className="mt-0.5 text-[10px] text-stone-400">Updated {formatClock(readinessCheckedAt)}</p>
            </div>
            <button
              onClick={loadReadiness}
              className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-xs font-semibold text-stone-600 hover:bg-stone-100"
            >
              <RefreshCw size={12} /> Recheck
            </button>
          </div>
          {readiness && (
            <>
              {vickermanSyncAppliesToSupplier && (vickermanFullSyncRunning || vickermanFullSync?.status === "failed" || vickermanFullSync?.status === "stopping" || vickermanFullSync?.status === "stopped") && (
                <div className={`mt-3 rounded-xl border px-3 py-3 ${
                  vickermanFullSyncRunning
                    ? "border-sky-200 bg-sky-50"
                    : vickermanFullSync?.status === "failed"
                      ? "border-rose-200 bg-rose-50"
                      : "border-stone-200 bg-stone-50"
                }`}>
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        {vickermanFullSyncRunning ? (
                          <Loader2 size={14} className="animate-spin text-sky-700" />
                        ) : vickermanFullSync?.status === "failed" ? (
                          <XCircle size={14} className="text-rose-600" />
                        ) : (
                          <Circle size={14} className="text-stone-400" />
                        )}
                        <p className={`text-xs font-semibold ${vickermanFullSyncRunning ? "text-sky-800" : vickermanFullSync?.status === "failed" ? "text-rose-800" : "text-stone-700"}`}>
                          {vickermanFullSyncRunning ? "Vickerman full-catalog run is active" : `Vickerman runner ${vickermanFullSync?.status}`}
                        </p>
                      </div>
                      <p className="mt-1 text-[11px] text-stone-700">
                        {vickermanBatchLabel} · {vickermanPhase}
                        {vickermanFullSync?.current_job_id ? ` · job ${vickermanFullSync.current_job_id}` : ""}
                      </p>
                      {vickermanFullSync?.message && (
                        <p className="mt-0.5 text-[10px] text-stone-500">{vickermanFullSync.message}</p>
                      )}
                      {vickermanFullSync?.error && (
                        <p className="mt-0.5 text-[10px] font-semibold text-rose-700">{vickermanFullSync.error}</p>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:min-w-[420px]">
                      <div className="rounded-lg bg-white px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">This batch</p>
                        <p className="text-sm font-semibold text-stone-800">
                          {vickermanBatchTotal > 0 ? `${vickermanBatchDone.toLocaleString()} / ${vickermanBatchTotal.toLocaleString()}` : vickermanBatchDone.toLocaleString()}
                        </p>
                      </div>
                      <div className="rounded-lg bg-white px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Imported run</p>
                        <p className="text-sm font-semibold text-stone-800">{(vickermanFullSync?.total_imported ?? 0).toLocaleString()}</p>
                      </div>
                      <div className="rounded-lg bg-white px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Active products</p>
                        <p className="text-sm font-semibold text-stone-800">{vickermanActiveCount.toLocaleString()}</p>
                      </div>
                      <div className="rounded-lg bg-white px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Batches done</p>
                        <p className="text-sm font-semibold text-stone-800">
                          {(vickermanFullSync?.batches_run ?? 0).toLocaleString()}
                          {vickermanFullSync?.max_batches ? ` / ${vickermanFullSync.max_batches.toLocaleString()}` : ""}
                        </p>
                      </div>
                    </div>
                  </div>
                  {vickermanBatchTotal > 0 && (
                    <div className="mt-3">
                      <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wide text-sky-700">
                        <span>Current batch progress</span>
                        <span>{vickermanBatchPct}%</span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-sky-100">
                        <div
                          className="h-full rounded-full bg-sky-500 transition-all duration-500"
                          style={{ width: `${vickermanBatchPct}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-stone-100">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                  style={{ width: `${readiness.ready_percent}%` }}
                />
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
                <div className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Needs attention</p>
                  {readinessAttentionSteps.length > 0 ? (
                    <div className="mt-2 space-y-2">
                      {readinessAttentionSteps.map((step) => (
                        <div key={step.key} className={`rounded-lg border bg-white px-3 py-2 ${readinessTone(step.status)}`}>
                          <div className="flex items-center gap-2">
                            {readinessDot(step.status)}
                            <p className="text-xs font-semibold">{step.label}</p>
                          </div>
                          <p className="mt-1 text-[11px] leading-snug opacity-90">{step.detail}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 flex items-center gap-2 rounded-lg border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold text-emerald-700">
                      <CheckCircle2 size={14} /> No readiness blockers
                    </div>
                  )}
                </div>
                <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-600">Confirmed</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {readinessDoneSteps.length > 0 ? readinessDoneSteps.map((step) => (
                      <span key={step.key} className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-emerald-700">
                        <CheckCircle2 size={11} /> {step.label}
                      </span>
                    )) : (
                      <span className="text-[11px] text-emerald-700">Nothing confirmed yet.</span>
                    )}
                  </div>
                  <p className="mt-2 text-[11px] leading-snug text-emerald-700">
                    These are already green, so they stay quiet while the next action stays visible.
                  </p>
                </div>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                <div className="rounded-lg bg-stone-50 px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Categories</p>
                  <p className="text-sm font-semibold text-stone-800">
                    {readiness.selected_category_count.toLocaleString()}
                    <span className="ml-1 text-[10px] font-medium text-stone-400">
                      {readiness.selected_category_mode === "all" ? "all" : readiness.selected_category_mode}
                    </span>
                  </p>
                </div>
                <div className="rounded-lg bg-stone-50 px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">
                    {readiness.product_count > 0 ? "Unique products" : "Estimated upload"}
                  </p>
                  <p className="text-sm font-semibold text-stone-800">
                    {(readiness.product_count > 0 ? readiness.product_count : readiness.estimated_selected_products).toLocaleString()}
                  </p>
                </div>
                <div className="rounded-lg bg-stone-50 px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Displayable photos</p>
                  <p className="text-sm font-semibold text-stone-800">{readiness.photo_ready_count.toLocaleString()}</p>
                </div>
                <div className="rounded-lg bg-stone-50 px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Stored photos</p>
                  <p className="text-sm font-semibold text-stone-800">
                    {readiness.internal_photo_count.toLocaleString()}
                    <span className="ml-1 text-[10px] font-medium text-stone-400">{readiness.storage_percent}%</span>
                  </p>
                </div>
                <div className="rounded-lg bg-stone-50 px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Builder lines</p>
                  <p className="text-sm font-semibold text-stone-800">{readiness.builder_item_count.toLocaleString()}</p>
                </div>
                {readiness.supplier_hosted_photo_count > 0 && (
                  <div className="rounded-lg bg-amber-50 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-500">Supplier fallbacks</p>
                    <p className="text-sm font-semibold text-amber-700">{readiness.supplier_hosted_photo_count.toLocaleString()}</p>
                  </div>
                )}
                {readiness.placeholder_image_count > 0 && (
                  <div className="rounded-lg bg-stone-50 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Placeholders</p>
                    <p className="text-sm font-semibold text-stone-800">{readiness.placeholder_image_count.toLocaleString()}</p>
                  </div>
                )}
                {readiness.retryable_image_problem_count > 0 && (
                  <div className="rounded-lg bg-rose-50 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-rose-500">Retryable images</p>
                    <p className="text-sm font-semibold text-rose-700">{readiness.retryable_image_problem_count.toLocaleString()}</p>
                  </div>
                )}
              </div>
              {readiness.image_problem_samples.length > 0 && (
                <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-600">Image review samples</p>
                    {isAllstateSupplier && readiness.placeholder_image_count > 0 && readiness.retryable_image_problem_count === 0 && (
                      <button
                        onClick={markPlaceholderImagesReviewed}
                        disabled={placeholderReviewing}
                        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-amber-700 px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-amber-800 disabled:opacity-60"
                      >
                        {placeholderReviewing ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                        Mark placeholders reviewed
                      </button>
                    )}
                  </div>
                  <div className="mt-1 grid gap-1.5">
                    {readiness.image_problem_samples.map((product) => (
                      <div key={`${product.product_id}-${product.supplier_sku}`} className="flex items-center justify-between gap-3 text-[11px] text-amber-800">
                        <span className="min-w-0 truncate">
                          <span className="font-mono font-semibold">{product.supplier_sku || `#${product.product_id}`}</span>
                          <span className="mx-1 text-amber-500">·</span>
                          <span>{product.name || "Unnamed product"}</span>
                        </span>
                        <span className="shrink-0 rounded-full bg-white px-2 py-0.5 font-medium text-amber-700">
                          {product.problem_type === "placeholder"
                            ? "placeholder"
                            : product.image_status || (product.photo_url?.startsWith("http") ? "supplier-hosted" : "retry")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {showAdvancedTools && isAllstateSupplier && (
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
                {!!enrichmentStatus.images_no_supplier_image && (
                  <p className="mt-0.5 text-[10px] text-stone-500">
                    {enrichmentStatus.images_no_supplier_image.toLocaleString()} marked no supplier image
                  </p>
                )}
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

      {showAdvancedTools && showSupplierImageStoragePanel && enrichmentStatus && (
        <div className="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold text-teal-700">Finish catalog photo storage</p>
              <p className="mt-0.5 text-[11px] text-teal-700">
                {readyCount.toLocaleString()} of {enrichmentStatus.total_active.toLocaleString()} products have displayable photos and details
                {" "}({readyDisplayPct}%).
              </p>
              <p className="mt-0.5 text-[10px] text-teal-600">
                {supplierDetailsReadyCount.toLocaleString()} detail payloads captured during scrape; {storedPhotoCount.toLocaleString()} photos stored internally.
              </p>
              {imageStorageWorkCount > 0 ? (
                <p className="mt-0.5 text-[10px] text-teal-600">
                  {supplierHostedPhotoCount.toLocaleString()} supplier-hosted photos can be copied into Leaf & Ledger storage.
                </p>
              ) : (
                <p className="mt-0.5 text-[10px] text-teal-600">Photo storage is current for imported products.</p>
              )}
              {supplierImageBackfillRunning && imageBackfill && (
                <p className="mt-0.5 text-[10px] text-teal-600">
                  Storing photos now: {imageBackfill.done.toLocaleString()} of {imageBackfill.total.toLocaleString()} checked.
                </p>
              )}
              {imageBackfillAppliesToSupplier && imageBackfill?.error && (
                <p className="mt-0.5 text-[10px] text-red-500">{imageBackfill.error}</p>
              )}
            </div>
            {imageStorageWorkCount > 0 ? (
              <button
                onClick={() => retryFailedImages(true)}
                disabled={supplierImageBackfillRunning}
                className="flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-teal-800"
              >
                {supplierImageBackfillRunning ? (
                  <><Loader2 size={14} className="animate-spin" /> Storing photos…</>
                ) : (
                  <><RefreshCw size={14} /> Store supplier photos</>
                )}
              </button>
            ) : (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm font-semibold text-emerald-700">
                <CheckCircle2 size={14} /> Photos stored
              </div>
            )}
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Details captured</p>
              <p className="text-sm font-semibold text-stone-800">
                {supplierDetailsReadyCount.toLocaleString()} / {enrichmentStatus.total_active.toLocaleString()}
              </p>
            </div>
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Photos available</p>
              <p className="text-sm font-semibold text-stone-800">{displayablePhotoCount.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Stored internally</p>
              <p className="text-sm font-semibold text-stone-800">{storedPhotoCount.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Supplier-hosted</p>
              <p className="text-sm font-semibold text-amber-700">{supplierHostedPhotoCount.toLocaleString()}</p>
            </div>
          </div>
          {supplierImageBackfillRunning && imageBackfill && imageBackfill.total > 0 && (
            <div className="mt-3">
              <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wide text-teal-700">
                <span>Photo storage</span>
                <span>{imageBackfillPct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-teal-100">
                <div
                  className="h-full rounded-full bg-teal-500 transition-all duration-500"
                  style={{ width: `${imageBackfillPct}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Fallback portal extraction button */}
      {showAdvancedTools && (
      <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-stone-700">Fallback portal extraction</p>
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
              disabled={!hasCredentials || credentialsNeedValidation || isRunning || isImporting}
            />
          </label>
          {/* Configure Portal — opens the wizard */}
          <button
            onClick={() => setCatalogWizardOpen(true)}
            disabled={!hasCredentials}
            title={hasCredentials ? "Choose which supplier portal categories to extract" : "Add credentials first"}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-stone-600 border border-stone-200 rounded-lg hover:bg-stone-100 bg-white disabled:opacity-40 transition-colors"
          >
            <BookOpen size={12} /> Configure Portal
          </button>
          <button
            onClick={startScrape}
            disabled={!hasCredentials || credentialsNeedValidation || isRunning || isImporting}
            title={credentialsFailed ? failedCredentialAction : credentialsUntested ? untestedCredentialAction : hasCredentials ? "Run portal extraction for this supplier" : "Add credentials first"}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-50 hover:opacity-90 transition-colors"
            style={{ backgroundColor: "#2d5a33" }}
          >
            {isRunning ? (
              <><Loader2 size={14} className="animate-spin" /> Extracting…</>
            ) : (
              <><RefreshCw size={14} /> {job?.status === "done" ? "Update From Portal" : "Extract From Portal"}</>
            )}
          </button>
        </div>
      </div>
      )}

      <div className="rounded-xl border border-emerald-200 bg-white px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
              <FileUp size={13} /> Upload catalog data
            </p>
            <p className="mt-0.5 text-[11px] text-stone-500">
              Upload the spreadsheet/export that came from a supplier, scraper, PDF parser, or manual cleanup. Leaf & Ledger organizes it after the data is already extracted.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white transition-colors ${
              catalogUploading ? "cursor-not-allowed bg-emerald-500 opacity-70" : "cursor-pointer bg-emerald-700 hover:bg-emerald-800"
            }`}>
              {catalogUploading ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
              {catalogUploading ? "Importing data..." : "Upload catalog data"}
              <input
                type="file"
                accept=".csv,.xlsx,.xlsm,.pdf"
                multiple
                disabled={catalogUploading}
                className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  e.currentTarget.value = "";
                  if (files.length === 0) return;
                  void uploadCatalogFiles(files);
                }}
              />
            </label>
          </div>
        </div>
        {catalogUploadProgress && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-[11px] font-semibold text-emerald-800">
            <Loader2 size={12} className="animate-spin" />
            {catalogUploadProgress}
          </div>
        )}
        {catalogFiles.length > 0 && (
          <div className="mt-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Selected files</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {catalogFiles.map((file) => (
                <span key={`${file.name}-${file.lastModified}`} className="max-w-full truncate rounded-md border border-stone-200 bg-white px-2 py-1 text-[11px] font-medium text-stone-700">
                  {file.name}
                </span>
              ))}
            </div>
          </div>
        )}
        {catalogUploadResult && !catalogUploadProgress && (
          <div className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-[11px] font-semibold ${
            catalogUploadResult.tone === "error"
              ? "border-rose-100 bg-rose-50 text-rose-700"
              : catalogUploadResult.tone === "success"
                ? "border-emerald-100 bg-emerald-50 text-emerald-800"
                : "border-sky-100 bg-sky-50 text-sky-700"
          }`}>
            {catalogUploadResult.tone === "error" ? <AlertTriangle size={12} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={12} className="mt-0.5 shrink-0" />}
            <span>{catalogUploadResult.message}</span>
          </div>
        )}

        <div className="mt-3 flex flex-col gap-2 border-t border-stone-100 pt-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[11px] text-stone-500">
            Portal extraction is a fallback for suppliers that cannot provide a usable file or scrape export. The preferred path is a clean spreadsheet into Product Library.
          </p>
          <button
            type="button"
            onClick={() => setShowAdvancedTools((value) => !value)}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-xs font-semibold text-stone-600 transition-colors hover:bg-stone-100"
          >
            {showAdvancedTools ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {showAdvancedTools ? "Hide fallback extraction tools" : "Fallback extraction tools"}
          </button>
        </div>

        {catalogImports.length > 0 && (
          <div className="mt-3 grid gap-3 lg:grid-cols-[260px_1fr]">
            <div className="space-y-2">
              {catalogImports.slice(0, 4).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => loadCatalogRows(item.id)}
                  className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                    selectedCatalogImport?.id === item.id
                      ? "border-emerald-300 bg-emerald-50"
                      : "border-stone-200 bg-stone-50 hover:bg-stone-100"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="min-w-0 truncate text-xs font-semibold text-stone-800">{item.catalog_name}</p>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      item.status.includes("failed") ? "bg-rose-100 text-rose-700" :
                      item.status.includes("committed") ? "bg-emerald-100 text-emerald-700" :
                      "bg-amber-100 text-amber-700"
                    }`}>
                      {item.status.replace(/_/g, " ")}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-stone-500">
                    {item.row_count.toLocaleString()} rows · {item.duplicate_count.toLocaleString()} matches
                  </p>
                </button>
              ))}
            </div>

            <div className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-3">
              {selectedCatalogImport ? (
                <>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold text-stone-800">{selectedCatalogImport.catalog_name}</p>
                      <p className="mt-0.5 text-[11px] text-stone-500">
                        {selectedCatalogImport.original_filename} · {selectedCatalogImport.row_count.toLocaleString()} parsed rows
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <span className="rounded-lg bg-white px-2 py-1 text-[11px] font-semibold text-stone-700">
                        {selectedCatalogImport.staged_count.toLocaleString()} new
                      </span>
                      <span className="rounded-lg bg-white px-2 py-1 text-[11px] font-semibold text-stone-700">
                        {selectedCatalogImport.duplicate_count.toLocaleString()} updates
                      </span>
                      {selectedCatalogImport.status.includes("failed") ? (
                        <button
                          type="button"
                          onClick={() => retryCatalogImport(selectedCatalogImport.id)}
                          disabled={catalogCommitting}
                          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
                        >
                          {catalogCommitting ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                          Retry with latest parser
                        </button>
                      ) : catalogCanCommit ? (
                        <button
                          type="button"
                          onClick={() => commitCatalogImport(selectedCatalogImport.id)}
                          disabled={catalogCommitting}
                          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-stone-800 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-stone-900 disabled:opacity-50"
                        >
                          {catalogCommitting ? <Loader2 size={12} className="animate-spin" /> : <Database size={12} />}
                          Finish import
                        </button>
                      ) : selectedCatalogImport.status.includes("committed") ? (
                        <span className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-emerald-100 bg-white px-3 py-1.5 text-[11px] font-semibold text-emerald-700">
                          <CheckCircle2 size={12} /> In Product Library
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {selectedCatalogImport.error_message && (
                    <p className="mt-2 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2 text-[11px] font-semibold text-rose-700">
                      {selectedCatalogImport.error_message}
                    </p>
                  )}

                  {selectedCatalogImport.row_count > 0 ? (
                    <div className="mt-3 overflow-hidden rounded-lg border border-stone-200 bg-white">
                      <div className="grid grid-cols-[90px_1fr_80px_70px_80px] gap-2 border-b border-stone-100 px-3 py-2 text-[10px] font-semibold uppercase text-stone-400">
                        <span>SKU</span>
                        <span>Name</span>
                        <span>Price</span>
                        <span>MOQ</span>
                        <span>Status</span>
                      </div>
                      {catalogRows.length > 0 ? catalogRows.map((row) => (
                        <div key={row.id} className="grid grid-cols-[90px_1fr_80px_70px_80px] gap-2 border-b border-stone-100 px-3 py-2 text-[11px] last:border-b-0">
                          <span className="truncate font-mono font-semibold text-stone-700">{row.supplier_sku}</span>
                          <span className="truncate text-stone-700">{row.name}</span>
                          <span className="text-stone-600">{row.current_price != null ? `$${row.current_price.toFixed(2)}` : "—"}</span>
                          <span className="text-stone-600">{row.moq ?? "—"}</span>
                          <span className="truncate text-stone-500">{row.status}</span>
                        </div>
                      )) : (
                        <button
                          type="button"
                          onClick={() => loadCatalogRows(selectedCatalogImport.id)}
                          className="w-full px-3 py-6 text-center text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
                        >
                          Load row preview
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-lg border border-stone-200 bg-white px-3 py-3">
                      <p className="text-xs font-semibold text-stone-700">No product rows found by the current parser</p>
                      <p className="mt-1 text-[11px] text-stone-500">
                        Try the latest parser again after updates. If it still finds no rows, this file may need an AI/OCR pass or a supplier CSV.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-stone-500">No catalog file has been parsed for this supplier yet.</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Catalog Wizard Modal */}
      {showAdvancedTools && catalogWizardOpen && (
        <CatalogWizard
          supplierId={supplier.id}
          supplierName={supplier.name}
          onClose={() => setCatalogWizardOpen(false)}
          onSaved={() => {
            void loadReadiness();
            onProductsImported();
          }}
        />
      )}

      {/* ── Milestone checklist panel ────────────────────────────────────── */}
      {showAdvancedTools && showMilestones && (
        <MilestonePanel
          job={job}
          isRunning={isRunning}
          isImporting={isImporting}
          elapsed={elapsed}
        />
      )}

      {/* ── Import action (phase ready) ── */}
      {/* Show the already-imported success card if the job is done with products imported and no in-memory result yet */}
      {showAdvancedTools && job?.phase === "done" && job?.status === "done" && (job?.products_imported ?? 0) > 0 && !importResult && (
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

      {showAdvancedTools && staleReadyImport && !importResult && (
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

      {showAdvancedTools && showImportAction && !importResult && (
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
      {showAdvancedTools && importResult && (
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
      {showAdvancedTools && showImportAction && showPreview && preview.length > 0 && (
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
  const credentialStatus = (supplier.credential_status || "").toLowerCase();
  const credentialsNeedValidation = credentialStatus === "failed" || credentialStatus === "error" || credentialStatus === "untested";
  const priceSyncDisabledReason = credentialStatus === "untested"
    ? "Test credentials with Configure Catalog first"
    : "Fix credentials before syncing prices";

  const handleSync = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!hasCredentials) {
      toast.error("Add login credentials before syncing prices.");
      return;
    }
    if (credentialsNeedValidation) {
      toast.error(priceSyncDisabledReason);
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
        disabled={syncing || !hasCredentials || credentialsNeedValidation}
        title={!hasCredentials ? "Add credentials to enable price sync" : credentialsNeedValidation ? priceSyncDisabledReason : "Sync prices only (fast)"}
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
  const credentialStatus = (supplier.credential_status || "").toLowerCase();
  const credentialsFailed = credentialStatus === "failed" || credentialStatus === "error";
  const credentialsUntested = credentialStatus === "untested";

  return (
    <div className={`bg-white rounded-xl border transition-all ${
      expanded ? "border-emerald-200 shadow-sm" : "border-stone-200"
    }`}>
      {/* Card header row */}
      <div
        className="flex flex-col gap-3 px-5 py-4 cursor-pointer md:flex-row md:items-center"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: "#e8f0e8" }}>
            <Building2 size={18} className="text-emerald-700" strokeWidth={1.5} />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="min-w-0 break-words font-semibold text-stone-800 text-sm">{supplier.name}</p>
              {supplier.login_url && (
                <a href={supplier.login_url} target="_blank" rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 text-stone-300 hover:text-emerald-600 transition-colors">
                  <ExternalLink size={12} />
                </a>
              )}
              {/* Credentials badge */}
              {credentialsFailed ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-red-700 bg-red-50 border border-red-100 px-1.5 py-0.5 rounded-full"><AlertTriangle size={9} /> Credentials failed</span>
              ) : credentialsUntested ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded-full"><AlertTriangle size={9} /> Credentials untested</span>
              ) : hasCredentials ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 px-1.5 py-0.5 rounded-full"><KeyRound size={9} /> Credentials saved</span>
              ) : (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded-full"><AlertTriangle size={9} /> No credentials</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5 text-xs text-stone-400">
              {supplier.contact_name && <span>{supplier.contact_name}</span>}
              {supplier.contact_email && <span className="break-all">{supplier.contact_email}</span>}
              {supplier.contact_phone && <span>{supplier.contact_phone}</span>}
            </div>
          </div>
        </div>

        <div className="flex w-full flex-wrap items-center justify-between gap-3 pl-[52px] md:w-auto md:flex-nowrap md:justify-end md:pl-0">
          {/* Product count */}
          <div className="text-left md:text-right flex-shrink-0">
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
      </div>

      {/* Expandable scraper panel */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-stone-100">
          <ScraperPanel
            supplier={supplier}
            onProductsImported={onProductsImported}
            onEditCredentials={onEdit}
          />
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

// ── Main Page ────────────────────────────────────────────────────────────────
export default function Suppliers() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
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

  return (
    <Layout>
      {/* Page header */}
      <header className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200" style={{ backgroundColor: "#f7f4ef" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Suppliers</h1>
          <p className="text-xs text-stone-500 mt-0.5">
            {loading && suppliers.length === 0
              ? "Checking suppliers..."
              : `${suppliers.length} supplier${suppliers.length !== 1 ? "s" : ""} · Click a row to sync its product catalog`}
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
