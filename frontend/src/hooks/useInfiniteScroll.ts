import { useCallback, useRef } from "react";

/** Every copy triggers ~800px before the sentinel scrolls into view. */
export const DEFAULT_INFINITE_SCROLL_ROOT_MARGIN = "800px 0px";

export type InfiniteScrollState = { enabled: boolean; onLoadMore?: () => void };

type ObserverFactory = (callback: IntersectionObserverCallback, options: IntersectionObserverInit) => IntersectionObserver;

/** Observer callback body: load when the first entry intersects and loading is enabled. Returns whether it loaded. */
export function handleInfiniteScrollEntries(
  entries: ReadonlyArray<Pick<IntersectionObserverEntry, "isIntersecting">>,
  state: InfiniteScrollState,
): boolean {
  if (!entries[0].isIntersecting) return false;
  if (!state.enabled) return false;
  state.onLoadMore?.();
  return true;
}

/**
 * Ref-callback body: disconnect the previous observer, then observe `node` (if any)
 * with a fresh one that reads `getState()` at fire time. Returns the new observer.
 */
export function observeInfiniteScrollSentinel(
  node: Element | null,
  previous: IntersectionObserver | null,
  getState: () => InfiniteScrollState,
  rootMargin: string,
  createObserver: ObserverFactory = (callback, options) => new IntersectionObserver(callback, options),
): IntersectionObserver | null {
  if (previous) previous.disconnect();
  if (!node) return null;
  const observer = createObserver((entries) => {
    handleInfiniteScrollEntries(entries, getState());
  }, { rootMargin });
  observer.observe(node);
  return observer;
}

/**
 * Returns a ref callback for the infinite-scroll sentinel.
 *
 * `enabled` and `onLoadMore` are read when the observer fires, so the callback
 * stays stable across renders. `resetKey`, if given, rebuilds the observer when
 * it changes. Designs/CatalogSearch pass `load` here to keep their original
 * `useCallback(..., [load])` re-observe behaviour.
 */
export function useInfiniteScroll({
  enabled,
  onLoadMore,
  rootMargin = DEFAULT_INFINITE_SCROLL_ROOT_MARGIN,
  resetKey,
}: {
  enabled: boolean;
  onLoadMore?: () => void;
  rootMargin?: string;
  resetKey?: unknown;
}): (node: Element | null) => void {
  const stateRef = useRef<InfiniteScrollState>({ enabled, onLoadMore });
  stateRef.current = { enabled, onLoadMore };
  const observerRef = useRef<IntersectionObserver | null>(null);
  return useCallback(
    (node: Element | null) => {
      observerRef.current = observeInfiniteScrollSentinel(node, observerRef.current, () => stateRef.current, rootMargin);
    },
    // resetKey is deliberately a dependency only: changing it re-creates the observer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rootMargin, resetKey],
  );
}
