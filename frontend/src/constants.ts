export enum Mode {
  DEV = "development",
  PROD = "production",
}

interface WithEnvMode {
  readonly env: {
    readonly MODE: Mode;
  };
}

export const mode = (import.meta as unknown as WithEnvMode).env.MODE;

declare const __API_PATH__: string;
export const API_PATH = __API_PATH__;

declare const __API_URL__: string;
export const API_URL = __API_URL__;

declare const __API_HOST__: string;
export const API_HOST = __API_HOST__;

declare const __API_PREFIX_PATH__: string;
export const API_PREFIX_PATH = __API_PREFIX_PATH__;

declare const __WS_API_URL__: string;
export const WS_API_URL = __WS_API_URL__;

declare const __APP_BASE_PATH__: string;
export const APP_BASE_PATH = __APP_BASE_PATH__;


// ─── localStorage keys shared by more than one file ──────────────────────────
// Changing a value orphans every user's existing cache. Bump the version suffix
// only on purpose.

/** Dashboard cache read/written by pages/App.tsx. Layout.tsx still writes a dead ":v1" copy that nothing reads. */
export const DASHBOARD_CACHE_KEY = "leaf-ledger:dashboard-cache:v2";
/** Projects list: pages/Arrangements.tsx and components/Layout.tsx. */
export const PROJECTS_LIST_CACHE_KEY = "leaf-ledger:projects-list-cache:v1";
/** Catalog library: pages/Library.tsx and pages/Favorites.tsx. */
export const LIBRARY_CACHE_KEY = "leaf-ledger:library-cache:v1";
/** Clients page: pages/Clients.tsx and components/Layout.tsx. */
export const CLIENTS_PAGE_CACHE_KEY = "leaf-ledger:clients-page-cache:v1";
/** Editable build templates: pages/Settings.tsx and pages/Arrangements.tsx. */
export const BUILD_TEMPLATE_STORAGE_KEY = "leaf-ledger:build-templates:v1";
/** Active purchase order id: utils/orders.ts and pages/Sourcing.tsx. */
export const ACTIVE_ORDER_KEY = "leaf-ledger:active-order:v1";
