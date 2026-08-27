import { apiFetch } from "utils/apiFetch";

// Shared, cross-page cache of the supplier directory (id, login_url,
// has_credentials, ...). Several pages show a supplier's saved login from
// here (Catalog Search / Library's "Log in" helper today; anything built
// the same way tomorrow) without each one re-fetching the whole list.
//
// The cache used to live inline in Library.tsx, fetched once and kept for
// the rest of the tab's life with no way to invalidate it. That meant
// saving a supplier's credentials on the Suppliers page "worked" -- the
// database write succeeded -- but every OTHER already-open page kept
// showing the stale answer (no login saved) until a full reload, which
// read as the password not really saving. Moving the cache here and
// invalidating it on every supplier save (see SUPPLIER_CREDENTIALS_CHANGED_EVENT)
// is the fix: one cache, one place that can tell it to forget itself.
export interface SupplierLoginInfo {
  id: number;
  name?: string;
  login_url?: string;
  has_credentials?: boolean;
  login_username?: string;
}

export const SUPPLIER_CREDENTIALS_CHANGED_EVENT = "leaf-ledger-supplier-credentials-changed";

let _supplierDirCache: Promise<Record<number, SupplierLoginInfo>> | null = null;

export function loadSupplierDirectory(): Promise<Record<number, SupplierLoginInfo>> {
  if (!_supplierDirCache) {
    _supplierDirCache = apiFetch("/api/suppliers/list", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: SupplierLoginInfo[]) => Object.fromEntries((rows || []).map((s) => [s.id, s])))
      .catch(() => ({}));
  }
  return _supplierDirCache;
}

export function invalidateSupplierDirectory() {
  _supplierDirCache = null;
}

if (typeof window !== "undefined") {
  window.addEventListener(SUPPLIER_CREDENTIALS_CHANGED_EVENT, invalidateSupplierDirectory);
}
