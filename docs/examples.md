# Examples

Example runs live under [../examples](../examples).

## Bad Agent Run

Path: [../examples/bad-agent-run](../examples/bad-agent-run)

Shows a run with forbidden path changes, missing evidence, bad output, and MCP/tool risk.

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

## MCP Blocked Tool

Path: [../examples/mcp-blocked-tool](../examples/mcp-blocked-tool)

Shows an MCP policy blocking a forbidden tool call.

Expected result:

```text
MCP blocked: yes
JSON-RPC error: -32001
```

## Root Bad-Agent Report

The root [../report.md](../report.md) file is kept as a simple launch proof that README references can render on GitHub.
