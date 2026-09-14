/**
 * localStorage JSON "speed caches". Every failure (no storage, corrupt JSON,
 * quota exceeded) is swallowed: a cache must never block the app.
 *
 * Shape validation stays with the caller. `readJsonCache` only parses, so a
 * stored `"null"` or `"5"` comes back as-is; callers keep their own
 * `Array.isArray(parsed?.x)` checks.
 */

/**
 * Parsed JSON at `key`, or `fallback` when the key is missing/empty, the JSON is
 * corrupt, or storage is unavailable.
 *
 * Matches both inline idioms: `raw ? JSON.parse(raw) : fallback` and
 * `JSON.parse(getItem(key) || "null")` followed by a shape check.
 */
export function readJsonCache<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

/** `JSON.stringify(value)` into `key`, ignoring any storage error. Same as Layout.tsx `writeJsonCache`. */
export function writeJsonCache(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Cache writes should never block the app.
  }
}

/**
 * Write `{ ...fields, cachedAt: Date.now() }`: the envelope shared by the
 * dashboard, projects-list, mockups, invoice, favorites, library and
 * clients-page caches.
 */
export function writeTimestampedJsonCache(key: string, fields: Record<string, unknown>): void {
  writeJsonCache(key, { ...fields, cachedAt: Date.now() });
}
