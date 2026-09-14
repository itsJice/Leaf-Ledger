import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { categoryLabel, formatCurrency, formatDate, formatDateTime, unitLabel } from "../format";

// Dates are pinned as if TZ=UTC. `process.env.TZ` assignment has no effect in
// vitest's worker threads, so the Date prototype methods get `timeZone: "UTC"`
// injected (format.ts passes an explicit "en-US" locale, which is kept).
const origDate = Date.prototype.toLocaleDateString;
const origDateTime = Date.prototype.toLocaleString;
beforeAll(() => {
  vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (this: Date, l?: string | string[], o?: Intl.DateTimeFormatOptions) {
    return origDate.call(this, l ?? "en-US", { ...o, timeZone: "UTC" });
  });
  vi.spyOn(Date.prototype, "toLocaleString").mockImplementation(function (this: Date, l?: string | string[], o?: Intl.DateTimeFormatOptions) {
    return origDateTime.call(this, l ?? "en-US", { ...o, timeZone: "UTC" });
  });
});
afterAll(() => {
  vi.restoreAllMocks();
});

describe("formatCurrency", () => {
  it("formats numbers as en-US USD", () => {
    expect([0, 1, -5, 1234.5, 1234.567, 0.005, 1e6].map(formatCurrency)).toEqual([
      "$0.00",
      "$1.00",
      "-$5.00",
      "$1,234.50",
      "$1,234.57",
      "$0.01",
      "$1,000,000.00",
    ]);
  });

  it("returns an em dash for null/undefined", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(undefined)).toBe("—");
  });

  it("passes non-finite numbers through Intl", () => {
    expect(formatCurrency(NaN)).toBe("$NaN");
    expect(formatCurrency(Infinity)).toBe("$∞");
  });
});

describe("formatDate", () => {
  it("formats strings and Date objects", () => {
    expect(formatDate("2026-09-13")).toBe("Sep 13, 2026");
    expect(formatDate("2026-09-13T23:59:59Z")).toBe("Sep 13, 2026");
    expect(formatDate(new Date(Date.UTC(2025, 0, 2)))).toBe("Jan 2, 2025");
  });

  it("returns an em dash for falsy input and 'Invalid Date' for garbage", () => {
    expect(formatDate("")).toBe("—");
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("not a date")).toBe("Invalid Date");
  });
});

describe("formatDateTime", () => {
  it("formats with hour and 2-digit minute", () => {
    expect(formatDateTime("2026-09-13T15:04:05Z")).toBe("Sep 13, 2026, 3:04 PM");
    expect(formatDateTime("2026-09-13")).toBe("Sep 13, 2026, 12:00 AM");
  });

  it("returns an em dash for falsy input and 'Invalid Date' for garbage", () => {
    expect(formatDateTime("")).toBe("—");
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("nope")).toBe("Invalid Date");
  });
});

describe("categoryLabel", () => {
  it("maps new, scraper and legacy categories", () => {
    expect(["containers", "wood", "greenery", "florals", "trees", "accents", "plant", "moss", "liners"].map(categoryLabel)).toEqual([
      "Containers",
      "Wood",
      "Greenery",
      "Florals",
      "Trees",
      "Accents",
      "Plant",
      "Moss",
      "Liners",
    ]);
  });

  it("passes unknown and empty values through unchanged (case-sensitive)", () => {
    expect(categoryLabel("Containers")).toBe("Containers");
    expect(categoryLabel("widgets")).toBe("widgets");
    expect(categoryLabel("")).toBe("");
  });

  it("BUG pinned: Object.prototype keys leak through the lookup map", () => {
    expect(typeof categoryLabel("constructor")).toBe("function");
    expect(typeof unitLabel("toString")).toBe("function");
  });
});

describe("unitLabel", () => {
  it("maps known units to themselves and passes others through", () => {
    expect(["stem", "pot", "flat", "bunch", "each", "case", ""].map(unitLabel)).toEqual(["stem", "pot", "flat", "bunch", "each", "case", ""]);
  });
});
