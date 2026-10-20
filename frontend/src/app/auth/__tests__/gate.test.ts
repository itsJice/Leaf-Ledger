/**
 * Who may open which page (app/auth/gate.ts, used by RoleGate). Help >
 * How-to videos (/help) is open to every signed-in role, including the field
 * logins (lead, crew) and the warehouse display (viewer).
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));

import { gateRedirect } from "../gate";

const staff = { pages: null, home: null, viewOnly: false, fieldOnly: false };
const field = { ...staff, fieldOnly: true };
const display = { ...staff, viewOnly: true };
const production = { ...staff, pages: ["/search", "/jobs", "/help"], home: "/search" };

describe("gateRedirect", () => {
  it("lets every kind of login open /help", () => {
    for (const me of [staff, field, display, production]) {
      expect(gateRedirect(me, "/help")).toBeNull();
    }
  });

  it("keeps field logins on their shifts, a form and Help", () => {
    expect(gateRedirect(field, "/shifts")).toBeNull();
    expect(gateRedirect(field, "/forms/product-request")).toBeNull();
    expect(gateRedirect(field, "/forms/product-request/responses")).toBe("/shifts");
    expect(gateRedirect(field, "/")).toBe("/shifts");
    expect(gateRedirect(field, "/clients")).toBe("/shifts");
    expect(gateRedirect(field, "/help/other")).toBe("/shifts");
  });

  it("keeps the display on the schedule, its Changes list and Help", () => {
    expect(gateRedirect(display, "/install-calendar")).toBeNull();
    expect(gateRedirect(display, "/install-changes")).toBeNull();
    expect(gateRedirect(display, "/jobs")).toBe("/install-schedule");
  });

  it("keeps production on its page list", () => {
    expect(gateRedirect(production, "/jobs/12")).toBeNull();
    expect(gateRedirect(production, "/")).toBe("/search");
    expect(gateRedirect({ ...production, pages: ["/search"] }, "/help")).toBe("/search");
  });

  it("leaves office logins alone", () => {
    expect(gateRedirect(staff, "/settings")).toBeNull();
  });
});
