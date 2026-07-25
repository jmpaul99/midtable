# Midtable Supabase email templates

Matchday HTML for [Supabase Auth email templates](https://supabase.com/docs/guides/auth/auth-email-templates).

| Folder | Contents |
|--------|----------|
| [`auth/`](./auth/) | Authentication emails (confirm, invite, magic link, change email, reset, reauth) |
| [`security/`](./security/) | Security notification emails (password/email/phone changed, identity, MFA) |

All templates are **centered** and use Matchday lockup PNG at `{{ .SiteURL }}/brand/png/lockup-matchday.png` (must be publicly reachable from the app origin).

League invites are sent by the backend via Mailjet (`backend/app/services/invite_email.py`), with a preview at `brand/emails/league-invite.html`.