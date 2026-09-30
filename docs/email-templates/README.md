# Supabase auth emails

Every email Supabase sends for Leaf & Ledger, in one branded layout. The
`.html` files are generated. Edit the wording in `build.py`, then run

    python3 docs/email-templates/build.py

and paste the files that changed into the Supabase dashboard. Supabase keeps
its templates there, not in this repo.

## Which file goes where (Supabase → Authentication → Emails)

| Supabase template | Subject | Body file | Link lands on |
|---|---|---|---|
| **Invite user** | You're invited to Leaf & Ledger | `invite.html` | `/set-password` |
| **Reset password** | Reset your Leaf & Ledger password | `reset-password.html` | `/set-password` |
| **Magic link** | Your Leaf & Ledger sign-in link | `magic-link.html` | `/auth/confirm` |
| **Confirm signup** | Confirm your email for Leaf & Ledger | `confirm-signup.html` | `/auth/confirm` |
| **Change email address** | Confirm your new Leaf & Ledger email | `change-email.html` | `/auth/confirm` |
| **Reauthentication** | Your Leaf & Ledger verification code | `reauthentication.html` | (6-digit code, no link) |

Security notifications are under **Emails → Security**. Turn on the ones you
want, then paste the body:

| Notification | Subject | Body file |
|---|---|---|
| Password changed | Your Leaf & Ledger password was changed | `notify-password-changed.html` |
| Email address changed | Your Leaf & Ledger sign-in email was changed | `notify-email-changed.html` |
| MFA method added | A verification method was added to your account | `notify-mfa-added.html` |
| MFA method removed | A verification method was removed from your account | `notify-mfa-removed.html` |

Your dashboard may list other security notifications, such as phone or
identity linking. Leaf & Ledger doesn't use those, so leave them off.

## Why the links go to a page, not straight to Supabase

Every link carries a one-time `token_hash`. The app only redeems it when the
person clicks the button on the page:

- `frontend/src/pages/SetPassword.tsx`: invite and password reset. The
  password is chosen in the same step.
- `frontend/src/pages/AuthConfirm.tsx`: magic link, confirm signup and
  change email.

Email security scanners open links to check them. A link that signs in or
verifies as soon as it's opened gets used up before the person clicks it,
which caused the `otp_expired` errors. `frontend/index.html` also forwards
Supabase's default-format links (`#type=invite`, `#type=recovery`,
`#error_code=otp_expired` on the site root) to `/set-password`.

## One-time setup (Supabase → Authentication → URL Configuration)

- **Site URL:** `https://leaf-ledger.onrender.com`. This is what `{{ .SiteURL }}`
  in the templates becomes. It was `http://localhost:3000`.
- **Redirect URLs:** add `https://leaf-ledger.onrender.com/**`. For local
  testing, also add `http://localhost:5174/**`.

**Optional: sender name and limits.** The built-in mailer sends as
"Supabase Auth" and allows only a few emails per hour. To send as
"Leaf & Ledger" from your own domain, set up **Emails → SMTP Settings** with
a provider such as Resend, Postmark or Google Workspace SMTP.

## Workflows

- **Invite someone:** Authentication → Users → Add user → Send invitation.
  They choose a password on `/set-password` and land in the app. Their role
  comes from Settings → Users, or from the install schedule roster.
- **Reset a password:** from the user's page, click Send password recovery.
  Or the person uses "Forgot your password?" on the sign-in page. Both land
  on `/set-password`.
- **Magic link:** from the user's page, click Send magic link. Or the person
  uses "Email me a sign-in link instead" on the sign-in page. This only works
  for existing accounts and never creates one. They press Sign in on
  `/auth/confirm`.

The logo is `frontend/public/email/logo.png`, served from the live site at
`/email/logo.png`.
