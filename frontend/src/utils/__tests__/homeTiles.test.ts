import { describe, expect, it } from "vitest";
import { HOME_TILES, installNotesLine, openCommentCount, scheduleDayHref, todayHeading, visibleTiles } from "../homeTiles";
import { userRoutes } from "../../user-routes";
import { INSTALL_PATHS } from "../installViews";

describe("home tiles", () => {
  it("every tile points at a real route", () => {
    const routes = new Set<string>(INSTALL_PATHS);
    userRoutes.forEach((r) => r.path && routes.add(r.path));
    for (const t of HOME_TILES) {
      const ok = routes.has(t.path) || (t.path.startsWith("/forms/") && routes.has("/forms/:slug/responses"));
      expect(ok, t.path).toBe(true);
    }
  });

  it("hides admin tiles from non-admins and respects restricted pages", () => {
    const staff = visibleTiles({ isAdmin: false, pages: null }).map((t) => t.id);
    expect(staff).not.toContain("quotes");
    expect(staff).toContain("schedule");
    const admin = visibleTiles({ isAdmin: true, pages: null }).map((t) => t.id);
    expect(admin).toContain("quotes");
    const prod = visibleTiles({ isAdmin: false, pages: ["/search", "/jobs"] }).map((t) => t.id);
    expect(prod).toEqual(["search", "jobs"]);
  });

  it("counts open comments", () => {
    expect(openCommentCount([{ status: "new" }, { status: "done" }, { status: "new" }])).toBe(2);
    expect(openCommentCount(null)).toBe(0);
  });
});

describe("Today strip: install notes", () => {
  it("says how many stops have install notes, and nothing when none", () => {
    expect(installNotesLine(2)).toBe("2 stops have install notes");
    expect(installNotesLine(1)).toBe("1 stop has install notes");
    expect(installNotesLine(0)).toBe("");
    expect(installNotesLine(undefined)).toBe("");
  });

  it("links to the schedule opened on that day", () => {
    expect(scheduleDayHref("2026-11-10")).toBe("/install-schedule?date=2026-11-10");
    expect(scheduleDayHref(undefined)).toBe("/install-schedule");
    expect(scheduleDayHref("11/10/2026")).toBe("/install-schedule");
  });
});

describe("Today strip: install or takedown", () => {
  it("calls a January day a takedown and a December day an install", () => {
    expect(todayHeading({ date: "2027-01-02", isToday: false })).toBe("Next takedown day");
    expect(todayHeading({ date: "2027-01-02", isToday: true })).toBe("Takedown today");
    expect(todayHeading({ date: "2026-12-26", isToday: false })).toBe("Next takedown day");
    expect(todayHeading({ date: "2026-12-10", isToday: false })).toBe("Next install day");
    expect(todayHeading({ date: "2026-12-25", isToday: true })).toBe("Installing today");
    expect(todayHeading(null)).toBe("Next install day");
  });
});
