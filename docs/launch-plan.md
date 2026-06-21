# Tracewall — Launch Plan (brand & marketing)

**Date:** 2026-06-20 · **Scope:** how we get Tracewall launched and in front of people — brand, messaging, channels. Prioritized **P0 → P2**. P0 = must exist before you launch at all; P1 = the launch moment; P2 = sustain & grow. Companion: [tracewall-business-plan.md](tracewall-business-plan.md) §7 (this operationalizes it).

> **Update 2026-06-20:** business plan done; **Priority 1 / P0 Foundation is complete.** Positioning, audience, and differentiators (§P0.1) are solid, and the **name is locked: `Tracewall`** — chosen after the working name collided with a live adjacent product (tracewall.ai) and a two-round naming pass showed almost every alternative was already taken by a 2026 agent-security tool; Tracewall came back clean on domains, PyPI, npm, and GitHub (§P0.2). Next: secure the domain + handles, run the rename rollout, and start Priority 2 (identity & landing page).

---

## The priority stack at a glance

| Tier | Meaning | Items |
|---|---|---|
| **P0** | Can't launch without these | Positioning & messaging · brand basics (name/domain/handles/identity) · landing page live · GitHub repo as storefront · email capture + analytics |
| **P1** | The launch moment | Announcement narrative · launch venues (Show HN, Product Hunt, communities) · 60–90s demo · launch-day checklist · early social proof |
| **P2** | Sustain after launch | Content engine (agent safety / EU AI Act) · SEO · docs/blog/changelog · community · weekly metrics · security-buyer outreach |

The rule: **P0.1 (messaging) is the bedrock — the landing page, the README, the launch post, and every tagline are derived from it.** Get it right first; it's written in full below.

---

# P0 — Foundation

## P0.1 — Positioning & messaging  *(the bedrock — drafted, ready to use)*

**Category.** The guardrail & audit layer for coding agents — an **"agent control plane."**

**One-liner.** *A checkpoint in front of your coding agent — every action recorded, risk-checked, and allowed, asked, or denied.*

**One sentence.** Tracewall sits in front of Claude Code, Codex, and other coding agents and checks every action they take — file reads, shell commands, web fetches, tool calls — *before it runs*, learning what's safe from your own allow/block decisions and keeping a tamper-evident trail of everything.

**One paragraph.** Coding agents now read `.env` like a README, install packages, hit the web, and call tools — autonomously. Nobody can watch every action. Tracewall is the layer that lets the agent move fast on the safe 90% and stops or escalates the rest: every action passes through it first, gets a verdict (allow / ask / deny), and is written to a hash-chained, tamper-evident log. You never hand-write rules — you review a run, click allow or block, and Tracewall drafts a reusable policy *with its reason*. The agent earns autonomy as it learns, while you keep a record you can prove.

**Who it's for.**
- **Primary user — developers** running coding agents who want speed without footguns.
- **Economic buyer — security / platform / engineering leads** who must answer *"what did the agent do, and can we prove it?"*

**Why now (the hook).** Agents are touching real systems; the blocker is **governance, not capability**. The EU AI Act's high-risk obligations become enforceable **August 2026**, and the category is consolidating through M&A (Invariant Labs → Snyk, Lakera → Check Point, Protect AI → Palo Alto). Early and opinionated wins.

**Differentiators (the wedge — lead with these).**
1. **Cross-agent, not single-vendor** — one control plane across Claude Code, Codex, and more; the agent vendors only govern their own.
2. **Policy by demonstration** — no rules to hand-write; react to real behavior and the policy writes itself, with reasons.
3. **Tamper-evident, compliance-grade audit** — a hash-chained trail a security team can actually stand behind.
4. **Local-first & open-source** — auditable, no black box. For a *security* tool, that trust is the product.
5. **Audit the boundary, not the brain** — we capture every action that crosses into a real system, not the model's inner monologue.

**Message house — three pillars (use everywhere).**
- **Record** — every action through one gateway, timestamped and attributed to its agent.
- **Risk-check** — deny secrets, ask on the genuinely risky, allow the safe majority — *before it runs*.
- **Learn** — your allow/block decisions become reusable policy; the agent earns trusted autonomy.

**Tagline — LOCKED.** *The brand runs a fort/knight world — see [brand-world.md](brand-world.md).*
> **The knight between your agents and disaster.**
> *From supply-chain vulnerability to agent actions you can't trace, Tracewall keeps the fort secure.*

Backups (same world): "Nothing passes unseen." · "Move boldly. The wall holds." · "The wall, and the knight who mans it."

**Boilerplate (for Product Hunt / press / repo).** *Tracewall is an open-source guardrail and tamper-evident audit layer for coding agents. Every action an agent takes — file reads, shell commands, web fetches, tool calls — passes through Tracewall first, is risk-checked and allowed / asked / denied, and is recorded to a hash-chained log. Teams adopt agents without betting the company on blind trust.*

