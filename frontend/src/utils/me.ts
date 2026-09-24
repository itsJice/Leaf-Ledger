import { useEffect, useState } from "react";
import { apiFetch } from "utils/apiFetch";

// Who is signed in and what they may do (`/api/me`, backend app/libs/roles.py).
// Fetched once per sign-in and shared: the router gate and the layout both
// read it on every page, and it only changes when someone edits Settings >
// Users. The server enforces every rule on its own -- this only decides what
// to show.

export type Role = "crew" | "lead" | "staff" | "admin" | "super_admin";

export interface RosterPerson {
  id: string;
  name: string;
  title: string;
  email: string;
  phone: string;
}

export interface Me {
  email: string;
  role: Role;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  /** Leads and crew: the lead pages only, no office sidebar. */
  fieldOnly: boolean;
  person: RosterPerson | null;
}

/** The only page a field-only login can open. */
export const FIELD_HOME = "/shifts";

let cached: { token: string; promise: Promise<Me> } | null = null;

async function fetchMe(): Promise<Me> {
  const r = await apiFetch("/api/me");
  if (!r.ok) throw new Error(`Couldn't load your account (${r.status})`);
  return r.json();
}

/** One request per signed-in user id; a different sign-in refetches. */
export function loadMe(userId: string): Promise<Me> {
  if (!cached || cached.token !== userId) {
    const promise = fetchMe();
    cached = { token: userId, promise };
    promise.catch(() => {
      if (cached?.promise === promise) cached = null;
    });
  }
  return cached.promise;
}

let current: { userId: string; me: Me } | null = null;

export function useMe(userId: string | undefined) {
  const [me, setMe] = useState<Me | null>(
    current && current.userId === userId ? current.me : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!userId) return;
    let live = true;
    loadMe(userId)
      .then((m) => {
        current = { userId, me: m };
        if (live) {
          setMe(m);
          setError(null);
        }
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [userId, attempt]);

  return { me, error, retry: () => setAttempt((n) => n + 1) };
}

/** The loaded account, for components rendered under the router gate. */
export function currentMe(): Me | null {
  return current?.me ?? null;
}
