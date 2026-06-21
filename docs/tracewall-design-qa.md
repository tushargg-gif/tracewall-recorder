# Tracewall — Design QA & Accessibility Audit

**Standard:** WCAG 2.1 AA · **Date:** 2026-06-20 · **Scope:** the generated design package (5 canvases — Front Door, Aha Loop, Governance, Wireframes, Prototype — + the `_ds` design system). Audit is from source + computed contrast, not pixel rendering.

> **Read this first — what these files are.** The `.dc.html` screens render through a React "design-canvas runtime" (`support.js`) using a DSL (`<sc-for>`, `<x-import>`, `{{ }}` bindings). They display correctly **inside the design tool**, but they are *design artifacts, not production code*. Two consequences: (1) opened as plain files in a browser without that runtime, the `{{ }}` data won't populate; (2) the accessibility gaps below are partly inherent to canvas exports — they matter most as a **spec for the real build** and as **token-level fixes** (which are portable to any build). The fixes I can apply now live in `_ds/.../tokens/*.css`.

---

## Summary

**Issues:** 11 · 🔴 Critical: 3 · 🟡 Major: 5 · 🟢 Minor: 3

The palette is genuinely well-chosen — ink text and all four verdict pills pass comfortably. The failures are concentrated and **fixable at the token level**: button text contrast, missing focus states, and a few misused color steps.

## Priority fixes (do these first)