**Voice.** Plain, confident, technical — now with a spine of courage and gravitas (the fort/knight world, [brand-world.md](brand-world.md)). Medievalism lives in *nouns and posture* (the wall, the watch, the Chronicle, hold the line), never in costume — no olde-English, no fantasy, no hype or exclamation marks. We earn gravitas; we don't cosplay. Speak to "you"; the product is "Tracewall," never "we."

## P0.2 — Brand basics
- **✅ Name — LOCKED: `Tracewall`.** The working name collided head-on with a live adjacent product ([tracewall.ai](https://tracewall.ai/)), and a two-round naming pass found nearly every guardrail/gate/audit name already claimed by a 2026 agent-security tool (Tollgate, Sluice, Cordon, Gateward, Latchgate, …). **Tracewall** came back clean — no software/security product uses it, free on the package registries — and it's on-message: *trace* (the tamper-evident audit trail) + *wall* (the guardrail). Run a final USPTO/registrar check before purchase.
- **Secure now (your action — I can't register domains or create accounts):** `tracewall.com` (parked/buyable; grab `tracewall.dev` too), the `tracewall` package name on **PyPI** and **npm** (both free — claim immediately), the **GitHub org** `tracewall`, **X/Twitter** + **LinkedIn** `tracewall`, and a `hello@tracewall.com` mailbox.
- **Rename rollout (tracked follow-on):** swap the name across this doc, the README, the repo, the Python package + CLI (`tracewall` → `tracewall`), and the design assets — mechanical but it touches many files; do it before the landing page goes live so everything reads consistently.
- **Visual identity:** already defined — the green "verified/allow" accent, the shield-with-check mark, Inter + JetBrains Mono, the allow/ask/deny color system. Reuse the design system from the product design work; re-skin to the final name.
- **Claim handles now (even if unused):** GitHub org, X/Twitter, LinkedIn page, **PyPI + npm** package names; consider a Discord for early users.

## P0.3 — Landing page  *(the #1 converting asset — already designed, get it live)*
The marketing landing is already designed (hero, install command, recent-actions card, Record/Risk-check/Learn). Ship it. Non-negotiables: the one-liner as the headline, `pip install tracewall` front and center, the allow/ask/deny visual, a primary CTA (**Get started** / **Star on GitHub**), and an **email capture for the Teams waitlist**.

## P0.4 — The GitHub repo as a storefront
For an open-source dev tool the README *is* your second landing page. Polish: a one-line hero + badge row, a 30-second quickstart, a short allow/ask/deny **demo gif**, the "what it covers / doesn't" table, and a clear contribution + license note. Most early traffic will judge you here.

## P0.5 — Capture + measure
- **Waitlist / email** for the Teams tier (so adoption has somewhere to convert).
- **Analytics** (Plausible or PostHog) on the site and install funnel from day one.
- **A line to early users** — a Discord/issues/email so the first installers can talk to you.

**P0 exit criteria:** locked messaging → a live landing page and a polished repo that both say the same thing → handles claimed → email capture + analytics running. After this you are *launch-ready*.

---

# P1 — The launch moment

- **Announcement narrative.** One sharp post: the problem (agents act autonomously on real systems), the insight (audit the boundary, policy by demonstration), the demo (it blocks a real `.env` read, drafts a rule), the ask (try it / star it / join the waitlist).
- **Venues, sequenced:** Show HN + a Launch/Product Hunt, then X and LinkedIn, then the agent-dev communities (Claude Code / Codex Discords, relevant subreddits), then a dev newsletter or two.
- **A 60–90s demo** (screen capture of the loop: agent tries something risky → Tracewall asks → you block → it writes the policy). This single asset does most of the persuading.
- **Launch-day checklist & sequencing** (who posts what, when; first-comment FAQ ready; monitoring inbound).
- **Early social proof:** 2–3 quotes from design partners who've blocked ≥1 real risky action.

---

# P2 — Sustain & grow

- **Content engine** aimed at both audiences: agent-safety pieces for developers; "prove your agents are governed" / EU AI Act readiness for security buyers.
- **SEO + docs + a changelog/blog** so adoption compounds and the project looks alive.
- **Community** (Discord, good first issues) and a **weekly metrics** habit (installs, stars, WAU, waitlist).
- **Top-down outreach** to the security/platform buyers once the developer base shows pull.

---

## Do-now checklist (P0)

- [ ] Lock the primary tagline + the one-liner from P0.1
- [x] ✅ **Name locked: Tracewall** (working name collided with tracewall.ai; full naming pass in §P0.2). Now secure `tracewall.com`, the `tracewall` GitHub org + PyPI + npm, and X/LinkedIn; set up `hello@tracewall.com`.
- [ ] Claim GitHub org, X, LinkedIn handles
- [ ] Ship the landing page (from the existing design) with email capture
- [ ] Polish the README hero + quickstart + demo gif
- [ ] Install analytics; stand up the Teams waitlist
