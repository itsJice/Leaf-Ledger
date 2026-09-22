import { getPins, type Pins } from "utils/jobs";

// Shared, in-memory cache of "which products are pinned to this job, and
// what groups does it have" — keyed by job id, read by every open + button
// (Catalog Search's cards, the product detail modal) instead of each one
// fetching its own copy.
//
// This exists to fix a real bug: the product modal used to call getPins()
// fresh on every open, keyed on the product id, so a click landed while
// `groups` was still its just-mounted empty default. PinToggle reads "the
// job has no groups" the same way whether that's actually true or the fetch
// just hasn't come back yet, so it silently pinned with no group instead of
// asking — the "doesn't always ask" bug. The fix is for a click to never be
// live until real data has loaded at least once; sharing one cache across
// every card and the modal also means that, in practice, it usually already
// has.
//
// A mutation (pin/unpin/move) already gets the fresh `pins` array back in
// its own response — call setCachedPins with it so every other open control
// for that job reflects it on its next render, with no extra round trip.

interface CacheEntry { groups: Pins["groups"]; pins: Pins["pins"] }

const cache = new Map<number, CacheEntry>();
const inflight = new Map<number, Promise<CacheEntry>>();

export function getCachedPins(jobId: number): CacheEntry | undefined {
  return cache.get(jobId);
}

export function loadPins(jobId: number): Promise<CacheEntry> {
  const cached = cache.get(jobId);
  if (cached) return Promise.resolve(cached);
  const pending = inflight.get(jobId);
  if (pending) return pending;
  const p = getPins(jobId)
    .then((r) => {
      const entry = { groups: r.groups, pins: r.pins };
      cache.set(jobId, entry);
      inflight.delete(jobId);
      return entry;
    })
    .catch((e) => {
      inflight.delete(jobId);
      throw e;
    });
  inflight.set(jobId, p);
  return p;
}

export function setCachedPins(jobId: number, pins: Pins["pins"], groups?: Pins["groups"]) {
  const cur = cache.get(jobId);
  cache.set(jobId, { groups: groups ?? cur?.groups ?? [], pins });
}

// What clicking + should do, computed as a pure function of state — the part
// of the old bug that actually mattered. `ready` must be false until the
// job's real pins/groups have loaded at least once; treating "not loaded
// yet" as "loaded, and it happens to have zero groups" is exactly what made
// the popup skip itself unpredictably before.
export interface PinGroupLike { id: number; name: string }
export type PinDecision =
  | { action: "need-job" }
  | { action: "wait" }
  | { action: "unpin" }
  | { action: "pin"; groupId: number | null }
  | { action: "choose"; groups: PinGroupLike[] };

export function decidePinAction(opts: {
  jobId: number | null;
  ready: boolean;
  groupId: number | null;
  groups: PinGroupLike[];
  isPinned: boolean;
}): PinDecision {
  if (!opts.jobId) return { action: "need-job" };
  if (!opts.ready) return { action: "wait" };
  if (opts.isPinned) return { action: "unpin" };
  if (opts.groupId != null || opts.groups.length === 0) return { action: "pin", groupId: opts.groupId };
  return { action: "choose", groups: opts.groups };
}
