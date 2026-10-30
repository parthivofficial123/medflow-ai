# MedFlow AI design system

One stylesheet (`public/static/css/app.css`), one script (`public/static/js/app.js`), no build
step and no libraries. Every token below is a custom property on `:root`; components use only
tokens, never raw values. If you add a value twice, make it a token.

**Character:** calm, precise, trustworthy. A tool for reading money and dates carefully, not a
marketing site. Restraint first: one accent color, neutral surfaces, motion that confirms
what just happened and then gets out of the way. Reference points: Linear's density and
typographic hierarchy, Vercel's neutral surfaces, Raycast's quick and physical feedback.

## Color

Semantic tokens only. Each has a dark value (the default) and a light value (`:root[data-theme="light"]`), chosen with the footer's theme switch and kept in a cookie the server reads, so the first paint is already right.

| Token | Use | Light | Dark |
|---|---|---|---|
| `--color-bg` | page background | `#f6f8f9` | `#0c1216` |
| `--color-surface` | cards, inputs, top bar | `#ffffff` | `#141c22` |
| `--color-surface-2` | tiles, notes, hover fills | `#f0f4f5` | `#1b252c` |
| `--color-text` | body text | `#16212a` | `#e6edf2` |
| `--color-muted` | secondary text, labels | `#56636f` | `#9aa8b5` |
| `--color-border` | card and row dividers | `#dde4e8` | `#26323b` |
| `--color-border-strong` | inputs, secondary buttons (3:1 against surface) | `#8794a0` | `#5f6e7a` |
| `--color-primary` | the one accent: primary buttons, links, current page | `#0f766e` | `#2bb5a8` |
| `--color-primary-soft` | accent fills (current nav item, date badge) | `#e2f3f0` | `#12302d` |
| `--color-danger` / `-soft` | destructive actions, errors, unpaid | `#b42318` | `#ff8a80` |
| `--color-warning` / `-soft` | "check this", AI uncertainty, reminders | `#8a4b00` | `#ffc266` |
| `--color-success` / `-soft` | confirmations, paid, totals that match | `#0a6b3f` | `#6fd6a0` |
| `--color-focus` | focus outline (never reused for anything else) | `#2563eb` | `#7aa7ff` |

Rules:
- Text on any background meets WCAG AA (4.5:1 body, 3:1 large text and UI boundaries). The
  pairs above are checked: muted on surface-2 is the weakest text pair at 5.6:1 (light);
  `--color-border-strong` is 3.1:1 on surface.
- Status is never color alone: every pill has a word, every error has text and an icon.
- Warning (amber) means "a person should check this"; danger (red) means "this removes data or
  is wrong". AI-uncertain fields are warning, not danger.

## Typography

System font stack (`--font-sans`): no web font, nothing to download, no layout shift.

| Token | Size | Use |
|---|---|---|
| `--text-xs` | 0.75rem | labels, pills, hints |
| `--text-sm` | 0.875rem | meta text, tables, alerts |
| `--text-md` | 1rem | body |
| `--text-lg` | 1.125rem | card and section titles |
| `--text-xl` | 1.375rem | stat values, detail titles |
| `--text-2xl` | 1.75rem | page titles |
| `--text-display` | clamp(2.25rem, 6vw, 3.75rem) | landing hero only |

- Headings: weight 650–700, `letter-spacing: -0.015em` (tighter as they grow; display -0.03em).
- Money and counts: `font-variant-numeric: tabular-nums` so columns line up.
- Line length: prose capped at about 65ch (`.lede`, landing copy).

## Spacing

4px base: `--space-1` 0.25rem, `-2` 0.5rem, `-3` 0.75rem, `-4` 1rem, `-5` 1.5rem, `-6` 2rem,
`-7` 3rem, `-8` 4.5rem (landing sections only). Inside a card: `--space-4`/`--space-5`.
Between top-level blocks: `--space-5`. Page gutter: `--space-4` on phones, `--space-6` from 60rem.

## Radius, borders, shadows

- Radius: `--radius-sm` 6px (chips, small fills), `--radius-md` 10px (buttons, inputs, tiles),
  `--radius-lg` 14px (cards), `--radius-xl` 20px (landing preview window), `--radius-pill`.
- Borders: 1px `--color-border` on every card; 2px only for an error or "check this" state.
- Shadows are soft and layered, never the only edge: `--shadow-sm` (resting card),
  `--shadow-md` (hover on a clickable card), `--shadow-lg` (landing preview only).

## Components and states

Every interactive component has all of these states, in this order of precedence:

