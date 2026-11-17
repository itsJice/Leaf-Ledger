import { useEffect } from "react";
import { reportEvent } from "utils/eventLog";

export const STUCK_AFTER_MS = 15_000;

/**
 * Logs "page stuck loading" when a loading state is still showing after
 * 15 seconds. A failed load usually shows up as a failed request too; this
 * catches the ones that never answer at all (the 11/15 outage looked like
 * this from the browser).
 */
export function useStuckCheck(loading: boolean, what: string): void {
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    const t = window.setTimeout(() => {
      reportEvent({
        kind: "stuck",
        message: `${what} still loading after ${Math.round((Date.now() - started) / 1000)}s`,
        detail: { waited_ms: Date.now() - started },
      });
    }, STUCK_AFTER_MS);
    return () => window.clearTimeout(t);
  }, [loading, what]);
}
