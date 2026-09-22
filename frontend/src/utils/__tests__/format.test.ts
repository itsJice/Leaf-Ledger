import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { categoryLabel, formatCurrency, formatDate, unitLabel } from "../format";

// Dates are pinned as if TZ=UTC. `process.env.TZ` assignment has no effect in
// vitest's worker threads, so the Date prototype methods get `timeZone: "UTC"`
// injected (format.ts passes an explicit "en-US" locale, which is kept).
const origDate = Date.prototype.toLocaleDateString;
const origDateTime = Date.prototype.toLocaleString;
function forceDates(timeZone: string, defaultLocale = "en-US") {
  vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (this: Date, l?: string | string[], o?: Intl.DateTimeFormatOptions) {
    return origDate.call(this, l ?? defaultLocale, { ...o, timeZone });
  });
  vi.spyOn(Date.prototype, "toLocaleString").mockImplementation(function (this: Date, l?: string | string[], o?: Intl.DateTimeFormatOptions) {
    return origDateTime.call(this, l ?? defaultLocale, { ...o, timeZone });
  });
}
beforeAll(() => {
  forceDates("UTC");
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

  // FIX: a date-only string used to parse as UTC midnight, so a viewer west
  // of UTC saw the previous day. It must render as the same calendar day
  // regardless of the viewer's timezone — checked at both ends of the real
  // range: America/Chicago (west of UTC) and Pacific/Kiritimati (UTC+14, the
  // most eastward real timezone).
  it("a date-only string renders as the same day under America/Chicago", () => {
    vi.restoreAllMocks();
    forceDates("America/Chicago");
    try {
      expect(formatDate("2026-09-13")).toBe("Sep 13, 2026");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
    }
  });

  it("a date-only string renders as the same day under Pacific/Kiritimati", () => {
    vi.restoreAllMocks();
    forceDates("Pacific/Kiritimati");
    try {
      expect(formatDate("2026-09-13")).toBe("Sep 13, 2026");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
    }
  });

  it("a full ISO timestamp keeps its current (UTC-instant) handling", () => {
    expect(formatDate("2026-09-13T23:59:59Z")).toBe("Sep 13, 2026");
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

  // FIX: `map[cat]` returned an inherited Object.prototype function for keys
  // like "constructor"/"toString"; an own-property check now makes them fall
  // through like any other unknown key.
  it("Object.prototype keys pass through unchanged, not the inherited function", () => {
    expect(categoryLabel("constructor")).toBe("constructor");
    expect(unitLabel("toString")).toBe("toString");
  });
});

describe("unitLabel", () => {
  it("maps known units to themselves and passes others through", () => {
    expect(["stem", "pot", "flat", "bunch", "each", "case", ""].map(unitLabel)).toEqual(["stem", "pot", "flat", "bunch", "each", "case", ""]);
  });
});
