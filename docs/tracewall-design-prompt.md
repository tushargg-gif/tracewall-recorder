# Tracewall — Master Design Prompt

> Paste this whole document into a design-capable AI (Claude artifacts, a Figma-generation tool, etc.) to generate the Tracewall product design. It is self-contained: product context, visual system, every screen, copy, and output spec. Edit the **Output format** section to target HTML, React, or Figma.

---

## 0. Role & objective

You are a senior product designer and front-end engineer. Design the **complete, end-to-end product experience for Tracewall** — from first install to team rollout — as a set of high-fidelity, desktop screens. The work must look like a real, shipping developer-infrastructure product: precise, restrained, and trustworthy. **No gimmicks, no neon, no decorative gradients.** Think Linear / Stripe / Vercel / Vanta levels of polish.

Design **11 screens** (listed in §5) plus a foundations/style sheet. Each screen is a `1440 × 960` desktop frame.

---

## 1. Product context

**Tracewall** is an open-source **guardrail + tamper-evident audit layer that sits in front of coding agents** (Claude Code, Codex, and similar). Every action an agent takes — file reads, shell commands, web fetches, MCP/tool calls — passes through Tracewall *before it runs* and is **recorded, risk-checked, and allowed / asked / denied**.

The magic is **policy by demonstration**: the user never hand-writes rules. They review a run, click allow or block on real actions, and Tracewall drafts a reusable policy *with its reason*. Over time the agent earns more autonomy while everything stays recorded in a **hash-chained, tamper-evident audit log**.

Three-word model: **Record → Risk-check → Learn.**

**Who it's for:** the primary user is a developer running coding agents; the economic buyer is a **security / platform / engineering lead** who must answer "what did the agent do, and can we prove it?" Design for both — developer-grade ergonomics, buyer-grade governance and audit.

**Core semantic system (use everywhere):** every agent action resolves to one of three verdicts — **Allow** (green), **Ask / escalate** (amber), **Deny / block** (red). A fourth accent, **violet**, is reserved exclusively for AI-generated policy suggestions.

---

## 2. Visual direction

Professional, light, calm, and dense-but-legible. High contrast, generous whitespace, hairline borders, flat surfaces. Color is used sparingly and only to carry meaning (the allow/ask/deny system). Dark UI appears **only** where it is real: terminal windows and the code editor.

---

## 3. Design system (use these exact tokens)

**Neutrals (cool gray):**
- Ink: `#0C111D` (primary text / strongest), `#1D2939`, `#344054` (body strong), `#475467` (secondary), `#667085` (muted), `#98A2B3` (placeholder)
- Borders: `#D0D5DD` (strong), `#EAECF0` (hairline — default)
- Surfaces: `#FFFFFF` (cards), `#F9FAFB` (page bg), `#F2F4F7` (subtle fill)

**Accent — green = "verified / allow" (the brand color):**
- `#079455` primary, `#027A48` text-on-light, `#DCFAE6` tint fill, `#ECFDF3` subtle

**Semantic:**
- Ask / warning (amber): `#F79009`, text `#854F0B`, tint `#FEF0C7`, subtle `#FFFAEB`
- Deny / error (red): `#F04438`, text `#B42318`, tint `#FEE4E2`, subtle `#FEF3F2`
- AI policy (violet — AI suggestions only): `#6938EF`, text `#5925DC`, tint `#F4F3FF`, border `#DAD3FB`

**Dark surfaces (terminal / IDE only):** bg `#0C111D`, panel `#161B26`, border `#243041`, text `#E6EBF2`, muted `#8A95A5`, green prompt `#5BE49B`.

**Typography:** UI font **Inter** (weights 400 Regular, 500 Medium, 600 Semi Bold — two weights per screen max). Monospace **Roboto Mono / JetBrains Mono** for commands, file paths, hashes, code.
Scale (size / line-height): Hero 46/54 (tracking −2%) · Display 28/36 · H2 20/28 · H3 16/24 · Body 14/22 · Body-medium 14/20 (500) · Small 13/18 · Caption 12/16 (Medium, +2% tracking, used as section eyebrows) · Mono 13/20.

