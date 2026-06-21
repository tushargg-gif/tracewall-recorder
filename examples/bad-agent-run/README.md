# Bad Agent Run

This example shows the type of run tracewall Recorder should flag before review or merge.

The agent appears to finish the task, but the evidence shows:

- forbidden file changes
- unrelated changes
- secret-like file changes
- bad data output
- forbidden or insecure network activity
- forbidden MCP tool call

Files:

- [contract.yaml](contract.yaml)
- [report.md](report.md)
- [evidence-snippet.jsonl](evidence-snippet.jsonl)

Expected result:

```text
Verdict: Fail
Score: 55/100
Risk: high
```

