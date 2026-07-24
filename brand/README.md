# Midtable brand assets

Canonical logo presentation files for Midtable.

| File | Use |
|------|-----|
| `midtable-logo-matchday.svg` | Matchday (light) presentation lockup |
| `midtable-logo-pitch-night.svg` | Pitch Night (dark) presentation lockup |
| `midtable-logo-variants.svg` | Side-by-side sheet with color swatches |
| `midtable-wordmark-matchday.svg` | Matchday staggered wordmark only |
| `midtable-wordmark-pitch-night.svg` | Pitch Night staggered wordmark only |

Wordmark SVGs embed a subset of **Outfit ExtraBold** as a base64 `@font-face` (glyphs for the lockup + variants labels), so they render correctly when opened directly or used as images — no Google Fonts network request.

Regenerate the embed with:

```bash
python scripts/embed-logo-font.py
```

(after refreshing `docs/brand/_fonts/outfit-extrabold-logo.b64` from the Outfit variable font).

Product-served lockups, marks, and favicons live in `frontend/public/brand/`.
In-app logo uses inline SVG via `MidtableLogo` so it shares the site’s `next/font` Outfit.
Brand documentation: `docs/brand/midtable-brand-guide.md`.
