import { describe, expect, it } from "vitest";
import { HOME_TILES, nextInstallDay, openCommentCount, visibleTiles } from "../homeTiles";
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

  it("picks today, else the next install day", () => {
    const days = [
      { id: "a", date: "2026-11-15", crewLabel: "Crew 1", lead: { id: "L1" }, crew: [{ id: "L1" }, { id: "p2" }], stops: [1, 2] },
      { id: "b", date: "2026-11-16", crewLabel: "Crew 2", lead: { id: "L2" }, crew: [{ id: "p3" }], stops: [1] },
      { id: "c", date: "2026-11-16", crewLabel: "Crew 1", lead: { id: "L1" }, crew: [{ id: "p2" }], stops: [1, 2, 3] },
    ];
    const next = nextInstallDay(days, "2026-11-16")!;
    expect(next).toMatchObject({ date: "2026-11-16", isToday: true, people: 4, stops: 4 });
    expect(next.crews.map((c) => c.label)).toEqual(["Crew 1", "Crew 2"]);
    expect(nextInstallDay(days, "2026-10-08")).toMatchObject({ date: "2026-11-15", isToday: false, stops: 2 });
    expect(nextInstallDay(days, "2026-12-01")).toBeNull();
  });
});
