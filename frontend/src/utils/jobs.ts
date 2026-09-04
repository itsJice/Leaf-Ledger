import { apiFetch } from "utils/apiFetch";

// Typed client for the Jobs API (`/api/jobs/*`): a client order carried from
// intake to the client shelf. Every mutating call returns the full, refreshed
// job so the page never has to stitch partial updates together.

// The buyer's stages. Derived on the server from the worksheet lines.
export type Stage = "new" | "sourcing" | "ordered" | "receiving" | "complete";

export const STAGES: Stage[] = ["new", "sourcing", "ordered", "receiving", "complete"];

export const STAGE_LABEL: Record<Stage, string> = {
  new: "New",
  sourcing: "Sourcing",
  ordered: "Ordered",
  receiving: "Receiving",
  complete: "Complete",
};

export type SourcingStatus =
  | "proposed" | "sold_out" | "ready" | "ordered" | "follow_up" | "allocated" | "on_hold";

export const SOURCING_LABEL: Record<SourcingStatus, string> = {
  proposed: "Proposed",
  ready: "Ready to order",
  ordered: "On order",
  follow_up: "Follow-up",
  allocated: "Allocated",
  sold_out: "Sold out",
  on_hold: "On hold",
};

export interface JobSummary {
  id: number;
  name: string;
  order_no?: string | null;
  client_name?: string | null;
  client_id?: number | null;
  project_id?: number | null;
  season?: string | null;
  collection?: string | null;
  install_date?: string | null;
  order_date?: string | null;
  due_date?: string | null;
  stage: Stage;
  summary: JobStats;
  updated_at?: string;
  created_at?: string;
}

export interface JobStats {
  piece_count: number;
  need_count: number;
  ready_count: number;
  gap_count: number;
  unsourced_count: number;
  open_tasks: number;
  buy_cost?: number | null;
}

export interface Piece {
  id: number;
  job_id: number;
  piece_type: string;
  qty: number;
  spec: Record<string, string | number | null>;
  design_id?: number | null;
  sort_order: number;
}

export interface SourcingLine {
  id: number;
  need_id: number;
  product_id?: number | null;
  supplier_id?: number | null;
  vendor_name?: string | null;
  sku?: string | null;
  description?: string | null;
  image_url?: string | null;
  status: SourcingStatus;
  price_per: "each" | "pack";
  pack_qty: number;
  covers_qty: number;
  packs: number;
  order_qty: number;
  unit_cost?: number | null;
  adj_unit_cost?: number | null;
  line_cost?: number | null;
  overage_qty: number;
  allocated_from_order_item_id?: number | null;
  allocated_qty: number;
  allocated_order_name?: string | null;
  order_item_id?: number | null;
  order_id?: number | null;
  order_name?: string | null;
  order_status?: string | null;
  expected_arrival?: string | null;
  po_quantity?: number | null;
  received_qty?: number | null;
  substitute_for?: number | null;
  notes?: string | null;
}

export interface Need {
  id: number;
  job_id: number;
  piece_id?: number | null;
  label: string;
  spec?: string | null;
  need_qty: number;
  unit: string;
  shelf_qty: number;
  source: string;
  notes?: string | null;
  sort_order: number;
  lines: SourcingLine[];
  allocated_qty: number;
  ordered_qty: number;
  received_qty: number;
  proposed_qty: number;
  gap_qty: number;
  unsourced_qty: number;
  on_shelf_qty: number;
  ready: boolean;
}

export interface Task {
  id: number;
  job_id: number;
  sourcing_line_id?: number | null;
  title: string;
  assignee?: string | null;
  due?: string | null;
  done_at?: string | null;
}

export interface JobPO {
  id: number;
  name: string;
  status: string;
  supplier_id?: number | null;
  supplier_name?: string | null;
  vendor_order_no?: string | null;
  placed_at?: string | null;
  expected_arrival?: string | null;
  freight?: number | null;
  line_count: number;
  total_qty: number;
  received_qty: number;
}

export interface Job extends JobSummary {
  designer?: string | null;
  sidemark?: string | null;
  delivery_method?: string | null;
  color_palette?: string | null;
  intake: Record<string, string | boolean | null>;
  notes?: string | null;
  built_at?: string | null;
  installed_at?: string | null;
  pieces: Piece[];
  needs: Need[];
  tasks: Task[];
  purchase_orders: JobPO[];
  created_line_id?: number;
  created_orders?: number[];
}

export interface OpenOrderLine {
  order_item_id: number;
  order_id: number;
  order_name: string;
  order_status: string;
  expected_arrival?: string | null;
  product_id?: number | null;
  quantity: number;
  received_qty: number;
  job_id?: number | null;
  job_name?: string | null;
  name: string;
  sku?: string | null;
  supplier_name?: string | null;
  unit_price?: number | null;
  allocated_qty: number;
  remaining_qty: number;
}

