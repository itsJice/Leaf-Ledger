/**
 * Which Christmas season a date belongs to -- the browser-side twin of
 * backend/app/libs/season.py, and the same rule: a season runs October
 * through the following January and is named for the year its October
 * falls in, so January still belongs to the season that started the
 * previous autumn. The rollover is 1 February.
 *
 *   2026-09-02 -> 2026   (planning the coming season)
 *   2027-01-15 -> 2026   (still finishing it)
 *   2027-02-01 -> 2027   (rolled over)
 */
export const ROLLOVER_MONTH = 2; // February, 1-based

export function seasonFor(date: Date = new Date()): number {
  const month = date.getMonth() + 1;
  return month >= ROLLOVER_MONTH ? date.getFullYear() : date.getFullYear() - 1;
}

export function currentSeasonLabel(date: Date = new Date()): string {
  return String(seasonFor(date));
}

/** "2026" -> "Oct 2026 – Jan 2027", the span a season badge stands for. */
export function seasonSpanLabel(season: string): string {
  const y = Number(season);
  if (!Number.isFinite(y)) return season;
  return `Oct ${y} – Jan ${y + 1}`;
}
