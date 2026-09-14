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
// to src/). Layout.tsx's count covers both its addEventListener and
// removeEventListener calls; Clients.tsx's covers its four inline dispatches;
// sidebarNav.ts's is a comment referencing the pattern by name. Shrink this as
// call sites move to notifyProjectsChanged/PROJECTS_CHANGED_EVENT; a literal may
// never be added (to this map, or to a file not already listed here).
const REMAINING_LITERALS_ALLOWLIST: Record<string, number> = {
  "components/Layout.tsx": 2,
  "components/sidebarNav.ts": 1,
  "pages/Clients.tsx": 4,
};

describe("the projects-changed event literal does not creep back into src/", () => {
  for (const file of listSrcFiles()) {
    if (EXCLUDED_FILES.has(file)) continue;
    it(`${file} does not exceed its allowlisted literal occurrences`, () => {
      const count = countOccurrences(readSrc(file), `"${PROJECTS_CHANGED_EVENT}"`);
      expect(count).toBeLessThanOrEqual(REMAINING_LITERALS_ALLOWLIST[file] ?? 0);
    });
  }
});
