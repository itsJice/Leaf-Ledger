import { type FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "app/auth/AuthProvider";
import { isSupabaseConfigured } from "app/auth/supabase";

export default function Login() {
  const { user, loading, signIn, sendPasswordReset } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetMode, setResetMode] = useState(false);

  const next = new URLSearchParams(location.search).get("next") || "/";

  // Already signed in (or just signed in) — go where they were headed.
  useEffect(() => {
    if (!loading && user) {
      navigate(next, { replace: true });
    }
  }, [user, loading, next, navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);

    if (!email.trim() || (!resetMode && !password)) {
      setError("Please fill in both fields.");
      return;
    }

    setBusy(true);
    if (resetMode) {
      const { error } = await sendPasswordReset(email);
      setBusy(false);
      if (error) {
        setError(error);
      } else {
        setNotice("Check your email for a link to reset your password.");
      }
      return;
    }

    const { error } = await signIn(email, password);
    setBusy(false);
    if (error) setError(error);
    // On success the effect above redirects.
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f7f6f2] px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-serif text-3xl tracking-tight text-[#1f3d2b]">
            Leaf &amp; Ledger
          </h1>
          <p className="mt-2 text-sm text-[#1f3d2b]/60">
            The Branch Design Group
          </p>
        </div>

        <div className="rounded-lg border border-[#1f3d2b]/10 bg-white p-6 shadow-sm">
          <h2 className="mb-1 text-lg font-medium text-[#1f3d2b]">
            {resetMode ? "Reset your password" : "Sign in"}
          </h2>
          <p className="mb-5 text-sm text-[#1f3d2b]/60">
            {resetMode
              ? "We'll email you a link to set a new password."
              : "Welcome back."}
          </p>

          {!isSupabaseConfigured && (
            <div className="mb-4 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Sign-in isn't configured for this build. Please contact your
              administrator.
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="mb-1 block text-sm font-medium text-[#1f3d2b]"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded border border-[#1f3d2b]/20 px-3 py-2 text-[#1f3d2b] outline-none transition focus:border-[#1f3d2b] focus:ring-1 focus:ring-[#1f3d2b]"
                placeholder="you@company.com"
              />
            </div>

            {!resetMode && (
              <div>
                <label
                  htmlFor="password"
                  className="mb-1 block text-sm font-medium text-[#1f3d2b]"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded border border-[#1f3d2b]/20 px-3 py-2 text-[#1f3d2b] outline-none transition focus:border-[#1f3d2b] focus:ring-1 focus:ring-[#1f3d2b]"
                  placeholder="••••••••"
                />
              </div>
            )}

            {error && (
              <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            )}
            {notice && (
              <p className="rounded bg-green-50 px-3 py-2 text-sm text-green-800">
                {notice}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || !isSupabaseConfigured}
              className="w-full rounded bg-[#1f3d2b] px-4 py-2.5 font-medium text-white transition hover:bg-[#162d20] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy
                ? "Please wait…"
                : resetMode
                  ? "Send reset link"
                  : "Sign in"}
            </button>
          </form>

          <button
            type="button"
            onClick={() => {
              setResetMode(!resetMode);
              setError(null);
              setNotice(null);
            }}
            className="mt-4 w-full text-center text-sm text-[#1f3d2b]/60 underline-offset-2 hover:text-[#1f3d2b] hover:underline"
          >
            {resetMode ? "Back to sign in" : "Forgot your password?"}
          </button>
        </div>

        <p className="mt-6 text-center text-xs text-[#1f3d2b]/40">
          Need an account? Ask your administrator to add you.
        </p>
      </div>
    </div>
  );
}
