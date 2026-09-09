import { apiFetch } from "utils/apiFetch";

// Typed client for the Request Form API (`/api/requests/*`). A request is
// how a design order enters the app — client/project once, then a
// spreadsheet of items, autosaved field by field. Once saved it's open for
// Charles to load into a job from the Jobs page.

export interface RequestItem {
  id: number;
  request_id: number;
  item: string;
  used_on?: string | null;
  qty?: string | null;
  match_rule?: "exact" | "similar" | "inspiration" | "" | null;
  description?: string | null;
  quality?: string | null;
  preferred_vendor?: string | null;
  style_color?: string | null;
  catalog_page?: string | null;
  sort_order: number;
}

export interface ProductRequest {
  id: number;
  client_name: string;
  project_name: string;
  deadline?: string | null;
  samples_note?: string | null;
  job_id?: number | null;
  job_name?: string | null;
  saved_at?: string | null;
  created_at: string;
  updated_at: string;
  items: RequestItem[];
  created_item_id?: number;
}

export interface RequestSummary {
  id: number;
  client_name: string;
  project_name: string;
  deadline?: string | null;
  job_id?: number | null;
  job_name?: string | null;
  item_count: number;
  updated_at: string;
}

export interface OpenRequest {
  id: number;
  client_name: string;
  project_name: string;
  deadline?: string | null;
  item_count: number;
  updated_at: string;
}

export interface RequestsMeta {
  match_rules: string[];
  match_labels: Record<string, string>;
  used_on_options: string[];
}

const JSON_HEADERS = { "content-type": "application/json" };

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(path, { credentials: "include", ...init });
  if (!r.ok) {
    let detail = r.statusText;
    try { const body = await r.json(); detail = body?.detail || detail; } catch {}
    throw new Error(detail || "Request failed");
  }
  return r.json();
}
const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
const patch = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) });
const del = <T,>(path: string) => call<T>(path, { method: "DELETE" });

export const fetchRequestsMeta = () => call<RequestsMeta>("/api/requests/meta");
export const listRequests = () => call<RequestSummary[]>("/api/requests/list");
export const listOpenRequests = () => call<OpenRequest[]>("/api/requests/open");
export const getRequest = (id: number) => call<ProductRequest>(`/api/requests/${id}`);
export const createRequest = (body: Partial<ProductRequest>) => post<ProductRequest>("/api/requests/create", body);
export const updateRequest = (id: number, body: Record<string, unknown>) => patch<ProductRequest>(`/api/requests/${id}`, body);
export const saveRequest = (id: number) => post<ProductRequest>(`/api/requests/${id}/save`, {});
export const deleteRequest = (id: number) => del<{ ok: boolean }>(`/api/requests/${id}`);

export const addRequestItem = (requestId: number, body: Partial<RequestItem>) =>
  post<ProductRequest>(`/api/requests/${requestId}/items`, body);
export const updateRequestItem = (itemId: number, body: Partial<RequestItem>) =>
  patch<ProductRequest>(`/api/requests/items/${itemId}`, body);
export const deleteRequestItem = (itemId: number) => del<ProductRequest>(`/api/requests/items/${itemId}`);

export const linkRequestToJob = (requestId: number, body: { job_id?: number; create_new?: boolean }) =>
  post<{ job_id: number; request: ProductRequest }>(`/api/requests/${requestId}/link`, body);
export const requestForJob = (jobId: number) => call<ProductRequest | null>(`/api/requests/for-job/${jobId}`);
