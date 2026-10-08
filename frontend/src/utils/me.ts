import { useEffect, useState } from "react";
import { apiFetch } from "utils/apiFetch";

// Who is signed in and what they may do (`/api/me`, backend app/libs/roles.py).
// Fetched once per sign-in and shared: the router gate and the layout both
// read it on every page, and it only changes when someone edits Settings >
// Users. The server enforces every rule on its own -- this only decides what
// to show.

export type Role = "crew" | "viewer" | "production" | "lead" | "staff" | "admin" | "super_admin";

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
  /** The warehouse display login: the install schedule, read-only, full screen. */
  viewOnly: boolean;
  /** The production login: view-only apart from what the server allows. */
  readOnly?: boolean;
  /** For a restricted login, the only pages it may open (else null). */
  pages?: string[] | null;
  /** Where a restricted login lands. */
  home?: string | null;
  person: RosterPerson | null;
}

/** The only page a field-only login can open. */
export const FIELD_HOME = "/shifts";
/** Where a view-only (warehouse display) login lands; it may open the
 *  schedule's other views too (utils/installViews.ts). */
export const DISPLAY_HOME = "/install-schedule";

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
        // CSS hook: `[data-readonly] [data-edit]` hides edit controls for the
        // production login (index.css). The server refuses those writes anyway.
        document.documentElement.toggleAttribute("data-readonly", Boolean(m.readOnly));
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

/** May this account open `path`? A page in `pages` covers its sub-pages
 *  ("/jobs" allows "/jobs/12"). Unrestricted accounts may open anything. */
export function pageAllowed(me: Me | null, path: string): boolean {
  if (!me?.pages) return true;
  return me.pages.some((p) => path === p || path.startsWith(p + "/"));
}

/** Where "back to Leaf & Ledger" goes from a standalone page (the request
 *  form). Normally the Dashboard; a restricted login can't open that -- and
 *  its home IS the form -- so send it to its first page that has the app
 *  around it, or the link would bounce straight back to the form. */
export function appHome(): string {
  const me = current?.me;
  if (!me?.pages) return "/";
  return me.pages.find((p) => !p.startsWith("/forms/")) ?? me.pages[0] ?? "/";
}

/** View-only apart from what the server allows (the production login). */
export function isReadOnly(): boolean {
  return Boolean(current?.me.readOnly);
}

/** The loaded account, for components rendered under the router gate. */
export function currentMe(): Me | null {
  return current?.me ?? null;
}
