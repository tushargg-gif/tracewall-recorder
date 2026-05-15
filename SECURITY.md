# Security Policy

AgentProof Recorder is early alpha local developer tooling. Please report security issues carefully.

## Supported Versions

Only the current `main` branch is actively maintained at this stage.

## Reporting A Vulnerability

Do not open a public GitHub issue for vulnerabilities.

Email the maintainer listed in [pyproject.toml](pyproject.toml), or open a private security advisory if GitHub enables that option for this repository.

Include:

- affected commit or version
- reproduction steps
- expected impact
- whether secrets, local files, or network access are involved
- any suggested fix

## Scope

Security-sensitive areas include:

- sidecar HTTP API auth
- MCP proxy forwarding
- secret redaction
- file path handling
- event-log integrity checks
- report generation from local evidence

## Current Security Model

AgentProof Recorder creates tamper-evident local evidence. It does not claim tamper-proof storage. A user or process with write access to the working directory can still alter local files.

For details, read [docs/security-model.md](docs/security-model.md).
