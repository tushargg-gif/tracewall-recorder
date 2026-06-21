# Tracewall — Business Plan

**Date:** 2026-06-20 · **Owner:** Tushar (founder) · **Companion docs:** [business-model.md](business-model.md) (the strategy decision), [north-star.md](north-star.md) (product compass)

> This plan takes the open-core direction as settled and turns it into an operating plan: how Tracewall makes money, how it goes to market, what the numbers could look like — and, in depth, **how we stop individual users from unlocking paid features for free** (§6), which is the load-bearing question for any open-source business.

---

## 1. Executive summary

Tracewall is an open-source **guardrail + tamper-evident audit layer in front of coding agents** (Claude Code, Codex). Every agent action is recorded, risk-checked, and allowed / asked / denied before it runs; the user teaches policy by demonstration.

**The business:** open-core. The free, Apache-2.0 product is the **local single-developer guardrail** (CLI + hooks + editor panel) — our distribution engine. We charge for the **team/organization control plane**: a hosted backend that shares policy across a team, keeps a central retained tamper-evident audit trail, and adds dashboards, SSO, and compliance exports. Developers adopt; security and platform leads pay — the Snyk motion.

**Why it defends against free-riding (the headline of §6):** the paid value is **architecturally server-side**. The valuable bits — multi-developer policy sync, the central audit store, the fleet dashboards — run on our hosted control plane and **never ship to the user's machine**. You cannot unlock what you don't have. This is the Tailscale pattern (open client, proprietary coordination server). For the minority who need self-hosting, paid features live in a separate proprietary module gated by **signed license keys** (the Cal.com / PostHog pattern). The free local tool stays clean and un-crippled — critical, because it's a *security* product and trust is the whole value proposition.

**Why now:** agent adoption is outrunning agent governance; the EU AI Act's high-risk obligations become enforceable in **August 2026**; and the category is consolidating through M&A (Invariant Labs → Snyk, Lakera → Check Point, Protect AI → Palo Alto). Being early and opinionated matters.

---

## 2. Company & product

**What it is.** A Policy Enforcement Point for agent actions. As a Claude Code `PreToolUse` hook (and a Codex hook / MCP proxy), Tracewall sees every Bash command, file read, web fetch, and tool call *before it runs* and returns allow / ask / deny. Decisions: the user's learned policy wins; otherwise safe defaults (deny secret reads, ask on the risky, allow the safe majority). Every action — including blocked attempts — is written to a hash-chained, source-attributed log.

**The hero loop.** Record a run → show the action flow → human marks allow/block → AI drafts a reusable rule *with its reason* → enforce next run. Each turn, the agent earns more trusted autonomy while everything stays recorded.

**Status.** Early alpha, Mac-first. Claude Code (full) and Codex (bash + MCP) integrations work. The record → review → learn → enforce loop runs end to end against a live agent.

**The wedge vs. the product.** The *experience* of teaching the system by reacting to real behavior is what we sell; the local capture/enforcement is what we give away to get adopted.

---

## 3. Problem & why now

Agents have crossed from demos into workflows that touch real systems — repos, databases, money, customer data. The blocker is **governance, not capability**: security, risk, and platform teams are the gatekeepers and have no tooling built for *agent* actions. Existing answers don't fit — SIEM/EDR don't understand agent intent, LLM guardrails watch prompts not effects, prompt logs aren't an audit trail of what actually happened.

Three tailwinds:

- **Regulation.** EU AI Act high-risk obligations enforceable **Aug 2026**; SOC 2 / GDPR / ISO / HIPAA all want immutable, attributable activity records — exactly what Tracewall produces.
- **Consolidation.** Big security vendors are buying their way into agent security (Invariant Labs → Snyk; Lakera → Check Point; Protect AI → Palo Alto), validating the category and signaling a live acquisition path. ([Snyk/Invariant](https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/))
- **No clear winner.** The "agent control plane" category is forming now.

---

## 4. Market & competition

**Shape of the market.** Bottoms-up: (developer teams running coding agents) × (annual contract value for governance). The user is the developer; the budget sits with security/platform. Land per-seat in the low hundreds of dollars/developer/year; expand to org-wide platform deals (5–6 figures) where compliance and central audit live.

