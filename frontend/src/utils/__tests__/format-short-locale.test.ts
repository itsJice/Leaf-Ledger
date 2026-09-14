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

const DATE_INPUTS: unknown[] = ["2026-09-13", "2026-09-13T15:04:05Z", "", null, "not a date", undefined, 0, "2026-12-31T23:59:59-06:00"];
const run = (fn: (x: string) => string) => DATE_INPUTS.map((i) => outcome(() => fn(i as string)));

describe("formatDateShortLocale", () => {
  it("matches the TreeCounts copy under UTC / en-US", () => {
    expect(run(formatDateShortLocale)).toEqual(run(formatDateTreeCounts));
  });

  it("matches the TreeCounts copy under America/Chicago / de-DE", () => {
    vi.restoreAllMocks();
    forceDates("America/Chicago", "de-DE");
    try {
      expect(run(formatDateShortLocale)).toEqual(run(formatDateTreeCounts));
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
    }
  });

  it("is not formatDate: differs on '' and null", () => {
    expect(formatDateShortLocale("")).toBe("Invalid Date");
    expect(formatDate("")).toBe("—");
    expect(formatDateShortLocale(null as unknown as string)).toBe("Jan 1, 1970");
  });
});
