# Tracewall — Business Model Plan

**Audience:** founder (commercial compass — companion to [north-star.md](north-star.md))
**Date:** 2026-06-18
**Status:** v1 — a decision document, not a finished strategy. Built to be revised as real signals come in.

> You're full-time with 12+ months of runway, and the three big questions — *how
> ambitious, who pays, open or closed* — are still open. Good. That's the right place to
> be. This doc doesn't force those decisions; it gives you a defensible default for each,
> the reasoning, and a 12-month plan whose whole job is to **turn "not sure" into evidence.**

---

## TL;DR — the recommendation in one breath

1. **Stay open — but go open-core, not pure-OSS-with-a-tip-jar.** Keep the local,
   single-developer guardrail free and Apache-2.0 forever; that's your distribution
   engine. Charge for the **team/org control plane** — the shared, centralized,
   retained, compliance-grade layer that only matters once more than one human and one
   agent are involved.
2. **Developers adopt; security & platform leads pay.** This is the Snyk motion exactly.
   Win the individual developer with the free tool, but design every paid feature for the
   person who has to *answer for* what the agents did.
3. **It's not extension vs. app vs. CLI — it's all three, with different jobs.** The
   CLI/hooks are how actions flow through you (the moat). The VS Code extension is the
   daily-driver adoption surface. The **hosted control-plane web app is the product you
   sell.**
4. **Don't price hard yet.** Use the runway to drive adoption and recruit 3–5 design
   partners; let *them* tell you the willingness-to-pay and which buyer is real. The plan
   below has explicit gates that decide venture-scale vs. indie *for* you, based on what
   you observe.

The single most useful fact for this whole document: the company most similar to you —
**Invariant Labs**, open-source guardrails for agents and MCP — was **acquired by Snyk**.
**Lakera** (agent-security guardrails) was acquired by **Check Point**; **Protect AI** by
**Palo Alto Networks**. The category you're in is real, venture-shaped, and already
consolidating. ([Snyk/Invariant](https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/), [Check Point/Lakera](https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/))

---

## Part 1 — "Why would anyone pay if it's open?"

This is the right question, and the answer is well-established: **people don't pay for the
bits. They pay for the things that only become valuable at organizational scale, and for
not having to run it themselves.** Open source is the *distribution* strategy; it is not,
by itself, the *revenue* strategy.

Concretely, what converts free users to paying customers in this category:

- **Scale & multiplayer.** One developer governing one agent on one machine = free. A
  *team* governing *many* agents across *many* repos, with shared policy and one timeline,
  is a different product — and a budget line.
