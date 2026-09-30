# Supabase auth emails

These are the branded **Invite user** and **Reset password** emails. Both link to
`/set-password` in the app with a one-time `token_hash`. That page
(`frontend/src/pages/SetPassword.tsx`) only redeems the token when the person
clicks the button, and sets their password in the same step. Email security
scanners that open links in advance therefore can't use the link up, which was
the cause of the `otp_expired` errors.

Supabase keeps its email templates in the dashboard, not in this repo. After
changing a file here, paste it in again.

## One-time setup (Supabase dashboard → Authentication)

1. **URL Configuration**
   - **Site URL:** `https://leaf-ledger.onrender.com`. This is what `{{ .SiteURL }}`
     in the templates becomes. It was `http://localhost:3000`, which is why invite
     links went nowhere.
   - **Redirect URLs:** add `https://leaf-ledger.onrender.com/**`. For local
     testing, also add `http://localhost:5174/**`.
2. **Emails → Templates** (on older dashboards, **Email Templates**)
   - **Invite user**
     - Subject: `You're invited to Leaf & Ledger`
     - Body: the contents of `invite.html`
   - **Reset password**
     - Subject: `Reset your Leaf & Ledger password`
     - Body: the contents of `reset-password.html`
3. **Optional: sender name and limits.** Supabase's built-in mailer sends as
   "Supabase Auth" and allows only a few emails per hour. To send as
   "Leaf & Ledger" from your own domain, set up **Emails → SMTP Settings** with a
   provider such as Resend, Postmark or Google Workspace SMTP.

## Inviting someone

Supabase dashboard → Authentication → Users → **Add user → Send invitation**.
They get `invite.html`, click **Set your password**, choose a password, and land
in the app. Their role comes from Settings → Users, or from the install
schedule roster for leads and crew (see `backend/app/libs/roles.py`).

The logo in the emails is `frontend/public/email/logo.png`, served from the live
site at `/email/logo.png`.