export interface POLine {
  id: number;
  product_id: number;
  quantity: number;
  received_qty: number;
  name: string;
  sku?: string | null;
  unit_price?: number | null;
  job_id?: number | null;
  need_id?: number | null;
  need_label?: string | null;
  sourcing_line_id?: number | null;
}

export interface JobsMeta {
  stages: Stage[];
  piece_types: string[];
  sourcing_statuses: SourcingStatus[];
}

const JSON_HEADERS = { "content-type": "application/json" };

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(path, { credentials: "include", ...init });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = body?.detail || detail;
    } catch {}
    throw new Error(detail || "Request failed");
  }
  return r.json();
}

const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
const patch = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) });
const del = <T,>(path: string) => call<T>(path, { method: "DELETE" });

export const fetchJobsMeta = () => call<JobsMeta>("/api/jobs/meta");
export const listJobs = () => call<JobSummary[]>("/api/jobs/list");
export const getJob = (id: number) => call<Job>(`/api/jobs/${id}`);
export const createJob = (body: Partial<Job>) => post<Job>("/api/jobs/create", body);
export const updateJob = (id: number, body: Record<string, unknown>) => patch<Job>(`/api/jobs/${id}`, body);
export const deleteJob = (id: number) => del<{ ok: boolean }>(`/api/jobs/${id}`);

export const addPiece = (jobId: number, body: Partial<Piece>) => post<Job>(`/api/jobs/${jobId}/pieces`, body);
export const updatePiece = (pieceId: number, body: Partial<Piece>) => patch<Job>(`/api/jobs/pieces/${pieceId}`, body);
export const deletePiece = (pieceId: number) => del<Job>(`/api/jobs/pieces/${pieceId}`);

export const addNeeds = (jobId: number, needs: Partial<Need>[]) => post<Job>(`/api/jobs/${jobId}/needs`, { needs });
export const updateNeed = (needId: number, body: Partial<Need>) => patch<Job>(`/api/jobs/needs/${needId}`, body);
export const deleteNeed = (needId: number) => del<Job>(`/api/jobs/needs/${needId}`);

export interface SourcingInput {
  product_id?: number;
  vendor_name?: string;
  supplier_id?: number;
  sku?: string;
  description?: string;
  unit_cost?: number;
  price_per?: "each" | "pack";
  pack_qty?: number;
  covers_qty?: number;
  status?: SourcingStatus;
  substitute_for?: number;
  notes?: string;
}
export const addSourcing = (needId: number, body: SourcingInput) => post<Job>(`/api/jobs/needs/${needId}/sourcing`, body);
export const updateSourcing = (lineId: number, body: Partial<SourcingLine>) => patch<Job>(`/api/jobs/sourcing/${lineId}`, body);
export const deleteSourcing = (lineId: number) => del<Job>(`/api/jobs/sourcing/${lineId}`);

export const searchOpenOrders = (params: { product_id?: number; q?: string }) => {
  const qs = new URLSearchParams();
  if (params.product_id) qs.set("product_id", String(params.product_id));
  if (params.q) qs.set("q", params.q);
  return call<OpenOrderLine[]>(`/api/jobs/open-orders/search?${qs.toString()}`);
};
export const allocateFromOrder = (needId: number, body: { order_item_id: number; qty: number; notes?: string }) =>
  post<Job>(`/api/jobs/needs/${needId}/allocate`, body);

export const sendToPO = (jobId: number, body: { sourcing_line_ids?: number[]; append_to?: Record<string, number> }) =>
  post<Job>(`/api/jobs/${jobId}/send-to-po`, body);
export const openPOsForVendor = (supplierId: number) =>
  call<Array<{ id: number; name: string; status: string; line_count: number }>>(`/api/jobs/vendors/${supplierId}/open-pos`);
export const updatePO = (orderId: number, body: Record<string, unknown>) => patch<JobPO>(`/api/jobs/po/${orderId}`, body);
export const poLines = (orderId: number) => call<POLine[]>(`/api/jobs/po/${orderId}/lines`);
export const receiveLine = (itemId: number, qty: number, note?: string) =>
  post<Job>(`/api/jobs/order-items/${itemId}/receive`, { qty, note });

export const addTask = (jobId: number, body: { title: string; assignee?: string; due?: string; sourcing_line_id?: number }) =>
  post<Job>(`/api/jobs/${jobId}/tasks`, body);
export const updateTask = (taskId: number, body: { title?: string; assignee?: string; due?: string; done?: boolean }) =>
  patch<Job>(`/api/jobs/tasks/${taskId}`, body);
export const deleteTask = (taskId: number) => del<Job>(`/api/jobs/tasks/${taskId}`);

export const exportUrl = (jobId: number) => `/api/jobs/${jobId}/export?format=xlsx`;

// Download through apiFetch so the Authorization header goes along (a plain
// <a href> to /api would come back 401).
export async function downloadExport(jobId: number, jobName: string) {
  const r = await apiFetch(exportUrl(jobId), { credentials: "include" });
  if (!r.ok) throw new Error("Export failed");
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${jobName.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_") || "job"}_tracking.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
