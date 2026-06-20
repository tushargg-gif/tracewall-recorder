# P0 — Execution Plan

**Companion:** [roadmap.md](roadmap.md) (the why) · this doc is the **how** — subtasks, goal, and test for each P0 item.
**Date:** 2026-06-20

P0 is the foundation flip: a standalone, always-on, local-first daemon plus the frozen contracts everything else inherits. It must be right before any visible surface is built on it.

## How we execute P0 (ponytail rules)

These are constraints, not suggestions. Every subtask is checked against them.

1. **Reuse before writing.** If `enforce` / `hook` / `recorder` / `verifier` / `sensitive` already does it, call it — don't reimplement.
2. **Deletion counts as progress.** Removing a path is preferred to adding one. One source of truth, never two that can drift.
3. **Minimum that works.** No abstraction without a second caller. No config without a second value. No file we don't need.
4. **Every subtask ships with its test.** "Done" = the test passes. No test, not done.
5. **Honest seams.** What we can't validate here (macOS launchd, real agent installs) is built and explicitly flagged for on-machine validation — never silently assumed.

Status legend: ✅ done · ◑ partial · ☐ todo

---

## P0.0 — Reduce unused code ✅

**Goal:** remove dead and superseded code so the foundation is built on a small, honest surface (and so "one source of truth" is literally true).

- [x] Delete speculative/orphaned modules: `gateway.py`, `paths.py` (+ their tests) — zero live importers.
- [x] Delete the write-only **sqlite mirror** `store.py`; make the JSONL hash-chain the only event store (`recorder._write_event` / `_last_event_hash`). This *enacts P0.4*.
- [x] Collapse `mcp_policy.py` (212→35 lines) to the two helpers the proxy uses; the standalone evaluator was superseded by `enforce.py`.
- [x] Remove dead symbols: `enforce.MODES`, `enforcement.to_decision` + `guard_supported`, `events.REDACTED`; and 4 unused imports.

**Test:** `pytest` green (67 passed, pre-existing sandbox PATH artifact aside); `pyflakes src/agentproof` clean; `vulture --min-confidence 60` shows only framework callbacks (`do_GET`/`do_POST`/`daemon_threads`).
**Result:** −3 source modules, −2 test files; sqlite path gone (no second store to drift from JSONL).

---

## P0.1 — Daemon (`agentproofd`) ✅ (built previously)

**Goal:** one warm, local engine answering allow/ask/deny over UDS + localhost HTTP; no per-action cold start.
**Reuse:** `enforce.evaluate_action`, `hook.run_pre/run_post`, `review.handle_api`.

- [x] `daemon.py`: UDS + localhost HTTP, in-memory mtime-invalidated `PolicyCache`, 0600 socket.
- [x] `agentproof daemon run|status|stop`; hook fast-path with in-process fallback.

**Test:** existing daemon tests green; warm decide <20ms. *On-machine check still owed: run a real agent through the daemon (see X.1).*

---

## P0.2 — Daemon as an OS service ✅ build · ◑ macOS load = on-Mac check

**Goal:** the daemon's lifecycle is independent of any editor — always on, survives VS Code closing, covers terminal/background agents.
**Reuse:** `daemon.serve`, `daemon.home()`; generate service files, don't hand-roll a supervisor.

- [x] `service_spec` generates a `launchd` plist (macOS, `~/Library/LaunchAgents`) and a `systemd --user` unit (Linux, `~/.config/systemd/user`) from one path — pure + unit-tested.
- [x] `agentproof daemon install` writes + best-effort-loads the unit; `daemon uninstall` reverses it. Idempotent; leaves a hint if the loader is unavailable.
- [x] Daemon already writes `daemon.json` so clients discover it regardless of who started it.

**Test:** *Linux (here):* `systemctl --user` loads the unit, daemon answers `/status`, survives parent shell exit. *macOS (user machine — flagged):* `launchctl load` auto-starts on login; killing VS Code leaves the daemon running. Unit-test the file *generation* (pure string) in CI; the load/auto-start step is the on-machine check.

---

## P0.3 — Freeze the event schema v1 ✅

**Goal:** the hash-chained event becomes a versioned public contract — the seed of the open standard (Ring 3). Treat it like an API.
**Reuse:** `events.normalize_event` / `event_hash` already define the shape; this formalizes and guards it.

- [x] Wrote `schema/agent-action-event.v1.json` (JSON Schema) + canonical `EVENT_SCHEMA_V1` dict in `events.py`; a test asserts they never drift.
- [x] Added `schema_version: "1"` in `normalize_event` (part of the hash, so the chain covers it) + a dependency-free `validate_event`.
- [x] `test_schema.py` (5 tests): every writer event_type validates, a **real hook-recorded run** validates, malformed events are rejected, and the chain still verifies.

