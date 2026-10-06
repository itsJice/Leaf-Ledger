import { describe, expect, it } from "vitest";
import { discountAmount, discountLabel, isDonation, nextSeasonPrice, storageLabel, type PricingView } from "../clients/pricing";

// Evelyn Lee, 2026: the 2025 invoice was only her storage, so install and
// takedown came out at $0 under "2025 invoice +5%".
const evelyn: PricingView = {
  ideal: { install: 8220, takedown: 8220, storage: 2850, pickup_delivery: 853.5, total: 20143.5, missing: [] },
  charged: 2850, charged_source: "total", discount_pct: 85.9,
  basis: "2025 invoice +5% (storage: boxes × $75, no uplift)",
};
const valleyForge: PricingView = {
  ideal: { install: 1100, takedown: 1100, storage: 1050, pickup_delivery: 242.5, total: 3492.5, missing: [] },
  charged: 0, charged_source: "total", discount_pct: 100, basis: "Donation — free install",
};

describe("Christmas card prices", () => {
  it("shows how far below the ideal a price sits, in dollars and percent", () => {
    expect(discountAmount(evelyn)).toBe(17293.5);
    expect(discountLabel(evelyn.discount_pct)).toBe("85.9% off");
    expect(discountAmount({ ...evelyn, charged: null })).toBeNull();
  });

  it("starts next season from the ideal", () => {
    expect(nextSeasonPrice(evelyn)).toEqual({ amount: 20143.5, note: "Charged from the ideal, not from this season's discounted price" });
  });

  it("keeps a donation free next season", () => {
    expect(isDonation(valleyForge.basis)).toBe(true);
    expect(nextSeasonPrice(valleyForge).amount).toBeNull();
    expect(nextSeasonPrice(valleyForge).note).toMatch(/free donation/);
    expect(isDonation("2025 invoice +5%")).toBe(false);
  });

  it("says what the card still needs when there is no ideal", () => {
    const p: PricingView = { ...evelyn, ideal: { ...evelyn.ideal, total: null, missing: ["est_hours", "role_need"] } };
    expect(nextSeasonPrice(p)).toEqual({ amount: null, note: "Needs install hours and crew headcounts on the card first" });
  });

  it("names the storage part of a price", () => {
    expect(storageLabel(38, 2850)).toBe("38 boxes × $75");
    expect(storageLabel(null, 2850)).toBe("");
    expect(storageLabel(0, 0)).toBe("");
  });
});
