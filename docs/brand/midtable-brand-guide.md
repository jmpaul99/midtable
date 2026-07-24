# Midtable Brand Guide

**Version 1.0 · July 2026**  
Visual identity & product system

> Draft clubs, follow every result, and climb the table.

**Source of truth:** `frontend/src/app/globals.css` · `frontend/src/lib/theme.tsx` · `frontend/src/components/ui/` · `brand/` · `frontend/public/brand/`

---

## 1. Essence

### Positioning

Football-first. Invite-only. Operationally clear.

Midtable is a multi-pool football draft platform for friends’ leagues. The brand feels like a modern matchday companion — confident greens on cool neutrals, bold compact type, and language commissioners actually use.

### Brand promise

Make private draft leagues feel official without the noise.

Soft surfaces, mint borders, and pitch greens signal football without stadium clichés or purple-saas defaults.

### Personality

| Trait | Meaning |
|-------|---------|
| **Direct** | Short CTAs, no hype filler |
| **Fluent** | Table, draft, matchday vocabulary |
| **Invite-only** | Private by default, never flashy |
| **Precise** | Ranks, scores, and status stay crisp |

### Naming

| Name | Role |
|------|------|
| **Midtable** | Primary product name |
| **Matchday** | Light theme (`data-theme="matchday"`; UI label “Light”) |
| **Pitch Night** | Dark theme (`data-theme="pitch"`; UI label “Dark”) |
| football-draft-league | Repo / package name — never shown as product brand in UI |

---

## 2. Logo

Primary lockup: staggered **Midtable** wordmark (Outfit ExtraBold) over the rank mark — three sharp squares, center framed.

| Asset | Path | Use |
|-------|------|-----|
| Matchday presentation | [`brand/midtable-logo-matchday.svg`](../../brand/midtable-logo-matchday.svg) | Spec / marketing on light |
| Pitch Night presentation | [`brand/midtable-logo-pitch-night.svg`](../../brand/midtable-logo-pitch-night.svg) | Spec / marketing on dark |
| Variants sheet | [`brand/midtable-logo-variants.svg`](../../brand/midtable-logo-variants.svg) | Side-by-side + swatches |
| App lockups | `frontend/public/brand/lockup-*.svg` | Transparent lockups (Outfit ExtraBold embedded) |
| App marks | `frontend/public/brand/mark-*.svg` | Rank mark only (nav, empty states) |
| App wordmarks | `frontend/public/brand/wordmark-*.svg` | Staggered Midtable text only |

Presentation and lockup/wordmark SVGs embed a subset of Outfit ExtraBold via `@font-face` data URI so the wordmark matches the product face even when the file is opened alone or used as an `<img>`.

### Construction

- Wordmark: single name, **Mid** raised 4px / **table** lowered 4px (8px stagger), tight gap between `d` and `t`
- Rank mark: sharp squares; side tiles solid brand; center = brand tile inside a gradient frame with a surface-colored gap
- Center frame bottom aligns with side-tile bottoms (center reads taller upward)

### Theme colors

| Part | Matchday | Pitch Night |
|------|----------|-------------|
| Wordmark | `#71717A` muted | `#2DD67B` brand |
| Side / center fill | `#067A4A` brand | `#2DD67B` brand |
| Frame gradient | `#8FD94A` → `#B9CDC0` (accent → line) | `#B8F25A` → `#9EE9D0` (accent → pale mint) |
| Frame gap | `#FFFFFF` surface | Surface / canvas dark |

### Product usage

- Nav: horizontal lockup (`MidtableLogo` `variant="nav"`) — rank mark + wordmark with box bottoms on the `table` baseline
- Home: full lockup via `MidtableLogo` (inline SVG using `--font-display` / Outfit — not `<img>`, so the face matches the app)
- Standalone wordmark: `variant="wordmark"` or `frontend/public/brand/wordmark-*.svg` / `brand/midtable-wordmark-*.svg`
- Standalone mark: `variant="mark"` or `frontend/public/brand/mark-*.svg`
- Favicon / apple touch: Matchday rank mark (`frontend/src/app/icon.svg`, `frontend/public/brand/apple-touch-icon.png`)
- Always ship both themes; colors swap with `data-theme` via `--logo-*` tokens in `globals.css`

