import { describe, expect, it } from "vitest";
import { SHIPPING_SPEEDS, formatPhone, gmailComposeHref, shippingSpeedLabel, telHref } from "../contactFormat";

describe("formatPhone", () => {
  it("formats 10-digit and 1+10-digit numbers", () => {
    expect(formatPhone("9523732020")).toBe("(952) 373-2020");
    expect(formatPhone(" (952) 373-2020 ")).toBe("(952) 373-2020");
    expect(formatPhone("952.373.2020")).toBe("(952) 373-2020");
    expect(formatPhone("19523732020")).toBe("+1 (952) 373-2020");
    expect(formatPhone("+1 952 373 2020")).toBe("+1 (952) 373-2020");
  });

  it("returns anything else trimmed but otherwise untouched", () => {
    expect(formatPhone("29523732020")).toBe("29523732020");
    expect(formatPhone("+44 20 7946 0958")).toBe("+44 20 7946 0958");
    expect(formatPhone("555-1234")).toBe("555-1234");
    expect(formatPhone("  952.373.2020 x12 ")).toBe("952.373.2020 x12");
    expect(formatPhone("call main line")).toBe("call main line");
  });

  it("returns empty string for empty/null/undefined", () => {
    expect(formatPhone("")).toBe("");
    expect(formatPhone("   ")).toBe("");
    expect(formatPhone(null)).toBe("");
    expect(formatPhone(undefined)).toBe("");
  });
});

describe("telHref", () => {
  it("keeps only digits and plus signs", () => {
    expect(telHref("(952) 373-2020")).toBe("tel:9523732020");
    expect(telHref("+44 20 7946 0958")).toBe("tel:+442079460958");
    // Extensions are glued onto the number.
    expect(telHref("952.373.2020 x12")).toBe("tel:952373202012");
    expect(telHref(null)).toBe("tel:");
    expect(telHref(undefined)).toBe("tel:");
  });
});

describe("gmailComposeHref", () => {
  it("encodes the trimmed address and optional subject", () => {
    expect(gmailComposeHref(" a+b@x.com ", "Hi & bye")).toBe("https://mail.google.com/mail/?view=cm&fs=1&to=a%2Bb%40x.com&su=Hi%20%26%20bye");
    expect(gmailComposeHref("a@x.com")).toBe("https://mail.google.com/mail/?view=cm&fs=1&to=a%40x.com");
    expect(gmailComposeHref("a@x.com", "")).toBe("https://mail.google.com/mail/?view=cm&fs=1&to=a%40x.com");
    expect(gmailComposeHref(null)).toBe("https://mail.google.com/mail/?view=cm&fs=1&to=");
  });
});

describe("shipping speeds", () => {
  it("pins the vocabulary", () => {
    expect(SHIPPING_SPEEDS).toEqual([
      { value: "next_day", label: "Ships next day" },
      { value: "2_3_days", label: "2–3 days" },
      { value: "about_1_week", label: "About a week" },
      { value: "2_weeks_plus", label: "2+ weeks — needs prompting" },
      { value: "varies", label: "Varies" },
    ]);
  });

  it("shippingSpeedLabel maps known values, passes unknown through, blanks empty", () => {
    expect(shippingSpeedLabel("next_day")).toBe("Ships next day");
    expect(shippingSpeedLabel("2_weeks_plus")).toBe("2+ weeks — needs prompting");
    expect(shippingSpeedLabel("by pigeon")).toBe("by pigeon");
    expect(shippingSpeedLabel("")).toBe("");
    expect(shippingSpeedLabel(null)).toBe("");
    expect(shippingSpeedLabel(undefined)).toBe("");
  });
});
