# Tracewall — Priority Roadmap

**Audience:** founding team (build order, not a pitch)
**Horizon:** next 2 weeks → this quarter → this year
**Date:** 2026-06-20
**Companion docs:** [north-star.md](north-star.md) (the destination) · [audit-control-plane.md](audit-control-plane.md) (the debated design) · [security-model.md](security-model.md)

This supersedes the forward-looking half of the root [`ROADMAP.md`](../ROADMAP.md), which describes the carved-down alpha spine. The spine is built. This is the plan to turn it into the **daemon + control plane + clients** architecture we just committed to, in priority order, grounded in code that already exists.

> **Read this first.** The ordering is deliberate. P0 items are *hard to change once shipped* — get them right before anything visible. Everything below P0 is sequenced so that each tier is demoable on its own and de-risks the next.

---

## 0. The three ambitions (why this is more than a product)

The "more than a product" feeling is correct. There are three concentric prizes here, and the build order below is designed so we earn each one on the way to the next — we never detour to chase the outer rings before the inner one works.

```
   ┌──────────────────────────────────────────────────────────┐
   │  RING 3 — STANDARD / CATEGORY                              │
   │  "Is there a Tracewall trail for this?" becomes the      │
   │  default question. An open event schema + verifier that    │
   │  other agent vendors emit. We named & own "agent control   │
   │  plane / policy by demonstration."                         │
   │   ┌────────────────────────────────────────────────────┐  │
   │   │  RING 2 — PLATFORM                                   │  │
   │   │  The always-on daemon + hosted control plane.       │  │
   │   │  Team audit, central policy, compliance evidence.   │  │
   │   │  This is the paid surface and the moat.             │  │
   │   │   ┌─────────────────────────────────────────────┐  │  │
   │   │   │  RING 1 — PRODUCT                            │  │  │
   │   │   │  The record→review→recommend→enforce loop   │  │  │
   │   │   │  a single dev loves on their own machine.   │  │  │
   │   │   │  Local-first, no signup. This must be loved │  │  │
   │   │   │  before Ring 2 matters.                     │  │  │
   │   │   └─────────────────────────────────────────────┘  │  │
   │   └────────────────────────────────────────────────────┘  │
   └──────────────────────────────────────────────────────────┘
```

- **Ring 1 (Product)** is mostly built — the spine, hook, guard, observe, recommender, review UI all exist. The work is *promoting it into a daemon* so it's ambient and fast.
- **Ring 2 (Platform)** is the company. The daemon ↔ control-plane sync, team audit, central policy, and compliance evidence are what an organization pays for.
- **Ring 3 (Standard)** is the category win. If the **event schema** and **verifier** are open and good, "emit Tracewall events" becomes the way agents prove they're governed — the way OpenTelemetry became the way services prove they're observable. We seed this by freezing the schema in P0 and open-sourcing the core later, deliberately.

Principle that keeps this honest (from the north star): **sell the experience, keep the spine small, observe→alert→block, leverage don't rebuild.** Every item below is a pluggable, trust-tagged collector or a thin client over the same small spine — not new gravity.

---

## P0 — Foundation flip *(do first; hard to change later)*

**Goal:** turn the per-invocation CLI into a **standalone, always-on, local-first daemon** that the editor, web, and agents all talk to — and freeze the contracts the rest of the system depends on. None of this is visible to a user, but every later tier inherits these decisions, so a wrong call here is expensive.