---

## 3. Color — Matchday (light)

Cool neutral canvas. Green is trim and brand — never the whole field.

| Token | Hex | Role |
|-------|-----|------|
| `--color-brand` | `#067A4A` | Primary CTAs, links, eyebrows |
| `--color-brand-dark` | `#055C38` | Hover / pressed primary |
| `--color-on-brand` | `#FFFFFF` | Text on brand |
| `--color-accent` | `#8FD94A` | Rank #1 and highlights |
| `--color-on-accent` | `#0A0F0C` | Text on accent |
| `--color-line` | `#B9CDC0` | Mint-tinted borders |
| `--color-bg` | `#F4F4F5` | Page canvas |
| `--color-bg-accent` | `#EBEBEF` | Bottom of page gradient |
| `--color-surface` | `#FFFFFF` | Cards & panels |
| `--color-surface-2` | `#F0F0F2` | Inset tracks & hover |
| `--color-ink` | `#18181B` | Primary text |
| `--color-muted` | `#71717A` | Labels & secondary |
| `--color-danger` | `#C43C42` | Errors / destructive |
| `--color-warning` | `#9A6410` | Caution status |

**Shadow:** `--shadow-soft: 0 10px 30px rgba(24, 24, 27, 0.06)`  
**Radial glow:** transparent in Matchday

---

## 4. Color — Pitch Night (dark)

Near-black green ground. Brand lifts to bright pitch green; text goes soft mint-white.

| Token | Hex | Role |
|-------|-----|------|
| `--color-brand` | `#2DD67B` | Primary on dark |
| `--color-brand-dark` | `#22C46A` | Hover primary |
| `--color-on-brand` | `#0A0F0C` | Dark text on bright green |
| `--color-accent` | `#B8F25A` | Highlights & rank #1 |
| `--color-on-accent` | `#0A0F0C` | Text on accent |
| `--color-line` | `#243028` | Borders on dark |
| `--color-bg` | `#0A0F0C` | Page canvas |
| `--color-bg-accent` | `#0D1410` | Gradient end |
| `--color-surface` | `#121A15` | Cards & panels |
| `--color-surface-2` | `#1A241C` | Inset / secondary |
| `--color-ink` | `#E8EEE9` | Primary text |
| `--color-muted` | `#8A9A90` | Secondary text |
| `--color-danger` | `#F07178` | Errors |
| `--color-warning` | `#E0A84A` | Warning |

**Shadow:** `--shadow-soft: 0 12px 32px rgba(0, 0, 0, 0.45)`  
**Radial glow:** `rgba(45, 214, 123, 0.14)` top-right

---

## 5. Themes

Default preference follows the device. Users can lock Light or Dark.

- Storage key: `midtable-theme`
- Attribute: `data-theme` on `<html>`

### Background recipe

Fixed dual-layer body:

1. Optional radial ellipse (dark glow only)
2. Vertical fade: `--gradient-top` → `--color-bg` → `--color-bg-accent`

Sticky chrome uses `bg-bg/90` (or `/95`) + backdrop blur.

### Opacity patterns

Use token opacities rather than new hex: `brand/5`–`/80`, `danger/10`–`/20`, `accent/30`, `surface/60`–`/70`, `surface-2/40`–`/50`.

---

## 6. Typography

### Typeface

**Outfit** for UI and display.

- Loaded via `next/font/google` as `--font-outfit`
- Mapped to `--font-sans` and `--font-display`
- Fallbacks: `"Segoe UI", ui-sans-serif, system-ui, sans-serif`

### Specimens

| Role | Spec |
|------|------|
| Display / H1 | ExtraBold, ~2xl→4xl, tracking −0.02em |
| H2 | ExtraBold, xl→2xl |
| Eyebrow | ExtraBold, uppercase, tracking `0.12em`, `text-brand` |
| Body | Regular, 15px / 1.5 |
| UI control | Bold |
| Stats / scores | ExtraBold + `tabular-nums` |

