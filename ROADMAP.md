# Roadmap

> **The detailed, prioritized build plan now lives in [`docs/roadmap.md`](docs/roadmap.md)** —
> the daemon + control-plane + clients architecture, in priority order (P0→P3) with the
> strategic "more-than-a-product" track. The section below is the original alpha-spine
> roadmap, kept for context; `docs/roadmap.md` supersedes its forward-looking items.

AgentProof Recorder is early alpha. The roadmap is intentionally focused on local evidence capture and verification before broader platform work.

The package is the **record → verify → report** spine plus opt-in enforcement.
Broader experiments (sidecar, MCP proxy, orchestration, data-artifact checks,
knowledge graph) have been moved to [`archive/`](archive/README.md); they can be
restored if a clear need emerges.

## Now

- Keep the CLI stable: `agentproof`
- Keep import compatibility: `agentproof`
- Improve task-contract defaults
- Expand bad-agent examples
- Improve report readability

## Near Term

- GitHub Action examples for pull request reports
- Signed run manifests
- Better JSON report schema documentation

## Later

- VS Code extension prototype
- Team dashboard experiments
- Agent reliability history
- Policy templates for different repo types
- Reconsider archived features (sidecar / MCP proxy / orchestration) only with a concrete use case

## Not Planned For Early Alpha

- Building a coding agent
- Replacing CI
- Replacing code review
- Providing insurance coverage
- Claiming tamper-proof local storage

