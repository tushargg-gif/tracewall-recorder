# MCP Blocked Tool

This example shows a master agent or orchestrator calling a forbidden MCP tool through the tracewall Recorder proxy.

The proxy records the attempted call, applies policy, and returns a JSON-RPC error instead of forwarding the dangerous tool call.

Files:

- [contract.yaml](contract.yaml)
- [report.md](report.md)

