/**
 * Install Schedule, Calendar, Staffing and Roster are four nav entries but
 * ONE page (user, 2026-10-08). Switching between them must not reload or
 * remount the schedule iframe: that is what keeps the switch instant, keeps
 * the scroll and open popups, and never drops the page's pending save.
 *
 * React keeps a component (and the iframe it renders) mounted when the same
 * element type stays at the same place in the tree. With react-router that
 * holds when every one of the four URLs matches through the SAME parent
 * route object whose element is <InstallSchedule>, and the child routes
 * render nothing of their own. These tests pin that route shape (vitest runs
 * without a DOM here, so the shape is what we can check; the mount itself is
 * checked by hand in the browser and on the iPhone simulator).
 */
import { describe, expect, it, vi } from "vitest";
import { matchRoutes } from "react-router-dom";

vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));

import "../../test/setup";
import { userRoutes } from "../../user-routes";
import {
  INSTALL_PATHS,
  isInstallPath,
  legacyView,
  pathForView,
  viewForPath,
  withHostFlags,
} from "utils/installViews";

describe("the four schedule routes share one mounted page", () => {
  const matched = INSTALL_PATHS.map((path) => matchRoutes(userRoutes, path));

  it("every path matches", () => {
    matched.forEach((m, i) => expect(m, INSTALL_PATHS[i]).not.toBeNull());
  });

  it("through the same parent route, so switching never remounts the iframe", () => {
    const parents = matched.map((m) => m![0].route);
    parents.forEach((p) => expect(p).toBe(parents[0]));
    expect(parents[0].path).toBeUndefined(); // pathless: only its children name URLs
    const el = parents[0].element as { type?: unknown } | undefined;
    expect(el?.type).toBeTruthy();
  });

  it("whose children render nothing of their own", () => {
    matched.forEach((m) => {
      expect(m).toHaveLength(2);
      expect(m![1].route.element).toBeUndefined();
      expect(m![1].route.Component).toBeUndefined();
    });
  });

  it("and other pages don't go through it", () => {
    const parent = matched[0]![0].route;
    for (const path of ["/", "/jobs", "/shifts", "/clients"]) {
      const m = matchRoutes(userRoutes, path);
      expect(m?.[0].route).not.toBe(parent);
    }
  });
});

describe("route <-> view", () => {
  it("maps each route to the page's own view names and back", () => {
    expect(INSTALL_PATHS.map(viewForPath)).toEqual(["days", "cal", "staff", "roster"]);
    for (const path of INSTALL_PATHS) expect(pathForView(viewForPath(path))).toBe(path);
    expect(viewForPath("/install-calendar/")).toBe("cal");
    expect(isInstallPath("/install-roster")).toBe(true);
    expect(isInstallPath("/shifts")).toBe(false);
  });

  it("keeps old tab links working", () => {
    expect(legacyView("?view=calendar", "")).toBe("cal");
    expect(legacyView("?tab=Roster", "")).toBe("roster");
    expect(legacyView("", "#staffing")).toBe("staff");
    expect(legacyView("", "")).toBeNull();
    expect(legacyView("?view=nonsense", "")).toBeNull();
  });
});

describe("startup flags", () => {
  it("tell the page it's hosted and which view to open on", () => {
    const out = withHostFlags("<html><head></head></html>", "cal", false, false);
    expect(out).toContain('<head><script>window.TBDG_HOSTED=true;window.TBDG_VIEW="cal";</script>');
    expect(out).not.toContain("TBDG_VIEWONLY");
  });

  it("keep the view-only and display flags", () => {
    const out = withHostFlags("<html><head></head></html>", "days", true, true);
    expect(out).toContain("window.TBDG_VIEWONLY=true;window.TBDG_DISPLAY=true;");
  });
});
