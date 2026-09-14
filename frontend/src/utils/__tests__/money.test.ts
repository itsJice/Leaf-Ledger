import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { formatMoney, formatMoneyGrouped } from "../money";
import { moneyCatalogPick, moneyJobs, moneyOrders, moneyOrnament, moneySourcing } from "./inline-copies";

// Same locale wrapping as inline-copies.test.ts: an `undefined` locale becomes en-US.
const origNumberToLocaleString = Number.prototype.toLocaleString;
function forceNumbers(defaultLocale: string) {
  vi.spyOn(Number.prototype, "toLocaleString").mockImplementation(function (
    this: number,
    locales?: string | string[],
    options?: Intl.NumberFormatOptions,
  ) {
    return origNumberToLocaleString.call(this, locales ?? defaultLocale, options);
  });
}
beforeAll(() => {
  forceNumbers("en-US");
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

const MONEY_INPUTS: unknown[] = [0, 1, -5, 1234.5, 1234.567, 0.005, 1e6, null, undefined, NaN, "abc", "12.5", -0, 1e21, Infinity];

// FIX: formatMoney/formatMoneyGrouped now return "—" for a non-finite value
// (NaN, a non-numeric string, or Infinity) instead of "$NaN"/"$abc"/"$∞"; the
// kept-verbatim inline copies (moneyCatalogPick/moneyJobs/moneySourcing/
// moneyOrders/moneyOrnament in inline-copies.ts) still don't. formatMoneyGrouped
// also now returns "—" instead of throwing on null/undefined, unlike the
// unfixed moneyOrnament copy. The comparisons below are restricted to the
// inputs those fixes don't touch; the divergences are pinned separately.
const MONEY_INPUTS_UNCHANGED_TOFIXED: unknown[] = [0, 1, -5, 1234.5, 1234.567, 0.005, 1e6, null, undefined, "12.5", -0, 1e21];
const MONEY_INPUTS_UNCHANGED_GROUPED: unknown[] = [0, 1, -5, 1234.5, 1234.567, 0.005, 1e6, "12.5", -0, 1e21];

describe("formatMoney", () => {
  for (const [name, copy] of Object.entries({ moneyCatalogPick, moneyJobs, moneySourcing, moneyOrders })) {
    it(`matches ${name} on inputs the non-finite fix doesn't touch`, () => {
      expect(MONEY_INPUTS_UNCHANGED_TOFIXED.map((i) => outcome(() => formatMoney(i as number)))).toEqual(
        MONEY_INPUTS_UNCHANGED_TOFIXED.map((i) => outcome(() => copy(i as number))),
      );
    });
  }

  it("returns '—' for non-finite values instead of '$NaN'/'$abc'/'$∞'", () => {
    expect([NaN, "abc", Infinity, -Infinity].map((n) => formatMoney(n as number))).toEqual(["—", "—", "—", "—"]);
  });
});

describe("formatMoneyGrouped", () => {
  it("matches moneyOrnament on inputs the fix doesn't touch (en-US)", () => {
    const shared = MONEY_INPUTS_UNCHANGED_GROUPED.map((i) => outcome(() => formatMoneyGrouped(i as number)));
    expect(shared).toEqual(MONEY_INPUTS_UNCHANGED_GROUPED.map((i) => outcome(() => moneyOrnament(i as number))));
  });

  it("matches moneyOrnament under a de-DE default locale, on inputs the fix doesn't touch", () => {
    vi.restoreAllMocks();
    forceNumbers("de-DE");
    try {
      expect(MONEY_INPUTS_UNCHANGED_GROUPED.map((i) => outcome(() => formatMoneyGrouped(i as number)))).toEqual(
        MONEY_INPUTS_UNCHANGED_GROUPED.map((i) => outcome(() => moneyOrnament(i as number))),
      );
    } finally {
      vi.restoreAllMocks();
      forceNumbers("en-US");
    }
  });

  it("returns '—' for null/undefined instead of throwing, and for non-finite values", () => {
    expect(formatMoneyGrouped(null)).toBe("—");
    expect(formatMoneyGrouped(undefined)).toBe("—");
    expect([NaN, "abc", Infinity, -Infinity].map((n) => formatMoneyGrouped(n as number))).toEqual(["—", "—", "—", "—"]);
    // The unfixed oracle still throws / passes non-finite values through.
    expect(() => moneyOrnament(null as unknown as number)).toThrow(TypeError);
    expect(moneyOrnament(NaN)).toBe("$NaN");
  });
});