**Layout:** 8px spacing system (4/8/12/16/24/32/48/64). Radius: 8 (controls), 12 (cards), 16 (large cards/modals); pills fully rounded. Borders 1px hairline `#EAECF0`. No drop shadows except a soft elevation on modals. Sentence case everywhere.

**Components to define once and reuse:**
- Buttons: primary (green `#079455`, white text), secondary (white, `#D0D5DD` border, ink text), destructive-outline (red text/border). Height ~44, radius 8.
- Pills/badges: Allowed (green tint/`#027A48`), Ask (amber tint/`#854F0B`), Denied (red tint/`#B42318`), AI policy (violet tint/`#5925DC`).
- Cards: white, 1px `#EAECF0`, radius 12, padding 20.
- Code/terminal block: dark `#0C111D`, mono, green prompt.
- App shell: left sidebar (240px, white, hairline right border) with logo + nav (Dashboard, Review, Policies, Audit log, Agents, Settings) and an `acme / payments-api` workspace footer; top bar (64px) with page label, an amber "N awaiting review" pill, and a user avatar.
- Logo: a green rounded square (`#079455`) with a white check, wordmark "Tracewall" (Inter Semi Bold, −1% tracking).

---

## 4. Copy & tone

Plain, confident, technical. Short labels. Real commands and data, never lorem ipsum. Reusable sample data:
- Repo `acme / payments-api`; agents `claude-code` (user "Tushar"), `codex` (CI runner), `claude-code` (user "Priya").
- Sample actions: `git status` → allowed; `read src/server.py` → allowed; `pip install stripe-agent-toolkit` → ask; `write src/webhooks.py` → allowed; `read .env` → **denied** (secret file); `web fetch api.stripe.com` → ask; `read config.yaml → opened .env` → **flagged (intent ≠ effect)**; `mcp github.create_pr` → ask.
- Install: `pip install tracewall`, then `tracewall init` and `tracewall install-hook`.

---

## 5. Screens to design (11)

Lay them out left-to-right as one end-to-end journey, grouped in five stages.

**Stage A — Discover & install**
1. **Install (web landing).** Top nav (logo; Docs, Pricing, GitHub ★2.4k; "Get started" button). Hero (left): eyebrow "GUARDRAILS FOR CODING AGENTS"; headline "A checkpoint in front of your coding agent."; subtext explaining record/risk-check/allow-ask-deny + learns from your decisions; a dark install command block `$ pip install tracewall` with a Copy affordance; secondary line `tracewall init · tracewall install-hook`; "Works with: Claude Code · Codex". Right: a white "Recent actions" card listing 4 sample actions each with an allow/ask/deny pill and a "hash-chained ✓" note. Bottom: three feature columns — Record / Risk-check / Learn.

**Stage B — Set up**
2. **CLI setup (dark terminal).** A realistic macOS terminal window centered on a light page. Shows `pip install tracewall` → success; `tracewall init` → `✓ created .tracewall/`; `tracewall install-hook` → `✓ wired into .claude/settings.json (PreToolUse, PostToolUse)` and `✓ now guarding claude-code · codex`; closing line "Restart Claude Code to begin." Caption beneath: "Two commands — one to install, one to wire it into your agent."
3. **Connected (success).** Centered white card on light bg: green check circle, "You're protected", subtext "Tracewall is guarding your agent in payments-api…", a status list (claude-code ✓ active, codex ✓ active, audit log ✓ recording, policy engine ✓ 12 rules), primary button "Open control plane →".

