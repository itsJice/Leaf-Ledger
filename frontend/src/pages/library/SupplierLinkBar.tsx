// Supplier product-page link + saved-login helper for the product detail
// modal. Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useEffect, useState } from "react";
import { ExternalLink, LogIn, Eye, EyeOff, Copy, Check } from "lucide-react";
import { apiFetch } from "utils/apiFetch";
import { loadSupplierDirectory, type SupplierLoginInfo } from "utils/supplierDirectory";

// ── Supplier link + login helper ───────────────────────────────────────────
// The directory cache itself (and its invalidation) lives in
// utils/supplierDirectory -- shared with anywhere else that needs to show a
// supplier's saved login, so a credentials save on the Suppliers page is
// visible here without a reload. See that file for why.

function CopyChip({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); })}
      className="inline-flex items-center gap-1 rounded-md border border-stone-200 px-2 py-1 text-[11px] font-medium text-stone-500 hover:border-emerald-300 hover:text-emerald-700"
      title="Copy"
    >
      {copied ? <Check size={11} /> : <Copy size={11} />} {copied ? "Copied" : "Copy"}
    </button>
  );
}

// Direct link to the product on the supplier's own site, plus a login helper.
// True silent auto-login to third-party sites isn't possible from a web app
// (cross-origin session cookies can't be set), so we open the vendor's login
// page and surface the saved username/password to paste — one-click-ish, safe.
export function SupplierLinkBar({ supplierId, supplierName, productUrl }: { supplierId?: number; supplierName?: string; productUrl?: string }) {
  const [info, setInfo] = useState<SupplierLoginInfo | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [creds, setCreds] = useState<{ login_username?: string; login_password?: string } | null>(null);
  const [revealPw, setRevealPw] = useState(false);
  const [loadingCreds, setLoadingCreds] = useState(false);

  useEffect(() => {
    let alive = true;
    if (supplierId != null) loadSupplierDirectory().then((dir) => { if (alive) setInfo(dir[supplierId] || null); });
    return () => { alive = false; };
  }, [supplierId]);

  const loginUrl = info?.login_url;
  const hasCreds = !!info?.has_credentials;
  const label = supplierName || "supplier site";

  const toggleLogin = () => {
    if (supplierId != null && !creds && hasCreds) {
      setLoadingCreds(true);
      apiFetch(`/api/suppliers/${supplierId}/credentials`, { credentials: "include" })
        .then((r) => (r.ok ? r.json() : null)).then(setCreds).catch(() => {}).finally(() => setLoadingCreds(false));
    }
    setShowLogin((v) => !v);
  };

  if (!productUrl && !loginUrl && !hasCreds) return null;
  return (
    <div className="border-b border-stone-100 bg-emerald-50/40 px-5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        {productUrl && (
          <a href={productUrl} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800">
            <ExternalLink size={14} /> View on {label}
          </a>
        )}
        {(loginUrl || hasCreds) && (
          <button type="button" onClick={toggleLogin}
            className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700">
            <LogIn size={14} /> {showLogin ? "Hide login" : "Log in"}
          </button>
        )}
      </div>
      {showLogin && (
        <div className="mt-3 rounded-lg border border-stone-200 bg-white p-3">
          <p className="mb-2 text-xs leading-relaxed text-stone-500">
            For security, sites can't be logged into automatically. Open the login page, paste your saved credentials,
            then click <span className="font-medium">View on {label}</span> — the product opens in your logged-in session.
          </p>
          {loginUrl && (
            <a href={loginUrl} target="_blank" rel="noopener noreferrer"
              className="mb-3 inline-flex items-center gap-1.5 rounded-md border border-stone-200 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:border-emerald-300">
              <ExternalLink size={12} /> Open {label} login
            </a>
          )}
          {loadingCreds ? (
            <p className="text-xs text-stone-400">Loading credentials…</p>
          ) : hasCreds && creds ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="w-20 shrink-0 text-[11px] uppercase tracking-wide text-stone-400">Username</span>
                <code className="flex-1 truncate rounded bg-stone-50 px-2 py-1 text-xs text-stone-700">{creds.login_username || "—"}</code>
                {creds.login_username && <CopyChip value={creds.login_username} />}
              </div>
              <div className="flex items-center gap-2">
                <span className="w-20 shrink-0 text-[11px] uppercase tracking-wide text-stone-400">Password</span>
                <code className="flex-1 truncate rounded bg-stone-50 px-2 py-1 text-xs text-stone-700">
                  {revealPw ? (creds.login_password || "—") : "•".repeat((creds.login_password || "").length || 8)}
                </code>
                <button type="button" onClick={() => setRevealPw((v) => !v)} className="rounded-md border border-stone-200 p-1 text-stone-400 hover:text-stone-700" title={revealPw ? "Hide" : "Show"}>
                  {revealPw ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
                {creds.login_password && <CopyChip value={creds.login_password} />}
              </div>
            </div>
          ) : (
            <p className="text-xs text-stone-400">No saved credentials for this supplier — add them on the Suppliers page.</p>
          )}
        </div>
      )}
    </div>
  );
}
