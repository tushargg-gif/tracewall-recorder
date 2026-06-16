# Archive — parked experiments

These modules were built during early exploration but sit **outside the core
record → verify → report spine**. They are kept here (not deleted) so the history
and ideas survive, but they are **not part of the `agentproof` package** and are
not imported, installed, or tested.

## What's here and why it was parked

| Path | What it was | Why parked |
| --- | --- | --- |
| `src/plugins.py` | ~1,000-line grab-bag of verifier checks: CSV/JSON/row-count/artifact/media (incl. JPEG byte parsing), network, browser, worker-scope, MCP | Verifying data artifacts is a different product from "did the agent touch a forbidden file." Biggest single source of scope creep. |
| `src/sidecar.py` | FastAPI HTTP sidecar service with bearer auth | A networked service for a local single-user CLI. Premature; pulled in fastapi/uvicorn/httpx. |
| `src/mcp_stdio.py`, `src/mcp_policy.py`, `src/mcp_targets.py` | MCP stdio + HTTP proxy with SSRF guards | Proxy/orchestration concern, not core evidence capture. |
| `src/orchestration.py` | Master-agent / worker delegation + attribution | Multi-agent orchestration is a separate product from single-run verification. |
| `agent-demo/` | Scripted "Rogue Agent" master/worker demo | Showcases `orchestration`, which is parked. |
| `agents-test/` | OpenAI Agents SDK experiments | Throwaway scratch; depends on external `agents` package. |
| `tools/knowledge_graph.py` + `knowledge-graph/` | AST-based self-documentation graph + interactive HTML viewer | Gold-plating: 600+ lines to document a ~2k-LOC package. |
| `docs/mcp-proxy.md`, `examples-mcp-blocked-tool/` | Docs/examples for the MCP proxy | Document parked features. |
| `tests/` | Tests for all of the above | Test parked code. |

## Restoring something

Everything is preserved in git history. To bring a module back:

```bash
git mv archive/src/<module>.py src/agentproof/<module>.py
# re-add its import wiring (verifier.py / cli.py) and its test, then add deps back
```

Removing these took the package from ~6,600 LOC to its core, and from four
third-party dependencies down to one (PyYAML).
