import { afterEach, describe, expect, it, vi } from "vitest";
import "../../test/setup";
import { notifyProjectsChanged, PROJECTS_CHANGED_EVENT } from "../projectsChanged";
import { countOccurrences, readSrc } from "./source-text";

afterEach(() => {
  vi.restoreAllMocks();
});

const DISPATCH = 'window.dispatchEvent(new Event("leaf-ledger-projects-changed"))';

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

  it("every page copy uses exactly this dispatch (no CustomEvent/detail variant)", () => {
    const expected: Record<string, number> = { "pages/Arrangements.tsx": 1, "pages/Library.tsx": 1, "pages/Clients.tsx": 4 };
    for (const [file, count] of Object.entries(expected)) {
      const src = readSrc(file);
      expect(countOccurrences(src, DISPATCH)).toBe(count);
      expect(countOccurrences(src, '"leaf-ledger-projects-changed"')).toBe(count);
    }
    const layout = readSrc("components/Layout.tsx");
    expect(countOccurrences(layout, `addEventListener("${PROJECTS_CHANGED_EVENT}"`)).toBe(1);
  });
});
