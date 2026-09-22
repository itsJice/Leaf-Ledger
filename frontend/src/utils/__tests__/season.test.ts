import { describe, expect, it } from "vitest";
import { currentSeasonLabel, seasonFor, seasonSpanLabel } from "../season";

describe("seasonFor", () => {
  it("names the season for the year its October falls in", () => {
    expect(seasonFor(new Date(2026, 8, 2))).toBe(2026); // 2 Sep 2026: planning
    expect(seasonFor(new Date(2026, 11, 25))).toBe(2026); // Christmas Day
    expect(seasonFor(new Date(2027, 0, 15))).toBe(2026); // 15 Jan 2027: still finishing
    expect(seasonFor(new Date(2027, 0, 31))).toBe(2026);
  });

  it("rolls over on 1 February", () => {
    expect(seasonFor(new Date(2027, 1, 1))).toBe(2027);
    expect(currentSeasonLabel(new Date(2027, 1, 1))).toBe("2027");
  });
});

describe("seasonSpanLabel", () => {
  it("spells out the four months a badge stands for", () => {
    expect(seasonSpanLabel("2026")).toBe("Oct 2026 – Jan 2027");
    expect(seasonSpanLabel("x")).toBe("x");
  });
});
