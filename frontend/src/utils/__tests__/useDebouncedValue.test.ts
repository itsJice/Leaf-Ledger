import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { scheduleDebouncedCommit } from "../../hooks/useDebouncedValue";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("scheduleDebouncedCommit", () => {
  it("commits after exactly delayMs", () => {
    const commit = vi.fn();
    scheduleDebouncedCommit("a", 350, commit);
    vi.advanceTimersByTime(349);
    expect(commit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(commit).toHaveBeenCalledWith("a");
  });

  it("cleanup cancels a pending commit", () => {
    const commit = vi.fn();
    const cancel = scheduleDebouncedCommit("a", 200, commit);
    vi.advanceTimersByTime(100);
    cancel();
    vi.advanceTimersByTime(1000);
    expect(commit).not.toHaveBeenCalled();
  });
});

/**
 * Simulates an effect keyed on `search`: on every change the previous cleanup
 * runs and a new one is scheduled (including on mount). Returns the observed
 * value at each millisecond.
 */
function simulate(
  keystrokes: Array<[number, string]>,
  horizon: number,
  schedule: (search: string, set: (v: string) => void) => () => void,
  read: (state: string) => string,
  initialState: string,
) {
  let state = initialState;
  let cleanup: (() => void) | null = null;
  let current: string | null = null;
  const seen: string[] = [];
  for (let t = 0; t <= horizon; t++) {
    const key = keystrokes.find(([at]) => at === t);
    if (key && key[1] !== current) {
      current = key[1];
      cleanup?.();
      cleanup = schedule(current, (v) => {
        state = v;
      });
    }
    seen.push(read(state));
    vi.advanceTimersByTime(1);
  }
  return seen;
}

describe("trim-at-read reproduces the inline `setTimeout(() => set(search.trim()), ms)` effects", () => {
  const typing: Array<[number, string]> = [[0, ""], [10, "a"], [100, "ab"], [200, "ab "], [300, "ab c"], [900, " ab c "], [1000, ""]];

  for (const delay of [200, 250, 350]) {
    it(`delay ${delay}ms`, () => {
      const original = simulate(typing, 1600, (s, set) => {
        const t = setTimeout(() => set(s.trim()), delay);
        return () => clearTimeout(t);
      }, (state) => state, "");
      const shared = simulate(typing, 1600, (s, set) => scheduleDebouncedCommit(s, delay, set), (state) => state.trim(), "");
      expect(shared).toEqual(original);
    });
  }
});