**Where we sit.** Adjacent but differentiated:
- *Per-agent native controls* (Claude Code permissions/hooks, Codex) — real, but single-vendor. Our edge is **cross-agent, unified, compliance-grade** governance and audit.
- *Agent guardrail APIs* (Lakera-style, prompt-injection focus) — watch content, not the action boundary and its audit trail.
- *LLM/agent observability* (Langfuse, Helicone) — log traces; they don't enforce or reconcile intent vs. effect.

Our defensible ground: **audit the boundary across every agent, with policy you never hand-write, in a tamper-evident trail a security team can stand behind.**

---

## 5. Business model & packaging

Open-core, drawn on the **buyer-based line**: if an individual contributor is who cares about a feature, it's free and open; if a manager/security lead/buyer is who cares, it's commercial. (GitLab's rule.)

### Free — "Tracewall Local" (Apache-2.0)
The wedge, free forever. CLI + hooks (Claude Code, Codex, MCP proxy), editor panel, policy-by-demonstration, allow/ask/deny, **local** tamper-evident log, single developer / single machine. Community support.

### Team — "Tracewall Cloud" (paid, per governed developer / mo)
Unlocks the moment a second person or agent is involved. Centralized policy shared across the team and repos; **central retained tamper-evident audit store**; multi-agent / multi-developer fleet timeline; web dashboard; basic SSO; roles. Hosted by default; self-host option via license key.

### Enterprise — "Tracewall Platform" (custom ACV)
Compliance & audit exports (SOC 2 / EU AI Act evidence), SIEM integration, SSO/SCIM, RBAC, on-prem / VPC, policy templates & governance, the OS-level "effect" collector, support SLA, indemnity.

**Pricing meter (illustrative — validate with design partners):** lead with **per-developer-governed seat** (clean, predictable, mirrors Snyk's per-contributor model). Indicative: Team ~$25–40 / developer / month (annual); Enterprise landed at ~$25k–$150k ACV depending on seats, deployment, and compliance scope. Free tier carries short audit retention and a single seat — retention and seats are the natural upgrade triggers (the Langfuse/Helicone gating pattern).

---

## 6. Protecting paid features from exploitation

This is the question every open-source business has to answer: *if the code is open, what stops an individual from just turning on the paid features for free?* For Tracewall the answer is **five layers**, ordered from strongest to softest. The first layer does most of the work; the rest cover the edges.

### 6.0 Threat model — who exploits, and how

| Actor | What they try | Where it bites |
|---|---|---|
| Free-tier individual | Use Team features (shared policy, central audit, dashboards) without paying | Most common; must be structurally impossible, not just discouraged |
| Self-hoster | Run the enterprise edition on their own box and flip a flag to unlock | Needs a license-key gate |
| Forker | Strip the license check out of the source and rebuild | Mitigated by *not shipping* the valuable code, + licensing |
| Seat-sharer | One paid seat used by a whole team | Server-side seat metering |
| Trial abuser | Recycle free trials / fake orgs | Trial + signup controls |
| Competitor | Take the OSS and resell a competing hosted Tracewall | Source-available license on the server |

### 6.1 Layer 1 — Architecture is the moat (the decisive one)

**Keep the paid value server-side so there is nothing local to unlock.** This is the Tailscale pattern: the client is open source (auditable, adoptable), but the **coordination/control server is proprietary and hosted** — you can't unlock what was never shipped to your machine. ([Tailscale open source](https://tailscale.com/opensource))

Mapped to Tracewall:

| Runs on the user's machine (open, free) | Runs on our hosted control plane (paid, never ships) |
|---|---|
| The gateway/hook, risk-check, allow/ask/deny | **Cross-developer policy sync** and conflict resolution |
| The *local* tamper-evident log (this machine) | The **central, retained, org-wide audit store** |
| Policy-by-demonstration for one developer | **Fleet dashboards**, multi-agent timeline, trends |
| | **SSO/SCIM, roles, seat management, billing** |
| | **Compliance exports** and SIEM streaming |

An individual on the free tier literally cannot "switch on" the team audit store or fleet view, because that code and data live on our servers behind authentication and entitlements — not in the binary they downloaded. This converts the hardest enforcement problem (stopping a local unlock) into a non-problem. It is why **SaaS-first is the recommended default**, and why the paid features are deliberately the ones that *only make sense* with a shared backend (multiplayer, retention, central governance) — Cal.com's "single-player APIs are open, multiplayer APIs are commercial." ([Cal.com license](https://cal.com/docs/self-hosting/license-key))

### 6.2 Layer 2 — Code separation + licensing (for the self-host/enterprise case)

Some enterprises must self-host (air-gapped, data-residency). For them the server *does* ship, so we need the next layer:

- **Don't put paid code in the open repo.** Enterprise features live in a separate proprietary module (a `/ee` directory or separate repo) under a **commercial license**, exactly as PostHog and Cal.com do — the Apache-2.0 core never contains the EE logic, so there's nothing to "uncomment." ([PostHog EE license](https://github.com/PostHog/posthog/blob/master/ee/LICENSE))
- **License the layers differently.** Client/edge stays **Apache-2.0** (maximize adoption and trust). The server/control-plane and EE module go **source-available** — the **Functional Source License** (Sentry's "freedom without free-riding": source is visible, competing commercial use is restricted, and it converts to open after two years) or BSL. This legally bars a competitor from reselling a hosted Tracewall without removing our distribution advantage. ([Sentry FSL](https://www.theregister.com/2023/11/20/sentry_introduces_the_functional_source/))
- **Cautionary tale — don't relicense the community core.** Redis moving its existing open core to SSPL triggered backlash and the AWS-backed Valkey fork, and it reverted to AGPL in 2025. Lesson: choose the licensing boundary **up front**, apply restrictive terms only to **new server/EE code**, and never yank features the community already relied on. ([source-available risks](https://www.termsfeed.com/blog/legal-risks-source-available-licenses/))

### 6.3 Layer 3 — Signed entitlement keys (gate the self-hosted EE)

Where the EE ships, gate it with **cryptographically signed license keys** (Cal.com requires a purchased key to self-host the commercial edition):

- A license is a signed token (e.g., JWT signed with our private key) carrying plan, seat count, expiry, and enabled features. The EE verifies it with our **public key** — so it works **offline / air-gapped** and the key can't be forged without our private key.
- Include **expiry + a grace period** (don't hard-brick a security tool on renewal lag), and a soft **phone-home/telemetry** for online deployments to flag overuse (CockroachDB ships telemetry on its free enterprise edition; paid customers can opt out).
- Entitlements are checked **server-side wherever possible**; the local key only gates the self-hosted server, never the free local tool.

This makes "flip a flag" require forging a signature (infeasible) or patching the proprietary binary (a license violation, and unsupported/unsafe for the buyer — enterprises won't run a cracked security tool).

### 6.4 Layer 4 — SaaS metering & anti-abuse (for the hosted majority)

For the hosted control plane, enforcement is ordinary SaaS hygiene, all server-side:
- **Seat metering** from real identity (SSO/accounts), with seat-sharing detection (concurrent sessions, device/IP heuristics) and overage prompts.
- **Plan-bound limits** that are valuable, not punitive: audit **retention window**, number of repos/agents, dashboard history, export volume.
- **Trial/signup controls** (email/domain verification, one trial per org) to stop trial-recycling.
- **Usage analytics** to spot the upgrade moment ("a teammate just tried to view your timeline") and convert it.

### 6.5 Layer 5 — Legal & trust (and what *not* to do)

- **Commercial terms** in the EE/Cloud license prohibit unauthorized production use, sharing, and circumvention — the backstop for the rare bad actor and the basis for enforcement against a reseller.
- **Do not put DRM or nagware in the free local tool.** It is a *security* product; aggressive checks, calling home, or crippling the OSS core would destroy the trust and adoption that are the entire strategy — and invite a clean community fork. Keep the free tool genuinely good and un-gated.
- **Accept some leakage and make paying easier than cheating.** A handful of clever individuals will always wriggle through; that's fine. The goal isn't zero leakage — it's that *organizations* (who have budget, compliance needs, and no appetite to run cracked security software) find buying obviously cheaper than circumventing. Architecture (Layer 1) already removes the incentive for the segment that actually pays.

**Net:** the people who *could* exploit a local unlock (individuals) are structurally blocked because the paid value isn't local; the people who *would* pay (orgs) have every reason to, and a license + source-available server protect against competitors. Enforcement lives at the **server boundary and the legal layer**, never as friction on the free developer experience.

---

## 7. Go-to-market

**Motion:** product-led adoption feeding a top-down security sale — the Snyk playbook (developers adopt the free CLI; security/platform leads buy governance). Sequence: **land** with individual developers and small teams on free OSS → **expand** to Team when a second person needs the shared timeline → **monetize** the security/platform buyer on central audit, retention, and compliance.

**Channels:**
- *Developer adoption:* GitHub presence, quickstarts, the editor extension, content on agent safety, the agent-dev communities (Claude Code / Codex users), Product Hunt / HN at launch.
- *Security/platform demand:* compliance-led content (EU AI Act, SOC 2 evidence for agents), design partners in regulated industries, security communities.
- *Partnerships / OEM:* agent-builder platforms embedding Tracewall so their agents ship "approved for production"; security vendors (the acquirers) as channel and, plausibly, eventual acquirers.

**Funnel:** install → weekly-active local user → invites a teammate (Team trial) → paid Team → security review → Enterprise. Instrument every step.

## 8. Financial model (illustrative — assumptions to validate)

Numbers below are **planning placeholders**, not forecasts; the 12-month plan exists to replace them with real conversion and willingness-to-pay data.

**Pricing assumptions:** Team $30 / governed developer / month ($360/yr); Enterprise ~$40k average ACV. Hosted SaaS gross margin ~80–85%.

**Adoption → revenue (rough trajectory):**

| | Year 1 | Year 2 | Year 3 |
|---|---|---|---|
| OSS installs (cumulative) | 5k–15k | 40k–80k | 150k+ |
| Paid Team accounts | 10–40 | 150–400 | 600–1,200 |
| Enterprise logos | 0–2 | 3–8 | 15–30 |
| ARR (illustrative) | $50k–150k | $0.5M–1.5M | $3M–6M |

**Unit economics (target shape):** PLG developer CAC is low (content + OSS, near-zero marginal); enterprise CAC is higher and carried by expansion. Net revenue retention should run >110% via seat expansion (more developers governed) and Free→Team→Enterprise tier movement. Watch payback on the enterprise motion as the main risk to efficiency.

**Use of the 12+ month runway:** customer discovery → ship a lovable free wedge → 3–5 paying design partners → build the hosted control plane → public Team launch → decide raise-vs-bootstrap on the signals below.

## 9. Metrics & milestones

- **North-star:** governed weekly-active agents (actions flowing through Tracewall each week). It captures adoption *and* stickiness.
- **Funnel:** install → WAU → team-invite → paid conversion → NRR.
- **Health:** % actions auto-allowed (autonomy earned), design-partner willingness-to-pay, time-to-first-policy.
- **Decision gates:** *venture/enterprise* if security leads pull it in unprompted and ask about SSO/retention/compliance, regulated inbound appears, and design partners sign 4–5-figure contracts; *indie/bootstrap* if it's individual-dev love with no org budget. Either is a real business — the signals decide the shape and whether to raise.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Platform risk** — agent vendors ship native governance | Own the cross-agent, compliance-grade audit a single vendor won't prioritize; never be "a nicer permission dialog" |
| **Free-rider leakage** | Architecture-as-moat (§6.1); accept individual leakage, defend the org segment |
| **Relicensing backlash** | Set the license boundary up front; restrictive terms only on new server/EE code; never claw back community features |
| **Timing (budgets not ready in 2026)** | Use full-time runway to be early on purpose; land design partners now, convert when budgets open (EU AI Act tailwind) |
| **Single-founder bandwidth** | Strong enterprise pull is the signal to raise and hire, not to grind solo |
| **Trust erosion from enforcement** | No DRM/nagware on the free security tool; enforcement at server + legal layer only |

## 11. The next 90 days

1. **Customer discovery** — ~20–30 calls split between agent-heavy developers and security/platform leads; confirm painkiller vs. vitamin and which buyer leans in.
2. **Lock the open-core + licensing boundary on paper** (§5, §6) — write it into the repo (a `COMMERCIAL.md`) so the free/paid line and the server license are decisions of record before any EE code exists.
3. **Ship the free wedge well** and instrument adoption (opt-in install/usage telemetry).
4. **Recruit 3–5 design partners**, stand up an "Tracewall for Teams" waitlist, and charge the first partners even a small amount to prove willingness-to-pay.
5. **Prototype the hosted control plane** as the first paid surface — the architecture that makes §6.1 real.

---

*Illustrative figures are planning assumptions, not projections or financial advice; validate pricing and conversion with real design partners before committing.*
