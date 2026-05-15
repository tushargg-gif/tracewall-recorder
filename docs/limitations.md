# Limitations

AgentProof Recorder is early alpha.

## Current Limitations

- Evidence is stored locally under `.agentproof/`.
- Local evidence is tamper-evident, not tamper-proof.
- The CLI records commands only when they are run through `agentproof run --`.
- `agentproof shell` is currently a lightweight placeholder.
- Verification is heuristic and task-contract driven.
- The score is a review signal, not a model benchmark.
- MCP hostname validation does not perform DNS resolution.
- The sidecar is local-first and not a hosted dashboard.
- AgentProof Recorder complements CI; it does not replace CI.

## Known Product Boundaries

AgentProof Recorder is not:

- a coding agent
- an LLM framework
- a full sandbox
- a CI system
- an insurance product
- a guarantee of correctness

## Good Early-Alpha Use Cases

- local agent-run evidence capture
- bad-agent scenario testing
- task-contract experiments
- MCP proxy evidence capture
- pre-review trust reports

