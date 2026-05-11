# AgentProof

**AI coding agents say they are done. AgentProof checks.**

AgentProof is an open-source verification layer for AI agent work. It records what an agent did, checks the work against a task contract, detects policy violations, scores reliability, and generates local audit evidence before the work is trusted, reviewed, merged, or shipped.

You can use it with Cursor, Claude Code, Codex-style agents, Windsurf, terminal agents, MCP-based agents, or even human-assisted workflows.

AgentProof does not replace your coding agent.

It acts as the black-box recorder, verifier, and risk report around the agent run.

---

## Why AgentProof exists

AI agents are getting smarter fast, but agent reliability is still messy.

Common failure modes:

- The agent says it fixed the issue, but did not run the right tests.
- The agent changes unrelated files.
- The agent touches dependency files without approval.
- The agent modifies secret-like files.
- The agent uses a forbidden tool or command.
- The agent completes a browser/API workflow incorrectly.
- The agent produces an output, but no reliable evidence exists.

AgentProof turns agent work into a verifiable run:

```text
Task contract -> agent execution -> evidence capture -> verification -> reliability report
```

The goal is simple:

Do not trust an agent because it says "done." Trust the evidence.

---

## What AgentProof does

AgentProof helps answer five questions after an agent run:

1. What did the agent change?
2. What commands, tools, APIs, or browser actions did it perform?
3. Did it follow the task contract?
4. Did it violate policy?
5. Should a human trust, review, block, or rerun the work?

AgentProof currently supports:

- Local run recording
- Task contracts
- Git/file-system evidence
- Wrapped command execution
- Universal agent events
- Policy checks
- Verification plugins
- Reliability scoring
- Markdown and JSON reports
- Tamper-evident event chains
- Secret redaction
- MCP proxy evidence capture
- Local sidecar mode for orchestrators

---

## Quick demo

```bash
agentproof init
agentproof start --agent "claude-code"
agentproof run -- pytest
agentproof stop --final-response "Fixed the issue and added a regression test."
agentproof verify
agentproof report --print
```

Example report:

```text
AgentProof Report

Verdict: Partial Pass
Score: 82/100
Risk: medium

Files changed: 2
Commands recorded: 1
Tests detected: yes
Policy violations: 0
Event chain: passed
Secret redaction: passed

Recommendation:
Safe for human review. Do not auto-merge without checking the diff.
```

---

## Bad-agent E2E proof

AgentProof is designed to catch bad or careless agent behavior.

The repository includes a bad-agent E2E report at:

```text
report.md
```

The bad agent attempted actions such as:

- Forbidden file/path changes
- Unrelated file changes
- Secret-like file changes
- Invalid data/artifact output
- Forbidden or insecure network requests
- Wrong browser final state
- MCP forbidden tool calls
- Secret arguments passed into MCP tools

Fresh E2E result:

```text
Verdict: Fail
Score: 55/100
Risk: high
Policy violations: 18
Event chain: passed
Secret redaction: passed
MCP blocked: yes
MCP response: JSON-RPC error -32001
```

This is the core promise:

AgentProof does not just record agent work. It catches bad agent behavior.

---

## Core workflow

AgentProof follows a simple loop:

```text
1. Define the task contract
2. Start a run
3. Use any coding agent or automation tool
4. Record command/tool/browser/API evidence
5. Stop the run
6. Verify the work
7. Generate a report
```

AgentProof stores local evidence under `.agentproof/`:

```text
.agentproof/
  runs/
  reports/
  agentproof.sqlite3
```

Evidence can include:

- Task contract
- Run metadata
- File-system snapshots
- Git diff evidence
- Wrapped command events
- Universal events
- MCP events
- Verification results
- Policy violations
- Markdown report
- JSON report

---

## Installation

### Local development install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Current automated test coverage includes negative cases for:

- Forbidden paths
- Unrelated changes
- Secret-like files
- Dependency changes
- Unapproved commands
- Missing tests
- Bad CSV schema/count
- Wrong artifact dimensions
- Insecure network requests
- Wrong browser final state
- Event hash-chain tampering
- Secret redaction
- MCP forbidden tool blocking
- MCP approval timeout
- MCP observed policy violation scoring

---

## Basic usage

### 1. Initialize AgentProof

```bash
agentproof init
```

This creates the local `.agentproof/` workspace.

---

### 2. Define or edit the task contract

