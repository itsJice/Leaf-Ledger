import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_INFINITE_SCROLL_ROOT_MARGIN,
  handleInfiniteScrollEntries,
  InfiniteScrollState,
  observeInfiniteScrollSentinel,
} from "../../hooks/useInfiniteScroll";

class FakeObserver {
  observed: unknown[] = [];
  disconnected = 0;
  constructor(public callback: IntersectionObserverCallback, public options: IntersectionObserverInit) {}
  observe(node: unknown) {
    this.observed.push(node);
  }
  disconnect() {
    this.disconnected++;
  }
  fire(isIntersecting: boolean) {
    this.callback([{ isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
}
const factory = (cb: IntersectionObserverCallback, options: IntersectionObserverInit) =>
  new FakeObserver(cb, options) as unknown as IntersectionObserver;
const node = {} as Element;

describe("observeInfiniteScrollSentinel", () => {
  it("observes with rootMargin only (no threshold), like all three copies", () => {
    const obs = observeInfiniteScrollSentinel(node, null, () => ({ enabled: true }), DEFAULT_INFINITE_SCROLL_ROOT_MARGIN, factory) as unknown as FakeObserver;
    expect(obs.options).toEqual({ rootMargin: "800px 0px" });
    expect(obs.observed).toEqual([node]);
  });

  it("disconnects the previous observer, and returns null for a null node", () => {
    const first = observeInfiniteScrollSentinel(node, null, () => ({ enabled: true }), "0px", factory);
    expect(observeInfiniteScrollSentinel(null, first, () => ({ enabled: true }), "0px", factory)).toBeNull();
    expect((first as unknown as FakeObserver).disconnected).toBe(1);
  });

  it("reads state at fire time", () => {
    const onLoadMore = vi.fn();
    let state: InfiniteScrollState = { enabled: false, onLoadMore };
    const obs = observeInfiniteScrollSentinel(node, null, () => state, "0px", factory) as unknown as FakeObserver;
    obs.fire(true);
    expect(onLoadMore).not.toHaveBeenCalled();
    state = { enabled: true, onLoadMore };
    obs.fire(false);
    expect(onLoadMore).not.toHaveBeenCalled();
    obs.fire(true);
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});

describe("guard mappings reproduce each copy", () => {
  const PAGE_SIZE = 60;

  it("Designs / CatalogSearch: enabled = !loading && itemsLen < total; load(offset + PAGE_SIZE, true)", () => {
    for (const loading of [false, true])
      for (const itemsLen of [0, 59, 60])
        for (const total of [0, 60, 61])
          for (const isIntersecting of [false, true]) {
            const s = { loading, itemsLen, total, offset: 120 };
            const originalLoad = vi.fn();
            // verbatim body of the observer callback in Designs.tsx / CatalogSearch.tsx
            ((entries: Array<{ isIntersecting: boolean }>) => {
              if (!entries[0].isIntersecting) return;
              if (!s.loading && s.itemsLen < s.total) originalLoad(s.offset + PAGE_SIZE, true);
            })([{ isIntersecting }]);
            const sharedLoad = vi.fn();
            handleInfiniteScrollEntries([{ isIntersecting }], {
              enabled: !s.loading && s.itemsLen < s.total,
              onLoadMore: () => sharedLoad(s.offset + PAGE_SIZE, true),
            });
            expect(sharedLoad.mock.calls).toEqual(originalLoad.mock.calls);
          }
  });

  it("Library: enabled = !pageLoading; onLoadMore reveals more cards, else loads the next page", () => {
    for (const pageLoading of [false, true])
      for (const visibleLimit of [40, 80])
        for (const sortedLen of [40, 80])
          for (const canLoadMore of [false, true])
            for (const isIntersecting of [false, true]) {
              const s = { visibleLimit, sortedLen, canLoadMore, pageLoading };
              const log: string[] = [];
              // verbatim body of the observer callback in Library.tsx (setters replaced by log)
              ((entries: Array<{ isIntersecting: boolean }>) => {
                if (!entries[0].isIntersecting) return;
                if (s.pageLoading) return;
                if (s.visibleLimit < s.sortedLen) {
                  log.push("reveal");
                } else if (s.canLoadMore) {
                  log.push("load");
                }
              })([{ isIntersecting }]);
              const shared: string[] = [];
              handleInfiniteScrollEntries([{ isIntersecting }], {
                enabled: !s.pageLoading,
                onLoadMore: () => {
                  if (s.visibleLimit < s.sortedLen) shared.push("reveal");
                  else if (s.canLoadMore) shared.push("load");
                },
              });
              expect(shared).toEqual(log);
            }
  });
});