| State | Treatment |
|---|---|
| Rest | border + `--shadow-sm` for cards; solid fill for primary buttons |
| Hover (pointer devices only) | one step darker fill, or stronger border + `--shadow-md` on clickable cards |
| Pressed | `scale(0.97)` on buttons, instantly; releases with the spring |
| Focus-visible | 3px `--color-focus` outline, 2px offset. Inputs: 2px outline at 0 offset plus a soft ring. Never removed. |
| Disabled / busy | 0.7 opacity, `cursor: progress`, label changes to say what is happening ("Reading your bill…") |
| Error | danger border (2px), message below the field linked by `aria-describedby`, summary at the top linking to each field |

Components (class names in `app.css`): `.btn` (`--primary`, `--secondary`, `--danger`,
`--danger-outline`, `--ghost`, `--sm`, `--lg`, `--block`), `.card`, `.panel`, `.form-card`,
`.field`, `.input`, `.alert` (`--success`, `--warning`, `--error`), `.pill` (one per status),
`.chip`, `.count`, `.stats`/`.stat`, `.table`, `.empty`, `.segmented`, `.skeleton`.

Tap targets are at least 44×44px (`2.75rem`) everywhere, including icon buttons and inline links
in cards.

## Motion

Motion explains a change: something appeared, something was saved, something is busy. It never
decorates, never delays reading, and never pretends to know progress it doesn't have.

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 90ms | press feedback |
| `--dur-fast` | 150ms | hover, color, border |
| `--dur-base` | 240ms | entrances, alerts |
| `--dur-slow` | 420ms | landing preview only |
| `--ease-out` | `cubic-bezier(0.22, 1, 0.36, 1)` | entrances and exits |
| `--ease-spring` | a `linear()` curve sampled from a spring (stiffness ≈ 380, damping ≈ 30), slight overshoot | press release, pop-in of a confirmation |

Principles (after Apple's spring guidance and "Make Interfaces Feel Better"):
1. **Fast.** Nothing in the app takes longer than 240ms; most is 150ms. Only the landing page's
   one-time preview runs longer.
2. **Small distances.** Entrances move 4–8px and fade; nothing slides across the screen.
3. **Only `opacity` and `transform`** are animated (compositor-only). No animated width, height,
   top/left, blur or box-shadow loops.
4. **Interruptible.** Hover and press use CSS transitions, which reverse from wherever they are
   when interrupted; no animation has to finish before you can act.
5. **Stagger sparingly.** Lists reveal with a 35ms stagger, capped at the first 8 items so a long
   list never makes you wait.
6. **Honest progress.** Waiting for the AI shows an indeterminate shimmer and a plain sentence;
   no percentages, no fake steps. Extracted charges appear only on the review page, after the
   server has checked the answer.
7. **Page changes** load normally, with no cross-fade. Chromium's cross-document View Transitions
   were tried and removed: each skipped transition logged an uncaught `AbortError` in the console.

No animation library is used. CSS transitions and keyframes cover every effect above, which
keeps the app working under its Content-Security-Policy (`default-src 'self'`: no CDN scripts,
no inline styles) and adds no dependency. If a future sequence genuinely needs JavaScript-driven
springs, the Web Animations API is built in; a library (Motion) would need approval and would be
vendored into `public/static/js/`, never loaded from a CDN.

## Reduced motion

`prefers-reduced-motion: reduce` turns every animation and transition off (one global rule at the
end of `app.css`), and every keyframe animation is also declared inside
`@media (prefers-reduced-motion: no-preference)`, so the final state is the default state.
Nothing is hidden waiting for an animation: with reduced motion, without JavaScript, or in an
old browser, the page simply appears complete. The busy shimmer becomes a static placeholder.

## Responsive behavior

Mobile-first; checked at 375px, 768px and 1280px.
- **< 40rem (phones):** nav moves to its own row under the logo and scrolls sideways if needed;
  stat tiles two per row; forms sit under lists, with a "jump to form" button in the page header.
- **40–60rem (tablets):** one column, wider cards; landing capability cards in a row.
- **≥ 60rem (desktop):** list + sticky form side by side (`.split`), 72rem max container.
- Long provider names and descriptions wrap (`overflow-wrap: anywhere`); tables scroll inside
  their card, never the page.

## Accessibility

- Semantic HTML first: `header`/`nav`/`main`/`footer`, one `h1` per page, lists for lists,
  tables for tables, `button` for actions, links for navigation.
- Skip link, `aria-current="page"` on the current nav item, `aria-pressed` on toggles.
- Every input has a `<label>`; hints and errors are linked with `aria-describedby`.
- Status changes are announced: flash messages and the busy sentence are `role="status"`;
  form errors are `role="alert"`.
- Decorative SVGs are `aria-hidden="true"`; the landing preview is a `figure` with a caption.
- JavaScript only enhances. Every form works without it.
