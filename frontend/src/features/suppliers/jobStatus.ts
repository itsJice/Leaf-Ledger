import type { ScrapeJobOut } from "types";

type BackfillBatch = {
  status: string;
  done: number;
  updated: number;
  stored_images: number;
  failed: number;
  started_at?: string | null;
};

type BackfillRun = {
  status: string;
  batches_run: number;
  total_updated: number;
  remaining_pending?: number | null;
  current_batch?: BackfillBatch | null;
  started_at?: string | null;
};

export function formatLastSynced(dateStr?: string | null): string {
  if (!dateStr) return "Never synced";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return "Never synced";
  const diffMinutes = Math.floor((Date.now() - date.getTime()) / 60000);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMinutes < 1) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function progressKey(auto?: BackfillRun | null, batch?: BackfillBatch | null): string {
  const activeBatch = auto?.current_batch || batch;
  return [
    auto?.status || "idle",
    auto?.batches_run ?? 0,
    auto?.remaining_pending ?? 0,
    activeBatch?.status || "idle",
    activeBatch?.done ?? 0,
    activeBatch?.updated ?? 0,
    activeBatch?.stored_images ?? 0,
    activeBatch?.failed ?? 0,
  ].join("|");
}

export function formatClock(timestamp?: number | null): string {
  if (!timestamp) return "Not checked yet";
  return new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function formatDuration(minutes?: number | null): string {
  if (!minutes || !Number.isFinite(minutes) || minutes <= 0) return "Calculating";
  const rounded = Math.max(1, Math.round(minutes));
  const hours = Math.floor(rounded / 60);
  const remainingMinutes = rounded % 60;
  if (hours <= 0) return `${remainingMinutes} min`;
  if (remainingMinutes === 0) return `${hours} hr`;
  return `${hours} hr ${remainingMinutes} min`;
}

export function parseApiTimestampMs(value?: string | null): number | null {
  if (!value) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const parsed = new Date(hasTimezone ? value : `${value}Z`).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

export function scrapeJobTimestampMs(job?: ScrapeJobOut | null): number | null {
  return parseApiTimestampMs(job?.completed_at || job?.started_at || job?.created_at);
}

export function estimateBackfillEta(
  auto?: BackfillRun | null,
  batch?: BackfillBatch | null,
  fallbackRemaining?: number,
) {
  const activeBatch = auto?.current_batch || batch || null;
  const now = Date.now();
  const runRemaining = typeof auto?.remaining_pending === "number" ? auto.remaining_pending : undefined;
  const remaining = runRemaining !== undefined && fallbackRemaining !== undefined
    ? Math.min(runRemaining, fallbackRemaining)
    : runRemaining ?? fallbackRemaining ?? 0;

  let ratePerMinute = 0;
  const runStartedAt = parseApiTimestampMs(auto?.started_at);
  if (runStartedAt && auto) {
    const processed = (auto.total_updated || 0) + (activeBatch?.updated || 0);
    ratePerMinute = processed / Math.max(1, (now - runStartedAt) / 60000);
  }
  if ((!ratePerMinute || !Number.isFinite(ratePerMinute)) && activeBatch?.started_at && activeBatch.done > 0) {
    const batchStartedAt = parseApiTimestampMs(activeBatch.started_at);
    if (batchStartedAt) ratePerMinute = activeBatch.done / Math.max(1, (now - batchStartedAt) / 60000);
  }

  const minutesRemaining = ratePerMinute > 0 ? remaining / ratePerMinute : null;
  const completionAt = minutesRemaining ? new Date(now + minutesRemaining * 60000) : null;
  return { remaining, ratePerMinute, minutesRemaining, completionAt };
}

export function isProgressStale(auto?: BackfillRun | null, lastProgressAt?: number | null): boolean {
  return auto?.status === "running" && !!lastProgressAt && Date.now() - lastProgressAt > 120000;
}

export function statusColor(status: string): string {
  if (status === "done") return "text-emerald-600";
  if (status === "failed") return "text-red-500";
  if (status === "running") return "text-amber-600";
  return "text-stone-400";
}

export function isPreviewReadyJob(job: ScrapeJobOut): boolean {
  const hasUnimportedProducts = (job.products_found ?? 0) > (job.products_imported ?? 0);
  return !!job.result_key && hasUnimportedProducts && (job.phase === "ready" || job.status === "done");
}

export function isResumableImportJob(job: ScrapeJobOut): boolean {
  const total = job.total_expected ?? job.products_found ?? 0;
  const done = job.products_importing ?? 0;
  return !!job.result_key && job.status === "failed" && done > 0 && total > done;
}

export function chooseSupplierJob(jobs: ScrapeJobOut[]): ScrapeJobOut | null {
  const latest = jobs[0];
  if (!latest) return null;
  if (latest.status === "running" || latest.phase === "importing" || isResumableImportJob(latest)) return latest;
  if (latest.status === "failed") return latest;
  if (latest.phase === "done" && (latest.products_imported ?? 0) > 0) {
    const recoverable = jobs.filter((job) => isPreviewReadyJob(job) || isResumableImportJob(job));
    if (recoverable.length > 0) {
      return recoverable.reduce(
        (best, next) => ((next.products_found ?? 0) > (best.products_found ?? 0) ? next : best),
        recoverable[0],
      );
    }
  }
  return latest;
}
