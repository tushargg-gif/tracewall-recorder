# Limitations

Tracewall Recorder is early alpha.

## Current Limitations

- Evidence is stored locally under `.tracewall/`.
- Local evidence is tamper-evident, not tamper-proof.
- The CLI records commands only when they are run through `tracewall run --`.
- Verification is heuristic and task-contract driven.
- The score is a review signal, not a model benchmark.
- Tracewall Recorder complements CI; it does not replace CI.

## Known Product Boundaries

Tracewall Recorder is not:

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
- pre-review trust reports