**Why now:** the foundation decisions (who owns the daemon's lifecycle, what's the source of truth, what's the wire format, what leaves the machine) are the ones I flagged as load-bearing. They cannot be retrofitted cheaply once an extension, a web app, and a sync protocol all depend on them.

- [x] **P0.0 — Reduce unused code.** ✅ Done — removed `gateway.py`, `paths.py`, and the write-only sqlite `store.py` (JSONL is now the only event store — *enacts P0.4*); collapsed `mcp_policy.py` 212→35 lines; deleted dead symbols + imports. Tests green, `pyflakes` clean. Plan + results in [p0-execution-plan.md](p0-execution-plan.md).
- [x] **P0.1 — Promote the engine to a daemon (`tracewalld`).** ✅ Done — `daemon.py` (UDS + localhost HTTP, in-memory mtime-invalidated policy cache), `tracewall daemon run|status|stop`, hook fast-path with in-process fallback. Warm decide <20ms, tests green. A long-running local service that holds policy in memory and answers decisions over a **Unix-domain socket + localhost HTTP**. This removes per-action cold-start and makes ambient (folder-level) governance possible — the friction-killer the user asked for. *Reuse:* `enforce.evaluate_action`, `hook.decide`, `recorder`, `review.handle_api`. *New:* a thin service wrapper + a `tracewall daemon` subcommand. *Definition of done:* a hook call resolves against the running daemon in <20ms with no Python cold start.
- [x] **P0.2 — Install the daemon as an independent OS service.** ✅ Built — `tracewall daemon install`/`uninstall` generate + best-effort-load a launchd plist (macOS) / systemd --user unit (Linux), idempotent; `test_service.py` (6), Linux unit generation verified. ◑ macOS auto-start-on-login is the on-Mac check. `launchd` plist on macOS, `systemd --user` unit on Linux. Its lifecycle is **independent of any editor** — it survives VS Code closing and covers terminal-only and background agents. *Definition of done:* `tracewall install-daemon` registers the service; it auto-starts on login; killing the editor does not stop governance.
- [x] **P0.3 — Freeze the event schema as a versioned contract.** ✅ Done — published `schema/agent-action-event.v1.json` + `EVENT_SCHEMA_V1`/`validate_event` in `events.py`, stamped `schema_version:"1"` on every event, `test_schema.py` validates every writer type + a real on-disk run + rejects malformed. The hash-chained event is already our format; promote it to `schema/agent-action-event.v1.json` with an explicit version field and a written spec. This is the literal seed of Ring 3 — treat it like a public API from day one. *Reuse:* `events.py`, `recorder.py`, `verifier.py`. *Definition of done:* every writer (`hook`, `mcp_stdio`, `guard`, `observe`, `recorder`) emits schema-valid v1 events; a conformance test rejects drift.
- [x] **P0.4 — Decide & document the source of truth.** ✅ Done — ADR ([adr-source-of-truth.md](adr-source-of-truth.md)) + enacted (sqlite mirror removed in P0.0) + server ingest-gate `verify_event_stream` (rejects malformed/broken/forked chains), tested. Commit (in writing) to **local daemon writes the tamper-evident log; cloud mirrors it.** The hash chain is authored locally and verified server-side; the cloud never becomes the primary. This is the fork that shapes everything downstream — pick it now. *Definition of done:* a one-page ADR in `docs/` stating local-authoritative, plus a server-side chain-verification stub.
- [x] **P0.5 — Local-first, no signup to run solo.** ✅ Done — audited every entry path (no outbound HTTP client, no login/account gate; only local UDS + 127.0.0.1); `test_local_first.py` (3) proves the full loop runs offline + a static no-network-client guard; README states the guarantee. The daemon must run fully offline and deliver the entire Ring-1 loop with **zero account**. Signup and sync are opt-in, for teams. Don't put an auth wall in front of a developer's first run. *Definition of done:* fresh machine → install → full record/review/recommend/enforce loop, never prompted to log in.
- [x] **P0.6 — Daemon threat model + hardening.** ✅ Done — `docs/daemon-threat-model.md`; `load_active_policy` refuses a world-writable policy (falls back to default-safe), the daemon logs `policy.changed`/`policy.rejected` to a hash-chained `policy-events.jsonl`, socket stays 0600; `test_daemon_hardening.py` (6). The daemon is privileged: it holds policy and watches every agent action, so it is itself a target. Socket permissions, refuse-if-world-writable policy files, signed/locked policy the governed agent can't silently edit, and tamper-evident self-logging. *New:* `docs/daemon-threat-model.md`. *Reuse:* `verifier.py` chain logic, `sensitive.py`. *Definition of done:* documented threat model + the agent-under-watch cannot disable or rewrite its own guardrail without leaving a record.
- [x] **P0.7 — Redaction-before-sync contract.** ✅ Done — redaction moved to *write* time (`mask_secret_material` in `events.py`) so secrets never enter the hashed log, + `redact_for_sync` idempotent fail-safe; `test_redaction.py` (7) masks tokens/PEM/AWS keys while keeping sensitive paths for audit. Define exactly what may leave the machine and guarantee secrets are redacted *before* any upload. This is both a trust requirement and a selling point. *Reuse:* `sensitive.looks_secret_token`, `looks_secret_path`. *Definition of done:* a redaction pass with tests proving known secret shapes (`.env`, `id_rsa`, `credentials`, tokens) never appear in a sync payload.

**Status (2026-06-20): P0 complete** — all items built and green (98 tests, pyflakes clean). The only open thread is the **macOS launchd auto-start** of P0.2, which is an on-Mac validation step, not a code gap.

**P0 exit criteria:** an always-on local daemon, an editor-agnostic decision/log API, a frozen v1 event schema, a written source-of-truth + threat model, and a redaction guarantee. After this, the visible product is just clients over a stable core.

---

## P1 — Product surfaces *(the flow you described)*

**Goal:** the surfaces a single developer touches — exactly your flow, with the foundation flipped so the engine is the daemon and the extension is *one* client, not the install.

**Why now:** this is what makes Ring 1 lovable and demoable in one sitting. It's mostly wiring existing pieces to the new daemon, not greenfield.

- [ ] **P1.1 — VS Code extension = installer + client.** One-click: detect agents (`~/.claude`, `~/.codex`, CLIs on `PATH`), wire their hooks, install+start the daemon, connect to it. *Reuse:* existing `vscode-extension/` shell, `install-hook` / `install-codex`. *Definition of done:* fresh VS Code → one click → daemon running, agents hooked, live log visible.
- [◑] **P1.2 — Extension talks to the daemon, not the CLI.** ◑ Started — the daemon now exposes `/api/state` + `/api/verdict` (the endpoints the extension will call instead of shelling out); rewiring `vscode-extension/` is the remaining piece. Replace shell-outs with the daemon's socket/HTTP API for a live log stream and inline approvals. *Reuse:* `review.handle_api`. *Definition of done:* the timeline updates in real time without re-shelling `tracewall review --json`.
- [◑] **P1.3 — Daemon-served local web UI (editor-agnostic).** ✅ First cut — the daemon serves `/review` (HTML), `/api/state`, `/api/verdict` per project via `?cwd=&run=`, reusing `review.handle_api`/`render_review_html`; `test_daemon_web.py` (2). Live-polling refresh is the remaining refinement. The daemon serves the review page on localhost so devs *not* in VS Code (terminal, Cursor, JetBrains) get the same timeline. *Reuse:* `review._PAGE`, `serve_review`, `export_review_html`. *Definition of done:* `http://localhost:<port>` shows the same flow as the extension, no editor required.
- [ ] **P1.4 — Approval mediation with a default + timeout.** When an action is "ask," the daemon mediates synchronously and delivers the prompt to extension + local web + **OS notification**. Define timeout semantics up front: **risky → deny on timeout**, low-risk → fall through to the agent's own prompt. *Reuse:* `hook.decide` ask path, `insight.analyze_action` for risk. *Definition of done:* an un-hooked agent (guarded) blocks on "ask," a notification fires, and a non-answer resolves deterministically by the documented rule.
- [ ] **P1.5 — Standalone install path.** `brew` / `curl | sh` for the engine so non-VS-Code users and **CI runners** are covered without the extension. *Definition of done:* a headless box installs and runs the daemon with no editor present.

**P1 exit criteria:** your end-to-end flow works — install → detect/wire agents → daemon runs → logs in extension *and* local web → approvals via extension/web/notification — for a solo dev, fully local.

---

## P2 — Team & control plane *(the paid surface)*

**Goal:** the hosted control plane that turns the local tool into something an organization buys. This is Ring 2 — the commercial core and the moat.

**Why now:** only after the solo loop is loved (the north star is explicit: don't harden for enterprise before the loop is loved). But the *sync contract* is designed in P0, so this is build-out, not redesign.

- [ ] **P2.1 — Daemon ↔ control-plane sync.** Append-only upload of redacted events; **server re-verifies the hash chain** (local stays authoritative per P0.4). *Reuse:* `verifier.py`, P0.7 redaction. *Definition of done:* two machines' runs appear in one org timeline with server-side chain verification passing.
- [ ] **P2.2 — Auth, orgs, device enrollment, SSO.** Org/workspace model; each daemon enrolls as a device; OIDC/SSO for the web. *Definition of done:* an admin sees every enrolled daemon and who owns it.
- [ ] **P2.3 — Web control plane = all functions & controls.** The full governance surface: org-wide audit, policy editing, device status. The web *drives the daemons*; local-only actions stay mediated locally. *Reuse:* `review` pages, `render_policy_html`. *Definition of done:* an admin reviews any run and edits org policy from the browser.
- [ ] **P2.4 — Central policy distribution + policy packs.** Push org policy down to enrolled daemons; ship reusable rule bundles (a `skill.md`-style pack: "block secret reads," "no prod egress"). *Reuse:* `recommend.py`, `enforce.py`, `accept_rules`. *Definition of done:* an admin publishes a pack; daemons enforce it on next run.
- [ ] **P2.5 — Compliance / evidence export.** A "your agents are governed" report (SOC2/ISO-flavored) — the Vanta-for-agents wedge into security buyers. *Reuse:* `reports.py`. *Definition of done:* one click produces an auditor-ready evidence pack from real run history.

**P2 exit criteria:** a team can enroll machines, see one audit trail, push policy centrally, and export compliance evidence — over SSO.

---

## P3 — Depth & moat *(what compounds)*

**Goal:** the defensible core the north star names — cross-layer reconciliation and production-grade observation — plus breadth across runtimes.

- [ ] **P3.1 — Reconciliation (intent vs effect).** The north-star "gold is the disagreement." Diff what the agent *said* it did (intent: `flow.py`) against what *actually happened* (effect: `observe.py`) and surface "claimed to read `config.yaml`, actually opened `.env`." *Reuse:* `flow.build_action_flow` + `observe.parse_strace`. *Definition of done:* a run where intent≠effect is flagged automatically.
- [ ] **P3.2 — Production OS observation.** Graduate `strace` → **eBPF** (Falco/Tetragon) on Linux and `sandbox-exec` → **Endpoint Security** on macOS — same events, lower overhead, harder to evade. *Reuse:* `guard.py`, `observe.py` already emit the target event shapes. *Definition of done:* effect events come from eBPF/ESF with the strace path as fallback.
- [ ] **P3.3 — More runtimes.** OpenClaw, Cursor, JetBrains, Codex-in-CI, generic guarded shell — each a pluggable, trust-tagged collector over the same schema. *Definition of done:* a second non-Claude/Codex agent runs end-to-end through the daemon.
- [ ] **P3.4 — Recommendation quality loop.** The north-star make-or-break: measure acceptance, learn from edits, improve suggested policy. *Reuse:* `recommend.py`, verdicts in `review.py`. *Definition of done:* recommendation-acceptance rate is tracked and trending up.

---

## Strategic track — *the "more than a product" moves* *(parallel, low-effort-now, high-optionality)*

These run alongside the build. They cost little today and create the optionality to be a category/standard, not just a tool. Do the cheap, irreversible-advantage ones early (publish the schema); defer the heavy ones.

- [ ] **S.1 — Open-core boundary.** Decide what's open (the spine: schema, recorder, verifier, hook contracts, local loop) vs commercial (control plane, SSO, compliance, central policy). The GitLab/HashiCorp/Vanta shape. *Do the decision now; the split is cheap before P2, expensive after.*
- [ ] **S.2 — Publish the event schema + verifier as an open spec.** This is the Ring-3 seed and nearly free once P0.3 is done. "OpenTelemetry for agent actions." Invite other agent vendors to emit it.
- [ ] **S.3 — Name & evangelize the category.** "Agent control plane / policy by demonstration." A sharp public writeup; get the sentence repeated back (north-star success signal).
- [ ] **S.4 — Compliance positioning.** Lead with trust for the security buyer ("prove your agents are governed"). Pairs with P2.5.
- [ ] **S.5 — Design partners.** The north star's explicit 12-month bar: a handful of teams running real agents through it, having blocked ≥1 real risky action. Start recruiting once P1 demos.

---

## Cross-cutting — *always on, every tier*

- [ ] **X.1 — Validate against REAL agent installs.** The standing honest gap: the hook/guard/observe paths are proven against documented contracts and simulation, **not** against live Claude Code / Codex / OpenClaw on a real machine. Close this continuously — it's the difference between "should work" and "works."
- [ ] **X.2 — Instrument the north-star metric.** Measure **Trusted Autonomy Rate** (share of actions auto-allowed by learned policy, still recorded/reversible) plus time-to-first-blocked-action, recommendation-acceptance, coverage. You can't optimize what you don't measure.
- [ ] **X.3 — Keep the spine small (ponytail).** Every new capability is a pluggable, trust-tagged collector or a thin client. Resist the gravity that produced the old 1,000-line modules. Deletion over addition; reuse stdlib/native/existing before writing code.
- [ ] **X.4 — Fail-open/closed discipline.** As we sit on the critical path, every enforcement point states its failure mode explicitly (hook fails open; guard fails closed). Reliability and latency now matter more than features.

---

## Decide before you build — *open forks*

Resolve these explicitly; each shapes code that's costly to change later. (Recommended default in **bold**.)

1. **Source of truth:** **local-authoritative, cloud-mirrors** vs cloud-first. *(P0.4 — recommend local.)*
2. **Daemon transport:** **UDS + localhost HTTP** vs gRPC. *(Recommend the simpler one; ponytail.)*
3. **What syncs:** **redacted events only, opt-in** vs full local log. *(P0.7 — recommend minimal + opt-in.)*
4. **Auth for teams:** **OIDC/SSO from the first team release** vs password-first then SSO. *(Recommend SSO-first; the buyer is security.)*
5. **Open-core line:** where exactly is the OSS/commercial cut. *(S.1 — decide before P2.)*
6. **Approval timeout default:** **risky→deny, low→fall-through** vs always-deny vs always-ask. *(P1.4 — recommend the split.)*

---

## Sequencing at a glance

| When | Focus | Items |
|------|-------|-------|
| **Next ~2 weeks** | Foundation flip | P0.1 daemon, P0.2 OS service, P0.3 freeze schema, P0.4 source-of-truth ADR |
| **This quarter** | Lovable solo loop | P0.5–P0.7, all of P1, X.1–X.2, S.2 publish schema |
| **This year** | Team + moat | P2 (control plane), P3.1 reconciliation, S.1/S.3/S.5, begin P3.2 |
| **Post-destination** | Scale | P3.2–P3.4, enterprise hardening, Ring-3 evangelism |

**The single most important sequencing rule:** do not build a visible surface (extension, web, sync) on top of the old per-call CLI. Flip to the daemon (P0.1–P0.2) and freeze the schema (P0.3) *first*. Everything else is a client over that.

---

## What we are still NOT doing (unchanged from the north star)

Building a coding agent or model · defending against a fully attacker-controlled agent vs the kernel · OS/eBPF interception *first* (it's the backstop) · adopting OPA *first* (hidden engine, swap later) · replacing CI/code-review/SIEM (we feed them) · enterprise hardening before the loop is loved.
