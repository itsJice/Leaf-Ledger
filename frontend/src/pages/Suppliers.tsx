import { apiFetch } from "utils/apiFetch";
import React, { useEffect, useState, useRef, useCallback } from "react";
import {
  Plus, Pencil, Trash2, X, ExternalLink, Building2, RefreshCw,
  CheckCircle2, XCircle, Loader2, Eye, EyeOff, Download, AlertTriangle,
  KeyRound, ChevronDown, ChevronUp, Package, ArrowRight, RefreshCcw,
  Circle, BookOpen, FileUp, Database, Copy, Check,
} from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { toast } from "sonner";

type Supplier = {
  id: number;
  name: string;
  login_url?: string;
  login_username?: string;
  login_password?: string;
  has_credentials?: boolean;
  credential_status?: string | null;
  scraper_key?: string | null;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  notes?: string;
  product_count: number;
  last_price_synced_at?: string | null;
  last_full_sync_at?: string | null;
  created_at: string;
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
  const [revealed, setRevealed] = useState(false);
  const [creds, setCreds] = useState<{ login_username?: string | null; login_password?: string | null } | null>(null);
  const [loadingCreds, setLoadingCreds] = useState(false);
  const [copied, setCopied] = useState<"user" | "pass" | null>(null);

  const hasCredentials = !!(supplier.has_credentials || (supplier.login_username && supplier.login_password));
  const username = creds?.login_username ?? supplier.login_username ?? "";
  const password = creds?.login_password ?? "";

  const loadCreds = async () => {
    if (creds || loadingCreds) return creds;
    setLoadingCreds(true);
    try {
      const res = await apiFetch(`/api/suppliers/${supplier.id}/credentials`, { credentials: "include" });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      setCreds(data);
      return data;
    } catch {
      toast.error("Couldn't load saved credentials");
      return null;
    } finally {
      setLoadingCreds(false);
    }
  };

  const toggleReveal = async () => {
    if (!revealed) await loadCreds();
    setRevealed((v) => !v);
  };

  const copy = async (text: string, which: "user" | "pass") => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied((c) => (c === which ? null : c)), 1200);
    } catch {
      toast.error("Copy failed");
    }
  };

  const copyPassword = async () => {
    const data = creds ?? (await loadCreds());
    const pw = data?.login_password || "";
    if (!pw) { toast.error("No password saved"); return; }
    await copy(pw, "pass");
  };

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
              {hasCredentials ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 px-1.5 py-0.5 rounded-full"><KeyRound size={9} /> Login saved</span>
              ) : (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-stone-500 bg-stone-50 border border-stone-200 px-1.5 py-0.5 rounded-full">No login</span>
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

          {/* Visit supplier site */}
          {supplier.login_url && (
            <a href={supplier.login_url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
              className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-stone-200 bg-white text-stone-600 hover:border-emerald-300 hover:text-emerald-700 transition-all">
              <ExternalLink size={12} /> Visit
            </a>
          )}

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

      {/* Expandable credentials reference */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-stone-100 pt-4 space-y-3">
          {/* Site link */}
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Supplier site / login</p>
              {supplier.login_url ? (
                <a href={supplier.login_url} target="_blank" rel="noopener noreferrer" className="text-sm text-emerald-700 hover:underline break-all">{supplier.login_url}</a>
              ) : (
                <p className="text-sm text-stone-400">No link saved — add one via Edit.</p>
              )}
            </div>
            {supplier.login_url && (
              <a href={supplier.login_url} target="_blank" rel="noopener noreferrer" className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 text-stone-600 hover:border-emerald-300 hover:text-emerald-700"><ExternalLink size={12} /> Open</a>
            )}
          </div>

          {hasCredentials ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {/* Username */}
              <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Username</p>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <span className="font-mono text-sm text-stone-800 break-all">{username || "—"}</span>
                  <button onClick={() => copy(username, "user")} disabled={!username} title="Copy username"
                    className="shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-md border border-stone-200 bg-white text-stone-500 hover:text-emerald-700 hover:border-emerald-300 disabled:opacity-40">
                    {copied === "user" ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                  </button>
                </div>
              </div>
              {/* Password */}
              <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Password</p>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <span className="font-mono text-sm text-stone-800 break-all">
                    {loadingCreds ? "…" : revealed ? (password || "—") : "••••••••"}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <button onClick={toggleReveal} title={revealed ? "Hide password" : "Show password"}
                      className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-stone-200 bg-white text-stone-500 hover:text-emerald-700 hover:border-emerald-300">
                      {revealed ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                    <button onClick={copyPassword} title="Copy password"
                      className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-stone-200 bg-white text-stone-500 hover:text-emerald-700 hover:border-emerald-300">
                      {copied === "pass" ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
              <p className="text-sm text-stone-500">No login credentials saved for this supplier.</p>
              <button onClick={onEdit} className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 text-stone-600 hover:border-emerald-300 hover:text-emerald-700"><Pencil size={12} /> Add login</button>
            </div>
          )}

          <div className="flex justify-end">
            <button onClick={onEdit} className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 hover:text-emerald-700"><Pencil size={11} /> Edit supplier &amp; credentials</button>
          </div>
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
      const res = await apiFetch("/api/suppliers/list", {
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
              : `${suppliers.length} supplier${suppliers.length !== 1 ? "s" : ""} · Click a supplier for its site link & login`}
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
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed mb-4">Add your first supplier to keep its site link and login credentials handy.</p>
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