AgentProof uses a task contract to define what the agent is allowed to do and what success means.

Example:

```yaml
task_id: AUTH-142
title: Fix expired JWT refresh bug

allowed_paths:
  - src/auth/**
  - tests/auth/**

forbidden_paths:
  - .env
  - infra/**
  - secrets/**

allowed_commands:
  - pytest
  - pytest tests/auth

forbidden_actions:
  - access_secrets
  - modify_database_schema
  - install_new_package

success_criteria:
  - expired refresh token test added
  - auth test suite passes
  - no unrelated files changed
  - no new dependency added

verification:
  tests:
    - pytest tests/auth

risk_level: medium
human_approval_required: true
```

---

### 3. Start a run

```bash
agentproof start --agent "claude-code"
```

You can use any agent after the run starts.

Examples:

- Claude Code
- Cursor
- Codex-style terminal agents
- Windsurf
- Custom local agents
- MCP-based agents
- Human-assisted coding sessions

---

### 4. Record command evidence

Run verification-relevant commands through AgentProof:

```bash
agentproof run -- pytest
agentproof run -- npm test
agentproof run -- npm run lint
agentproof run -- python scripts/check_output.py
```

AgentProof records:

- Command
- Exit code
- Start/end time
- Duration
- stdout/stderr logs
- Failure status

---

### 5. Record non-command events

AgentProof can also record API, browser, tool, artifact, and LLM events.

```bash
agentproof event network.request --payload '{"url":"https://api.example.com/data","status_code":200}'
```

```bash
agentproof event browser.navigate --payload '{"url":"https://example.com/done"}'
```

```bash
agentproof event artifact.created --payload '{"path":"outputs/hero.png","width":1024,"height":768}'
```

Useful event types:

```text
process.exec
network.request
browser.navigate
browser.dom_snapshot
artifact.created
tool.call
llm.call
human.approval
mcp.tool.call.started
mcp.tool.call.finished
policy.decision
approval.requested
approval.approved
approval.denied
```

---

### 6. Stop the run

```bash
agentproof stop --final-response "Fixed the issue and added a regression test."
```

---

### 7. Verify the run

```bash
agentproof verify
```

AgentProof checks the run against the task contract and recorded evidence.

---

### 8. Generate report

```bash
agentproof report --print
```

Reports are available as Markdown and JSON.

---

## Verification checks

AgentProof currently verifies multiple work types.

### Coding verification

Checks include:

- Allowed path changes
- Forbidden path changes
- Unrelated file changes
- Secret-like file changes
- Dependency/package changes
- Test command evidence
- Missing required verification commands
- Failed command runs
- Large diffs
- Regression-test evidence

### Script verification

Checks include:

- Required commands
- Forbidden command patterns
- Command duration limits
- Failed command executions

### Data verification

Checks include:

- Expected CSV/JSON files
- Required columns
- Minimum row count
- Minimum item count
- Schema-style evidence

### Artifact verification

Checks include:

- Expected artifact existence
- Minimum file size
- Hash evidence
- Image width/height
- Video/image metadata from events

### Network verification

Checks include:

- Allowed domains
- Forbidden domains
- HTTPS requirement
- Maximum request count
- Insecure network calls

### Browser verification

Checks include:

- Required visited domains
- Forbidden domains
- Expected final URL
- Required final page text
- DOM snapshot evidence

### MCP verification

Checks include:

- Allowed/forbidden MCP tools
- Forbidden resource patterns
- Approval-required tools
- Tool-call timeout
- Policy decision events
- MCP error evidence
- Secret redaction

---

## Example policy sections

### Network policy

```yaml
network_policy:
  allowed_domains:
    - api.example.com
  forbidden_domains:
    - prod.example.com
  require_https: true
  max_requests: 5
```

### Browser policy

```yaml
browser_policy:
  required_visited_domains:
    - example.com
  forbidden_domains:
    - admin.example.com
  expected_final_url: https://example.com/done
  required_final_text:
    - Success
```

### Data artifact policy

```yaml
expected_data:
  - path: data/results.csv
    format: csv
    required_columns:
      - id
      - score
    min_rows: 1
```

### Image artifact policy

```yaml
expected_artifacts:
  - path: outputs/hero.png
    type: image
    width: 1024
    height: 768
    min_size_bytes: 100
```

### Script policy