**Test:** `test_schema.py` — every writer's event validates; a deliberately malformed event is rejected; `event_hash` recomputes equal (chain still verifies via `verify_event_chain`).

---

## P0.4 — Source of truth: local-authoritative ✅

**Goal:** commit, in writing, that the local JSONL hash-chain is authoritative and the cloud only mirrors/verifies — so the architecture can't quietly drift to cloud-first.
**Reuse:** `verifier.verify_event_chain` *is* the verification logic; the server reuses it, doesn't reinvent.

- [x] ADR: [adr-source-of-truth.md](adr-source-of-truth.md) — local authoritative, cloud mirrors.
- [x] Enacted in code: sqlite mirror removed in P0.0; JSONL is the only store.
- [x] Server-side ingest gate `events.verify_event_stream(events)`: validates every event against v1 and runs `verify_event_chain`, rejecting malformed/broken/forked uploads. Seed of P2 sync.

**Test:** `verify_event_chain` on a good run returns valid; tampering with one event's payload makes it invalid at the right index (already covered — extend with a "server ingest" wrapper test).

---

## P0.5 — Local-first, no signup ✅

**Goal:** the entire Ring-1 loop runs offline with zero account; no auth wall in front of a developer's first run.

- [x] Audited every entry path (`cli`, `daemon`, `hook`, `review`): no outbound HTTP client anywhere, no login/account gate; the only network is local UDS + `127.0.0.1`, the only env var is the `AGENTPROOF_HOME` path override.
- [x] Documented the "fully local, no account" guarantee in the README (also a trust selling point).

**Test:** `test_local_first.py` (3) — the full record→recommend→enforce loop runs offline with no account; a static guard asserts no source imports an outbound network client; the `AGENTPROOF_HOME` knob is a path override, not a gate.

---

## P0.6 — Daemon threat model + hardening ✅

**Goal:** the daemon is privileged (it sees every action and holds policy), so it must be a hard target and the governed agent must not be able to silently disable its own guardrail.
**Reuse:** `verifier` chain for tamper-evidence; daemon already does 0600 socket.

- [x] `docs/daemon-threat-model.md`: assets, trust boundary, and what we defend vs explicitly don't (not an anti-malware sandbox — tamper-*evident*, not tamper-*proof*).
- [x] Hardening: `load_active_policy` refuses a **world-writable** policy/dir (falls back to no rules → default-safe); the daemon logs `policy.changed` / `policy.rejected` to a hash-chained `policy-events.jsonl`; the cache signature includes file mode so a `chmod` is caught too; socket stays `0600`.

**Test:** `test_daemon_hardening.py` (6) — world-writable policy refused; a policy change emits a `policy.changed` event that `verify_event_chain` validates; a world-writable file emits `policy.rejected`; socket is `0600`.

---

## P0.7 — Redaction-before-sync ✅

**Goal:** guarantee secrets are stripped *before* any event could leave the machine — a trust requirement and a selling point.
**Reuse:** `events.redact_secrets` (key-based) + `sensitive.looks_secret_token` / `looks_secret_path` (path/token-based) — combine, don't invent.

- [x] Masking moved to **write time** (`mask_secret_material` in `normalize_event`) so secrets never enter the hashed log; `redact_for_sync` re-runs it as an idempotent, hash-stable fail-safe (so the mirror can still verify the chain).
- [x] Masks inline material (Bearer / `sk-` / `AKIA` / `gh*_` / `xox` tokens, PEM private keys); **keeps** sensitive paths (`.env`, `id_rsa`) — they're the audit signal, not the secret.

**Test:** `test_redaction.py` (7) — tokens, AWS keys, and PEM private keys are masked; secret-named keys stay structurally redacted; sensitive paths are preserved; `redact_for_sync` is a hash-stable no-op on a written event; masking is idempotent.

**Note:** deviated from the planned `looks_secret_token` reuse on purpose — that matches *paths*, but the leak risk in a sync payload is inline *material* (tokens/keys), so masking targets values, not filenames.

---

## Suggested execution order

`P0.0 ✅` → `P0.3` (freeze schema — unblocks everything, pure formalization) → `P0.7` (redaction — small, reuse-heavy, testable here) → `P0.4 stub` → `P0.6` (threat model + hardening) → `P0.2` (OS service — build here, validate on Mac) → `P0.5` (audit + doc). Each lands green before the next starts.
