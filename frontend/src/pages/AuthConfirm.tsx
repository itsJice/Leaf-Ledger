import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { EmailOtpType } from "@supabase/supabase-js";
import { supabase } from "app/auth/supabase";
import { LeafLedgerLogo } from "components/LeafLedgerLogo";

/**
 * Where the magic-link, confirm-signup and change-email emails land
 * (docs/email-templates). Invite and password-reset emails go to
 * /set-password instead, because those also need a password chosen.
 *
 * Same rule as /set-password: the one-time token_hash is only redeemed when
 * the person presses the button. Email security scanners open links to check
 * them, and a link that verifies on open is spent before the person ever
 * clicks it.
 */
type Kind = "magiclink" | "signup" | "email_change";

const COPY: Record<Kind, { title: string; body: string; button: string; done: string }> = {
  magiclink: {
    title: "Sign in to Leaf & Ledger",
    body: "Press the button to finish signing in on this device.",
    button: "Sign in",
    done: "Signed in",
  },
  signup: {
    title: "Confirm your email",
    body: "Press the button to confirm your email address and open Leaf & Ledger.",
    button: "Confirm email",
    done: "Email confirmed",
  },
  email_change: {
    title: "Confirm your new email",
    body: "Press the button to confirm the change to your sign-in email.",
    button: "Confirm new email",
    done: "Email change confirmed",
  },
};

function readLink() {
  const q = new URLSearchParams(window.location.search);
  const type = q.get("type") || "";
  const kind: Kind = type === "email_change" ? "email_change" : type === "signup" ? "signup" : "magiclink";
  // Only same-site paths: never bounce someone to another site from a link.
  const nextRaw = q.get("next") || "/";
  const next = nextRaw.startsWith("/") && !nextRaw.startsWith("//") ? nextRaw : "/";
  return { tokenHash: q.get("token_hash"), type: (type || "email") as EmailOtpType, kind, next };
}

export default function AuthConfirm() {
  const navigate = useNavigate();
  const [{ tokenHash, type, kind, next }] = useState(readLink);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const copy = COPY[kind];

  useEffect(() => {
    // Keep the one-time token out of history once we've read it.
    if (tokenHash) window.history.replaceState(null, "", "/auth/confirm");
  }, [tokenHash]);

  const confirm = async () => {
    if (!tokenHash) return;
    setBusy(true);
    setError(null);
    const { data, error: vErr } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    setBusy(false);
    if (vErr) {
      setError(
        kind === "email_change"
          ? "This link has expired or was already used. Request the email change again from your account."
          : "This link has expired or was already used. Request a new one, or sign in with your password.",
      );
      return;
    }
    // Secure email change sends a link to both addresses; the first click
    // confirms one side and Supabase waits for the other.
    if (kind === "email_change" && !data.session) {
      setNotice("Confirmed. Now open the link sent to your other email address to finish the change.");
      return;
    }
    setNotice(copy.done);
    navigate(next, { replace: true });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="ll-enter mb-8 text-center">
          <h1 className="sr-only">Leaf &amp; Ledger</h1>
          <LeafLedgerLogo className="mx-auto h-auto w-56" />
          <p className="mt-2 text-sm text-brand-deep/60">The Branch Design Group</p>
        </div>

        <div className="ll-enter rounded-lg border border-brand-deep/10 bg-white p-6 shadow-sm">
          <h2 className="mb-1 text-lg font-medium text-brand-deep">{copy.title}</h2>
          <p className="mb-5 text-sm text-brand-deep/60">{copy.body}</p>

          {!tokenHash && !notice ? (
            <p className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Open this page from the link in your email.
            </p>
          ) : notice ? (
            <p className="rounded bg-green-50 px-3 py-2 text-sm text-green-800">{notice}</p>
          ) : (
            <>
              {error && <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              {!error && (
                <button
                  type="button"
                  onClick={confirm}
                  disabled={busy}
                  className="w-full rounded bg-brand-deep px-4 py-2.5 font-medium text-white transition hover:bg-brand-deepest disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? "Please wait…" : copy.button}
                </button>
              )}
            </>
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