```yaml
script_policy:
  required_commands:
    - python scripts/fetch_data.py
  forbidden_command_patterns:
    - curl *prod*
  max_command_duration_seconds: 30
```

### MCP policy

```yaml
mcp_policy:
  allowed_tool_names:
    - safe_tool
  forbidden_tool_names:
    - delete_all
  allowed_domains:
    - api.example.com
  forbidden_domains:
    - prod.example.com
  forbidden_resource_patterns:
    - secrets://*
  approval_required_tools:
    - pay_invoice
  max_tool_call_duration_seconds: 30
  approval_timeout_seconds: 300
```

---

## Local sidecar mode

AgentProof can run as a local sidecar for a master agent, orchestrator, or external automation system.

```bash
agentproof sidecar --host 127.0.0.1 --port 8797 --root .agentproof
```

The sidecar exposes local APIs for:

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

```text
observe          Record events and policy violations
block_critical   Block critical MCP policy violations
approval_gates   Pause risky MCP actions until approval or timeout
```

---

## MCP proxy

AgentProof can sit between an agent and MCP tools to record evidence and enforce policy.

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

```text
mcp.initialize
mcp.tools.list
mcp.tool.call.started
mcp.tool.call.finished
mcp.resources.list
mcp.resource.read
mcp.prompts.list
mcp.prompt.get
mcp.error
policy.decision
approval.requested
approval.approved
approval.denied
```

Sensitive fields are redacted before evidence is written.

Redacted fields include:

```text
authorization
api_key
token
password
secret
cookie
```

---

## Evidence integrity

AgentProof writes raw evidence as append-only JSONL with event hash chaining.

This helps detect event-log tampering during local verification.

AgentProof also stores a SQLite index for easier queries over:

- Runs
- Events
- Checks
- Violations
- Approvals
- MCP proxies
- Artifacts

Important note:

Local evidence is tamper-evident, not tamper-proof. For high-trust enterprise or marketplace use cases, remote notarization or signed external storage should be added.

---

## What AgentProof is not

AgentProof is not:

- A coding agent
- An LLM framework
- A replacement for tests
- A replacement for code review
- A security sandbox by itself
- A guarantee that agent output is correct
- An insurance product

AgentProof is an evidence and verification layer.

It helps teams decide whether agent work should be trusted, reviewed, blocked, rerun, or escalated.

---

## Roadmap

Near-term:

- Cleaner demo workflows
- `agentproof shell` for automatic command recording
- GitHub Action for PR verification
- Better report formatting
- More adversarial test cases
- VS Code extension prototype

Mid-term:

- Team dashboard
- Agent comparison
- Policy templates
- CI/CD integrations
- Cloud evidence sync
- Signed run manifests
- Remote evidence notarization

Long-term:

- Agent reliability history
- Agent reputation scoring
- Marketplace trust signals
- Reward/settlement evidence
- Insurance-readiness reports

---

## Use cases

AgentProof is useful for:

- Developers using AI coding agents
- Engineering teams reviewing agent-generated PRs
- Security teams governing autonomous tools
- AI-agent platforms that need execution evidence
- Agent marketplaces that need trust signals
- Enterprises adopting agentic workflows
- Researchers studying agent reliability failures

---

## Repository structure

```text
src/agentproof/     Core AgentProof package
tests/              Automated test suite
report.md           Example bad-agent report
.agentproof/        Local evidence workspace, created at runtime
```

---

## Contributing

AgentProof is early. Contributions are welcome, especially around:

- New verifier plugins
- Better scoring logic
- More adversarial test cases
- Agent integration examples
- GitHub/GitLab CI support
- VS Code integration
- MCP policy coverage
- Report design

Run the test suite before opening a PR:

```bash
pytest
```

---

## Suggested GitHub topics

To make this repository easier to discover, add topics such as:

```text
ai-agents
agentic-ai
ai-agent-security
agent-observability
agent-reliability
llm-agents
coding-agents
mcp
model-context-protocol
ai-devtools
agent-verification
software-testing
```

---

## License

Add a license before public launch.

Recommended options:

- Apache-2.0 if you want permissive enterprise-friendly adoption with patent protection.
- MIT if you want maximum simplicity.

---

## Status

AgentProof is an early-stage open-source project.

The current focus is narrow:

Make AI coding-agent work verifiable.

The broader vision:

Build the trust, verification, and risk layer for the agent economy.
