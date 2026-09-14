/**
 * Characterisation tests for the pure helpers inside pages/Library.tsx.
 *
 * These pin the CURRENT behaviour (quirks included) so the helpers can later be
 * moved into their own modules and proven unchanged.
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// Module mocks are hoisted only within the declaring file, so they live here.
vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("components/Layout", () => ({ default: () => null }));

import { clearStorage, seedStorage } from "../../test/setup";
import * as L from "../library/index";
import type { Product } from "../library/index";

const p = (overrides: Partial<Product> = {}): Product => ({
  id: 1,
  name: "",
  category: "florals",
  unit: "each",
  supplier_id: 1,
  created_at: "",
  updated_at: "",
  ...overrides,
});

beforeEach(() => {
  clearStorage();
});

describe("constants", () => {
  it("filter vocabularies", () => {
    expect(L.CATEGORIES).toEqual(["containers", "wood", "greenery", "florals", "trees"]);
    expect(L.UNITS).toEqual(["stem", "pot", "flat", "bunch", "each"]);
    expect(L.AVAILABILITY_FILTERS).toEqual([
      "Available today", "Within 1-4 months", "Over 4 months", "Sold out / unavailable", "Future ETA",
    ]);
    expect(L.PRODUCT_TYPE_RULES.map((rule) => rule.label)).toEqual([
      "Ribbon", "Spray", "Pick", "Ornament", "Wreath", "Garland", "Tree", "Stem", "Bush", "Bundle", "Floral", "Container",
    ]);
    expect(L.STALE_DAYS).toBe(30);
  });

  it("colour tables", () => {
    expect(L.KNOWN_COLOR_WORDS[0]).toBe("aqua");
    expect(L.KNOWN_COLOR_WORDS[L.KNOWN_COLOR_WORDS.length - 1]).toBe("yellow");
    expect(Object.keys(L.ALLSTATE_COLOR_CODE_MAP)).toHaveLength(29);
    expect(L.ALLSTATE_COLOR_CODE_MAP.CW).toEqual(["Clear", "White"]);
    expect(L.ALLSTATE_COLOR_CODE_MAP.FS).toEqual(["Frost", "Silver"]);
    expect(L.CATEGORY_COLORS.containers).toBe("rgb(var(--cat-botanicals))");
    expect(L.RAW_ATTRS_HIDE.has("gallery_images_json")).toBe(true);
  });

  it("cache keys", () => {
    expect(L.LIBRARY_CACHE_KEY).toBe("leaf-ledger:library-cache:v1");
    expect(L.LIBRARY_METADATA_CACHE_KEY).toBe("leaf-ledger:library-filter-metadata:v1");
    expect(L.LIBRARY_CACHE_RAW_KEYS).toHaveLength(29);
  });
});

describe("cache helpers", () => {
  it("trimRawDataForCache keeps only whitelisted defined keys", () => {
    expect(L.trimRawDataForCache(null)).toEqual({});
    expect(L.trimRawDataForCache({ Description: "x", foo: 1, UPC: "123", Class: undefined })).toEqual({ Description: "x", UPC: "123" });
  });

  it("trimProductForCache trims raw_data only", () => {
    expect(L.trimProductForCache(p({ id: 4, name: "Pine", raw_data: { Season: "Winter", gallery: [1] } }))).toEqual(
      p({ id: 4, name: "Pine", raw_data: { Season: "Winter" } })
    );
  });

  it("readLibraryCache", () => {
    expect(L.readLibraryCache()).toBeNull();
    seedStorage({ [L.LIBRARY_CACHE_KEY]: { suppliers: [{ id: 1, name: "A" }], products: [{ id: 2 }], productTotal: 5, cachedAt: 9 } });
    expect(L.readLibraryCache()).toEqual({ suppliers: [{ id: 1, name: "A" }], products: [{ id: 2 }], productTotal: 5 });
    seedStorage({ [L.LIBRARY_CACHE_KEY]: { products: [] } });
    expect(L.readLibraryCache()).toBeNull();
    seedStorage({ [L.LIBRARY_CACHE_KEY]: "not json" });
    expect(L.readLibraryCache()).toBeNull();
  });

  it("readLibraryMetadataCache", () => {
    expect(L.readLibraryMetadataCache()).toBeNull();
    seedStorage({ [L.LIBRARY_METADATA_CACHE_KEY]: { categories: [{ value: "x", count: 2 }] } });
    expect(L.readLibraryMetadataCache()).toEqual({ categories: [{ value: "x", count: 2 }] });
    seedStorage({ [L.LIBRARY_METADATA_CACHE_KEY]: "5" });
    expect(L.readLibraryMetadataCache()).toBeNull();
    seedStorage({ [L.LIBRARY_METADATA_CACHE_KEY]: "null" });
    expect(L.readLibraryMetadataCache()).toBeNull();
  });

  it("applyLocalFavoriteState merges locally stored favourite ids", () => {
    seedStorage({ "leaf-ledger:favorite-product-ids:v1": [2, "3"] });
    expect(
      L.applyLocalFavoriteState([p({ id: 1 }), p({ id: 2 }), p({ id: 3, is_favorited: false }), p({ id: 4, is_favorited: true })]).map(
        (product) => product.is_favorited
      )
    ).toEqual([false, true, true, true]);
  });
});

describe("isPriceStale", () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-03-01T12:00:00.000Z"));
  });
  afterAll(() => {
    vi.useRealTimers();
  });

  it("is stale when missing or older than 30 days", () => {
    expect(L.isPriceStale(null)).toBe(true);
    expect(L.isPriceStale("2026-02-20T12:00:00.000Z")).toBe(false);
    expect(L.isPriceStale("2026-01-30T12:00:00.000Z")).toBe(false);
    expect(L.isPriceStale("2026-01-01T00:00:00.000Z")).toBe(true);
  });
});

describe("value and name helpers", () => {
  it("formatDetailValue", () => {
    expect(L.formatDetailValue(null)).toBe("—");
    expect(L.formatDetailValue("")).toBe("—");
    expect(L.formatDetailValue(3)).toBe("3");
    expect(L.formatDetailValue(0)).toBe("0");
    expect(L.formatDetailValue(2.5)).toBe("2.50");
    expect(L.formatDetailValue(false)).toBe("false");
    expect(L.formatDetailValue("abc")).toBe("abc");
  });

  it("sourceValue returns the first non-empty raw key", () => {
    const product = p({ raw_data: { BasePrice: "", price: 4.5, zero: 0 } });
    expect(L.sourceValue(product, "BasePrice", "price")).toBe(4.5);
    expect(L.sourceValue(product, "zero")).toBe(0);
    expect(L.sourceValue(product, "missing")).toBeUndefined();
    expect(L.sourceValue(p(), "price")).toBeUndefined();
  });

  it("displayProductName prefers name, then raw Description, then description", () => {
    expect(L.displayProductName(p({ name: " Pine Spray ", raw_data: { Description: "Desc" } }))).toBe("Pine Spray");
    expect(L.displayProductName(p({ name: "", raw_data: { Description: "Legacy" } }))).toBe("Legacy");
    expect(L.displayProductName(p({ name: "", description: "Copy" }))).toBe("Copy");
    expect(L.displayProductName(p())).toBe("");
  });

  it("prettifyKey", () => {
    expect(L.prettifyKey("allstate_subcategory")).toBe("Allstate Subcategory");
    expect(L.prettifyKey("Box-LxWxH")).toBe("Box LxWxH");
    expect(L.prettifyKey("  p__cat  vol")).toBe("P Cat Vol");
  });

  it("withUnit appends a unit to bare numbers only", () => {
    expect(L.withUnit(null, "in")).toBeNull();
    expect(L.withUnit(undefined, "in")).toBeUndefined();
    expect(L.withUnit("360", "in")).toBe("360 in");
    expect(L.withUnit(" 5 ", "lb")).toBe("5 lb");
    expect(L.withUnit("0", "in")).toBe("0");
    expect(L.withUnit(0, "in")).toBe(0);
    expect(L.withUnit("", "in")).toBe("");
    expect(L.withUnit("12x4", "in")).toBe("12x4");
    expect(L.withUnit('12"', "in")).toBe('12"');
  });
});

describe("search text", () => {
  it("normalizeSearchText", () => {
    expect(L.normalizeSearchText(`4" Ornament's Gold-Glitter`)).toBe("4 ornaments gold glitter");
    expect(L.normalizeSearchText(12.5)).toBe("12 5");
    expect(L.normalizeSearchText("  Café  ")).toBe("caf");
    expect(L.normalizeSearchText(null)).toBe("");
  });

  it("titleCase", () => {
    expect(L.titleCase("gold GLITTER ribbon")).toBe("Gold Glitter Ribbon");
    expect(L.titleCase("4in pine")).toBe("4in Pine");
  });

  it("expandSearchAliases", () => {
    expect(L.expandSearchAliases("")).toBe("");
    expect(L.expandSearchAliases("Pine Garland")).toBe("pine garland");
    expect(L.expandSearchAliases("2 ea")).toBe("2 ea each ea 2 each ea");
    expect(L.expandSearchAliases("Qty 12")).toBe("qty quantity qty 12");
  });

  it("looksLikeCodeQuery", () => {
    expect(L.looksLikeCodeQuery("ab12")).toBe(true);
    expect(L.looksLikeCodeQuery("abc")).toBe(true);
    expect(L.looksLikeCodeQuery("a/b")).toBe(true);
    expect(L.looksLikeCodeQuery("abcd")).toBe(false);
    expect(L.looksLikeCodeQuery("ribbon")).toBe(false);
  });

  it("matchesSearchTokens / matchesNormalizedTokens", () => {
    expect(L.matchesSearchTokens("gold glitter ribbon", "Glitter  GOLD")).toBe(true);
    expect(L.matchesSearchTokens("gold ribbon", "silver")).toBe(false);
    expect(L.matchesSearchTokens("anything", "  ")).toBe(true);
    expect(L.matchesNormalizedTokens("abc", [])).toBe(true);
    expect(L.matchesNormalizedTokens("pine cone", ["pine", "con"])).toBe(true);
    expect(L.matchesNormalizedTokens("pine cone", ["pine", "fir"])).toBe(false);
  });

  it("supplierKey and uniqStrings", () => {
    expect(L.supplierKey(p({ supplier_name: "All-State" }))).toBe("all state");
    expect(L.supplierKey(p())).toBe("");
    expect(L.uniqStrings([" a", "a", null, "", undefined, "b "])).toEqual(["a", "b"]);
  });

  it("searchableCodeText", () => {
    expect(L.searchableCodeText(p({ supplier_sku: "AB-12", upc: "0123", name: "Pine" }))).toBe("ab-12 0123 pine ab 12 0123 pine");
    expect(L.searchableCodeText(p({ name: "", raw_data: { "Item No": "X9" } }))).toBe("x9 x9");
    expect(L.searchableCodeText(p())).toBe("");
  });
});

describe("colour decoding", () => {
  it("looksLikeSupplierColorCode", () => {
    expect(L.looksLikeSupplierColorCode("GO/SI")).toBe(true);
    expect(L.looksLikeSupplierColorCode("RE-WH GR")).toBe(true);
    expect(L.looksLikeSupplierColorCode("Gold")).toBe(false);
    expect(L.looksLikeSupplierColorCode("ABCDE")).toBe(false);
    expect(L.looksLikeSupplierColorCode("")).toBe(false);
    expect(L.looksLikeSupplierColorCode(null)).toBe(false);
  });

  it("extractKnownColorWords matches whole words only", () => {
    expect(L.extractKnownColorWords("Rose Gold glitter")).toEqual(["Gold", "Rose"]);
    expect(L.extractKnownColorWords("Tangerine Mint")).toEqual(["Mint"]);
    expect(L.extractKnownColorWords("")).toEqual([]);
  });

  it("extractKnownColorWords does not match colour words as substrings (regression)", () => {
    // "tan" must not match inside "tangerine"; "red" must not match inside "credit".
    expect(L.extractKnownColorWords("Tangerine")).toEqual([]);
    expect(L.extractKnownColorWords("Store credit")).toEqual([]);
    // A real whole-word match is still found alongside a would-be substring trap.
    expect(L.extractKnownColorWords("Tangerine and Tan ribbon")).toEqual(["Tan"]);
  });

  it("decodeAllstateColorGroup", () => {
    expect(L.decodeAllstateColorGroup("GO/SI")).toEqual(["Gold", "Silver"]);
    expect(L.decodeAllstateColorGroup("cw-wh")).toEqual(["Clear", "White"]);
    expect(L.decodeAllstateColorGroup("ZZ")).toEqual([]);
    expect(L.decodeAllstateColorGroup("")).toEqual([]);
  });

  it("metadataColorLabels", () => {
    expect(L.metadataColorLabels("GO/SI")).toEqual(["Gold", "Silver"]);
    expect(L.metadataColorLabels("Burgundy Velvet")).toEqual(["Burgundy"]);
    expect(L.metadataColorLabels("Velvet")).toEqual([]);
  });

  it("mergeOptionLists dedupes and sorts numerically", () => {
    expect(L.mergeOptionLists(["b", "Item 10"], [null, "Item 2", "b"])).toEqual(["b", "Item 2", "Item 10"]);
  });

  it("productColorLabels", () => {
    expect(L.productColorLabels(p({ color: "Gold/Silver", name: "Glitter Ball" }))).toEqual(["Gold", "Silver"]);
    expect(
      L.productColorLabels(p({ supplier_name: "Allstate", name: "Rose Spray", raw_data: { ColorGrp: "RE/WH", Description: "Ivory Rose Spray" } }))
    ).toEqual(["Ivory", "Red", "Rose", "White"]);
    expect(L.productColorLabels(p({ color: "Champagne mix" }))).toEqual(["Champagne", "Mix"]);
    expect(L.productColorLabels(p())).toEqual([]);
  });

  it("productColorSummary", () => {
    expect(L.productColorSummary(p({ color: "Gold/Silver" }))).toBe("Gold, Silver");
    expect(L.productColorSummary(p({ raw_data: { ColorGrp: "ZZ" } }))).toBe("ZZ");
    expect(L.productColorSummary(p())).toBe("—");
  });
});

describe("product facets", () => {
  it("productCountryLabel", () => {
    expect(L.productCountryLabel(p({ country_of_origin: "CHINA" }))).toBe("China");
    expect(L.productCountryLabel(p({ raw_data: { "Country of Origin": "united states" } }))).toBe("United States");
    expect(L.productCountryLabel(p())).toBeUndefined();
  });

  it("productAvailabilityLabel", () => {
    expect(L.productAvailabilityLabel(p({ availability_note: "Available Today" }))).toBe("Available today");
    expect(L.productAvailabilityLabel(p({ raw_data: { "Avail. Qty": "Within 1-4 months" } }))).toBe("Within 1-4 months");
    expect(L.productAvailabilityLabel(p({ availability_note: "Out of stock" }))).toBe("Sold out / unavailable");
    expect(L.productAvailabilityLabel(p({ availability: "in_stock" }))).toBe("Available today");
    expect(L.productAvailabilityLabel(p({ availability: "out_of_stock" }))).toBe("Sold out / unavailable");
    expect(L.productAvailabilityLabel(p({ availability: "eta" }))).toBe("Future ETA");
    expect(L.productAvailabilityLabel(p({ availability_note: "Available March 2027" }))).toBe("Future ETA");
    expect(L.productAvailabilityLabel(p({ availability_note: "Over 4 months" }))).toBe("Over 4 months");
    expect(L.productAvailabilityLabel(p())).toBeUndefined();
  });

  it("productTypeLabels", () => {
    expect(L.productTypeLabels(p({ name: "Red Velvet Ribbon 2.5in x 10yd", category: "florals" }))).toEqual(["Ribbon"]);
    expect(L.productTypeLabels(p({ name: "Pine Wreath with Pinecones", category: "greenery" }))).toEqual(["Wreath"]);
    expect(L.productTypeLabels(p({ name: "Ceramic Pot", raw_data: { allstate_subcategory: "Flower Pick" } }))).toEqual([
      "Pick", "Floral", "Container",
    ]);
    expect(L.productTypeLabels(p({ name: "Lantern", category: "other" }))).toEqual([]);
  });

  it("productSizeLabels", () => {
    expect(L.productSizeLabels(p({ name: 'Gold Ribbon 2.5" x 10 yd' }))).toEqual(["2.5 in", "2.5 in x 10 yd", "10 yd"]);
    expect(L.productSizeLabels(p({ name: "Pine Garland 9 ft", raw_data: { ProdLength: "108 inches" } }))).toEqual(["9 ft", "108 in"]);
    expect(L.productSizeLabels(p({ name: 'Gold Ribbon 2.5" x 10 yd' }), [])).toEqual(["10 yd"]);
    expect(L.productSizeLabels(p({ name: "Vase" }))).toEqual([]);
    expect(L.productSizeLabels(p())).toEqual([]);
  });

  it("sourceBasePrice / sourceUom / sourceOrderContext", () => {
    expect(L.sourceBasePrice(p({ raw_data: { BasePrice: "12.00" } }))).toBe("12.00");
    expect(L.sourceBasePrice(p({ current_price: 4.5 }))).toBe("$4.50");
    expect(L.sourceBasePrice(p())).toBe("—");
    expect(L.sourceUom(p({ raw_data: { UOM: "DZ" } }))).toBe("DZ");
    expect(L.sourceUom(p({ unit: "stem" }))).toBe("STEM");
    expect(L.sourceOrderContext(p({ moq: 6, raw_data: { BoxQty: 12, CaseQty: "", SugRetail: "9.99" } }))).toEqual([
      ["MinQty", 6], ["BoxQty", 12], ["SugRetail", "9.99"],
    ]);
    expect(L.sourceOrderContext(p({ moq: 0 }))).toEqual([["MinQty", 0]]);
  });

  it("buildProductSearchEntry", () => {
    const product = p({
      id: 7,
      name: 'Gold Ribbon 2.5" x 10 yd',
      supplier_sku: "RB-25",
      supplier_name: "Acme",
      category: "florals",
      color: "Gold",
      country_of_origin: "china",
      availability: "in_stock",
      current_price: 3,
      is_favorited: true,
    });
    const entry = L.buildProductSearchEntry(product);
    expect(entry).toEqual({
      product,
      category: "florals",
      categoryLabel: "Florals",
      supplierName: "Acme",
      productTypes: ["Ribbon"],
      colors: ["Gold"],
      sizes: ["2.5 in", "2.5 in x 10 yd", "10 yd"],
      availability: "Available today",
      country: "China",
      searchText: entry.searchText,
      codeText: L.searchableCodeText(product),
      sortName: 'Gold Ribbon 2.5" x 10 yd',
      isFavorited: true,
    });
    // Without raw ColorGrp the entry text and the visible-text helper are identical.
    expect(entry.searchText).toBe(L.searchableVisibleText(product));
    // The unit pass expands "10 yd" first, then each alias token is expanded again.
    expect(entry.codeText).toBe(
      'rb-25 gold ribbon 2.5" x 10 yd rb 25 gold ribbon 2 5 x 10 yd yard yd yards yd yard yards yd yard 10 yard yd yards yd yard 10 yards yd yard'
    );
  });

  it("searchableVisibleText", () => {
    // No price: sourceBasePrice gives "—", which normalises away.
    expect(L.searchableVisibleText(p({ name: "Pine", category: "trees", unit: "stem" }))).toBe("pine trees stem");
  });
});

describe("image and detail status", () => {
  it("hasNoSupplierImage / hasSupplierPlaceholderImage", () => {
    expect(L.hasNoSupplierImage(p({ raw_data: { image_status: "no_supplier_image" } }))).toBe(true);
    expect(L.hasNoSupplierImage(p())).toBe(false);
    expect(L.hasSupplierPlaceholderImage(p({ photo_url: "https://x/PRICE_UPDATE.GIF" }))).toBe(true);
    expect(L.hasSupplierPlaceholderImage(p({ raw_data: { source_photo_url: "https://x/price_update.gif" } }))).toBe(true);
    expect(L.hasSupplierPlaceholderImage(p({ photo_url: "https://x/a.jpg" }))).toBe(false);
  });

  it("productDisplayImageUrl / productImageSources", () => {
    expect(
      L.productDisplayImageUrl(p({ photo_url: "  ", image_urls: ["", "https://g/1.jpg"], raw_data: { source_photo_url: "https://s.jpg" } }))
    ).toBe("https://g/1.jpg");
    expect(L.productDisplayImageUrl(p({ photo_url: "/a", raw_data: { image_status: "no_supplier_image" } }))).toBeUndefined();
    expect(L.productDisplayImageUrl(p())).toBeUndefined();
    expect(
      L.productImageSources(p({ photo_url: "/a", raw_data: { source_photo_url: "https://s" }, image_urls: ["https://s", "https://g"] }))
    ).toEqual(["/a", "https://s", "https://g"]);
    expect(L.productImageSources(p({ photo_url: "https://x/price_update.gif" }))).toEqual([]);
  });

  it("imageStatus", () => {
    expect(L.imageStatus(p({ raw_data: { image_status: "stored" }, photo_url: "/api/img/1" }))).toBe("stored");
    expect(L.imageStatus(p({ photo_url: "https://x/a.jpg" }))).toBe("visible");
    expect(L.imageStatus(p({ raw_data: { image_status: "failed" } }))).toBe("failed");
    expect(L.imageStatus(p({ raw_data: { image_status: "stored" } }))).toBe("pending");
    expect(L.imageStatus(p({ photo_url: "/a", raw_data: { image_status: "no_supplier_image" } }))).toBe("no_supplier_image");
    expect(L.imageStatus(p({ photo_url: "https://x/price_update.gif" }))).toBe("placeholder");
    expect(L.imageStatus(p())).toBe("pending");
  });

  it("detailStatus", () => {
    expect(L.detailStatus(p({ raw_data: { detail_status: "failed", detail_url: "x" } }))).toBe("failed");
    expect(L.detailStatus(p({ raw_data: { detail_status: "stored" } }))).toBe("stored");
    expect(L.detailStatus(p({ raw_data: { detail_url: "x" } }))).toBe("stored");
    expect(L.detailStatus(p())).toBe("pending");
  });
});