- **Centralization & retention.** A local audit log is useful to you. A **central,
  retained, tamper-evident store** of every agent action across the org — queryable,
  exportable, kept for years — is what a security or compliance team needs. This is the
  single clearest paid gate, and it's exactly how the open observability companies draw
  the line: Langfuse Cloud's free tier caps you at **2 users and 30-day retention**;
  paid tiers unlock seats, history, and volume. ([Langfuse pricing](https://langfuse.com/))
- **Not running it.** Most teams will pay to *not* self-host the control plane, manage the
  database, and keep it up. Hosted convenience is a product even when the code is free.
- **Assurance.** SSO/SCIM, RBAC, SOC 2, support SLAs, on-prem/VPC deployment, indemnity.
  None of this is a "feature" to a developer; all of it is mandatory to a buyer.
- **Compliance evidence.** "Show me what every agent did, prove the log wasn't tampered
  with, export it for the auditor." The **EU AI Act's high-risk obligations become
  enforceable in August 2026**, and SOC 2 / GDPR / ISO / HIPAA all want immutable,
  attributable activity records. That regulatory clock is a tailwind pointing straight at
  what Tracewall already produces. ([governance/compliance context](https://www.truefoundry.com/blog/claude-enterprise-security))

So the open core isn't charity — it's the cheapest, most credible customer-acquisition
channel you have. For a **security/guardrail** product especially, being open is an
*advantage*: people are reluctant to put a black box in the chokepoint of their agents.
Open source lets them inspect the thing they're trusting. Adoption and trust are the two
things you most need, and open buys you both.

---

## Part 2 — Decision 1: Open source vs. private vs. open-core

| Option | What it means for Tracewall | Upside | Why it's wrong for you (or right) |
|---|---|---|---|
| **Pure OSS** (donations/sponsorship/support only) | Everything stays Apache-2.0; revenue from GitHub Sponsors, support contracts | Maximum trust & adoption | Almost never funds a company solo; you'd be buying yourself a job, not a business. ✗ |
| **Fully proprietary** (close the source) | Stop open development; sell the whole product | Cleanest monetization, no clone risk | Kills your single biggest advantage in a *trust* category — and the wedge that's already getting you users. You'd be a no-name closed security tool competing on enterprise sales with zero distribution. ✗ |
| **Open-core** (free local core + paid org layer) | Apache-2.0 client/CLI/extension; commercial control plane | Keeps trust + adoption, monetizes the part with budget behind it | The proven path for exactly your situation. **Recommended.** ✓ |

**Recommendation: open-core, using GitLab's "buyer-based" rule to decide what's free.** The
rule is simple and keeps you honest: *if the person who cares about a feature is an
individual contributor, it's open source. If the person who cares is a manager, security
lead, or buyer, it's commercial.* ([open-core guidance](https://handbook.opencoreventures.com/open-core-business-model/), [GitLab model](https://www.opencoreventures.com/blog/open-core-is-a-misunderstood-business-model))

Two guardrails on the open-core line, both learned from companies that got it wrong:

- **Never move a free feature behind the paywall, and never withhold security fixes from
  the OSS core.** That's how you torch community trust. Features can move *down* into free,
  never *up* out of it.
- **Mind the clone risk on the server.** Your Apache-2.0 license is perfect for the
  client/edge (you *want* maximal adoption of the capture layer). But when you build the
  hosted control plane, consider a source-available license (BSL/Elastic-style) for *that
  server component only*, so a cloud vendor can't take your control plane and resell it
  against you. Keep the edge permissive, protect the spine. Decide this when you build the
  server, not now.

---

## Part 3 — Decision 2: Who actually pays

You said you're unsure who the buyer is. Here's the map, then a recommended sequence.

| Candidate buyer | The pitch to them | Money | Reality |
|---|---|---|---|
| **Individual developers** | "Keep your agent from doing something dumb" | Low / hard to charge | Your *adoption* engine, not your *revenue* engine. Keep them free. |
| **Eng teams (startups/scaleups)** | "Govern your team's agents, shared policy, one timeline" | Mid (per-seat) | The **first paid tier** and your land motion. |
| **Enterprise security/platform** | "Prove and control what every agent did, for compliance" | High (platform deals) | Where the real budget is — your **north-star buyer**. Longer sales. |
| **Agent-builder platforms (OEM)** | "Embed Tracewall so your agent ships 'approved for production'" | Partnership / rev-share | A powerful **secondary channel**, not your starting point. |

**Recommendation: run the Snyk playbook.** Snyk built a free developer CLI for open-source
vulnerability scanning, got tens of thousands of developers, and then learned the lesson
that defines your strategy: *developers were the users, but security leaders were the
buyers.* Their self-serve-only model stalled until they ran a **hybrid motion** —
bottom-up developer adoption feeding top-down security sales. That company is now at
~$343M ARR. ([Snyk story](https://www.reo.dev/blog/from-open-source-to-343m-arr-how-snyk-made-developers-its-secret-weapon))

Tracewall is almost a clean find-and-replace on that story: *free CLI/extension for
developers → governance & audit product for the security/platform lead.* So:

1. **Land** with individual developers and small eng teams via the free OSS tool.
2. **Expand** to the team tier when a second person needs to see the timeline or share a
   policy.
3. **Monetize seriously** at the security/platform buyer, who pays for centralized
   control, retention, and compliance evidence.
4. **Partner** with agent-builders (OEM/embed) as a parallel channel once the core product
   is proven.

You don't have to pick one — you have to *sequence* them. Adoption first, because nothing
else works without it.

---

## Part 4 — Decision 3: Extension vs. application vs. CLI

The framing of "vs." is the trap. Tracewall needs all three, and they do **different
jobs for different people**. The mistake would be treating them as alternatives instead of
layers.

- **CLI + hooks = the capture mechanism. This is the moat, and it must stay open.** It's
  how every agent action flows *through* you (Claude Code's hook contract, Codex hooks,
  the MCP proxy). If actions go through Tracewall, "every action is recorded" becomes a
  guarantee. Never gate this — its ubiquity *is* the strategy. Note this matches where
  agents already expose control: Claude Code alone exposes **26 programmable hook events**,
  and that surface is what you plug into. ([Claude Code hooks/governance](https://www.truefoundry.com/blog/enterprise-security-for-claude))
- **VS Code extension = the adoption & daily-driver surface.** It's where the individual
  developer lives, reviews allow/block, and falls in love with the loop. Keep it free; it's
  marketing that also happens to be the product. (It's on your roadmap already — pull it
  forward as adoption, not as a paid feature.)
- **Hosted control-plane web app = the product you sell.** The team timeline, the central
  tamper-evident store, policy across repos, dashboards, SSO, compliance exports. This is
  the thing a buyer logs into. This is where the money is.

A clean way to hold it in your head:

> **The CLI captures. The extension converts. The control plane charges.**

This also resolves the "another whole application?" worry: yes, eventually — but the
application is the *commercial* surface for teams, not a rewrite of what you have. The
single-player experience stays exactly where developers already are (their terminal and
editor).

---

## Part 5 — The recommended packaging

Three tiers, drawn on the buyer-based line. **Treat the specific limits and prices below as
hypotheses to test with design partners, not as commitments.**

### Free — "Tracewall Local" (Apache-2.0)
The wedge. Everything a solo developer needs, free forever.
- CLI + hooks (Claude Code, Codex, MCP proxy), VS Code extension
- Policy-by-demonstration, allow/ask/deny, safe defaults
- Local tamper-evident log, single developer / single machine, single repo
- Community support

### Team — "Tracewall Cloud/Team" (paid, per-developer-governed)
The land tier. Unlocks the moment a *second* person or agent is involved.
- Centralized policy shared across teammates and repos
- **Central audit store with retention** (the Langfuse/Helicone gate: free = short
  retention & few seats; paid = history, seats, volume)
- Multi-agent / multi-developer fleet timeline in one place
- Web dashboard, basic SSO, roles
- Email support

### Enterprise — "Tracewall Platform" (custom)
Where the margin is.
- Compliance & audit exports (SOC 2 / EU AI Act evidence), SIEM integration
- SSO/SCIM, RBAC, on-prem / VPC deployment
- Policy templates & governance, the OS-level "effect" layer (your north-star's ground-truth
  collector), support SLA, indemnity

**Pricing meter:** lead with **per-developer-governed seat** (clean, predictable, mirrors
Snyk's per-contributor model and what buyers expect). Consider a hybrid with per-agent or
audit-volume later if usage skews heavily — but a single legible meter beats a clever one
early. Anchor the *shape* on the open + cloud comparables: free self-host with real value,
paid cloud gated on **seats + retention + scale**. ([Langfuse](https://langfuse.com/) ·
[Helicone, Apache-2.0, paid from $79/mo](https://www.helicone.ai/blog/the-complete-guide-to-LLM-observability-platforms))

---

## Part 6 — The 12-month plan

The runway's job is to **convert your three open questions into evidence.** Don't build the
paid product first; earn the right to build it by proving people want the free one and
learning what they'd pay for.

### Phase 0 — Validate & set up (Months 0–2)
- **Customer discovery, ~20–30 conversations.** Split between (a) developers running agents
  heavily and (b) security/platform leads at companies adopting agents. Goal: confirm the
  pain is "painkiller," not "vitamin," and hear which buyer leans in.
- **Lock the open-core boundary on paper** (this doc's Part 5) so you never accidentally
  build a free feature you meant to charge for. No re-architecting later.
- **Instrument adoption** (opt-in telemetry, install counts, GitHub stars/issues). You
  cannot manage what you can't see.
- **Write the design-partner profile** and start a "Teams" waitlist landing page.

### Phase 1 — Adoption with OSS (Months 2–5)
- Make the **free single-player loop genuinely lovable**: CLI + VS Code extension, fast,
  quiet, obviously safe. Polish the wedge before widening it.
- **Recruit 3–5 design partners** actually running it on real work.
- Watch for the expansion trigger: the first time someone says *"can my teammate see
  this?"* or *"can we share a policy?"* — that sentence is your Team tier's product spec.

### Phase 2 — Build & charge for the Team tier (Months 5–9)
- Build the **hosted control plane** with design partners in the loop.
- **Charge them — even a small amount.** A signed invoice is the only real proof of
  willingness-to-pay. Free pilots tell you nothing.
- Establish v1 pricing from what they'll actually pay, not a spreadsheet.

### Phase 3 — Launch & decide the company's shape (Months 9–12)
- Public launch of the paid Team tier (Product Hunt / HN / the agent-dev communities).
- Land **1–2 enterprise design partners** on the security/compliance story, and open **one
  agent-builder OEM conversation.**
- **Decide venture vs. indie from the signals below** — and if venture, this is when you'd
  raise, with adoption + early revenue + design-partner logos as the story.

---

## Part 7 — Signals that resolve "am I venture or indie, and who's my buyer?"

You don't have to decide ambition now. You have to **watch for the evidence that decides it.**

**Lean venture / enterprise if you see:**
- Security/platform leads pull it in *unprompted* and immediately ask about SSO, retention,
  compliance exports, on-prem.
- Inbound from regulated companies (finance, health, gov-adjacent) citing audit needs.
- Design partners will pay 4–5 figures/year and want a contract, not a credit card.
- The expansion is org-wide ("roll this out to all our agent users"), not seat-by-seat.

**Lean indie / bootstrapped if you see:**
- Lots of individual-developer love, but org budget never materializes.
- Willingness-to-pay tops out at low per-seat, self-serve only.
- The compliance pull is theoretical, not a check.

**Either way it's a real business** — the signals just tell you *which* one, and therefore
whether to raise money, how fast to hire, and how hard to chase enterprise. Given the
category is consolidating through M&A (Part 1), even the "indie" branch has a credible
acquisition path; you don't have to choose IPO-or-bust to choose ambition.

---

## Part 8 — Risks (read this part twice)

**1. Platform risk — the agent vendors build it natively. This is the big one.** Claude
Code already ships managed settings, permission boundaries, 26 hook events, MCP controls,
and native audit logs; Codex has its own. Your honest defense is the thing they *won't*
prioritize: **cross-agent, cross-vendor, unified, compliance-grade governance and audit.**
Anthropic governs Claude; OpenAI governs Codex; *nobody on the vendor side is incentivized
to give a security team one tamper-evident timeline across all of them, with policy you
never hand-write.* Own the boundary *between* agents and the *audit/compliance* surface, not
the per-agent permission prompt. If you ever look like "a nicer Claude Code permission
dialog," you've lost; if you look like "the audit trail for every agent in the company,"
you've won. ([native governance context](https://www.truefoundry.com/blog/claude-enterprise-security))

**2. Clone risk.** Permissive license on the server lets a cloud vendor resell your control
plane. Mitigation in Part 2 (source-available license on the server component only).

**3. Timing — is agent governance a 2026 budget line yet, or a 2027 one?** The EU AI Act
August-2026 enforcement and the M&A activity say the clock is real, but you may be early. A
12-month runway full-time is the right way to *be early on purpose* — get the adoption and
the design partners now so you're the obvious choice when budgets open.

**4. Single-founder bandwidth.** You + Claude can build, but enterprise sales, compliance,
and a hosted service are a lot. This is itself a signal: if the enterprise pull is strong,
it's an argument *for* raising (to hire), not for grinding solo.

---

## Part 9 — Do this week

1. **Send 10 discovery-call requests** — 5 agent-heavy developers, 5 security/platform
   leads. The single highest-value thing on this list.
2. **Stand up a one-page "Tracewall for Teams" waitlist** describing the control plane;
   measure who signs up and what title they have.
3. **Turn on opt-in install/usage telemetry** so Phase 1 has a denominator.
4. **Write the open-core boundary into the repo** (a `COMMERCIAL.md` or a section in the
   README) so the free/paid line is a decision of record, not a vibe.
5. **Pick the one buyer you'll aim the next month at** — default to eng-teams-leading-to-
   security, per Part 3 — and tailor discovery to them.

---

## Appendix — Comparables

| Company | What they are | Model | Outcome / signal |
|---|---|---|---|
| **Invariant Labs** | OSS guardrails for agents & MCP + Explorer dashboard | Open-source + premium | **Acquired by Snyk** — your closest comp |
| **Lakera** | Agent/GenAI guardrail API | Enterprise SaaS, API-first | **Acquired by Check Point** (Nov 2025) |
| **Protect AI** | AI/ML security platform | Enterprise | **Acquired by Palo Alto Networks** |
| **Snyk** | Developer security (the playbook) | Free CLI wedge → security buyer; hybrid GTM | ~$343M ARR, 3,000+ orgs |
| **Langfuse** | OSS LLM observability | MIT core + cloud; gated on seats/retention/volume | Free self-host all features; Cloud from $29/mo |
| **Helicone** | OSS LLM observability (proxy) | Apache-2.0 + cloud | Free 10k req/mo; paid from $79/mo |
| **GitLab** | DevOps platform | Buyer-based open-core | The boundary rule you should copy |

### Sources
- Snyk — open source to $343M ARR, developer-adoption-vs-security-buyer: https://www.reo.dev/blog/from-open-source-to-343m-arr-how-snyk-made-developers-its-secret-weapon
- Snyk acquires Invariant Labs (agentic AI security): https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/
- Check Point acquires Lakera: https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/
- Open-core business model (buyer-based boundary): https://handbook.opencoreventures.com/open-core-business-model/ · https://www.opencoreventures.com/blog/open-core-is-a-misunderstood-business-model
- Langfuse (MIT core + cloud pricing/retention gating): https://langfuse.com/
- Helicone (Apache-2.0 + cloud pricing): https://www.helicone.ai/blog/the-complete-guide-to-LLM-observability-platforms
- Claude Code enterprise governance / hooks / native audit logs: https://www.truefoundry.com/blog/enterprise-security-for-claude · https://www.truefoundry.com/blog/claude-enterprise-security

