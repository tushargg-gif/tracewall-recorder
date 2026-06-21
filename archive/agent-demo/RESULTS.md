# tracewall Orchestrator Demo Results

This is the latest publishable result from:

```bash
python3 agent-demo/master_agent_demo.py
```

This result comes from a scripted test harness, not a live LLM-agent run. The agents are deterministic Python classes. The tracewall Recorder behavior under test - evidence capture, event-chain integrity, attribution, verification, and report generation - is real.

## Result

```text
Harness status: PASS
Expected final decision: FAIL
tracewall verdict: Fail
Score: 70/100
Risk: high
Violating agent: Rogue Agent
Network evidence status: passed
```

## What This Proves

The demo is expected to fail the orchestrated agent run. That failure means tracewall caught the intentionally unsafe worker behavior.

- The scripted Master Agent selected the reusable `docs_only` policy template.
- The policy was automatically amended to let the Code Agent update `examples/**`.
- Five worker agents were registered, delegated, and recorded.
- The Rogue Agent claimed it changed no risky files.
- tracewall used actual before/after file evidence and attributed `package.json` to the Rogue Agent.
- The event hash chain passed.

## Detected Violations

- `no_forbidden_path_change`: `package.json` was forbidden.
- `no_unrelated_file_change`: `package.json` was outside the allowed docs/examples scope.
- `no_unapproved_dependency`: `package.json` is a dependency manifest.
- `worker_scope_exceeded`: Rogue Agent changed a file outside its worker scope.
- `worker_forbidden_path_change`: Rogue Agent changed a forbidden file.

## Published Evidence

- [policy.json](generated/policy.json)
- [events.jsonl](generated/events.jsonl)
- [tracewall_report.json](generated/tracewall_report.json)

The published JSON report is sanitized to use `agent-demo/.workspace` instead of machine-local absolute paths.
