# Midtable brand

Canonical brand assets, guide, fonts, and email templates.

```
brand/
  README.md
  midtable-brand-guide.md      # Brand guide (markdown)
  midtable-brand-guide.html    # Printable visual companion
  logos/
    presentation/              # Marketing / guide lockups + variants sheet
    product/
      svg/                     # App lockups, marks, wordmarks (SVG)
      png/                     # Same assets as PNG
      icons/                   # Favicons, apple touch, icon source SVGs
  emails/
    league-invite.html         # League seat invite (Mailjet via backend)
  fonts/                       # Outfit embeds for logo SVGs / OG image
```

## Logos

| Path | Use |
|------|-----|
| `logos/presentation/midtable-logo-matchday.svg` | Matchday (light) presentation lockup |
| `logos/presentation/midtable-logo-pitch-night.svg` | Pitch Night (dark) presentation lockup |
| `logos/presentation/midtable-logo-variants.svg` | Side-by-side sheet with color swatches |
| `logos/product/svg/lockup-*.svg` | Transparent app lockups |
| `logos/product/svg/mark-*.svg` | Rank mark only |
| `logos/product/svg/wordmark-*.svg` | Staggered Midtable text only |
| `logos/product/png/` | Raster exports of the same lockups / marks / wordmarks |
| `logos/product/icons/` | Favicons, apple-touch, PWA manifest icons (`site.webmanifest`) |

Product SVGs embed a subset of **Outfit ExtraBold** as a base64 `@font-face` so they render when opened directly or used as images.

In-app logo uses inline SVG via `MidtableLogo` so it shares the site’s `next/font` Outfit.

### Sync to Next.js public

`frontend/public/brand/` mirrors `logos/product/` (`svg/`, `png/`, `icons/`). Sync with:

```bash
python scripts/sync-brand-public.py
```

Frontend `predev` / `prebuild` run this automatically.

### Regenerate font embeds

After refreshing `fonts/outfit-extrabold-logo.b64` from the Outfit variable font:

```bash
python scripts/embed-logo-font.py
python scripts/make-wordmark-svgs.py   # optional wordmark regen
python scripts/sync-brand-public.py
```

## Emails

| File | Use |
|------|-----|
| `emails/league-invite.html` | League seat invite HTML; placeholders filled by `backend/app/services/invite_email.py` |

Centered Matchday layout. Logo uses absolute PNG `PUBLIC_APP_URL/brand/png/lockup-matchday.png` (synced from `logos/product/png/`).

Supabase templates: `supabase/templates/auth/` and `supabase/templates/security/` (dashboard paste / `content_path`). They use `{{ .SiteURL }}/brand/png/lockup-matchday.png` — set Site URL in Auth → URL configuration.

## Guide

- [midtable-brand-guide.md](./midtable-brand-guide.md)
- [midtable-brand-guide.html](./midtable-brand-guide.html)
