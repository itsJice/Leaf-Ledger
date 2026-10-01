#!/usr/bin/env python3
"""Build every Supabase auth email from one Leaf & Ledger layout.

    python3 docs/email-templates/build.py

Writes one .html per email next to this file. Paste each into Supabase →
Authentication → Emails (README.md lists which file goes where). Edit the
wording here, not in the generated files, so the emails stay consistent.

`{{ .Email }}`, `{{ .SiteURL }}`, `{{ .TokenHash }}`, `{{ .Token }}` and
`{{ .NewEmail }}` are Supabase template variables, filled in when it sends.
"""
import pathlib

HERE = pathlib.Path(__file__).parent
LOGO = "https://leaf-ledger.onrender.com/email/logo.png"


def page(heading, paras, *, button=None, link=None, code=None, footnote=""):
    body = "".join(
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#44524a;">{p}</p>' for p in paras
    )
    if button:
        body += (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:12px 0 24px;">'
            '<tr><td style="background:#2d5a33;border-radius:8px;">'
            f'<a href="{link}" style="display:inline-block;padding:13px 26px;font-size:15px;'
            f'font-weight:700;color:#ffffff;text-decoration:none;">{button}</a></td></tr></table>'
        )
    if code:
        body += (
            '<p style="margin:12px 0 24px;padding:14px 18px;background:#eef4ef;border-radius:8px;'
            'font-family:Menlo,Consolas,monospace;font-size:28px;letter-spacing:6px;color:#1f3d2b;'
            f'text-align:center;font-weight:700;">{code}</p>'
        )
    if footnote:
        body += f'<p style="margin:0 0 24px;font-size:13px;line-height:1.6;color:#6b776f;">{footnote}</p>'
    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f7f6f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f6f2;padding:32px 12px;font-family:'Nunito Sans',Helvetica,Arial,sans-serif;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border:1px solid #e3e8e3;border-radius:12px;overflow:hidden;">
      <tr><td align="center" style="background:#1f3d2b;padding:28px 24px;">
        <img src="{LOGO}" width="180" alt="Leaf &amp; Ledger" style="display:block;width:180px;height:auto;border:0;">
      </td></tr>
      <tr><td style="padding:32px 32px 8px;">
        <h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;color:#1f3d2b;font-weight:700;">{heading}</h1>
        {body}
      </td></tr>
      <tr><td style="padding:16px 32px 24px;border-top:1px solid #eef1ee;font-size:12px;line-height:1.5;color:#8a948d;">
        Leaf &amp; Ledger · The Branch Design Group
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""


EMAIL = '<strong style="color:#1f3d2b;">{{ .Email }}</strong>'
NOT_YOU = "If you didn't ask for this, you can ignore this email."
CHANGED = ("If this wasn't you, reset your password from the sign-in page right away "
           "and tell your administrator.")

TEMPLATES = {
    # ── emails with a link or code (Authentication → Emails → Templates) ──
    "invite.html": page(
        "You're invited to Leaf &amp; Ledger",
        ["The Branch Design Group has set up an account for you. Choose a password to get started.",
         f"Your sign-in email is {EMAIL}."],
        button="Set your password",
        link="{{ .SiteURL }}/set-password?token_hash={{ .TokenHash }}&amp;type=invite",
        footnote="This link works once. If it has expired or was already used, "
                 "ask your administrator to resend the invite."),
    "reset-password.html": page(
        "Reset your password",
        ["Someone asked to reset the password for your Leaf &amp; Ledger account. Choose a new one below.",
         f"Account: {EMAIL}."],
        button="Choose a new password",
        link="{{ .SiteURL }}/set-password?token_hash={{ .TokenHash }}&amp;type=recovery",
        footnote=f"This link works once and expires soon. {NOT_YOU} Your password won't change."),
    "magic-link.html": page(
        "Your sign-in link",
        [f"Use the button below to sign in to Leaf &amp; Ledger as {EMAIL}. No password needed."],
        button="Sign in to Leaf &amp; Ledger",
        link="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=email",
        footnote=f"This link works once and expires soon. {NOT_YOU}"),
    "confirm-signup.html": page(
        "Confirm your email",
        [f"Confirm {EMAIL} to finish setting up your Leaf &amp; Ledger account."],
        button="Confirm email",
        link="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=signup",
        footnote=f"This link works once. {NOT_YOU}"),
    "change-email.html": page(
        "Confirm your new email",
        ["Someone asked to change the sign-in email on your Leaf &amp; Ledger account "
         f"from {EMAIL} to <strong style=\"color:#1f3d2b;\">{{{{ .NewEmail }}}}</strong>."],
        button="Confirm the change",
        link="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=email_change",
        footnote=f"This link works once. If you didn't ask for this, don't click it, and "
                 "tell your administrator."),
    "reauthentication.html": page(
        "Your verification code",
        [f"Enter this code in Leaf &amp; Ledger to confirm it's you ({EMAIL})."],
        code="{{ .Token }}",
        footnote=f"The code expires soon. {NOT_YOU}"),
    # ── security notifications, no link (Authentication → Emails → Security) ──
    "notify-password-changed.html": page(
        "Your password was changed",
        [f"The password for your Leaf &amp; Ledger account ({EMAIL}) was just changed."],
        footnote=CHANGED),
    "notify-email-changed.html": page(
        "Your sign-in email was changed",
        ["The sign-in email for your Leaf &amp; Ledger account was just changed."],
        footnote=CHANGED),
    "notify-mfa-added.html": page(
        "A sign-in verification method was added",
        [f"A new two-step verification method was added to your Leaf &amp; Ledger account ({EMAIL})."],
        footnote=CHANGED),
    "notify-mfa-removed.html": page(
        "A sign-in verification method was removed",
        [f"A two-step verification method was removed from your Leaf &amp; Ledger account ({EMAIL})."],
        footnote=CHANGED),
}

if __name__ == "__main__":
    for name, html in TEMPLATES.items():
        (HERE / name).write_text(html)
        print("wrote", name)
