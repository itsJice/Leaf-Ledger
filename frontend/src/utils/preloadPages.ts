/**
 * Warm every page chunk once the app is idle after sign-in.
 *
 * Pages are code-split (see user-routes.tsx), so the first visit to a tab
 * downloads that tab's chunk before it can render. The router's Suspense
 * fallback keeps the sidebar on screen while that happens, but the best wait
 * is no wait: fetching the chunks in the background right after the shell
 * mounts means every tab is already in the browser cache by the time it is
 * clicked. The glob resolves to the very same modules React.lazy imports, so
 * Vite emits one chunk per page and this simply fetches it early.
 *
 * Runs in an idle callback so it never competes with the page the user is
 * actually looking at; failures are ignored (the real navigation will retry
 * and, on a stale-chunk error, lazyWithReload handles recovery).
 */
const pageLoaders = import.meta.glob("../pages/*.tsx");

let started = false;

export function preloadPagesWhenIdle(): void {
  if (started || typeof window === "undefined") return;
  started = true;
  const run = () => {
    for (const load of Object.values(pageLoaders)) {
      load().catch(() => {});
    }
  };
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(run, { timeout: 4000 });
  } else {
    window.setTimeout(run, 1500);
  }
}
