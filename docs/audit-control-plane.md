# Tracewall — From Recorder to AI Audit & Control Plane

**Status:** Proposed (design only — no implementation yet)
**Date:** 2026-06-14 · **Updated:** 2026-06-15
**Author:** Tushar
**Supersedes scope of:** the local "evidence recorder" framing in README/ROADMAP

> **Update 2026-06-15 — three forks resolved.** D7 refined to **policy by
> demonstration** (record → review → AI-recommend, engine hidden). D9 confirmed
> **leverage** (but the ready-made OS tools are Linux-only). Platform: **Mac first,
> intent layer first** — the deep OS/eBPF layer is deferred. See the new
> **Section 6 — Execution plan (first build)**.

> **Correction 2026-06-15 — the gateway is the core, not a footnote.**
> Tracewall is **not** a recorder a human drives by hand (`tracewall run --`).
> The **AI is the orchestrator**; it drives the agents. **Tracewall is the gateway
> every agent action flows through — the orchestrator's eyes and hands on the agents.**
> A worker agent cannot run a command or call a tool except *through* the gateway,
> which records → policy-checks → executes/blocks → returns, attributing each action
> to the agent that took it. This is the "one chokepoint" / "completeness by
> construction" principle (D1–D2) made real. The manual CLI is just a thin operator
> seam; the **`Gateway`** broker is the product surface. Everything else we built
> (flow, risk insight, review, recommender, policy engine, policy view) sits *on top*
> of what the gateway captures.

---

## 1. Why this document exists

We just carved Tracewall down to a clean **record → verify → report** spine and
parked the broader experiments (MCP proxy, sidecar, orchestration, data-artifact
checks) in `archive/`. This document deliberately re-opens scope — but in a
controlled way — because the product thesis has changed.

The new thesis, in one sentence:

> **Enterprises want to put AI agents into real workflows, but they can't accept
> an agent that acts as a black box. Tracewall becomes the layer that makes every
> agent action observable, attributable, and — where it matters — blockable.**

This is not a developer convenience tool anymore. It is a **governance / control
plane**: the thing a security or platform team installs so that "an agent did X to
our systems" is always answerable, and risky actions can be stopped or escalated
rather than discovered after the fact.

The rest of this document debates the major design choices (why / how /
alternatives), then finalizes a single architecture and a phased plan.

---

## 2. Threat model and non-goals (scope discipline)

Getting this wrong is how the project bloats again, so it is stated first.

**Primary persona / driver:** an *honest-but-unpredictable* agent operating on
behalf of a human or a service, inside an enterprise that needs **accountability,
visibility, and inline control** to satisfy security, risk, and compliance before
they will adopt agents at all.

**What we defend against (in scope):**

- Agents taking **unintended, unsafe, or out-of-policy actions** (touching secrets,
  hitting prod, exfiltrating data, running unknown binaries, calling forbidden tools).
- **Black-box opacity** — no record of what the agent did or why.
- **Drift between "what we audit" and "what we control"** — they must come from one source.

**What we explicitly do NOT promise (non-goals):**

- We are **not** a containment boundary for a fully **attacker-controlled** agent
  that is actively trying to defeat the host kernel. That is malware sandboxing /
  EDR territory and a different, much harder product. We raise the cost of evasion
  and we *detect* it; we do not claim perfect prevention.
- We are **not** building a coding agent, an LLM framework, or a model.
- We are **not** replacing CI, code review, or an enterprise SIEM — we **feed** them.