### Weights

- **400** body  
- **600** labels  
- **700** controls / nav  
- **800** titles, eyebrows, stats  

---

## 7. Components & UI motifs

### Surfaces

- Default card: `rounded-xl border border-line bg-surface shadow-soft p-4 sm:p-5`
- Inset: `bg-surface-2`, no soft shadow
- List hover: `border-brand/40`, slight scale

### Buttons

Variants: `primary` · `secondary` · `danger` · `ghost`

- Always `rounded-xl font-bold`
- Press: `active:scale-[0.98]`
- Sizes: md / sm / icon

### Status & rank

- Status pill + 2px brand/warning/danger dot
- Rank #1: `bg-accent text-on-accent`
- Live draft / on-the-clock: brand fill + pulsing status dot
- Banners: left `border-l-4` brand/danger bar + tinted fill

### Geometry

| Token | Value |
|-------|--------|
| Primary radius | `--radius-xl: 0.875rem` (14px) |
| Compact | `rounded-lg` |
| Chips | `rounded-full` |
| Touch targets | `min-h-11` (44px) |
| Content max width | 1180px |

### Motion

- Entrance: `animate-in` fade-up 0.28s (`translateY(6px)` → 0)
- Respect `prefers-reduced-motion`
- Use motion for hierarchy — not ambient noise

### Icons

Custom 24×24 stroke icons (`strokeWidth={2}`, round caps). No icon library dependency for brand chrome.

---

## 8. Voice

### Tone

Short. Functional. Football-fluent.

Write like a commissioner briefing the group chat — clear, invite-aware, zero fluff.

### Approved lines

| Line | Use |
|------|-----|
| “Draft clubs, follow every result, and climb the table.” | Product meta / tagline |
| “Magic link or password. Leagues remain invite-only.” | Auth framing |
| “Accept an invite link to join a league.” | Empty state |
| “Start from a template, build a new one, or create a blank league…” | Create flow |
| “How you appear across leagues…” | Profile |
| “Follow your device setting, or lock light or dark.” | Theme settings |

### Principles

- Imperative CTAs: Sign in, Create account, Send magic link
- Prefer commissioner words: league, draft, standings, pool
- Eyebrows stay sparse: Welcome, Account, Invite, Step 1
- Never promise public social features Midtable doesn’t have
- Don’t use emoji as brand voice

### Don’t

> “Unleash next-level fantasy vibes with your squad 🔥”

Hype, emoji stacks, and generic fantasy-app copy are off-brand.

---

## 9. Application checklist

### Always

- Outfit ExtraBold for titles; brand green eyebrows
- Token colors only — no one-off hex in components
- `rounded-xl` + `border-line` + soft shadow for panels
- Support Matchday and Pitch Night
- Use official logo lockup / mark assets from `brand/` and `frontend/public/brand/`
- 44px minimum interactive height
- Invite-only framing when talking about access

### Never

- Purple / indigo “AI default” themes
- Warm cream + terracotta editorial looks
- Newspaper / broadsheet layouts
- Glow stacks, emoji rows, pill clusters as decoration
- Cards in a hero that aren’t interactive
- Replacing Midtable with the repo name in UI
- Rounding the rank-mark squares or dropping the center frame gap

---

## Related files

| Path | What |
|------|------|
| [`midtable-brand-guide.html`](./midtable-brand-guide.html) | Printable visual companion |
| [`brand/`](../../brand/) | Logo presentation SVGs (Matchday, Pitch Night, variants) |
| `frontend/public/brand/` | App lockups, marks, favicons |
| `frontend/src/components/MidtableLogo.tsx` | Theme-aware logo component |
| `frontend/src/app/globals.css` | Color tokens, themes, base type |
| `frontend/src/lib/theme.tsx` | Theme preference & persistence |
| `frontend/src/components/ui/` | Buttons, cards, and chrome primitives |

When tokens change in CSS, update this guide.
