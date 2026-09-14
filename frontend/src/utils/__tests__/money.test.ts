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

describe("formatMoney", () => {
  for (const [name, copy] of Object.entries({ moneyCatalogPick, moneyJobs, moneySourcing, moneyOrders })) {
    it(`matches ${name} on every input`, () => {
      expect(MONEY_INPUTS.map((i) => outcome(() => formatMoney(i as number)))).toEqual(MONEY_INPUTS.map((i) => outcome(() => copy(i as number))));
    });
  }
});

describe("formatMoneyGrouped", () => {
  it("matches moneyOrnament on every input, including throws (en-US)", () => {
    const shared = MONEY_INPUTS.map((i) => outcome(() => formatMoneyGrouped(i as number)));
    expect(shared).toEqual(MONEY_INPUTS.map((i) => outcome(() => moneyOrnament(i as number))));
    expect(shared).toContainEqual({ throws: "TypeError" });
  });

  it("matches moneyOrnament under a de-DE default locale", () => {
    vi.restoreAllMocks();
    forceNumbers("de-DE");
    try {
      expect(MONEY_INPUTS.map((i) => outcome(() => formatMoneyGrouped(i as number)))).toEqual(
        MONEY_INPUTS.map((i) => outcome(() => moneyOrnament(i as number))),
      );
    } finally {
      vi.restoreAllMocks();
      forceNumbers("en-US");
    }
  });
});