**Stage C — First value (the "aha")**
4. **Approval prompt (live escalation).** A dimmed full-screen scrim with a centered modal: amber warning glyph + "Approval needed" + "claude-code · payments-api · before it runs"; line "The agent wants to install a package:"; dark code box `$ pip install stripe-agent-toolkit`; a context note ("Part of task 'add Stripe webhook handler.' Installing pulls third-party code — Tracewall paused the agent."); a checkbox "Remember my decision as a policy for this repo"; buttons: **Allow once** (green), **Always allow** (secondary), **Block this action** (red outline, full width).
5. **Review (HERO screen).** Full app shell. Page title "Review a run" + subtitle. A run-header card (task "add Stripe webhook handler", source claude-code, "in progress" pill). Two columns:
   - Left — **Action timeline** card: the 8 sample actions as rows (color-coded icon chip, mono command, why-subtext, verdict pill, timestamp). The `pip install` row is **selected** (light highlight + green left bar). The `read config.yaml → .env` row is shown in red as an **intent ≠ effect** mismatch — the highest-signal catch.
   - Right — **Detail panel** for the selected action: title "Package install", a key/value box (source, repo, category, default = ask), dark code box, an amber explainer ("Installing a package can pull arbitrary code…"), three verdict buttons (Allow [green, active] / Ask / Block), and below them the **AI policy card** (violet): "✦ Policy by demonstration", rule "Allow pip install from this repo", a one-line reason, a mono scope chip `cmd = pip/npm install · repo = payments-api → ALLOW`, and buttons Accept rule / Edit / Dismiss.
6. **Policy created (confirmation).** Centered card: green check, "Policy created", the new rule shown in a violet-tinted box with its scope, a note "Next time, this action passes automatically — still recorded.", and a small "9 → 10 policies" counter. Reinforces the loop closing.

**Stage D — Daily use**
7. **Dashboard (fleet overview).** App shell. Four metric cards: Actions today `3,482`, Auto-allowed `94.2%` (green, "policy is learning"), Escalated `181` ("4 awaiting"), Blocked `37`. A "Trust trend — autonomy earned" area chart climbing from 71% → 94% over 14 days. A "Recent risky events" feed (denied .env read, asked pip install, flagged intent≠effect, asked web fetch). An agents table (agent, source, repo, actions, asked, blocked, last event).
8. **Policies.** App shell. List of policy rows, each: an icon tinted by verdict, the rule name, a mono scope, provenance ("from your block · 2 days ago" or "default"), and an on/off toggle. Sample rules: Block reading secret files (.env, *.pem, *.key); Allow read-only git; Ask before installing packages; Ask before outbound web requests; Block destructive shell outside workspace. Header note: "You never hand-wrote any of these."
9. **Audit log.** App shell. A dense table: Time, Source (claude-code/codex), Action (mono), Verdict pill, and "Entry hash ← prev" (mono, with a small chain icon) — emphasizing tamper-evidence. Header actions: "Verify chain" and "Export for auditor". Caption: "One ordered timeline across every agent."
10. **VS Code extension panel (dark IDE).** A faux VS Code window: title bar, activity bar, file tree (with `.env` marked locked), an editor showing `webhooks.py`, and a docked **Tracewall panel** (bottom) running the same review loop in miniature — action rows with inline Allow/Block, a "denied" state on `.env`, and a violet "Suggested: allow pip install for this repo → Accept" row.

**Stage E — Scale**
11. **Team / upgrade.** App shell or settings view. Invite teammates (email field + role select + a member list with avatars/roles), a "shared policy across the team" note, and an upgrade panel comparing **Free (local, single developer)** vs **Team (centralized retained audit, SSO, roles, dashboards)** with a primary "Upgrade to Team" button. Frame the value as: developers adopt free; teams pay for centralized governance, retention, and compliance.

Also produce a **Foundations** board: color swatches (with hex), the type scale, and the component atoms (buttons, the four pills, code chip).

---

## 6. Output format

Produce **[CHOOSE ONE: a single self-contained clickable HTML/CSS prototype  |  a React + Tailwind component set  |  Figma frames]**. Requirements:
- Desktop `1440 × 960` per screen; ship all 11 + the Foundations board.
- Use the exact tokens in §3; reuse the shared app shell and components; keep spacing on the 8px grid.
- Real sample data from §4 — no placeholders.
- If interactive: clicking an action in Review updates the detail panel; clicking a verdict reveals the AI policy card; a button opens the approval modal. Persist nothing to browser storage; in-memory state only.
- Accessibility: AA contrast, visible focus states, semantic structure.
- Deliver clean, production-quality layout — alignment, optical spacing, and consistent radii must be exact. Then self-review each screen against this brief and fix any misalignment, overflow, or inconsistency before finishing.
```
```