Holding this line lets us make strong, honest claims ("every brokered action is
recorded and policy-checked; un-brokered activity is detected and alerted") instead
of weak, unfalsifiable ones ("tamper-proof").

---

## 3. The conceptual model everything hangs on

**Three layers of truth.** An agent acts on three layers, and an auditor wants all three:

| Layer | What it answers | Example evidence |
|---|---|---|
| **Decision** | *Why* did it act? | prompt, completion, tool-call request, tokens |
| **Intent** | *What* did it mean to do? | MCP/tool call name + arguments + result |
| **Effect** | *What actually happened?* | file opened, process exec'd, socket opened, bytes sent |

The single most valuable audit signal is **disagreement between layers**: "the tool
call claimed it read `config.yaml`, but the effect layer shows it opened `.env`," or
"it reported 'ran the tests' but no test process ever spawned." A recorder captures
layers; an **auditor reconciles them and flags the gaps.**

**Trust tiers of capture.** Each way of capturing an action trades semantic richness
against tamper-resistance:

1. **Self-reported** — the agent calls us. Richest, cheapest, least trustworthy.
2. **Brokered** — the agent can only reach a capability *through* us (proxy/gateway).
   Trustworthy for whatever is forced through the broker.
3. **Observed** — we watch real effects at the OS level regardless of cooperation.
   Most trustworthy, semantically poorest ("PID 9123 opened a socket" — to do what?).

A real control plane uses **brokered for intent + observed for ground truth +
reconciliation for findings.** Self-reported is garnish.

**The chokepoint principle (the heart of it).** If the agent has **no affordance to
touch a real system except through a path we mediate**, then "every action is
recorded" stops being best-effort and becomes a **deployment guarantee**. Recording
and enforcing at the *same* chokepoint means what we audit and what we block can
never drift — this is just the generalization of a principle already in the codebase
(the enforcement guard reuses the verifier's sensitive-path definitions).

---

## 4. Architecture decisions (debated)

Each decision: the question, the options, the debate, the verdict.

### D1 — Capture philosophy: passive observation vs. capability broker

**Options.** (A) Passive observability — watch any agent from outside via OS hooks +
interceptable proxies. (B) Capability-broker gateway — the agent can only act through
brokered paths; completeness by construction. (C) Hybrid.

**Debate.** Pure (A) works with agents we didn't build and requires no cooperation,
but completeness is best-effort and you cannot *block* cleanly from outside — you're
always a step behind the effect. Pure (B) gives true completeness and clean inline
blocking, but only over channels we broker, and it constrains how the agent runs
(we must own enough of the runtime). The enterprise requirement is **inline control
and a completeness story**, which (A) alone cannot give; but (B) alone is blind to
anything that happens *inside* a brokered action (see D3).

**Verdict: (C) Hybrid, broker-first.** Broker every external effect (model, tools,
commands, network); back it with OS-level observation to see *inside* brokered
actions and to detect anything un-brokered. Brokering is the primary mechanism;
observation is the verification/backstop.

### D2 — Audit and control: two systems or one chokepoint?

**Options.** (A) An audit logger plus a separate enforcement product. (B) One
**Policy Enforcement Point (PEP)** that records and enforces at the same point.

**Debate.** Splitting them is how you get the classic failure: the audit log says
one thing, the enforcement rules another, and an action slips through the gap. A
single PEP guarantees that every decision (allow / deny / redact / require-approval)
is itself an audit event, and every audited action was evaluated by policy.

**Verdict: (B) One PEP.** Every mediated action flows: *observe → evaluate policy →
decide → record decision + outcome to the tamper-evident log.* This is the spine's
job.

### D3 — Execution capture: command broker alone, or broker + OS interception?

**Options.** (A) Brokered command runner only (we already have `tracewall run --`),
gate on the command string. (B) Add OS-level interception (eBPF / sandbox / Endpoint
Security) so we see child execs and syscalls *inside* an approved command. (C)
Full syscall sandbox only, no command broker.

**Debate.** This is the crux the conversation kept circling. The command broker is
powerful: if the agent has no native execution and must route every command through
us, we catch direct `nc`, `curl evil.com`, `/tmp/malware` *before* they run — better
than I first credited. **But a command is a coarse unit.** One approved
`python build.py` (or `bash -c …`, `make`, `npm run x`) can itself open forty
sockets, exec ten child binaries, and read `.env` — none of which are separate tool
calls. The broker sees the *intent* ("run python build.py") and is blind to what the
command did underneath. Gating on the command **string** is also evadable
(base64-decode-and-run, copy-and-rename a binary, `eval`). (C) sees everything but
loses intent and is heavy/platform-specific.

**Verdict: (B) Broker + OS interception, working together.** The command broker
gives intent; OS interception (seccomp/eBPF on Linux, `sandbox-exec` / Endpoint
Security on macOS — we already have the seed in `enforcement.py`) gives ground truth
inside the command. Reconciling the two is a core feature, not plumbing.

### D4 — "Untrusted binary" detection: string match or exec interception?

**Options.** (A) Match the command string against an allow/deny list. (B) Intercept
the **exec syscall** and check the actual binary against a **trust registry**
(allowlist by path + content hash).

**Debate.** (A) is trivial and evadable — the whole point of an "untrusted binary"
alert is to catch the thing that *doesn't* look obvious. (B) is application
allowlisting (what EDR/AppLocker do): you check what is *actually* being executed,
by hash, at the kernel boundary, so renaming or obfuscation doesn't help. It requires
a **binary trust registry** as a first-class artifact and OS-level exec hooks.

**Verdict: (B).** Exec interception + a binary trust registry. The dev/"test" mode
*builds* the registry by recording every binary an agent touches; prod mode flips
unknowns to alert-or-block.

### D5 — Network capture: trust the command broker, or lock egress?

**Options.** (A) Assume all network happens via brokered commands/tools. (B)
**Egress lockdown** — the runtime can only reach the network through our proxy —
plus socket-syscall capture at the OS layer for anything non-HTTP.

**Debate.** (A) is false in general (an approved interpreter can open a raw socket,
per D3). For a real completeness claim on the network, traffic must be *forced*
through the proxy (no direct egress), and non-HTTP/raw sockets must be visible at the
OS layer. This is a **deployment property** (network policy on the container/host),
not only code.

**Verdict: (B).** Egress locked to the proxy for HTTP(S) (also the natural home for
the LLM and tool proxies); OS-level socket capture as the backstop and the
discrepancy detector.

### D6 — Which interception layers, in what order?

**Options / the menu.** LLM proxy (decision), MCP/tool gateway (intent), command
broker (intent→effect bridge), OS interception (effect), filesystem watcher (effect).

**Debate.** We cannot build all five at once without re-bloating. Prioritize by
**leverage × shippability × where risky actions actually occur.** The MCP/tool
gateway wins: tool calls are where consequential actions happen, the protocol is
already structured, it is exactly the place to *block*, and **we already built an
MCP proxy that is sitting in `archive/`.** The LLM proxy is second (explainability —
"show me the reasoning behind this action"). OS interception is third and only where
agents have raw local access. The standalone FS watcher is largely subsumed by OS
interception + existing snapshots.

**Verdict.** Order: **(1) MCP/tool gateway → (2) command broker hardening →
(3) LLM proxy → (4) OS interception (eBPF/macOS ES) → (5) FS as needed.**

### D7 — Policy engine: bespoke YAML, code, or a real declarative engine?

**Options.** (A) Keep extending the task-contract YAML with ad-hoc fields. (B) Hard
-code rules in Python. (C) A declarative policy engine — evolve contracts into a
versioned policy language, or embed **OPA/Rego** (or Cedar).

**Debate.** (A) is how `plugins.py` became a 1,000-line grab-bag — ad-hoc fields
metastasize. (B) doesn't let customers express their own policy without forking us.
Enterprise buyers expect **policy-as-code**: versioned, testable, auditable,
reviewable in a PR. OPA/Rego is the de-facto standard and avoids us inventing a
language; the cost is a dependency and a learning curve, and Rego is awkward for
non-engineers. A thin contract layer on top (human-friendly) that *compiles to* the
engine is a reasonable middle path.

**Verdict: (C), via *policy by demonstration* — and this is the product, not plumbing.**
We separate two things that "policy engine" usually conflates:

- The **engine** (evaluates rules at runtime) — boring, hidden. Start with a *simple
  homegrown rule format* the existing `policy`/`verifier` modules can evaluate; we can
  swap in **OPA** later *without users ever noticing*, precisely because they never
  touch it. (Note: OPA is open-source — customers don't "buy OPA"; they buy the
  experience below.)
- The **authoring experience** (how rules get created) — *this* is what we sell.
  Instead of asking customers to write rules upfront, we **record a real run, show the
  flow of actions, let a human allow/block each one in our UX, and have an AI layer
  draft the reusable rule *with reasons why*.** Human accepts/edits → it becomes policy.

This sidesteps the killer risk in the original framing ("policy UX is make-or-break,
Rego is hard"): nobody hand-writes policy; they react to what the agent actually did,
and the system proposes the rule. LLMs are good at the "explain the reasoning" part,
so the recommender is a natural fit (a skill/prompt over the recorded flow + the
human's allow/block labels).

### D8 — Event schema & provenance: invent or adopt standards?

**Options.** (A) Our own JSON event shapes (today's state). (B) Adopt emerging
standards: **OpenTelemetry GenAI semantic conventions** for spans/traces,
**CloudEvents** for the envelope, **in-toto / SLSA-style attestations** for signed
provenance.

**Debate.** Inventing a schema feels faster but isolates us from the ecosystem
(SIEMs, OTel collectors, dashboards) and means re-litigating fields forever.
Enterprises already run OTel pipelines and SIEMs; emitting standard spans means we
plug into existing observability instead of demanding new infrastructure. The cost is
conforming to specs still in flux.

**Verdict: (B).** Normalize everything to an **OTel-GenAI-aligned causal trace**;
sign run manifests as in-toto-style attestations. This is what turns "a log" into
"an auditor's evidence."

### D9 — Build vs. leverage (the strategic one)

**Options.** (A) Build our own eBPF capture, our own gateway, our own policy engine.
(B) **Leverage** mature components — eBPF via Falco/Tetragon, LLM gateway patterns,
OPA for policy, OTel for schema — and **own only the differentiated spine:
cross-layer correlation, the tamper-evident audit store, reconciliation/verification,
and signed attestation.**

**Debate.** Reimplementing eBPF tooling or a battle-tested policy engine is years of
work and a security liability we'd own. Our actual moat is **not** any single proxy
or syscall hook — those are commodities. It is the **unified, tamper-evident,
cross-layer causal record + the reconciliation that turns it into findings.** Every
hour spent rebuilding Tetragon is an hour not spent on the moat.

**Verdict: (B).** Integrate best-of-breed collectors at the edges; concentrate
original engineering on correlation, audit integrity, verification, and reporting.
This also keeps the spine small — the lesson from the carve-down.

**Caveat that shapes sequencing:** the ready-made tools we'd leverage here
(Falco, Tetragon) are **Linux-only**. So "leverage" and "**Mac first**" partly
conflict — on macOS the equivalent is Apple's Endpoint Security framework plus the
`sandbox-exec` seed already in `enforcement.py`, which is more *build* than *leverage*.
This is the main reason the **first build defers the OS layer entirely** and lives at
the intent layer, where Mac support is free (see Section 6).

### D10 — Deployment topology

**Options.** (A) Local CLI only (today). (B) **Edge + control plane**: lightweight
collectors/enforcers run where the agent runs (host/container/sidecar); a central
control plane holds policy, the audit store, and dashboards. (C) Pure central proxy,
no edge.

**Debate.** (C) can't see local effects (D3/D5) — it only sees what crosses the
network. (A) doesn't fit enterprise multi-agent, multi-team reality. (B) matches how
the capture actually has to work: OS/exec interception must be *on the agent's host*,
while policy and audit want to be *central* for governance, retention, and review.
The cost is that we're now building a small distributed system (the proxy is in the
request path → availability, latency, fail-open/closed all become real).

**Verdict: (B).** Edge collectors/enforcers + central control plane. The control
plane is the carved spine, grown up; collectors are pluggable and trust-tagged.

### D11 — Tamper model: how strong, how soon?

**Options.** (A) Hash-chained append-only log (we have this). (B) + **signed**
run manifests / attestations. (C) + **external notarization** (independent
timestamping / transparency log) and an isolated recorder the agent host can't rewrite.

**Debate.** (A) detects edits but the host can still rewrite history wholesale. For
compliance evidence you want signatures (non-repudiation) and ideally an external
anchor so even a compromised host can't silently rewrite. (C) is heavier and can come
later, but the *interfaces* should assume it.

**Verdict.** Keep (A) now; add (B) signed attestations in the near term; design the
store interface so (C) external notarization can slot in without redesign.

### D12 — Enforcement graduation & safety

**Options.** (A) Block from day one. (B) **Observe → Alert → Block**, with a
baseline/learning mode.

**Debate.** A control plane that blocks legitimate work on day one will be ripped
out. Real agent work shells out constantly (builds, package managers, test runners
spawn dozens of children) so an over-eager exec policy is a foot-gun. A learning mode
that records and proposes an allowlist, then graduates environments from
alert-only to enforce, is how you earn the right to block. Also forces the
fail-open vs fail-closed decision per environment (dev fail-open, prod fail-closed
on the highest-risk classes).

**Verdict: (B).** Observe/learn in dev → alert in staging → block the high-risk
classes in prod. Policy carries the mode.

### D13 — Identity & attribution

**Options.** (A) Record the agent name only (today). (B) Bind every action to a
**principal chain**: which agent, acting on behalf of which human/service, in which
session, under which authorization — tied to enterprise SSO/IdP, with the trace
context propagated across sub-agents.

**Debate.** "Who authorized this?" is the first question an auditor asks. Without a
principal chain the log is unanswerable for governance. The cost is real integration
(OIDC, short-lived credentials, propagation across delegation).

**Verdict: (B).** Attribution is part of the schema (D8), not an afterthought.

### D14 — Relationship to the existing spine & archive

**Debate.** The carve-down was correct and we don't undo it. The pivot **re-motivates
specific** archived pieces — chiefly the **MCP proxy** — which return as *edge
collectors*, not as spine. `orchestration` returns later (sub-agent delegation +
attribution propagation). `plugins.py`'s data/media checks stay parked (out of scope).

**Verdict.** Spine stays small and central (normalize, correlate, store, verify,
report, attest). Un-archive the MCP proxy first as a collector. Everything else is
new, pluggable, and trust-tagged.

---

## 5. The finalized architecture

```
                    ┌──────────────────────────────────────────────┐
                    │              CONTROL PLANE                     │
                    │  (the carved spine, grown up — central)        │
                    │                                                │
   policy as code → │  Policy engine (OPA?)   Correlation /          │
   (versioned)      │  Tamper-evident audit   reconciliation engine  │
                    │  store (hash-chain →     → findings             │
                    │  signed attestations)   Verify + Report + SIEM  │
                    └───────▲───────────────────────▲────────────────┘
                            │ decisions + events     │ (OTel-aligned causal trace,
                            │ (allow/deny/redact/     │  signed manifests)
                            │  approve)               │
        ┌───────────────────┴───────────┬────────────┴───────────────┐
        │  EDGE: brokered PEPs (intent)  │  EDGE: observers (effect)   │
        │                                │                             │
        │  • LLM proxy   (decision)      │  • OS interception:         │
        │  • MCP / tool gateway (intent) │     exec + socket + file    │
        │  • Command broker (run --)     │     (eBPF / macOS ES;       │
        │  • Egress proxy (network)      │     builds on enforcement.py)│
        │                                │  • Binary trust registry    │
        └────────────────────────────────┴────────────────────────────┘
                         run where the agent runs
                    (host / container / sidecar, egress-locked)
```

**Data flow for one action:**

1. Agent emits an action (model call / tool call / command / network request).
2. The relevant **brokered PEP** intercepts it, attaches the **principal + trace
   context**, and asks the **policy engine**: allow / deny / redact / require-approval.
3. The decision *and* the action are written to the **tamper-evident audit store** as
   an OTel-aligned span.
4. If allowed, the action executes; **OS observers** capture its real effects
   (child execs, sockets, file ops) as further spans in the same trace.
5. The **reconciliation engine** matches intent spans to effect spans; mismatches and
   policy violations become **findings**.
6. **Report / attest / forward to SIEM.** High-risk actions can pause for **human
   approval** instead of a hard block.

**Completeness claim we can honestly make:** *every action through a brokered path is
recorded and policy-checked; every effect inside a brokered command is observed at the
OS layer; any activity with no matching brokered intent is detected and surfaced as a
coverage gap.* Completeness depends on the **deployment** (egress-locked, no
un-brokered execution) — that's a documented requirement, not a silent assumption.

---

## 6. Execution plan (the first build)

**What we're building first:** the **policy-by-demonstration loop**, at the **intent
layer**, on **Mac** — *record a run → show the flow → human allow/block → AI recommends
policy with reasons → enforce on the next run.* Nothing else. This is the whole product
in miniature, and it's demoable.

**Self-debate on the ordering (why this, in this order):**

- *Why the intent layer first, not the OS layer?* The magic you care about
  (record → recommend → approve) needs to see **tool calls and commands**, not kernel
  syscalls. And the OS tools we'd "leverage" are Linux-only while we want Mac first
  (D9). So the OS ground-truth layer is the *backstop* — it earns its place later, not
  now. Building it first would be the slow, conflicted path.
- *Why the review UX before the recommender?* The AI recommender **learns from** the
  human's allow/block choices. No human decisions captured → nothing to learn from. So
  the review step has to exist before the recommendation step.
- *Why a homegrown rule format, not OPA now?* Users never see the engine (D7), so a
  tiny format the existing `policy`/`verifier` can evaluate is enough to prove the
  loop. Swap in OPA later, invisibly. Starting with OPA is premature weight.
- *Why reuse, not rebuild?* We already have command capture (`tracewall run --`) and
  an MCP proxy in `archive/`. The intent layer is mostly *assembly*, not new invention.

**The loop, step by step (no timelines — just order):**

1. **Unify intent capture.** Make one run produce one ordered **action flow**. Use the
   existing command events; un-archive the **MCP proxy** so tool calls land in the same
   event log. Output: a clean, ordered list of "what the agent did."
2. **Show the flow for review.** A simple local view that renders the run's actions in
   order, each with an **allow / block** control. (Lighter fallback if we want to move
   even faster: mark decisions in a generated file via CLI — but the clickable view
   *is* the product, so prefer it.)
3. **Capture the human's verdicts.** Persist allow/block per action — this is the
   training signal for step 4.
4. **Recommend policy (the differentiator).** An AI pass reads *(the flow + the human's
   allow/block labels)* and drafts reusable rules in the simple format, each **with a
   plain-language reason**. Human accepts/edits → saved as the run's policy.
5. **Enforce on the next run.** Apply the saved policy at the intent chokepoint in
   **observe → alert → block** mode. Show an action getting stopped.
6. **Close the loop.** Re-run; demonstrate the recommended policy catching the exact
   thing the human flagged last time. That round-trip is the demo.

**Deliberately NOT in the first build:** OS/eBPF interception, the binary trust
registry, the LLM proxy, reconciliation, SSO, signed attestations, SIEM export. They're
real and they're in the design above — just not needed to prove the loop.

**After the loop proves out (later, in roughly this order):** add the **OS ground-truth
layer** (Linux via Falco/Tetragon + the binary trust registry) so we see *inside*
commands; add the **LLM proxy + reconciliation** to flag decision/intent/effect
mismatches (this is what makes it a true *auditor*); then **enterprise hardening** (SSO,
signed attestations, SIEM, human-approval workflow, sub-agent attribution).

---

## 7. Risks & open questions

- **The proxy is now critical-path infra.** It can break workflows when it blocks;
  reliability/latency/fail-mode bar is far higher than a passive recorder. (Mitigation:
  D12 graduation, per-env fail modes.)
- **Policy UX is make-or-break** (D7). Too strict → ripped out; too loose → theater.
  Mitigation is the whole point of **policy by demonstration**: nobody hand-writes
  rules; they react to real runs and the system recommends. The open risk shifts to
  *recommendation quality* — bad AI suggestions erode trust fast.
- **OS interception is platform-specific and heavy** (D3/D4). Linux (eBPF) is the real
  prod target; macOS is dev. Decide whether to lean on Falco/Tetragon (D9) vs. our own.
- **Completeness is a deployment property, not just code.** If a customer doesn't
  egress-lock or leaves un-brokered execution, our guarantee weakens — we must *detect
  and report* that posture, not pretend.
- **Standards in flux** (D8) — OTel-GenAI conventions are still moving; pin versions.
- **Scope re-bloat** — the gravity that produced `plugins.py` is still there. Defense:
  spine stays small; everything else is a pluggable, trust-tagged collector.

---

## 8. Recommendation (the finalized call)

Build an **enterprise agent audit & control plane** on the **hybrid broker-first**
model: a single **Policy Enforcement Point** that records and enforces at the same
chokepoint, with **brokered proxies for intent** and **OS-level observation for ground
truth**, reconciled into an **OTel-aligned, tamper-evident, attributable causal
trace**. **Leverage** mature components (OPA, eBPF tooling, OTel) and concentrate
original work on the **correlation + audit-integrity spine**. The **first build** is
the **policy-by-demonstration loop at the intent layer, on Mac** (Section 6): record →
review → AI-recommend → enforce, un-archiving the MCP proxy and reusing existing
command capture. Once that loop delights, add the **OS ground-truth layer**, then the
**reconciliation engine** that makes it a true auditor, then enterprise hardening.

The completeness claim is honest and strong *because* it's bounded: every brokered
action recorded and gated; every in-command effect observed; every un-brokered action
detected — with the deployment requirements that make that true written down, not
assumed.
