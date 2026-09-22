// Helpers so tests can prove an oracle copy still matches the page source text.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Read a file relative to `src/`. */
export function readSrc(relativeToSrc: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${relativeToSrc}`, import.meta.url)), "utf8");
}

/** The text from the first `start` marker through the next `end` marker (inclusive). */
export function snippet(source: string, start: string, end: string): string {
  const i = source.indexOf(start);
  if (i < 0) throw new Error(`start marker not found: ${start}`);
  const j = source.indexOf(end, i);
  if (j < 0) throw new Error(`end marker not found after: ${start}`);
  return source.slice(i, j + end.length);
}

/** Number of non-overlapping occurrences of `needle` in `source`. */
export function countOccurrences(source: string, needle: string): number {
  return source.split(needle).length - 1;
}
