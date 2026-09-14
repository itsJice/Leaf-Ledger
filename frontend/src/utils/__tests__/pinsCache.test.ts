import { beforeEach, describe, expect, it, vi } from "vitest";

const getPins = vi.hoisted(() => vi.fn());
vi.mock("../jobs", () => ({ getPins }));

type PinsCacheModule = typeof import("../pinsCache");
let mod: PinsCacheModule;

beforeEach(async () => {
  // The cache is module-scoped: start each test from a fresh module.
  vi.resetModules();
  getPins.mockReset();
  mod = await import("../pinsCache");
});

const groups = [{ id: 1, name: "Tall" }];
const pins = [{ product_id: 10, group_id: 1 }];

describe("pins cache", () => {
  it("is empty until loaded, then keeps only groups + pins", async () => {
    expect(mod.getCachedPins(4)).toBeUndefined();
    getPins.mockResolvedValue({ id: 4, name: "Job", client_name: "C", groups, pins });
    const entry = await mod.loadPins(4);
    expect(getPins).toHaveBeenCalledWith(4);
    expect(entry).toEqual({ groups, pins });
    expect(mod.getCachedPins(4)).toBe(entry);
  });

  it("serves the cached entry without refetching", async () => {
    getPins.mockResolvedValue({ groups, pins });
    const first = await mod.loadPins(4);
    const second = await mod.loadPins(4);
    expect(second).toBe(first);
    expect(getPins).toHaveBeenCalledTimes(1);
  });

  it("shares one in-flight request between concurrent callers", async () => {
    let resolve!: (v: unknown) => void;
    getPins.mockReturnValue(new Promise((r) => (resolve = r)));
    const a = mod.loadPins(4);
    const b = mod.loadPins(4);
    expect(b).toBe(a);
    resolve({ groups, pins });
    await a;
    expect(getPins).toHaveBeenCalledTimes(1);
  });

  it("does not cache failures; the next call retries", async () => {
    getPins.mockRejectedValueOnce(new Error("boom"));
    await expect(mod.loadPins(4)).rejects.toThrow("boom");
    expect(mod.getCachedPins(4)).toBeUndefined();
    getPins.mockResolvedValueOnce({ groups, pins });
    await expect(mod.loadPins(4)).resolves.toEqual({ groups, pins });
    expect(getPins).toHaveBeenCalledTimes(2);
  });

  it("setCachedPins keeps existing groups unless given; defaults to []", async () => {
    mod.setCachedPins(8, pins);
    expect(mod.getCachedPins(8)).toEqual({ groups: [], pins });
    mod.setCachedPins(8, pins, groups);
    mod.setCachedPins(8, []);
    expect(mod.getCachedPins(8)).toEqual({ groups, pins: [] });
    // Seeding the cache makes loadPins skip the fetch.
    await expect(mod.loadPins(8)).resolves.toEqual({ groups, pins: [] });
    expect(getPins).not.toHaveBeenCalled();
  });

  it("invalidatePins forgets the entry", () => {
    mod.setCachedPins(8, pins, groups);
    mod.invalidatePins(8);
    expect(mod.getCachedPins(8)).toBeUndefined();
  });
});

describe("decidePinAction", () => {
  const base = { jobId: 3, ready: true, groupId: null, groups: [] as { id: number; name: string }[], isPinned: false };

  it("walks the decision order", () => {
    expect(mod.decidePinAction({ ...base, jobId: null })).toEqual({ action: "need-job" });
    expect(mod.decidePinAction({ ...base, jobId: 0 })).toEqual({ action: "need-job" });
    expect(mod.decidePinAction({ ...base, ready: false, isPinned: true })).toEqual({ action: "wait" });
    expect(mod.decidePinAction({ ...base, isPinned: true, groups })).toEqual({ action: "unpin" });
    expect(mod.decidePinAction({ ...base, groupId: 5, groups })).toEqual({ action: "pin", groupId: 5 });
    expect(mod.decidePinAction({ ...base, groupId: 0, groups })).toEqual({ action: "pin", groupId: 0 });
    expect(mod.decidePinAction(base)).toEqual({ action: "pin", groupId: null });
  });

  it("asks to choose when the job has groups and none is selected", () => {
    const d = mod.decidePinAction({ ...base, groups });
    expect(d).toEqual({ action: "choose", groups });
    expect((d as { groups: unknown }).groups).toBe(groups);
  });
});
