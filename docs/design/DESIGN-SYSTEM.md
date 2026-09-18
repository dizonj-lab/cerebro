# CEREBRO — Design System

CEREBRO should read as a personal intelligence workspace: modern, minimalist,
calm, precise, trustworthy. Not social media, not an admin dashboard, not a
crypto app, not a sci-fi control panel.

## Brand

Name **CEREBRO**, tagline **Adaptive Knowledge and Reasoning Digital Twin**,
pillars **Learn · Connect · Reason · Recall**. All three live in the `BRAND`
constant in `src/components/brand/Logo.tsx` and are never retyped in a page.

Two compositions, both from that module:

| Component      | Contents                            | Used on                      |
| -------------- | ----------------------------------- | ---------------------------- |
| `<Logo />`     | mark + wordmark                     | Construct header, footer     |
| `<LogoLockup />` | mark + wordmark + tagline + pillars | Landing hero, auth pages     |

`LogoLockup` takes `compact` (drops the pillar strip) and `showWordmark`
(false on the landing hero, where the header already carries the wordmark).

The mark is decorative everywhere — `alt=""` and `aria-hidden` — because the
accessible name comes from the adjacent `CEREBRO` text. The wordmark is set in
type rather than baked into the artwork so it stays crisp at every size,
inherits the ink token and remains selectable and searchable.

**The artwork at `public/brand/cerebro-mark.svg` is a placeholder.** See
`frontend/public/brand/README.md` for what to supply.

## Tokens

All tokens live in `frontend/src/app/globals.css` under `@theme`. Nothing else
declares a raw colour.

### Surfaces

| Token             | Value     | Use                           |
| ----------------- | --------- | ----------------------------- |
| `canvas`          | `#ffffff` | Page background               |
| `surface`         | `#ffffff` | Cards, inputs, header         |
| `surface-subtle`  | `#f7f8fa` | Sidebar, inert chips          |
| `surface-sunken`  | `#f2f4f7` | Recessed areas                |

### Text — every value passes WCAG AA on every surface above

| Token        | Value     | Canvas | Subtle | Sunken |
| ------------ | --------- | ------ | ------ | ------ |
| `ink`        | `#14171c` | 17.96  | 16.87  | 16.30  |
| `ink-muted`  | `#5b6472` | 5.98   | 5.62   | 5.43   |
| `ink-subtle` | `#636c7a` | 5.31   | 4.99   | 4.82   |

### Accent — exactly one

| Token            | Value     | Use                                |
| ---------------- | --------- | ---------------------------------- |
| `accent`         | `#2a5d9f` | Primary buttons, links, active nav |
| `accent-hover`   | `#234f88` | Hover                              |
| `accent-subtle`  | `#eef3fa` | Active nav background, avatar      |

`accent` is 6.64:1 against white in both directions, so it is valid as a button
background with white text and as link text on white.

### Semantic — only where meaning demands it

`danger` `#b42318` (6.57:1), `danger-subtle` `#fef3f2`, `success` `#067647`.

### Radius and elevation

Radius: `sm` 6px, `md` 8px, `lg` 12px. Moderate and consistent.
Shadows: `subtle` and `card` only — both barely perceptible. No glows.

## Component layering

```
Tokens → UI primitives → CEREBRO components → Pages → The Construct
```

Primitives (`src/components/ui/`): `Button`, `Input`, `FormField`, `Card`,
`ErrorMessage`, `LoadingState`.

CEREBRO components: `Logo` (brand), `AuthShell` (auth), and `Sidebar`,
`NavigationItem`, `ConstructHeader`, `UserMenu`, icons (construct).

Only the primitives today's four pages actually need were built.

## Rules

- Content dominates chrome. Generous whitespace, subtle borders, restrained
  shadows.
- One accent. No neon, no glow, no gradients, no glassmorphism.
- No decorative charts and no fake data.
- Every interactive control has a visible focus ring (`:focus-visible`,
  2px accent, 2px offset).
- Placeholder navigation announces itself as such (`aria-disabled`, tooltip)
  rather than silently doing nothing.
- Semantic HTML: one `h1` per page, real `<label>`s, `role="alert"` on
  validation messages, `aria-busy` on submitting buttons.

## Verification

Accessibility is asserted, not assumed: `frontend/e2e/ui.spec.ts` runs axe-core
against all four pages for WCAG 2.1 A/AA and fails the build on any violation.
Responsiveness is asserted at 375, 768 and 1440 with a no-horizontal-overflow
check.
