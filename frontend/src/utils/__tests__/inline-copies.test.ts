import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { formatDate } from "../format";
import { productImageUrl } from "../ornamentRecipe";
import {
  formatDateTreeCounts,
  moneyCatalogPick,
  moneyJobs,
  moneyOrders,
  moneyOrnament,
  moneySourcing,
  proxiedCatalogPick,
  proxiedOrders,
  proxiedOrnament,
  proxiedSourcing,
} from "./inline-copies";

// Characterisation of the inline duplicates (oracle for the Phase 3
// consolidation). Every copy is asserted on every input.
//
// Locale / timezone: `moneyOrnament` and `formatDateTreeCounts` call
// `toLocaleString` / `toLocaleDateString` with `undefined` locale (machine
// default), and all date formatting depends on the machine timezone. Assigning
// `process.env.TZ = "UTC"` does NOT take effect inside vitest 0.34's worker
// threads (verified: date-only strings still rendered in America/Chicago), so
// instead the prototype methods are wrapped for this file to behave as if the
// process ran with TZ=UTC and an en-US default locale: `timeZone: "UTC"` is
// added to the options and an `undefined` locale becomes "en-US". Explicit
// locales/options passed by the code under test are otherwise untouched.

const FORCED_DEFAULT_LOCALE = "en-US";
const origDateToLocaleDateString = Date.prototype.toLocaleDateString;
const origNumberToLocaleString = Number.prototype.toLocaleString;

function forceDates(timeZone: string, defaultLocale = FORCED_DEFAULT_LOCALE) {
  vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (
    this: Date,
    locales?: string | string[],
    options?: Intl.DateTimeFormatOptions,
  ) {
    return origDateToLocaleDateString.call(this, locales ?? defaultLocale, { ...options, timeZone });
  });
}

function forceNumbers(defaultLocale = FORCED_DEFAULT_LOCALE) {
  vi.spyOn(Number.prototype, "toLocaleString").mockImplementation(function (
    this: number,
    locales?: string | string[],
    options?: Intl.NumberFormatOptions,
  ) {
    return origNumberToLocaleString.call(this, locales ?? defaultLocale, options);
  });
}

