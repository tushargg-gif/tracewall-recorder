# Tracewall — North Star

**Audience:** founding team (internal compass)
**Horizon:** ~12 months — this year's destination
**Date:** 2026-06-15
**Companion docs:** [audit-control-plane.md](audit-control-plane.md) (the debated design)

This is our compass, not a pitch. It is candid about the hard parts. When a decision
is unclear, we come back here and ask: *does this move us toward the star?*

---

## 1. The North Star

> **Make AI agents safe to put to work — by making every action an agent takes
> visible, attributable, and controllable, without forcing anyone to hand-write a
> single policy.**

The world is moving to agentic workflows. The thing standing in the way is not model
quality — it's **trust**. No serious organization will let an agent act on its systems
when the agent is a black box. We are building the layer that turns that black box into
something a human can **see, understand, and control** — and we make it effortless by
*learning the policy from what the agent actually does*, instead of asking people to
write rules up front.

If we are wildly successful, "is there a Tracewall trail for this?" becomes the
default question before any agent is allowed near a production system.

---

## 2. Why now

- Agents are crossing from demos into real workflows that touch real systems (repos,
  databases, email, money, customer data).
- The blocker is **governance, not capability**. Security, risk, and platform teams are
  the gatekeepers, and they have no tooling built for *agent* actions.
- Existing answers don't fit: SIEM/EDR don't understand agent intent; LLM guardrails
  only watch prompts, not actions; prompt logging isn't an audit trail of *effects*.
- The category ("agent observability / agent control plane") is forming **right now**
  and has no obvious winner. Being early and opinionated matters.

---

## 3. Who we serve

The buyer and the user are the **team that has to say yes** to an agent: security,
platform, and engineering leads who want to enable agents without betting the company
on blind trust. Their job-to-be-done: *"Let me adopt this agent and still be able to
answer, at any moment, what it did and why — and stop it when it's about to do
something I wouldn't allow."*

Secondary beneficiary: the **agent builder**, who gets a faster path to "approved for
production" because the governance story already exists.

---

## 4. The core idea (the product, in one breath)

**Audit the boundary, not the brain.** We don't need every internal thought the model
had; we need every action that crosses into a real system — and a single place where
those actions are recorded *and* controlled.

Three things make this real:

1. **Three layers of truth.** *Decision* (why — the model's request), *Intent* (what —
   the tool/command it invoked), *Effect* (what actually happened on the machine). The
   gold is the **disagreement** between them: "claimed to read `config.yaml`, actually
   opened `.env`." A logger captures layers; an **auditor reconciles them**.

2. **One chokepoint that records and enforces** (a Policy Enforcement Point). What we
   audit and what we block come from the *same* place, so they can never drift. If the
   agent can only act *through* us, "every action is recorded" becomes a guarantee, not
   a hope.

3. **Policy by demonstration** — the part that makes it lovable. Nobody writes rules up
   front. We **record a real run, show the flow of actions, let a human allow or block
   each one, and an AI drafts the reusable policy — with reasons.** The engine that
   enforces those rules stays hidden; the *experience* of teaching the system by
   reacting to real behavior is what we sell.

---

## 5. The product, in more detail

### The hero loop

```
   ┌─────────────────────────────────────────────────────────────┐
   │   1. RECORD a run        → unified "action flow"            │
   │   2. SHOW the flow       → every action, in order           │
   │   3. HUMAN allow/block   → react to what actually happened  │
   │   4. AI RECOMMENDS policy → reusable rules, with reasons     │
   │   5. ENFORCE next run    → observe → alert → block           │
   │   6. CLOSE the loop      → policy catches it next time       │
   └─────────────────────────────────────────────────────────────┘
                  the round-trip IS the product
```

Every turn of this loop, the agent earns a little more trusted autonomy: actions a
human already approved stop needing approval, while everything stays recorded.

### Architecture shape

- **Control plane (the spine, central):** normalize events → correlate into a causal
  trace → tamper-evident store → evaluate policy → verify/reconcile → report. This is
  the carved-down spine, grown up. It stays small on purpose.
- **Edge collectors (where the agent runs):** brokered proxies that capture *intent*
  (tool/MCP calls, commands) today; OS-level observers that capture *effect* (exec,
  socket, file) later. Each is pluggable and tagged with how much we trust it.

### What the user experiences

They run their agent through Tracewall. They open a clean timeline of what it did.
They click allow/block down the list. The system says: *"Based on your choices, here's
the policy I'd suggest, and here's why."* They accept. Next run, the agent flies
through the approved actions and stops at the one that crosses a line — with a record
of every step. That's the entire value, visible in one sitting.

---

## 6. This year's destination (the 12-month picture)

By this time next year, **winning looks like:**

- The **hero loop works end-to-end** on Mac at the intent layer: record → review →
  recommend → enforce → catch-it-next-time, as a thing we can demo in one sitting.
