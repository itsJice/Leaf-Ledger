// Pinned to the same values as backend tests/test_install_times.py.
import { describe, expect, it } from "vitest";
import { diffLabel, fmtClock, fmtDuration, onSiteMinutes, parseClock, TimeParseError } from "../installTimes";

const cases: [string, boolean, string][] = [
  ["10:15p", false, "10:15 PM"],
  ["10:15P", true, "10:15 PM"],
  ["1:30a", true, "1:30 AM"],
  ["1030pm", false, "10:30 PM"],
  ["1030 pm", true, "10:30 PM"],
  ["10:15 PM", false, "10:15 PM"],
  ["10:15 p.m.", false, "10:15 PM"],
  ["9:00 a.m.", false, "9:00 AM"],
  ["10p", false, "10:00 PM"],
  ["12a", false, "12:00 AM"],
  ["12p", true, "12:00 PM"],
  ["noon", true, "12:00 PM"],
  ["midnight", false, "12:00 AM"],
  ["22:15", false, "10:15 PM"],
  ["0015", false, "12:15 AM"],
  ["09:30", true, "9:30 AM"],
  ["10.15p", false, "10:15 PM"],
  ["8", false, "8:00 AM"],
  ["830", false, "8:30 AM"],
  ["12:30", false, "12:30 PM"],
  ["3", false, "3:00 PM"],
  ["6:45", false, "6:45 PM"],
  ["1030", true, "10:30 PM"],
  ["11", true, "11:00 PM"],
  ["12:20", true, "12:20 AM"],
  ["130", true, "1:30 AM"],
  ["5:15", true, "5:15 AM"],
];

describe("parseClock", () => {
  it.each(cases)("%s (night %s) -> %s", (text, night, want) => {
    expect(fmtClock(parseClock(text, night))).toBe(want);
  });

  it("is null for blank", () => {
    expect(parseClock("")).toBeNull();
    expect(parseClock("   ")).toBeNull();
    expect(parseClock(null)).toBeNull();
  });

  it.each(["abc", "25:00", "10:75p", "13p", "0a", "10:15x", "1:2", "12345"])("rejects %s", (text) => {
    expect(() => parseClock(text)).toThrow(TimeParseError);
  });
});

describe("rollover and labels", () => {
  it("treats a Leave before the Arrive as the next day", () => {
    expect(onSiteMinutes(parseClock("10:15p", true), parseClock("12:30a", true))).toBe(135);
    expect(onSiteMinutes(parseClock("8:30"), parseClock("1:15"))).toBe(285);
    expect(onSiteMinutes(9 * 60, 9 * 60)).toBe(1440);
    expect(onSiteMinutes(null, 60)).toBeNull();
  });

  it("formats durations and differences", () => {
    expect(fmtDuration(2.25)).toBe("2 h 15 min");
    expect(fmtDuration(0.75)).toBe("45 min");
    expect(fmtDuration(3)).toBe("3 h");
    expect(diffLabel(2, 2.5)).toEqual({ text: "30 min over (+25%)", tone: "over" });
    expect(diffLabel(4, 3)).toEqual({ text: "1 h under (-25%)", tone: "under" });
    expect(diffLabel(2, 2.05)).toEqual({ text: "on estimate", tone: "even" });
    expect(diffLabel(null, 2)).toBeNull();
  });
});
