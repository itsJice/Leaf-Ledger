// Recursively lists .ts/.tsx files under src/, for guard tests that scan the
// whole tree for leftover literals (see cache-keys.test.ts, projectsChanged.test.ts).
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC_ROOT = fileURLToPath(new URL("../../", import.meta.url));

/** Paths (relative to src/, forward-slashed) of every .ts/.tsx file under src/. */
export function listSrcFiles(excludeDirs: string[] = ["__tests__"]): string[] {
  const out: string[] = [];
  (function walk(dir: string) {
    for (const entry of readdirSync(dir)) {
      if (excludeDirs.includes(entry)) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith(".ts") || entry.endsWith(".tsx")) out.push(relative(SRC_ROOT, full).split("\\").join("/"));
    }
  })(SRC_ROOT);
  return out;
}
