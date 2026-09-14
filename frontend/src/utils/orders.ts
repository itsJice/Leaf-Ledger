import { apiFetch } from "utils/apiFetch";
import { ACTIVE_ORDER_KEY as ACTIVE_KEY } from "../constants";
// Shared team purchase orders — client API + "active order" helper.
// Orders themselves live on the backend (shared across the team); only the
// pointer to which order you're currently adding to is per-browser.

export interface OrderSummary {
  id: number;
  name: string;
  notes?: string | null;
  status: string;
  created_by?: string | null;
  created_at?: string;
  updated_at?: string;
  item_count: number;
  total_qty: number;
  vendor_count: number;
  total_cost?: number | null;
  supplier_name?: string | null;
  vendor_order_no?: string | null;
  placed_at?: string | null;
  expected_arrival?: string | null;
  job_names?: string | null;
}

export const ORDER_STATUSES = ["draft", "approved", "placed", "follow_up", "shipped", "arrived", "closed"];

export async function setOrderStatus(id: number, status: string) {
  return apiFetch(`/api/orders/${id}`, {
    method: "PATCH", credentials: "include", headers: JSON_HEADERS,
    body: JSON.stringify({ status }),
  });
}

export interface OrderLine {
  item_id: number;
  product_id: number;
  name: string;
  sku?: string | null;
  size?: string | null;
  quantity: number;
  variant_note?: string | null;
  unit_price?: number | null;
  line_total?: number | null;
  product_url?: string | null;
  image_url?: string | null;
}

export interface OrderVendor {
  supplier_id?: number | null;
  supplier_name: string;
  supplier_login_url?: string | null;
  items: OrderLine[];
  subtotal: number;
  subtotal_qty: number;
}

export interface OrderDetail {
  id: number;
  name: string;
  notes?: string | null;
  status: string;
  created_by?: string | null;
  created_at?: string;
  updated_at?: string;
  vendors: OrderVendor[];
  total_cost: number;
  total_qty: number;
  item_count: number;
  vendor_count: number;
}

const JSON_HEADERS = { "content-type": "application/json" };

export const getActiveOrderId = (): number | null => {
  const v = localStorage.getItem(ACTIVE_KEY);
  return v ? Number(v) : null;
};
export const setActiveOrderId = (id: number) => localStorage.setItem(ACTIVE_KEY, String(id));

export function defaultOrderName(): string {
  const d = new Date();
  return `Order — ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

export async function listOrders(): Promise<OrderSummary[]> {
  const r = await apiFetch("/api/orders/list", { credentials: "include" });
  return r.ok ? r.json() : [];
}

export async function createOrder(name: string, created_by?: string): Promise<OrderSummary> {
  const r = await apiFetch("/api/orders/create", {
    method: "POST", credentials: "include", headers: JSON_HEADERS,
    body: JSON.stringify({ name, created_by }),
  });
  return r.json();
}

export async function getOrder(id: number): Promise<OrderDetail> {
  const r = await apiFetch(`/api/orders/${id}`, { credentials: "include" });
  if (!r.ok) throw new Error("Order not found");
  return r.json();
}

export async function updateItemQty(itemId: number, quantity: number) {
  return apiFetch(`/api/orders/items/${itemId}`, {
    method: "PATCH", credentials: "include", headers: JSON_HEADERS,
    body: JSON.stringify({ quantity }),
  });
}

export async function removeItem(itemId: number) {
  return apiFetch(`/api/orders/items/${itemId}`, { method: "DELETE", credentials: "include" });
}

export async function deleteOrder(id: number) {
  return apiFetch(`/api/orders/${id}`, { method: "DELETE", credentials: "include" });
}
