# UI/UX audit and upgrade plan (2026-10-29)

Scope: the whole frontend before the product-wide UI and motion upgrade. Design rules that came
out of it are in `DESIGN.md`.

## 1. Current frontend architecture

- Server-rendered Jinja: `base.html` (top bar, flashes, footer), `_macros.html` (`field`,
  `select_field`, `error_summary`), one folder per feature (`appointments/`, `expenses/`,
  `bills/`, `auth/`), `error.html`. 20 templates, no inline scripts or styles.
- One stylesheet, `public/static/css/app.css` (376 lines): tokens on `:root` with a dark-mode
  override, then base, layout, components, feature sections. BEM-ish class names.
- One script, `public/static/js/app.js` (56 lines): the double-submit guard for forms with
  `data-busy-label`. Everything works without it.
- CSP on every response: `default-src 'self'`. That rules out CDN scripts, CDN fonts, inline
  `style=""` attributes and `data:` images in CSS. Any animation must be CSS or a local file.
- `/` redirects to Appointments; signed-out visitors (Supabase mode) are sent to `/login`, a
  single card. There is no page that explains MedFlow before sign-in.

## 2. Strongest existing elements (keep)

- A real token system with a dark mode and AA-level text colors.
- Very careful content design: "Not billed yet" vs. $0, "Unpaid recorded bills. Not verified",
  "Totals are calculated by MedFlow, not by the AI", "AI-generated explanation".
- Accessibility basics done right: skip link, `aria-current`, `aria-pressed`, labelled inputs,
  error summaries that link to fields, 44px tap targets, focus outlines, reduced-motion rule.
- Calm teal accent and neutral surfaces: appropriate for health and money.
- The review page's structure: totals check first, problems flagged in amber, nothing pre-ticked
  when it couldn't be read.

## 3. Problems and inconsistencies

1. **No public front door.** Signed-out visitors see a bare sign-in card.
2. **Flat interaction feedback.** Buttons only change color; no press state; clickable cards
   barely react; inputs have no hover state.
3. **Waiting for the AI looks frozen.** The button text changes, nothing else moves for 2–45 s.
4. **Review page density.** Every charge looks the same whether ticked or not; unticked charges
   don't recede.
5. **Input and secondary-button borders are 1.8:1** against white, below the 3:1 WCAG asks for
   component boundaries.
6. **Empty states are dead ends** ("Add one with the form"), with no next action or icon.
7. **Flash messages have no icon**; success, warning and error differ by color only.
8. **The file input is the raw browser control**, small and hard to hit on a phone.
9. **Top bar scrolls away**; on long expense pages the nav is far away.
10. **No motion system.** Durations and easings are ad hoc (`120ms ease` in two places).

## 4. Visual direction

"Quiet precision": keep the teal and the neutral palette, add depth through layered soft
shadows and a sticky translucent top bar, tighten heading type, give money tabular numerals
everywhere, and let one accent carry all emphasis. Motion is quick and physical (spring on
press, short fades on entrance), never ornamental. The landing page uses the same components as
the app, so it previews the real product instead of a separate marketing style.

## 5. Recommended animation stack

**CSS transitions + keyframes. No library.** (Cross-document View Transitions were tried and removed: they logged console errors.)

- Motion (motion.dev) or GSAP would be a new dependency, which `CLAUDE.md` says needs approval,
  and loading either from a CDN is blocked by our CSP (and fragile on demo day). Vendoring a copy
  is possible later, with approval.
- Every effect on the list (press feedback, hover, staggered reveals, skeletons, alert
  entrances, the bill-item reveal, page cross-fades) is a CSS one-liner or a keyframe. Springs
  come from CSS `linear()` easing sampled from a real spring curve.
- There are no modals or drawers to animate: confirmations are separate pages, which works
  without JavaScript, keeps Back working and was a deliberate choice. Adding modals before a
  demo is a risk with no product benefit, so none were added.

## 6. Changes by page

| Page | Change |
|---|---|
| **New: landing (`/` signed out, `/welcome` always)** | Hero "Medical bills, made simpler.", animated preview of the review screen (fictional bill), three capabilities, upload → review → organize, privacy and prototype limits, Google CTA through the existing `POST /login`. |
| Shell (`base.html`) | Sticky translucent top bar, nav icons, flash icons, footer link to the landing page. |
| Sign-in | Same flow; link back to "What is MedFlow?". |
| Bill upload | Large drop-zone file input; busy state with spinner and an indeterminate shimmer placeholder (no percentages). |
| Bill review | Charges reveal with a short stagger; unticked charges dim; flagged charges get an amber edge; totals check gets an icon. |
| Appointments list/detail | Hover lift on cards, entrance stagger, better empty state with an action. |
| Expenses | Stat tiles and cards stagger in; table row hover; empty state with "Upload a bill" action. |
| Confirm / error pages | Consistent card, icon, primary action. |
| All forms | Input hover/focus ring, 3:1 borders, button press feedback. |

## 7. Prioritized implementation plan

1. `DESIGN.md` + this audit (no code risk).
2. Landing page and its tests (new route and template; auth flow unchanged).
3. Global polish in CSS only: tokens, borders, buttons, inputs, cards, top bar, alerts.
4. Motion in CSS: entrances, stagger, review-page reveal, busy shimmer; all
   off under reduced motion.
5. Small template touches: icons in nav and flashes, empty states, file drop zone.
6. Tests (landing, CSP-safe templates, reduced motion present), full suite, browser checks at
   375/768/1280px, light/dark, reduced motion.

Each step is its own commit, so any one can be reverted alone.

## 8. Risks for the demo and Vercel

- **Demo is tomorrow.** Everything here is CSS and templates; no Python logic, storage, money
  math, auth or CSRF code changes except one new public route. Revert path: `git revert` the
  UI commits.
- **`/` changes for signed-out visitors** (landing instead of a redirect to `/login`). Signed-in
  users still land on Appointments. One existing test asserted the old redirect and was updated.
- **View Transitions** were removed after the end-to-end check: Chromium logged
  "AbortError: Transition was skipped" on ordinary navigation.
- **`:has()`** (dimming unticked charges) is progressive: without it, charges just don't dim.
- **Vercel:** static files stay in `public/static/`; no new files outside it; nothing needs a
  build. Not deployed.
- **CSP:** no inline styles or scripts were added (a test now checks every page).
