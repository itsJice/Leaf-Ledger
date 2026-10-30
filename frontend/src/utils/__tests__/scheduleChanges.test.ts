import { describe, expect, it, vi } from "vitest";
import { matchRoutes } from "react-router-dom";

vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));

import "../../test/setup";
import { userRoutes } from "../../user-routes";
import { NAV_GROUPS } from "components/sidebarNav";
import { isInstallPath } from "utils/installViews";
import {
  CHANGES_PATH,
  EMPTY_FILTERS,
  TYPE_FILTERS,
  badgeText,
  centralToday,
  changesQuery,
  dayHeading,
  groupByDay,
  hasFilters,
  mergePages,
  toggleType,
} from "utils/scheduleChanges";
import type { ChangeEvent } from "utils/scheduleChanges";

function ev(id: string, day: string, isNew = false): ChangeEvent {
  return {
    id, day, isNew, kind: "moved", type: "moves", text: `change ${id}`, clients: [], dates: [],
    time: "4:02 PM", at: `${day}T21:02:00+00:00`, by: "Justice Wenz", mine: false,
  };
}

describe("the Changes entry", () => {
  it("sits in the Installs menu after the schedule's views", () => {
    const installs = NAV_GROUPS.find((g) => g.id === "installs")!;
    expect(installs.items.map((i) => i.path)).toEqual([
      "/install-schedule", "/install-calendar", "/install-staffing", "/install-roster",
      "/install-trailer-loader", CHANGES_PATH,
    ]);
    expect(installs.items[4].label).toBe("Trailer Loader");
    expect(installs.items[5].label).toBe("Install Changes");
  });

  it("is its own page, not a view of the schedule iframe", () => {
    const m = matchRoutes(userRoutes, CHANGES_PATH);
    expect(m).toHaveLength(1);
    expect(m![0].route.path).toBe(CHANGES_PATH);
    expect(isInstallPath(CHANGES_PATH)).toBe(false);
  });
});

describe("filters to a query", () => {
  it("sends only what is set", () => {
    expect(changesQuery(EMPTY_FILTERS)).toBe("limit=50");
    expect(changesQuery({ q: " jinks ", from: "2026-10-01", to: "2026-10-12", types: ["moves", "holds"] }, "13-0", 25))
      .toBe("limit=25&before=13-0&q=jinks&from=2026-10-01&to=2026-10-12&type=moves%2Cholds");
  });

  it("asks for test saves only when the toggle is on", () => {
    expect(changesQuery(EMPTY_FILTERS, null, 50, false)).toBe("limit=50");
    expect(changesQuery(EMPTY_FILTERS, "h9-0", 50, true)).toBe("limit=50&tests=1&before=h9-0");
  });

  it("knows when any filter is on", () => {
    expect(hasFilters(EMPTY_FILTERS)).toBe(false);
    expect(hasFilters({ ...EMPTY_FILTERS, q: "  " })).toBe(false);
    expect(hasFilters({ ...EMPTY_FILTERS, types: ["staffing"] })).toBe(true);
    expect(hasFilters({ ...EMPTY_FILTERS, to: "2026-10-12" })).toBe(true);
  });

  it("toggles type chips", () => {
    expect(toggleType([], "holds")).toEqual(["holds"]);
    expect(toggleType(["holds", "moves"], "holds")).toEqual(["moves"]);
  });

  it("offers every type the server knows", () => {
    expect(TYPE_FILTERS.map((t) => t.type)).toEqual(
      ["moves", "adds", "holds", "approvals", "staffing", "locks", "dates"],
    );
  });
});

describe("grouping by day", () => {
  const today = "2026-10-12";

  it("labels today, yesterday, then weekday and date", () => {
    expect(dayHeading("2026-10-12", today)).toBe("Today");
    expect(dayHeading("2026-10-11", today)).toBe("Yesterday");
    expect(dayHeading("2026-10-09", today)).toBe("Fri 10/9");
    expect(dayHeading("2025-12-30", today)).toBe("Tue 12/30/2025");
  });

  it("keeps newest-first order and counts what's new per day", () => {
    const groups = groupByDay(
      [ev("3-0", "2026-10-12", true), ev("2-1", "2026-10-12", true), ev("2-0", "2026-10-12"), ev("1-0", "2026-10-09")],
      today,
    );
    expect(groups.map((g) => [g.heading, g.events.length, g.newCount])).toEqual([
      ["Today", 3, 2],
      ["Fri 10/9", 1, 0],
    ]);
  });

  it("joins a further page without repeats", () => {
    const shown = [ev("3-0", today), ev("2-0", today)];
    expect(mergePages(shown, [ev("2-0", today), ev("1-0", today)]).map((e) => e.id)).toEqual(["3-0", "2-0", "1-0"]);
  });

  it("works out today in Central time", () => {
    // 2:30 AM UTC on the 13th is still the evening of the 12th in Houston.
    expect(centralToday(new Date("2026-10-13T02:30:00Z"))).toBe("2026-10-12");
  });
});

describe("the menu badge", () => {
  it("shows a count only when there is one", () => {
    expect(badgeText(0)).toBe("");
    expect(badgeText(3)).toBe("3");
    expect(badgeText(140)).toBe("99+");
  });
});