- A handful of **design partners** are running real agents through it and can answer
  "what did the agent do?" from our timeline — and have let us *block* at least one
  real risky action.
- We have the beginnings of the **ground-truth layer** (seeing inside commands) so the
  "untrusted binary" story is real, not aspirational — even if Linux/eBPF is still
  early.
- The **recommendation quality** is good enough that partners trust the suggested
  policies more often than they rewrite them.
- The narrative is sharp enough that "agent control plane / policy by demonstration" is
  a sentence people repeat back to us.

What we are **not** trying to have in 12 months: full enterprise hardening, multi-cloud,
SSO/SOC2 at scale, the reconciliation engine fully built, or adversarial-agent
containment. Those are post-destination.

### Rough sequence to get there

1. **Intent capture unified** — one run = one ordered action flow (reuse command
   capture; un-archive the MCP proxy).
2. **Review UX** — the clickable allow/block timeline.
3. **Policy-by-demonstration recommender** — AI drafts rules with reasons from the
   human's choices.
4. **Enforcement** — observe → alert → block on the next run; close the loop.
5. **First design partners** — real agents, real feedback, harden the loop.
6. **Begin the ground-truth layer** — see inside commands; make "untrusted binary" real.

---

## 7. Our North Star metric

One number to optimize, because it captures the whole thesis:

> **Trusted Autonomy Rate** — the share of an agent's actions that execute **without
> human pre-approval because policy already covers them**, while remaining fully
> recorded and reversible.

It rises only when both halves are working: the agent is doing useful work *and* the
demonstration loop has taught the system enough policy to safely get out of the way.
Pure logging can't move it (no autonomy granted); pure automation can't move it safely
(no trust). It is the number that means "agents are safe to put to work."

Supporting signals: time-to-first-blocked-action, recommendation acceptance rate,
% of actions captured (coverage), design-partner retention.

---

## 8. Principles (non-negotiables)

- **Sell the experience, not the engine.** The policy engine is a hidden commodity;
  the record→recommend→enforce loop is the product. Users never write Rego.
- **Keep the spine small.** Everything new is a pluggable, trust-tagged collector. The
  gravity that produced the old 1,000-line `plugins.py` is always pulling; we resist it.
- **Honest, bounded claims.** "Every brokered action recorded and gated; every
  un-brokered action detected." Never "tamper-proof," never "contains a hostile agent."
- **Observe → alert → block.** Earn the right to block by first showing value as a
  recorder. A control plane that breaks real work on day one gets ripped out.
- **Leverage, don't rebuild.** We don't reimplement eBPF or a policy engine. Our moat
  is correlation + audit integrity + the recommendation loop, not commodity plumbing.
- **The boundary, not the brain.** Govern actions that touch real systems; we don't
  need to capture the model's every thought.

---

## 9. The moat

Not any single proxy or syscall hook — those are commodities anyone can wire up. Our
defensibility is the **unified, tamper-evident, cross-layer causal record** of what an
agent did, plus the **policy-by-demonstration loop** that turns that record into
governance a human actually wants to use. Two things compound over time: the **trace +
reconciliation quality** (we get better at spotting "intent ≠ effect"), and the
**recommendation quality** (every customer interaction teaches us to suggest better
policy). Both improve with usage; neither is a weekend clone.

---

## 10. What we are explicitly NOT doing (this year)

- Building a coding agent, an LLM, or a model.
- Defending against a fully **attacker-controlled** agent trying to defeat the kernel
  (that's malware-sandbox/EDR territory — different, harder, not us).
- OS/eBPF interception **first** (it's the backstop, and the leverage-able tools are
  Linux-only while we start on Mac).
- Adopting **OPA first** (hidden engine; start simple, swap later, invisibly).
- Replacing CI, code review, or the SIEM — we **feed** them.
- Enterprise hardening at scale (SSO/SOC2/multi-tenant) before the loop is loved.

---

## 11. Risks we're watching

- **Recommendation quality is the new make-or-break.** Policy by demonstration removes
  the "Rego is hard" risk but replaces it with "bad AI suggestions erode trust fast."
  This is the thing to get right in step 3.
- **We're becoming critical-path infra.** The moment we can block, we can break a
  workflow. Reliability, latency, and fail-open/closed behavior matter far more than
  they did for a passive recorder.
- **Completeness is a deployment property.** Our guarantee only holds if the agent has
  no un-brokered path. We must *detect and report* a weak posture, never pretend.
- **Scope re-bloat.** The same pull that bloated the project before. The spine stays
  small; collectors stay pluggable; non-goals stay non-goals.

---

## 12. The one-sentence version

**We make agents safe to put to work by recording everything they do at one
controllable chokepoint, and teaching the guardrails from real behavior instead of
asking anyone to write them — so a human can always see, understand, and stop what an
agent is about to do.**
