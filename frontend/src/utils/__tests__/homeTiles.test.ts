import { describe, expect, it } from "vitest";
import { HOME_TILES, openCommentCount, visibleTiles } from "../homeTiles";
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
