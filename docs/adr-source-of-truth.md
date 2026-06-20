# ADR-001 — The local hash-chained log is the source of truth

**Status:** Accepted · 2026-06-20
**Context:** P0.4 in [p0-execution-plan.md](p0-execution-plan.md). Decided as part of the daemon/control-plane flip ([roadmap.md](roadmap.md)).

## Decision

The **append-only, hash-chained JSONL event log on the developer's machine is authoritative.** The cloud control plane (P2) is a **mirror**: it ingests uploaded events and *re-verifies* the chain, but it is never the primary and never the writer. If the local log and the cloud ever disagree, the local log wins.

## Why

- **Trust + local-first.** AgentProof's promise is "runs fully local, no account required" (P0.5). A cloud-authoritative design contradicts that and makes the network a hard dependency for a guardrail that must work offline.
- **One source can't drift.** Two writers (local + cloud) means two truths that can diverge — the worst failure mode for an *audit* product. One authoritative writer, one chain, verified anywhere.
- **The chain already gives us portability.** Because every event carries `prev_event_hash` + `event_hash`, anyone holding the JSONL can verify it independently — the server gets integrity for free without owning the data.

## Consequences

- **Enacted now:** the redundant write-only sqlite mirror (`store.py`) was removed (P0.0). `recorder` writes the JSONL chain directly (`_write_event` / `_last_event_hash`); it is the only event store.
- **Cloud sync (P2)** is upload-and-verify: the server runs `verifier.verify_event_chain` on ingest and rejects a broken or forked chain. It stores a copy for team audit; it does not author events.
- **Redaction (P0.7)** happens at *write* time: `normalize_event` masks secret material before the event is hashed, so the local log never stores a raw credential and its hashes cover the redacted form. Sync uploads verbatim and the chain still verifies; `redact_for_sync` re-runs the same mask as an idempotent fail-safe. Sensitive *paths* (`.env`, `id_rsa`) are kept on purpose — they're the audit signal, not the secret.
- **Performance:** the chain tip is read from the JSONL tail per append (fine at per-run sizes). If it ever shows up hot, the daemon caches the tip in memory — an optimization, never a second source.

## Alternatives considered

- **Cloud-first / SaaS-authoritative.** Rejected: breaks offline use and the local-first promise; makes the vendor a custodian of every developer's command history by default.
- **Dual-write (sqlite + JSONL), sqlite for queries.** Rejected: that was the prior state — a second store nothing read, free to drift. If query performance is ever needed, build a *derived, disposable* index from the authoritative log, not a parallel writer.
