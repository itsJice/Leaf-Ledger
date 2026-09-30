import { type FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { EmailOtpType } from "@supabase/supabase-js";
import { supabase } from "app/auth/supabase";
import { LeafLedgerLogo } from "components/LeafLedgerLogo";

/**
 * Where invite and password-reset emails land (docs/email-templates).
 *
 * The email links here with a one-time `token_hash` rather than straight to
 * Supabase's verify endpoint. That matters: email security scanners open
 * links to check them, and a verify link is spent the moment anything opens
 * it -- which is how invites arrived already "expired". Here the token is only
 * redeemed when the person presses the button, and then the password is set
 * in the same step.
 *
 * Also accepts the older link shape (Supabase's default templates), where the
 * session arrives in the URL hash and supabase-js signs the user in on load;
 * then only the password is left to set.
 */
const MIN_LENGTH = 8;

type LinkKind = "invite" | "recovery";

function readLink(): { tokenHash: string | null; kind: LinkKind; linkError: string | null } {
  const q = new URLSearchParams(window.location.search);
  const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const type = q.get("type") || h.get("type");
  const kind: LinkKind = type === "invite" ? "invite" : "recovery";
  const desc = q.get("error_description") || h.get("error_description");
  return { tokenHash: q.get("token_hash"), kind, linkError: desc ? desc.replace(/\+/g, " ") : null };
}

export default function SetPassword() {
  const navigate = useNavigate();
  const [{ tokenHash, kind, linkError }] = useState(readLink);
  const [hasSession, setHasSession] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(linkError ? expiredMessage() : null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setHasSession(Boolean(data.session));
      setEmail(data.session?.user.email ?? null);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => {
      setHasSession(Boolean(s));
      setEmail(s?.user.email ?? null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const usable = Boolean(tokenHash) || hasSession;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      if (tokenHash && !hasSession) {
        const { error: vErr } = await supabase.auth.verifyOtp({
          token_hash: tokenHash,
          type: kind as EmailOtpType,
        });
        if (vErr) {
          setError(expiredMessage());
          return;
        }
      }
      const { error: uErr } = await supabase.auth.updateUser({ password });
      if (uErr) {
        setError(friendly(uErr.message));
        return;
      }
      // Drop the token from the address bar, then into the app.
      window.history.replaceState(null, "", "/set-password");
      navigate("/", { replace: true });
    } finally {
      setBusy(false);
    }
  };

  const title = kind === "invite" ? "Welcome to Leaf & Ledger" : "Set a new password";

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="ll-enter mb-8 text-center">
          <h1 className="sr-only">Leaf &amp; Ledger</h1>
          <LeafLedgerLogo className="mx-auto h-auto w-56" />
          <p className="mt-2 text-sm text-brand-deep/60">The Branch Design Group</p>
        </div>

        <div className="ll-enter rounded-lg border border-brand-deep/10 bg-white p-6 shadow-sm">
          <h2 className="mb-1 text-lg font-medium text-brand-deep">{title}</h2>
          <p className="mb-5 text-sm text-brand-deep/60">
            {kind === "invite"
              ? "Choose a password to finish setting up your account."
              : "Choose a new password for your account."}
            {email && (
              <>
                {" "}
                <span className="font-medium text-brand-deep">{email}</span>
              </>
            )}
          </p>

          {!usable ? (
            <p className={`rounded px-3 py-2 text-sm ${error ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-900"}`}>
              {error || "Open this page from the link in your invite or password-reset email."}
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="password" className="mb-1 block text-sm font-medium text-brand-deep">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  autoFocus
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded border border-brand-deep/20 px-3 py-2 text-brand-deep outline-none transition-[border-color,box-shadow] focus:border-brand-deep focus:ring-1 focus:ring-brand-deep"
                  placeholder={`At least ${MIN_LENGTH} characters`}
                />
              </div>
              <div>
                <label htmlFor="confirm" className="mb-1 block text-sm font-medium text-brand-deep">
                  Confirm password
                </label>
                <input
                  id="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full rounded border border-brand-deep/20 px-3 py-2 text-brand-deep outline-none transition-[border-color,box-shadow] focus:border-brand-deep focus:ring-1 focus:ring-brand-deep"
                />
              </div>

              {error && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

              <button
                type="submit"
                disabled={busy || !usable}
                className="w-full rounded bg-brand-deep px-4 py-2.5 font-medium text-white transition hover:bg-brand-deepest disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? "Please wait…" : kind === "invite" ? "Set password and sign in" : "Save new password"}
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={() => navigate("/login")}
            className="mt-4 w-full text-center text-sm text-brand-deep/60 underline-offset-2 hover:text-brand-deep hover:underline"
          >
            Back to sign in
          </button>
        </div>
      </div>
    </div>
  );
}

function expiredMessage(): string {
  return "This link has expired or was already used. Use “Forgot your password?” on the sign-in page to get a new one, or ask your administrator to resend the invite.";
}

function friendly(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("should be different")) return "Choose a password you haven't used before.";
  if (m.includes("weak") || m.includes("at least")) return message;
  if (m.includes("failed to fetch") || m.includes("network")) {
    return "Can't reach the sign-in service. Check your internet connection.";
  }
  return message;
}
