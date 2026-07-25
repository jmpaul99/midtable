# Authentication email templates

Paste into **Authentication → Email Templates** (auth flows). Set the subject from the table below.

Security notifications live in [`../security/`](../security/).

League seat invites are **not** here — those use [`brand/emails/league-invite.html`](../../../brand/emails/league-invite.html), filled and sent via Mailjet (`backend/app/services/invite_email.py`).

| Template | File | Subject |
|----------|------|---------|
| Confirm sign up | `confirm-signup.html` | `Confirm your email — Midtable` |
| Invite user | `invite-user.html` | `Come play Midtable` |
| Magic link / OTP | `magic-link.html` | `Sign in to Midtable` |
| Change email address | `change-email.html` | `Confirm your new Midtable email` |
| Reset password | `reset-password.html` | `Reset your Midtable password` |
| Reauthentication | `reauthentication.html` | `{{ .Token }} is your Midtable code` |

## Variables

| Variable | Description | Used in |
|----------|-------------|---------|
| `{{ .ConfirmationURL }}` | Full verify/action link | Confirm, invite, magic link, change email, reset |
| `{{ .Token }}` | OTP code | Magic link, reauthentication |
| `{{ .TokenHash }}` | Hashed token (custom verify links) | Optional |
| `{{ .SiteURL }}` | Project Site URL (also hosts logo: `/brand/png/lockup-matchday.png`) | Required for logo image |
| `{{ .RedirectTo }}` | Client redirect allow-list URL | Optional |
| `{{ .Email }}` | User email | Optional / change-email context |
| `{{ .NewEmail }}` | New address being confirmed | **Change email only** |
| `{{ .Data }}` | `user_metadata` | Optional personalization |

**Note:** After an email change completes, Supabase can also send the security notification in [`../security/email-changed.html`](../security/email-changed.html) (`{{ .OldEmail }}` → `{{ .Email }}`). That is separate from confirming `{{ .NewEmail }}` here.

## Local CLI (optional)

```toml
[auth.email.template.confirmation]
subject = "Confirm your email — Midtable"
content_path = "./templates/auth/confirm-signup.html"

[auth.email.template.invite]
subject = "Come play Midtable"
content_path = "./templates/auth/invite-user.html"

[auth.email.template.magic_link]
subject = "Sign in to Midtable"
content_path = "./templates/auth/magic-link.html"

[auth.email.template.email_change]
subject = "Confirm your new Midtable email"
content_path = "./templates/auth/change-email.html"

[auth.email.template.recovery]
subject = "Reset your Midtable password"
content_path = "./templates/auth/reset-password.html"

[auth.email.template.reauthentication]
subject = "{{ .Token }} is your Midtable code"
content_path = "./templates/auth/reauthentication.html"
```
