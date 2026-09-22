import { afterEach, describe, expect, it, vi } from "vitest";
import "../../test/setup";
import { notifyProjectsChanged, PROJECTS_CHANGED_EVENT } from "../projectsChanged";
import { countOccurrences, readSrc } from "./source-text";
import { listSrcFiles } from "./list-src-files";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("notifyProjectsChanged", () => {
  it("dispatches one plain Event named leaf-ledger-projects-changed", () => {
    const spy = vi.spyOn(window, "dispatchEvent");
    notifyProjectsChanged();
    expect(spy).toHaveBeenCalledTimes(1);
    const event = spy.mock.calls[0][0];
    expect(event.constructor).toBe(Event);
    expect(event.type).toBe("leaf-ledger-projects-changed");
    expect(PROJECTS_CHANGED_EVENT).toBe("leaf-ledger-projects-changed");
  });
});

// Files excluded from the scan below: constants.ts and utils/projectsChanged.ts
// define/export the event; __tests__ files are already excluded by listSrcFiles.
const EXCLUDED_FILES = new Set(["constants.ts", "utils/projectsChanged.ts"]);

// How many raw occurrences of the quoted "leaf-ledger-projects-changed" literal
// legitimately remain outside utils/projectsChanged.ts, keyed by file (relative
// to src/). Nothing remains: Layout.tsx uses PROJECTS_CHANGED_EVENT, Clients.tsx
// uses notifyProjectsChanged(), and sidebarNav.ts's comment references the
// constant by name instead of the literal. A literal may never be added (to
// this map, or to a file not already listed here).
const REMAINING_LITERALS_ALLOWLIST: Record<string, number> = {};

describe("the projects-changed event literal does not creep back into src/", () => {
  for (const file of listSrcFiles()) {
    if (EXCLUDED_FILES.has(file)) continue;
    it(`${file} does not exceed its allowlisted literal occurrences`, () => {
      const count = countOccurrences(readSrc(file), `"${PROJECTS_CHANGED_EVENT}"`);
      expect(count).toBeLessThanOrEqual(REMAINING_LITERALS_ALLOWLIST[file] ?? 0);
    });
  }
});
