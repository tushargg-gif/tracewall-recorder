# AgentProof

AgentProof is a developer-first verification layer for agent work. It records an agent run, checks the work against a task contract, detects policy violations, scores reliability, and generates local audit evidence.

## MVP CLI

```bash
agentproof init
agentproof start --agent "claude-code"
agentproof run -- pytest
agentproof event network.request --payload '{"url":"https://api.example.com/data","status_code":200}'
agentproof stop --final-response "Fixed the issue and added a regression test."
agentproof verify
agentproof report --print
```

The first version stores local run evidence under `.agentproof/`:

- task contracts
- run metadata
- filesystem snapshots
- git evidence when available
- wrapped command events
- universal agent events
- verification results
- Markdown and JSON reports

## Core Loop

AgentProof does not perform the coding work. Use Cursor, Claude Code, Codex, Windsurf, a terminal agent, or a human. AgentProof watches and verifies the work.

1. Define the task contract.
2. Start a run.
3. Use any agent.
4. Run commands through `agentproof run -- ...` when you want command evidence.
5. Record non-command events through `agentproof event ...` when the agent uses browsers, APIs, tools, or media generation.
6. Stop the run.
7. Verify and generate the report.

## Universal Events

AgentProof can now record events beyond coding commands:

```bash
agentproof event network.request --payload '{"url":"https://api.example.com/data"}'
agentproof event browser.navigate --payload '{"url":"https://example.com/done"}'
agentproof event browser.dom_snapshot --payload '{"text":"Success"}'
agentproof event artifact.created --payload '{"path":"outputs/hero.png","width":1024,"height":768}'
```

Useful event types include:

- `process.exec`
- `network.request`
- `browser.navigate`
- `browser.dom_snapshot`
- `artifact.created`
- `tool.call`
- `llm.call`
- `human.approval`

## Verifier Plugins

The verifier now supports multiple work types:

- coding: paths, tests, dependencies, secrets, large diffs
- script: required commands, forbidden command patterns, command duration
- data: CSV/JSON existence, schema, row/item counts
- artifact: file existence, size, hash, image dimensions, video metadata from events
- network: allowed domains, forbidden domains, HTTPS policy, request count
- browser: required visited domains, forbidden domains, final URL, final page text evidence

Example task contract additions:

```yaml
expected_data:
  - path: data/results.csv
    format: csv
    required_columns: [id, score]
    min_rows: 1

expected_artifacts:
  - path: outputs/hero.png
    type: image
    width: 1024
    height: 768
    min_size_bytes: 100

network_policy:
  allowed_domains: [api.example.com]
  forbidden_domains: [prod.example.com]
  require_https: true
  max_requests: 5

browser_policy:
  required_visited_domains: [example.com]
  forbidden_domains: [admin.example.com]
  expected_final_url: https://example.com/done
  required_final_text: [Success]

script_policy:
  required_commands:
    - python scripts/fetch_data.py
  forbidden_command_patterns:
    - curl *prod*
  max_command_duration_seconds: 30
```

## Orchestrator Sidecar

AgentProof can run as a local sidecar for a master agent or orchestration layer:

```bash
agentproof sidecar --host 127.0.0.1 --port 8797 --root .agentproof
```

The sidecar exposes:

```text
POST /v1/runs
POST /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/stop
POST /v1/runs/{run_id}/verify
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/report.md
GET  /v1/runs/{run_id}/report.json
GET  /v1/approvals/pending
POST /v1/approvals/{approval_id}/approve
POST /v1/approvals/{approval_id}/deny
POST /v1/mcp/proxies
POST /mcp/{proxy_id}
```

Create a run:

```bash
curl -X POST http://127.0.0.1:8797/v1/runs \
  -H 'content-type: application/json' \
  -d '{
    "agent": "master-agent",
    "orchestrator": "custom-orchestrator",
    "control_mode": "observe",
    "task_contract": {
      "task_id": "TASK-123",
      "title": "Fetch data and update report",
      "verification": {}
    }
  }'
```

Control modes:

- `observe`: forward actions and record policy violations
- `block_critical`: block critical MCP policy violations
- `approval_gates`: pause risky MCP actions until approval or timeout

## MCP Proxy

For a local stdio MCP server:

```bash
agentproof mcp stdio --run-id run_123 --server-name filesystem -- python mcp_server.py
```

For a Streamable HTTP MCP server, register a proxy through the sidecar:

```json
{
  "run_id": "run_123",
  "server_name": "remote-tools",
  "transport": "streamable_http",
  "target_url": "https://tools.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ..."
  }
}
```

AgentProof records MCP traffic as evidence:

- `mcp.initialize`
- `mcp.tools.list`
- `mcp.tool.call.started`
- `mcp.tool.call.finished`
- `mcp.resources.list`
- `mcp.resource.read`
- `mcp.prompts.list`
- `mcp.prompt.get`
- `mcp.error`
- `policy.decision`
- `approval.requested`
- `approval.approved`
- `approval.denied`

Sensitive fields such as `authorization`, `api_key`, `token`, `password`, `secret`, and `cookie` are redacted before evidence is written.

MCP policy options live under `mcp_policy`:

```yaml
mcp_policy:
  allowed_tool_names: [safe_tool]
  forbidden_tool_names: [delete_all]
  allowed_domains: [api.example.com]
  forbidden_domains: [prod.example.com]
  forbidden_resource_patterns:
    - secrets://*
  approval_required_tools: [pay_invoice]
  max_tool_call_duration_seconds: 30
  approval_timeout_seconds: 300
```

Raw evidence is append-only JSONL with hash chaining. SQLite indexes runs, events, checks, violations, approvals, MCP proxies, and artifacts for sidecar queries.

## Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```
