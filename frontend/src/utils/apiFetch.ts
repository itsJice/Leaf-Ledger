import { auth } from "app/auth/auth";

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
  return fetch(input, {
    ...init,
    headers,
    credentials: init.credentials ?? "include",
  });
}
