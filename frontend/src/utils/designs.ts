import { apiFetch } from "utils/apiFetch";

// Typed client for the Designs API (`/api/designs/*`).
//
// The endpoint is built in parallel with this page, so every helper here is
// written to degrade to an empty result rather than throw: a 404/500/HTML
// response must render the page's empty state, never a crash or a spinner that
// never resolves.

export interface DesignFacet {
  value: string;
  count: number;
}

export interface DesignFacets {
  clients: DesignFacet[];
  projects: DesignFacet[];
  groups: DesignFacet[];
  build_types: DesignFacet[];
  materials: DesignFacet[];
}

export const EMPTY_FACETS: DesignFacets = {
  clients: [],
  projects: [],
  groups: [],
  build_types: [],
  materials: [],
};

export interface Design {
  id: number | string;
  name: string;
  build_type?: string | null;
  status?: string | null;
  client_name?: string | null;
  project_id?: number | string | null;
  project_name?: string | null;
  group_id?: number | string | null;
  group_name?: string | null;
  item_count?: number | null;
  total_cost?: number | null;
  hero_image_url?: string | null;
  materials?: string[] | null;
  updated_at?: string | null;
}

export interface DesignItem {
  id?: number | string;
  name?: string;
  quantity?: number | null;
  unit_cost?: number | null;
  total_cost?: number | null;
  image_url?: string | null;
  [key: string]: unknown;
}

export interface DesignDetail extends Design {
  items?: DesignItem[];
}

export interface DesignListResponse {
  items: Design[];
  total: number;
  facets: DesignFacets;
}

export type DesignSort = "recent" | "name" | "cost" | "type";

export interface DesignListQuery {
  search?: string;
  clients?: string[];
  projects?: string[];
  groups?: string[];
  build_types?: string[];
  materials?: string[];
  sort?: DesignSort;
  limit?: number;
  offset?: number;
}

const EMPTY_LIST: DesignListResponse = { items: [], total: 0, facets: EMPTY_FACETS };

function facetList(raw: unknown): DesignFacet[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((row) => {
      if (typeof row === "string") return { value: row, count: 0 };
      const r = row as { value?: unknown; count?: unknown };
      return { value: String(r?.value ?? ""), count: Number(r?.count ?? 0) || 0 };
    })
    .filter((f) => f.value !== "");
}

function normalizeFacets(raw: unknown): DesignFacets {
  const f = (raw || {}) as Record<string, unknown>;
  return {
    clients: facetList(f.clients),
    projects: facetList(f.projects),
    groups: facetList(f.groups),
    build_types: facetList(f.build_types),
    materials: facetList(f.materials),
  };
}

export function designListParams(q: DesignListQuery): string {
  const p = new URLSearchParams();
  const csv = (key: string, values?: string[]) => {
    if (values && values.length) p.set(key, values.join(","));
  };
  if (q.search) p.set("search", q.search);
  csv("clients", q.clients);
  csv("projects", q.projects);
  csv("groups", q.groups);
  csv("build_types", q.build_types);
  csv("materials", q.materials);
  if (q.sort) p.set("sort", q.sort);
  if (q.limit != null) p.set("limit", String(q.limit));
  if (q.offset != null) p.set("offset", String(q.offset));
  return p.toString();
}

/**
 * GET /api/designs/list — always resolves. When the endpoint is missing or
 * errors, resolves to an empty list so the caller renders its empty state.
 */
export async function fetchDesignList(q: DesignListQuery = {}): Promise<DesignListResponse> {
  try {
    const res = await apiFetch(`/api/designs/list?${designListParams(q)}`);
    if (!res.ok) return EMPTY_LIST;
    // A dev-server or router fallback can answer with HTML; don't let that
    // blow up in JSON.parse.
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("json")) return EMPTY_LIST;
    const data = (await res.json()) as Record<string, unknown> | null;
    const items = Array.isArray(data?.items) ? (data!.items as Design[]) : [];
    return {
      items,
      total: Number(data?.total ?? items.length) || items.length,
      facets: normalizeFacets(data?.facets),
    };
  } catch {
    return EMPTY_LIST;
  }
}

/** GET /api/designs/{id} — resolves to null when unavailable. */
export async function fetchDesign(id: number | string): Promise<DesignDetail | null> {
  try {
    const res = await apiFetch(`/api/designs/${encodeURIComponent(String(id))}`);
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("json")) return null;
    return (await res.json()) as DesignDetail;
  } catch {
    return null;
  }
}
