# Security notification email templates

Paste into **Authentication → Email Templates** (security notifications). **Enable** each notification at the project level or they will not send.

Auth flow emails live in [`../auth/`](../auth/).

| Template | File | Subject | Must replace |
|----------|------|---------|--------------|
| Password changed | `password-changed.html` | `Your Midtable password was changed` | — (`{{ .SiteURL }}` for CTA) |
| Email address changed | `email-changed.html` | `Your Midtable email was changed` | `{{ .OldEmail }}`, `{{ .Email }}` |
| Phone number changed | `phone-changed.html` | `Your Midtable phone number was changed` | `{{ .OldPhone }}`, `{{ .Phone }}` |
| Sign-in method linked | `identity-linked.html` | `A sign-in method was linked to your Midtable account` | `{{ .Provider }}`, `{{ .Email }}` |
| Sign-in method removed | `identity-unlinked.html` | `A sign-in method was removed from your Midtable account` | `{{ .Provider }}`, `{{ .Email }}` |
| MFA method added | `mfa-enrolled.html` | `A verification method was added to your Midtable account` | `{{ .FactorType }}` |
| MFA method removed | `mfa-unenrolled.html` | `A verification method was removed from your Midtable account` | `{{ .FactorType }}` |

## Variables (notification-only)

| Variable | Description | Template |
|----------|-------------|----------|
| `{{ .OldEmail }}` | Previous email | Email address changed |
| `{{ .Email }}` | Current email (after change) | Email changed; identity linked/removed |
| `{{ .OldPhone }}` | Previous phone | Phone number changed |
| `{{ .Phone }}` | New phone | Phone number changed |
| `{{ .Provider }}` | Linked/removed sign-in provider | Identity linked / unlinked |
| `{{ .FactorType }}` | MFA factor type added/removed | MFA enrolled / unenrolled |
| `{{ .SiteURL }}` | Site URL for “Sign in to Midtable” + logo (`/brand/png/lockup-matchday.png`) | All drafts |

## Local CLI (optional)

```toml
[auth.email.notification.password_changed]
enabled = true
subject = "Your Midtable password was changed"
content_path = "./templates/security/password-changed.html"

[auth.email.notification.email_changed]
enabled = true
subject = "Your Midtable email was changed"
content_path = "./templates/security/email-changed.html"

[auth.email.notification.phone_changed]
enabled = true
subject = "Your Midtable phone number was changed"
content_path = "./templates/security/phone-changed.html"

[auth.email.notification.identity_linked]
enabled = true
subject = "A sign-in method was linked to your Midtable account"
content_path = "./templates/security/identity-linked.html"

[auth.email.notification.identity_unlinked]
enabled = true
subject = "A sign-in method was removed from your Midtable account"
content_path = "./templates/security/identity-unlinked.html"

[auth.email.notification.mfa_factor_enrolled]
enabled = true
subject = "A verification method was added to your Midtable account"
content_path = "./templates/security/mfa-enrolled.html"

[auth.email.notification.mfa_factor_unenrolled]
enabled = true
subject = "A verification method was removed from your Midtable account"
content_path = "./templates/security/mfa-unenrolled.html"
```
