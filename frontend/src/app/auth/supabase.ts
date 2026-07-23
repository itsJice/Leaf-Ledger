import { createClient } from "@supabase/supabase-js";

/**
 * The Supabase client used for signing in and out.
 *
 * Both values are public by design — the anon key is meant to be visible in a
 * browser. It grants nothing on its own: the database is not exposed over HTTP
 * (the Data API is disabled), and every /api route verifies the signed token
 * server-side.
 */
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as
  | string
  | undefined;

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

if (!isSupabaseConfigured) {
  // A missing key means nobody can sign in, so fail loudly rather than
  // showing an empty login box with no explanation.
  console.error(
    "Supabase is not configured: VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY " +
      "must be set at build time. Sign-in will not work.",
  );
}

export const supabase = createClient(
  supabaseUrl ?? "https://placeholder.supabase.co",
  supabaseAnonKey ?? "placeholder",
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  },
);
