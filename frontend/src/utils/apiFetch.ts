import { toast } from "sonner";
import { auth } from "app/auth/auth";
import { isReadOnly } from "utils/me";

/**
 * fetch() for our own /api routes, with the signed-in user's token attached.
 *
 * Every /api route requires authentication, and the token lives in the Supabase
 * session — not in a cookie — so a plain fetch() with `credentials: "include"`
 * sends nothing the server can authenticate and comes back 401. Use this for
 * any call to /api that doesn't go through `apiclient`.
 */
export async function apiFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const authHeader = await auth.getAuthHeaderValue();
  const headers = new Headers(init.headers ?? {});
  if (authHeader && !headers.has("Authorization")) {
    headers.set("Authorization", authHeader);
  }
  const res = await fetch(input, {
    ...init,
    headers,
    credentials: init.credentials ?? "include",
  });
  // A view-only login that reaches a change the server refuses gets one
  // plain explanation rather than a page-specific error.
  const method = (init.method || "GET").toUpperCase();
  if (res.status === 403 && method !== "GET" && isReadOnly()) {
    toast.info("This account is view only. Ask the office to make this change.", { id: "ll-readonly" });
  }
  return res;
}
