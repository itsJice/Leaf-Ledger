/**
 * The `pricing` block every christmas_install season row carries out of
 * GET /clients/list and PUT /clients/{id}/seasons/{season} -- computed by
 * backend/app/libs/pricing.py, never stored. This file only names its shape
 * and formats it; no price is computed in the browser.
 */

export type IdealBreakdown = {
  install: number | null;
  takedown: number | null;
  storage: number | null;
  pickup_delivery: number | null;
  total: number | null;
  /** Card fields ("est_hours", "role_need") or rates ("rate:general") still needed. */
  missing: string[];
};

export type PricingView = {
  ideal: IdealBreakdown;
  /** What the client was (or will be) billed: the real invoice, else the total as sent. */
  charged: number | null;
  charged_source: "invoice" | "total" | null;
  /** 1 - charged / ideal, in percent. Negative means they pay above the ideal. */
  discount_pct: number | null;
  basis: string | null;
};

export const INVENTORY_TYPES = ["tree", "wreath", "garland", "spray", "swag", "other"] as const;
export type InventoryType = typeof INVENTORY_TYPES[number];

export type InventoryLine = { type: InventoryType; size?: string; qty: number; note?: string };

export type RoleNeed = { leads?: number; specialty?: number; designer?: number; general?: number };

export const ROLE_LABELS: Array<{ key: keyof RoleNeed; label: string }> = [
  { key: "leads", label: "Crew leads" },
  { key: "specialty", label: "Specialty" },
  { key: "designer", label: "Designers" },
  { key: "general", label: "General" },
];

const MISSING_LABEL: Record<string, string> = {
  est_hours: "install hours",
  role_need: "crew headcounts",
  "rate:crew_lead": "crew lead rate",
  "rate:specialty": "specialty rate",
  "rate:designer": "designer rate",
  "rate:general": "general installer rate",
  "rate:storage_box": "storage rate",
  "rate:van_crew_rate": "van crew rate",
  "rate:handling_min_per_box": "minutes per box",
  "rate:drive_min_default": "default drive time",
};

/** "add install hours and crew headcounts" -- what the ideal still needs. */
export function missingLabel(missing: string[] | undefined): string {
  if (!missing || missing.length === 0) return "";
  const parts = missing.map((m) => MISSING_LABEL[m] || m.replace(/^rate:/, "").replace(/_/g, " "));
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/** "20% off" / "12% above" / "" */
export function discountLabel(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return "";
  if (Math.abs(pct) < 0.05) return "at ideal";
  const n = Math.abs(pct) % 1 === 0 ? String(Math.abs(pct)) : Math.abs(pct).toFixed(1);
  return pct > 0 ? `${n}% off` : `${n}% above`;
}
