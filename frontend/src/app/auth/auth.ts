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
};
