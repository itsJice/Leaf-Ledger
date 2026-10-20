import { supabase } from "./supabase";

/**
 * Supplies the bearer token for API calls.
 *
 * `apiclient` calls getAuthHeaderValue() on every request, so attaching the
 * Supabase session here is all that's needed for the whole app to send its
 * credentials. getSession() refreshes an expired token automatically.
 */
export const auth = {
  getAuthHeaderValue: async (): Promise<string> => {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    return token ? `Bearer ${token}` : "";
  },
  getAuthToken: async (): Promise<string> => {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? "";
  },
  /**
   * Calls `cb` whenever Supabase issues a new access token (the hourly
   * refresh, or a sign-in). The Install Schedule iframe can't refresh its
   * own copy, so it is handed each new one. Returns an unsubscribe.
   */
  onTokenChange: (cb: () => void): (() => void) => {
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "TOKEN_REFRESHED" || event === "SIGNED_IN") cb();
    });
    return () => data.subscription.unsubscribe();
  },
};
