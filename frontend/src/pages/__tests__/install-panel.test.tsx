/**
 * The client page's "2026 Install" panel (Comments #23): board date with a
 * Confirmed badge and who/when, preferred time, scheduling restrictions,
 * business or residence, the job's size, and the last three contacts.
 * Office staff only; nothing here is money.
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("utils/me", () => ({ currentMe: vi.fn(() => null), isReadOnly: vi.fn(() => false) }));

import "../../test/setup";
import { currentMe } from "utils/me";
import {
  InstallPanelView, boardDateLabel, canSeeInstallPanel, mdy, todayCT, whenCT, type InstallSummary,
} from "../clients/InstallPanel";

const BASE: InstallSummary = {
  client_id: 1,
  season: "2026",
  board_available: true,
  on_board: true,
  board_date: "2026-11-19",
  board_dates: ["2026-11-19"],
  card_date: "2026-11-19",
  date_mismatch: false,
  crews: [{ day_id: "2026-11-19|Crew 1|0", date: "2026-11-19", crew: "Crew 1", crew_title: "Lesly's crew (Crew 1)",
            lead: "Lesly Ruiz", staffed: 3, stops: 2 }],
  confirmed: true,
  confirmed_at: "2026-11-03T22:02:00+00:00",
  confirmed_by: "Cynthia",
  hold: false,
  not_installing: false,
  visit_type: null,
  property_type: "Residence",
  time_preference: "morning",
  schedule_restrictions: "No Fridays",
  size: { est_hours: 3.5, hours_basis: "2025 real", crew_size: 3, roles: { leads: 1, general: 2 },
          crew_size_basis: "card", crews: 1, crew_days: 1, days: 1, whole_day: false, multi_crew: false },
  contacts: [
    { date: "2026-11-05", method: "call", note: "confirmed 11/19, prefers morning", by: "Cynthia", at: "c" },
    { date: "2026-11-03", method: "voicemail", note: "", by: "Cynthia", at: "b" },
    { date: "2026-11-02", method: "text", note: "sent reminder", by: "Amy", at: "a" },
    { date: "2026-10-30", method: "email", note: "first ask", by: "Amy", at: "0" },
  ],
  contact_count: 4,
  legacy_confirmation_notes: "Called 9/23, ok with 11/19",
};

const html = (s: Partial<InstallSummary> = {}, props = {}) =>
  renderToStaticMarkup(<InstallPanelView summary={{ ...BASE, ...s }} {...props} />);

describe("formatting", () => {
  it("dates and times", () => {
    expect(boardDateLabel("2026-11-19")).toBe("Thu 11/19/2026");
    expect(mdy("2026-11-03")).toBe("11/03/2026");
    expect(whenCT("2026-11-03T22:02:00+00:00")).toBe("Nov 3, 4:02 PM CT");
    expect(whenCT(null)).toBe("");
    expect(todayCT(new Date("2026-11-09T03:00:00Z"))).toBe("2026-11-08"); // still the 8th in Houston
  });
});

describe("InstallPanelView", () => {
  it("shows the confirmed board date, who confirmed it and when, crew and link", () => {
    const out = html({}, { onOpenSchedule: () => {} });
    expect(out).toContain("2026 Install");
    expect(out).toContain("Thu 11/19/2026");
    expect(out).toContain("data-confirmed");
    expect(out).toContain("by Cynthia, Nov 3, 4:02 PM CT");
    expect(out).toContain("Lesly&#x27;s crew (Crew 1) · Lead Lesly Ruiz");
    expect(out).toContain('href="/install-schedule?date=2026-11-19"');
    expect(out).toContain("Open on schedule");
  });

  it("preferred time chip, restrictions and business/residence tag", () => {
    const out = html();
    expect(out).toContain("Early morning");
    expect(out).toContain("No Fridays");
    expect(out).toContain("Residence");
    expect(html({ time_preference: null, schedule_restrictions: null, property_type: "Business" }))
      .toMatch(/No preference[\s\S]*None[\s\S]*Business/);
  });

  it("size is derived: hours, people by role, Whole day / Multi-crew", () => {
    const out = html();
    expect(out).toContain("3.5h");
    expect(out).toContain("3 people (1 lead, 2 general)");
    expect(out).not.toContain("Whole day");
    const big = html({ size: { ...BASE.size, crews: 2, crew_days: 4, days: 2, whole_day: true, multi_crew: true } });
    expect(big).toContain("2 crews · 4 crew-days over 2 days");
    expect(big).toContain("Whole day");
    expect(big).toContain("Multi-crew");
  });

  it("last three contacts, See all, and the legacy note", () => {
    const out = html();
    expect(out).toContain("confirmed 11/19, prefers morning");
    expect(out).toContain("Voicemail");
    expect(out).toContain("sent reminder");
    expect(out).not.toContain("first ask");
    expect(out).toContain("See all (4)");
    expect(out).toContain("Earlier confirmation note:");
    expect(html({}, { initialShowAll: true })).toContain("first ask");
  });

  it("not confirmed, not on board, and the card date fallback", () => {
    expect(html({ confirmed: false, confirmed_at: null, confirmed_by: null })).toContain("Not confirmed yet");
    const off = html({ on_board: false, board_date: null, board_dates: [], crews: [], card_date: "2026-11-13" },
                     { onOpenSchedule: () => {} });
    expect(off).toContain("11/13/2026");
    expect(off).toContain("not on board");
    expect(off).not.toContain("Open on schedule");
    expect(html({ date_mismatch: true, card_date: "2026-11-13" })).toContain("Season card says 11/13/2026. The schedule wins.");
  });

  it("read-only view has no edit, log or save controls", () => {
    const out = html();
    expect(out).not.toContain("Log contact");
    expect(out).not.toContain("Edit scheduling restrictions");
    const staff = html({}, { editable: true, initialLogOpen: true });
    expect(staff).toContain("Edit scheduling restrictions");
    expect(staff).toContain("data-log-form");
    for (const m of ["Call", "Voicemail", "Text", "Email", "In person"]) expect(staff).toContain(`>${m}</button>`);
  });

  it("never shows money or em dashes", () => {
    const out = html({}, { editable: true, initialLogOpen: true });
    expect(out).not.toContain("$");
    expect(out).not.toContain("—");
  });
});

describe("canSeeInstallPanel", () => {
  it.each([
    ["staff", true], ["admin", true], ["super_admin", true],
    ["viewer", false], ["production", false], ["lead", false], ["crew", false],
  ])("%s -> %s", (role, ok) => {
    vi.mocked(currentMe).mockReturnValue({ role } as ReturnType<typeof currentMe>);
    expect(canSeeInstallPanel()).toBe(ok);
  });
});
