import { useEffect, useState } from "react";

/**
 * Schedule `commit(value)` after `delayMs`; returns the cleanup that cancels it.
 * This is the whole body of the hand-rolled debounce effects (pure, so it can be
 * tested without React).
 */
export function scheduleDebouncedCommit<T>(value: T, delayMs: number, commit: (value: T) => void): () => void {
  const handle = setTimeout(() => commit(value), delayMs);
  return () => clearTimeout(handle);
}

/**
 * `value`, delayed until it has stopped changing for `delayMs`.
 *
 * Starts equal to `value`. Like the originals, a timer is also scheduled on
 * mount; it commits the same value, so nothing re-renders.
 *
 * To reproduce `setTimeout(() => setX(search.trim()), ms)` exactly, debounce the
 * raw value and trim when reading it: `useDebouncedValue(search, 350).trim()`.
 * Passing `search.trim()` instead would stop a trailing space from restarting
 * the timer.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => scheduleDebouncedCommit(value, delayMs, (next) => setDebounced(() => next)), [value, delayMs]);
  return debounced;
}
