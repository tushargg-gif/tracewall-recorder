# Security Model

AgentProof Recorder is local early alpha developer tooling. Its security model is intentionally modest.

## What It Protects Against

AgentProof Recorder helps detect:

- agents touching forbidden paths
- secret-like file changes
- unapproved dependency changes
- unsafe MCP tool calls
- MCP HTTP proxy targets pointing at local/private networks
- secret-like values in evidence payloads
- local event-log tampering after events are written

## What It Does Not Protect Against

AgentProof Recorder does not make local agents tamper-proof.

It does not prevent a user or process with write access from deleting or rewriting `.agentproof/`.

It does not replace:

- OS sandboxing
- container isolation
- CI
- code review
- secret management
- endpoint security
- repository branch protection

## Sidecar Auth

The sidecar supports optional bearer-token auth:

```bash
agentproof sidecar --auth-token "$AGENTPROOF_TOKEN"
```

When a token is set, every endpoint except `/health` requires:

```text
Authorization: Bearer <token>
```

A warning is printed if the sidecar binds to `0.0.0.0` without auth.

## Evidence Integrity

Event evidence is append-only JSONL with hash chaining. Verification checks the chain to detect edits.

This is tamper-evident local evidence, not tamper-proof storage.

## Secret Redaction

AgentProof Recorder redacts common sensitive fields before writing evidence, including:

- authorization
- api_key
- token
- password
- secret
- cookie

Do not intentionally pass secrets into reports or issue templates.

