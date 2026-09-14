import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { formatDate, formatDateShortLocale } from "../format";
import { formatDateTreeCounts } from "./inline-copies";

// Same wrapping as inline-copies.test.ts: timeZone forced, `undefined` locale → default.
const origDateToLocaleDateString = Date.prototype.toLocaleDateString;
function forceDates(timeZone: string, defaultLocale = "en-US") {
  vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (
    this: Date,
    locales?: string | string[],
    options?: Intl.DateTimeFormatOptions,
  ) {
    return origDateToLocaleDateString.call(this, locales ?? defaultLocale, { ...options, timeZone });
  });
}
beforeAll(() => {
  forceDates("UTC");
});
afterAll(() => {
  vi.restoreAllMocks();
});

type Outcome = { value: unknown } | { throws: string };
function outcome(fn: () => unknown): Outcome {
  try {
    return { value: fn() };
  } catch (e) {
    return { throws: (e as Error).constructor.name };
  }
}

// Inputs the fix below does not touch: a full ISO timestamp/offset (parsed as
// before) and the numeric epoch 0 (never matches the date-only pattern), so
// formatDateShortLocale must still match the historical TreeCounts copy on
// these regardless of timezone/locale.
const UNCHANGED_DATE_INPUTS: unknown[] = ["2026-09-13T15:04:05Z", 0, "2026-12-31T23:59:59-06:00"];
const run = (inputs: unknown[], fn: (x: string) => string) => inputs.map((i) => outcome(() => fn(i as string)));

describe("formatDateShortLocale", () => {
  it("matches the TreeCounts copy under UTC / en-US on inputs the fix doesn't touch", () => {
    expect(run(UNCHANGED_DATE_INPUTS, formatDateShortLocale)).toEqual(run(UNCHANGED_DATE_INPUTS, formatDateTreeCounts));
  });

  it("matches the TreeCounts copy under America/Chicago / de-DE on inputs the fix doesn't touch", () => {
    vi.restoreAllMocks();
    forceDates("America/Chicago", "de-DE");
    try {
      expect(run(UNCHANGED_DATE_INPUTS, formatDateShortLocale)).toEqual(run(UNCHANGED_DATE_INPUTS, formatDateTreeCounts));
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
    }
  });

  // FIX: formatDateShortLocale used to be a verbatim copy of the buggy
  // TreeCounts inline helper (off-by-one date-only parsing, "Invalid Date"
  // for "", the epoch for null, no invalid-date guard). It has since been
  // fixed to parse date-only strings as local calendar dates and to return
  // "—" for "", null/undefined and unparseable strings, matching formatDate's
  // falsy handling — so these inputs now diverge from the kept-verbatim
  // `formatDateTreeCounts` oracle in inline-copies.ts/inline-copies.test.ts.
  // (0 is intentionally excluded from that "—" guard, so it still agrees with
  // the oracle above — see UNCHANGED_DATE_INPUTS.)
  it("returns '—' for '', null, undefined and invalid dates, matching formatDate's falsy handling", () => {
    expect(formatDateShortLocale("")).toBe("—");
    expect(formatDateShortLocale(null)).toBe("—");
    expect(formatDateShortLocale(undefined)).toBe("—");
    expect(formatDateShortLocale("not a date")).toBe("—");
    // formatDate still returns "Invalid Date" for garbage (unchanged by this fix).
    expect(formatDate("")).toBe("—");
    expect(formatDate("not a date")).toBe("Invalid Date");
  });

  it("a date-only string renders as the same day under America/Chicago", () => {
    vi.restoreAllMocks();
    forceDates("America/Chicago");
    try {
      expect(formatDateShortLocale("2026-09-13")).toBe("Sep 13, 2026");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
    }
  });

  it("a date-only string renders as the same day under Pacific/Kiritimati", () => {
    vi.restoreAllMocks();
    forceDates("Pacific/Kiritimati");
    try {
      expect(formatDateShortLocale("2026-09-13")).toBe("Sep 13, 2026");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
    }
  });
});
