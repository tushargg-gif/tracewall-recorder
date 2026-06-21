# Daemon threat model (P0.6)

**Companion:** [security-model.md](security-model.md) · [adr-source-of-truth.md](adr-source-of-truth.md) · [p0-execution-plan.md](p0-execution-plan.md)
**Date:** 2026-06-20

The daemon (`tracewalld`) is privileged in one specific sense: it holds the active policy and mediates every agent action, so it decides what an agent is allowed to do. That makes it worth attacking. This document states what it defends, what it explicitly does not, and the concrete mitigations in code.

## Assets

1. **The active policy** (`.tracewall/policy.json`) — the allow/ask/block rules. If an attacker can edit it, they can grant an agent permissions a human never approved.
2. **The hash-chained event log** (`events.jsonl`, `policy-events.jsonl`) — the tamper-evident record of what happened. Its value is integrity: you can detect after-the-fact edits.
3. **The decision socket** (`~/.tracewall/daemon.sock`) — the channel the hook uses to ask "allow/ask/deny?". If another local user could talk to it or impersonate it, they could spoof decisions.

## Trust boundary

- **Trusted:** the developer who owns the machine and the `~/.tracewall` directory; the daemon process running as that user.
- **Untrusted:** the agent under governance (it may be buggy, prompt-injected, or pointed at a malicious repo) and any *other* local user account.

The core stance: **the agent is the thing we watch, not a partner.** It must not be able to silently widen its own permissions or erase its trail.

## What we defend against

| Threat | Mitigation | Where |
|---|---|---|
| Another local user edits the policy to add allow rules | Refuse to **trust** a world-writable policy file or directory — fall back to no rules (default-safe decisions), never honor a possibly-tampered allowlist | `enforce.load_active_policy` + `enforce.world_writable` |
| The agent silently changes policy to disable a block | The daemon records a **`policy.changed`** event (with before/after fingerprint) to a hash-chained `policy-events.jsonl` whenever it observes the policy change; a `chmod` to world-writable logs **`policy.rejected`** | `daemon.PolicyCache` + `recorder.record_policy_event` |
| After-the-fact edit of the audit log to hide an action | Every event carries `prev_event_hash`/`event_hash`; `verify_event_chain` detects any edit/reorder/truncation | `events.py` |
| Another local user reads or drives the decision socket | The UDS is created owner-only (`0600`) | `daemon._UDSServer` |
| A secret leaks into the synced/stored log | Secret material is masked at write, before hashing (P0.7) | `events.mask_secret_material` |

## What we explicitly do NOT defend against (non-goals)

Consistent with the north star: this is **not** an anti-malware sandbox or EDR.

- **A fully attacker-controlled agent vs. the kernel.** If the agent runs arbitrary native code as the user, it can ultimately bypass a user-space guardrail (kill the daemon, write events directly, etc.). Containing hostile code is OS-sandbox/EDR territory — different and harder. Our honest claim is *tamper-evident*, not *tamper-proof*: we make interference **detectable**, not impossible.
- **A compromised root / another root user.** Root can do anything; out of scope.
- **Confidentiality of the local log at rest.** We redact secrets, but the log itself is a normal user-readable file; protecting the disk is the OS's job.

## Honest limits

- World-writability is checked via the world-writable bit (`0o002`); a group-writable file on a shared-group setup is **not** flagged (avoids false positives on common dev machines) — documented, not silent.
- The daemon notices a policy change on the **next action after** the change (it's a watcher, not a kernel hook). Two edits within the same filesystem mtime granularity that also leave the mode unchanged could be coalesced — negligible for real edits seconds apart, noted for honesty.
- Tamper-evidence requires the daemon to be running for continuous policy-change logging; the `verify_event_chain` integrity guarantee holds regardless.
