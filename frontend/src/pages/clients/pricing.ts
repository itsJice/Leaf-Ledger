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

/** A free job ("Donation — free install"): it stays free next season unless
 *  its basis changes, so no next-season price is pushed. */
export function isDonation(basis: string | null | undefined): boolean {
  return /^\s*donation\b/i.test(basis || "");
}

/** How many dollars the charged price sits below the ideal (negative: above). */
export function discountAmount(p: PricingView | null | undefined): number | null {
  if (!p || p.charged == null || p.ideal?.total == null) return null;
  return Math.round((p.ideal.total - p.charged) * 100) / 100;
}

export type NextSeasonPrice = { amount: number | null; note: string };

/**
 * Next season's starting price (user, 2026-10-05): we charge from the ideal,
 * not from this season's discounted price. Shown only, never stored. A
 * donation stays free; a card the ideal cannot be computed for says what it
 * still needs.
 */
export function nextSeasonPrice(p: PricingView | null | undefined): NextSeasonPrice {
  if (isDonation(p?.basis)) return { amount: null, note: "Stays a free donation install unless that changes" };
  const total = p?.ideal?.total;
  if (total == null) {
    const m = missingLabel(p?.ideal?.missing);
    return { amount: null, note: m ? `Needs ${m} on the card first` : "Not enough on the card to price" };
  }
  return { amount: total, note: "Charged from the ideal, not from this season's discounted price" };
}

/** "38 boxes × $75" for the storage part of a price, or "" when it can't say. */
export function storageLabel(boxes: unknown, storageFee: unknown): string {
  const b = Number(boxes), fee = Number(storageFee);
  if (!Number.isFinite(b) || b <= 0 || !Number.isFinite(fee) || fee <= 0) return "";
  const per = Math.round((fee / b) * 100) / 100;
  return `${b} boxes × $${per % 1 === 0 ? per : per.toFixed(2)}`;
}