1. 🔴 **Darken primary & destructive button fills.** White on `--green-600 #079455` = **3.91:1** and white on `--red-500 #F04438` = **3.76:1** — both fail 4.5:1 for the 14px labels. Use `--green-700 #027A48` (→ 5.41:1) and `--red-700 #B42318` (→ 6.57:1) for button *fills*. Highest impact: primary buttons are on every screen.
2. 🔴 **Add a visible focus indicator.** There is no `:focus-visible` rule anywhere in the system (the readme promised a green ring; the CSS doesn't implement it). Add a global 2px `--green-600` outline + 3px tint ring on focusable controls.
3. 🔴 **Make interactive elements real controls.** Clickable items are styled `<div>`s with `onClick` (0 `<button>`/`<a>` in the markup). In the real build, render them as `<button>`/`<a>` (or add `role` + `tabindex="0"` + Enter/Space handlers) so they're keyboard-operable and announced.
4. 🟡 **Stop using `--ink-400` and `--amber-500` for text/icons.** `--ink-400 #98A2B3` (timestamps) = 2.58:1 and `--amber-500 #F79009` as text/status-dot = 2.35:1 both fail. Use `--ink-500` (4.97:1) for meta text and `--amber-700` for amber icons/dots.

---

## Findings

### Perceivable
| # | Issue | WCAG | Severity | Fix |
|---|-------|------|----------|-----|
| 1 | Primary/destructive button text below 4.5:1 (3.91 / 3.76) | 1.4.3 | 🔴 Critical | Button fills → green-700 / red-700 |
| 2 | `ink-400` used for timestamps/meta text (2.58:1) | 1.4.3 | 🟡 Major | Use ink-500 for any real text |
| 3 | `amber-500` as text or status dot (2.35:1; non-text 3:1 also fails) | 1.4.3 / 1.4.11 | 🟡 Major | amber-700 for amber text & icons |
| 4 | 46 inline SVGs with no `aria-hidden`/label; logo unlabeled | 1.1.1 | 🟡 Major | Decorative → `aria-hidden="true"`; logo → `role="img"`+label |
| 5 | Input/control border `#D0D5DD` = 1.47:1 (boundary < 3:1) | 1.4.11 | 🟡 Major | Darken control border to ≥3:1 (e.g. ink-500); card hairlines are exempt |
| 6 | `green-600` used as small text in spots (3.91:1) | 1.4.3 | 🟢 Minor | Green text → green-700 (system already intends this) |

### Operable
| # | Issue | WCAG | Severity | Fix |
|---|-------|------|----------|-----|
| 7 | No visible focus indicator defined anywhere | 2.4.7 | 🔴 Critical | Add `:focus-visible` ring on all controls |
| 8 | `div`+`onClick` not keyboard-reachable/operable | 2.1.1 | 🔴 Critical | Use real `<button>`/`<a>` (or role+tabindex+key handlers) |
| 9 | Verify icon-only targets meet 44×44 (pills/close ✕) | 2.5.5 | 🟢 Minor | Pad small icon buttons to 44px hit area |

### Understandable
| # | Issue | WCAG | Severity | Fix |
|---|-------|------|----------|-----|
| 10 | Form inputs (sign-up email, workspace name, invite) — no visible `<label>`/`aria-label` association | 3.3.2 | 🟡 Major | Associate a `<label for>` or `aria-label` with each field |

### Robust
| # | Issue | WCAG | Severity | Fix |
|---|-------|------|----------|-----|
| 11 | Custom-element controls expose no name/role/value to AT | 4.1.2 | 🔴 Critical | Native semantics in the real build; or ARIA on the canvas components |

---

## Color contrast (computed)

| Pair | FG | BG | Ratio | Need | Pass |
|------|----|----|------|------|------|
| ink-900 / white | #0C111D | #FFFFFF | 18.86 | 4.5 | ✅ |
| ink-700 body / white | #344054 | #FFFFFF | 10.46 | 4.5 | ✅ |
| ink-600 secondary / white | #475467 | #FFFFFF | 7.69 | 4.5 | ✅ |
| ink-500 muted / white | #667085 | #FFFFFF | 4.97 | 4.5 | ✅ |
| **ink-400 / white** | #98A2B3 | #FFFFFF | **2.58** | 4.5 | ❌ |
| green-700 text / white | #027A48 | #FFFFFF | 5.41 | 4.5 | ✅ |
| **green-600 as text / white** | #079455 | #FFFFFF | **3.91** | 4.5 | ❌ |
| **amber-500 as text / white** | #F79009 | #FFFFFF | **2.35** | 4.5 | ❌ |
| amber-700 / white | #854F0B | #FFFFFF | 6.73 | 4.5 | ✅ |
| red-700 / white | #B42318 | #FFFFFF | 6.57 | 4.5 | ✅ |
| **red-500 as text / white** | #F04438 | #FFFFFF | **3.76** | 4.5 | ❌ |
| violet-700 / white | #5925DC | #FFFFFF | 7.71 | 4.5 | ✅ |
| Pill — allow (g700/tint) | #027A48 | #DCFAE6 | 4.86 | 4.5 | ✅ |
| Pill — ask (a700/tint) | #854F0B | #FEF0C7 | 5.93 | 4.5 | ✅ |
| Pill — deny (r700/tint) | #B42318 | #FEE4E2 | 5.45 | 4.5 | ✅ |
| Pill — AI (v700/tint) | #5925DC | #F4F3FF | 7.02 | 4.5 | ✅ |
| **Button white / green-600** | #FFFFFF | #079455 | **3.91** | 4.5 | ❌ |
| **Button white / red-500** | #FFFFFF | #F04438 | **3.76** | 4.5 | ❌ |
| dark-text / dark-bg | #E6EBF2 | #0C111D | 15.74 | 4.5 | ✅ |
| dark-muted / dark-bg | #8A95A5 | #0C111D | 6.22 | 4.5 | ✅ |
| green-prompt / dark-bg | #5BE49B | #0C111D | 11.69 | 4.5 | ✅ |
| **UI border / white** | #EAECF0 | #FFFFFF | **1.18** | 3.0 | ❌* |
| **UI border-strong / white** | #D0D5DD | #FFFFFF | **1.47** | 3.0 | ❌* |

\* Card hairlines are decorative and **exempt** from 1.4.11; this only fails where the border is the *sole* boundary of a control (inputs, toggles).

---

## Design critique (beyond accessibility)

**What's strong** — faithfully on-brief: the allow/ask/deny + violet-for-AI system is applied consistently; the voice ("you never hand-wrote any of these") matches the spec; tokens, type scale, and 8px spacing are clean. It sensibly **extended** the journey with sign-up, a "Just me / My team" workspace step, and a "run fully local, no account" path — which aligns with the open-core, developer-first strategy. The interactive Prototype tying land→sign-up→install→guarding is a real asset.

**Refinements to consider**
- **Render/packaging:** the canvases need the dc-runtime to populate data. For a shareable demo or the real site, export a static build (or implement for real) so nothing depends on the design host.
- **States:** only happy-path is shown. Add empty (no actions yet), loading, and error/blocked-by-network states — especially for the dashboard and review timeline.
- **Responsive:** everything is fixed 1440 desktop. Define at least a tablet breakpoint for the marketing site (the app can stay desktop-first).
- **amber tone:** `#F79009` is a vivid orange; fine as a fill behind dark text, but never as the text/icon itself (see contrast). Consider `--amber-600` for any standalone amber graphic.
- **Heading order:** confirm each screen goes h1→h2→h3 without skipping when multiple screens share one document.

---

## How to apply

I can patch these **now** in the design-system CSS (portable to any future build):
- `tokens/colors.css` / `styles.css`: add `--btn-primary-bg: var(--green-700)` and `--btn-danger-bg: var(--red-700)`; add a `--border-control` token ≥3:1; swap green-600→green-700 for text roles.
- `base.css`: add a global `:focus-visible` ring and an `aria-hidden` convention for decorative SVGs.

The **semantic/keyboard items (3, 8, 10, 11)** can't be truly fixed in a canvas export — they belong in the real front-end build (use native `<button>`/`<a>`/`<label>`). I've written them as exact requirements so they're a one-pass checklist when you implement.