beforeAll(() => {
  forceDates("UTC");
  forceNumbers();
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
const THROWS_TYPE_ERROR: Outcome = { throws: "TypeError" };
const v = (value: unknown): Outcome => ({ value });

/** Group copy names whose outcome vectors are identical across all inputs. */
function groupCopies(copies: Record<string, (x: any) => unknown>, inputs: unknown[]): string[][] {
  const bySignature = new Map<string, string[]>();
  for (const [name, fn] of Object.entries(copies)) {
    const sig = JSON.stringify(inputs.map((i) => outcome(() => fn(i))), (_k, x) => (x === undefined ? "__undefined__" : x));
    bySignature.set(sig, [...(bySignature.get(sig) ?? []), name]);
  }
  return [...bySignature.values()];
}

// ─── money ───────────────────────────────────────────────────────────────────

const MONEY_INPUTS: unknown[] = [0, 1, -5, 1234.5, 1234.567, 0.005, 1e6, null, undefined, NaN, "abc", "12.5"];

// `Number(n).toFixed(2)` family: no grouping, "$" before the minus sign.
const MONEY_TOFIXED_EXPECTED: Outcome[] = [
  v("$0.00"),
  v("$1.00"),
  v("$-5.00"),
  v("$1234.50"),
  v("$1234.57"),
  v("$0.01"),
  v("$1000000.00"),
  v("—"),
  v("—"),
  v("$NaN"),
  v("$NaN"),
  v("$12.50"),
];

// `n.toLocaleString(...)`: grouping separators, throws on null/undefined, and
// strings use String.prototype.toLocaleString (no number formatting at all).
const MONEY_ORNAMENT_EXPECTED: Outcome[] = [
  v("$0.00"),
  v("$1.00"),
  v("$-5.00"),
  v("$1,234.50"),
  v("$1,234.57"),
  v("$0.01"),
  v("$1,000,000.00"),
  THROWS_TYPE_ERROR,
  THROWS_TYPE_ERROR,
  v("$NaN"),
  v("$abc"),
  v("$12.5"),
];

const MONEY_COPIES: Record<string, (x: any) => unknown> = {
  moneyCatalogPick,
  moneyJobs,
  moneySourcing,
  moneyOrders,
  moneyOrnament,
};

describe("inline money copies", () => {
  for (const name of ["moneyCatalogPick", "moneyJobs", "moneySourcing", "moneyOrders"]) {
    it(`${name} pins the toFixed(2) outputs`, () => {
      expect(MONEY_INPUTS.map((i) => outcome(() => MONEY_COPIES[name](i)))).toEqual(MONEY_TOFIXED_EXPECTED);
    });
  }

  it("moneyOrnament pins the toLocaleString outputs (en-US default locale)", () => {
    expect(MONEY_INPUTS.map((i) => outcome(() => moneyOrnament(i as number)))).toEqual(MONEY_ORNAMENT_EXPECTED);
  });

  it("moneyOrnament depends on the machine default locale", () => {
    vi.restoreAllMocks();
    forceDates("UTC");
    forceNumbers("de-DE");
    try {
      expect(moneyOrnament(1234.5)).not.toBe("$1,234.50");
      expect(moneyJobs(1234.5)).toBe("$1234.50");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
      forceNumbers();
    }
  });

  it("grouping: the four toFixed copies agree on every input; moneyOrnament is its own group", () => {
    expect(groupCopies(MONEY_COPIES, MONEY_INPUTS)).toEqual([
      ["moneyCatalogPick", "moneyJobs", "moneySourcing", "moneyOrders"],
      ["moneyOrnament"],
    ]);
  });

  it("grouping: moneyOrnament agrees with moneyJobs only on 0, 1, -5, 0.005 and NaN", () => {
    const agree = MONEY_INPUTS.filter(
      (i) => JSON.stringify(outcome(() => moneyOrnament(i as number))) === JSON.stringify(outcome(() => moneyJobs(i as number))),
    );
    expect(agree).toEqual([0, 1, -5, 0.005, NaN]);
  });
});

// ─── proxied ─────────────────────────────────────────────────────────────────

const PROXY_INPUTS: unknown[] = ["", "https://x.com/a.jpg", "http://x.com/a.jpg?b=1", "/relative/a.png", "data:image/png;base64,AAA", null, undefined];

const PROXIED_EXPECTED: Outcome[] = [
  v(undefined),
  v("/api/products/image-proxy?url=https%3A%2F%2Fx.com%2Fa.jpg"),
  v("/api/products/image-proxy?url=http%3A%2F%2Fx.com%2Fa.jpg%3Fb%3D1"),
  v("/api/products/image-proxy?url=%2Frelative%2Fa.png"),
  v("/api/products/image-proxy?url=data%3Aimage%2Fpng%3Bbase64%2CAAA"),
  v(undefined),
  v(undefined),
];

const PRODUCT_IMAGE_URL_EXPECTED: Outcome[] = [
  v("https://images.vickerman.com/_1000.jpg"),
  v("https://images.vickerman.com/https://x.com/a.jpg_1000.jpg"),
  v("https://images.vickerman.com/http://x.com/a.jpg?b=1_1000.jpg"),
  v("https://images.vickerman.com//relative/a.png_1000.jpg"),
  v("https://images.vickerman.com/data:image/png;base64,AAA_1000.jpg"),
  v("https://images.vickerman.com/null_1000.jpg"),
  v("https://images.vickerman.com/undefined_1000.jpg"),
];

const PROXIED_COPIES: Record<string, (x: any) => unknown> = {
  proxiedCatalogPick,
  proxiedSourcing,
  proxiedOrders,
  proxiedOrnament,
  productImageUrl,
};

describe("inline proxied copies", () => {
  for (const name of ["proxiedCatalogPick", "proxiedSourcing", "proxiedOrders", "proxiedOrnament"]) {
    it(`${name} pins the image-proxy URLs`, () => {
      expect(PROXY_INPUTS.map((i) => outcome(() => PROXIED_COPIES[name](i)))).toEqual(PROXIED_EXPECTED);
    });
  }

  it("productImageUrl (utils/ornamentRecipe) is a different function: SKU -> Vickerman CDN URL, no proxying", () => {
    expect(PROXY_INPUTS.map((i) => outcome(() => productImageUrl(i as string)))).toEqual(PRODUCT_IMAGE_URL_EXPECTED);
  });

  it("grouping: all four proxied copies agree on every input; productImageUrl agrees with none", () => {
    expect(groupCopies(PROXIED_COPIES, PROXY_INPUTS)).toEqual([
      ["proxiedCatalogPick", "proxiedSourcing", "proxiedOrders", "proxiedOrnament"],
      ["productImageUrl"],
    ]);
    // Not on a single input, either.
    PROXY_INPUTS.forEach((i) => expect(productImageUrl(i as string)).not.toBe(proxiedOrders(i as string)));
  });

  it("the proxy wraps a CDN URL built by productImageUrl", () => {
    expect(proxiedOrnament(productImageUrl("N590803DSV"))).toBe(
      "/api/products/image-proxy?url=https%3A%2F%2Fimages.vickerman.com%2FN590803DSV_1000.jpg",
    );
  });
});

// ─── formatDate ──────────────────────────────────────────────────────────────

const DATE_INPUTS: unknown[] = ["2026-09-13", "2026-09-13T15:04:05Z", "", null, "not a date"];

describe("inline formatDate copy (pages/TreeCounts.tsx)", () => {
  it("formatDateTreeCounts pins outputs under UTC / en-US", () => {
    expect(DATE_INPUTS.map((i) => outcome(() => formatDateTreeCounts(i as string)))).toEqual([
      v("Sep 13, 2026"),
      v("Sep 13, 2026"),
      v("Invalid Date"),
      v("Jan 1, 1970"), // new Date(null) is the epoch
      v("Invalid Date"),
    ]);
  });

  it("utils/format formatDate pins outputs under UTC", () => {
    expect(DATE_INPUTS.map((i) => outcome(() => formatDate(i as string)))).toEqual([
      v("Sep 13, 2026"),
      v("Sep 13, 2026"),
      v("—"),
      v("—"),
      v("Invalid Date"),
    ]);
  });

  it("grouping: the two agree on valid dates and 'not a date', differ on '' and null", () => {
    const agree = DATE_INPUTS.filter((i) => formatDateTreeCounts(i as string) === formatDate(i as string));
    expect(agree).toEqual(["2026-09-13", "2026-09-13T15:04:05Z", "not a date"]);
    expect(groupCopies({ formatDateTreeCounts, formatDate }, DATE_INPUTS)).toEqual([["formatDateTreeCounts"], ["formatDate"]]);
  });

  it("both shift a date-only string to the previous day west of UTC (America/Chicago)", () => {
    vi.restoreAllMocks();
    forceDates("America/Chicago");
    forceNumbers();
    try {
      expect(formatDateTreeCounts("2026-09-13")).toBe("Sep 12, 2026");
      expect(formatDate("2026-09-13")).toBe("Sep 12, 2026");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
      forceNumbers();
    }
  });

  it("only the TreeCounts copy follows the machine default locale", () => {
    vi.restoreAllMocks();
    forceDates("UTC", "de-DE");
    forceNumbers();
    try {
      expect(formatDateTreeCounts("2026-09-13")).not.toBe("Sep 13, 2026");
      expect(formatDate("2026-09-13")).toBe("Sep 13, 2026");
    } finally {
      vi.restoreAllMocks();
      forceDates("UTC");
      forceNumbers();
    }
  });
});
