import { describe, expect, it } from "vitest";
import { METRIC_CHEAT, findMetricConversions, metricHintText, mmToInches } from "../measurements";

describe("mmToInches", () => {
  it("uses the trade chart for listed sizes", () => {
    expect([40, 50, 60, 70, 76, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 200, 210, 250, 300].map(mmToInches)).toEqual([
      1.5, 2, 2.5, 2.75, 3, 3, 3.5, 4, 4.25, 4.75, 5, 5.5, 6, 6.25, 6.75, 7, 8, 8.25, 10, 12,
    ]);
  });

  it("rounds tiny gauges (< 25mm) to 0.1 and others to 0.25", () => {
    expect(mmToInches(5)).toBe(0.2);
    expect(mmToInches(24)).toBe(0.9);
    expect(mmToInches(25)).toBe(1);
    expect(mmToInches(33)).toBe(1.25);
    expect(mmToInches(101)).toBe(4);
  });

  it("handles zero and negatives arithmetically", () => {
    expect(mmToInches(0)).toBe(0);
    expect(mmToInches(-10)).toBe(-0.4);
  });
});

describe("findMetricConversions", () => {
  it("converts each unit", () => {
    expect(findMetricConversions("Ornament 100mm shatterproof")).toEqual([{ raw: "100mm", imperial: "4″" }]);
    expect(findMetricConversions("Wreath 60cm")).toEqual([{ raw: "60cm", imperial: "23.5″" }]);
    expect(findMetricConversions("Garland 2.7m long")).toEqual([{ raw: "2.7m", imperial: "8′10″" }]);
    expect(findMetricConversions("Pole 3m")).toEqual([{ raw: "3m", imperial: "9′10″" }]);
    expect(findMetricConversions("Ribbon 0.5m")).toEqual([{ raw: "0.5m", imperial: "1′8″" }]);
    expect(findMetricConversions("Bag 500g / 1.5kg")).toEqual([
      { raw: "500g", imperial: "17.64 oz" },
      { raw: "1.5kg", imperial: "3.31 lb" },
    ]);
    expect(findMetricConversions("Spray 250ml")).toEqual([{ raw: "250ml", imperial: "8.45 fl oz" }]);
  });

  it("is case-insensitive, drops the space from raw, and de-duplicates", () => {
    expect(findMetricConversions("Ball 80 MM and 80mm again, 5mm hook")).toEqual([
      { raw: "80mm", imperial: "3″" },
      { raw: "5mm", imperial: "0.2″" },
    ]);
  });

  it("ignores litres, inches and empty input; is repeatable (regex lastIndex reset)", () => {
    expect(findMetricConversions("100 L lights")).toEqual([]);
    expect(findMetricConversions("size 4in")).toEqual([]);
    expect(findMetricConversions("")).toEqual([]);
    expect(findMetricConversions(null)).toEqual([]);
    expect(findMetricConversions(undefined)).toEqual([]);
    expect(findMetricConversions("100mm")).toEqual(findMetricConversions("100mm"));
  });
});

describe("metricHintText", () => {
  it("joins up to `max` conversions (default 3)", () => {
    expect(metricHintText("10mm 20mm 30mm 40mm")).toBe("10mm ≈ 0.4″ · 20mm ≈ 0.8″ · 30mm ≈ 1.25″");
    expect(metricHintText("10mm 20mm 30mm", 1)).toBe("10mm ≈ 0.4″");
    expect(metricHintText("Bag 500g / 1.5kg")).toBe("500g ≈ 17.64 oz · 1.5kg ≈ 3.31 lb");
  });

  it("returns null when nothing metric is found", () => {
    expect(metricHintText("100 L lights")).toBeNull();
    expect(metricHintText(null)).toBeNull();
  });

  it("pins the cheat sheet", () => {
    expect(METRIC_CHEAT).toBe("Ornament sizes — 80mm≈3″ · 100mm≈4″ · 120mm≈4.75″ · 150mm≈6″ · 200mm≈8″");
  });
});
