# Examples

Example runs live under [../examples](../examples).

## Bad Agent Run

Path: [../examples/bad-agent-run](../examples/bad-agent-run)

Shows a run with forbidden path changes, missing evidence, and bad output.

Expected result:

```text
Verdict: Fail
Score: 55/100
Risk: high
```

## Good Agent Run

Path: [../examples/good-agent-run](../examples/good-agent-run)

Shows a narrow contract with allowed paths, expected tests, and a clean report.

Expected result:

```text
Verdict: Pass
Risk: low
```

## Root Bad-Agent Report

The root [../report.md](../report.md) file is kept as a simple launch proof that README references can render on GitHub.
