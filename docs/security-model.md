# Security Model

Tracewall Recorder is local early alpha developer tooling. Its security model is intentionally modest.

## What It Protects Against

Tracewall Recorder helps detect:

- agents touching forbidden paths
- secret-like file changes
- unapproved dependency changes
- unsafe MCP tool calls
- MCP HTTP proxy targets pointing at local/private networks
- secret-like values in evidence payloads
- local event-log tampering after events are written

## What It Does Not Protect Against

Tracewall Recorder does not make local agents tamper-proof.

It does not prevent a user or process with write access from deleting or rewriting `.tracewall/`.

It does not replace:

- OS sandboxing
- container isolation
- CI
- code review
- secret management
- endpoint security
- repository branch protection

## Real-Time Enforcement (Optional)

By default Tracewall Recorder is observe-only: it *flags* sensitive-file access
after the fact (`action_taken="flagged"`). With `--enforce` it also *prevents* it
in real time (`action_taken="blocked"`):

```bash
tracewall start --agent claude-code --enforce
```

In enforce mode, every command recorded with `tracewall run` is launched inside
an OS sandbox that denies **read, write, and delete** on sensitive paths
(`tracewall.sensitive.SECRET_PATTERNS`: `.env`, `*.pem`, `*.key`, `id_rsa`,
`credentials`, `secrets/`, …). Because Tracewall launches the agent, it confines
the **process tree it spawns** — no kernel driver, EDR, or elevated privilege.

Backends:

- **macOS** — `sandbox-exec` (Seatbelt). Denies with `EPERM`. Verified.
- **Linux** — `bubblewrap`. Masks sensitive paths in a mount namespace. **Authored
  but not yet verified on a Linux host**; a masked file reads as *empty* rather
  than raising `EPERM`, and masks are enumerated at launch (files created later
  that match a pattern are not covered). A Landlock/LD_PRELOAD backend is planned
  to restore `EPERM` + pattern coverage.

Each decision is recorded as an `enforcement_decision` event in the hash-chained
log, so prevention is itself auditable.

Honest limits:

- **Fail-closed.** If no sandbox backend is available, recorded commands refuse to
  run rather than run unprotected.
- This is a **guardrail against accidental or rogue access, not a containment
  boundary** for an attacker who fully controls the agent binary.
- It confines processes Tracewall spawns (the agent and its children), not
  pre-existing processes.

## Evidence Integrity

Event evidence is append-only JSONL with hash chaining. Verification checks the chain to detect edits.

This is tamper-evident local evidence, not tamper-proof storage.

## Secret Redaction

Tracewall Recorder redacts common sensitive fields before writing evidence, including:

- authorization
- api_key
- token
- password
- secret
- cookie

Do not intentionally pass secrets into reports or issue templates.

