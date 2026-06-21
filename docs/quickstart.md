# Quickstart

Tracewall is a guardrail in front of your coding agent. This gets it running
locally. For the full Claude Code walkthrough + smoke test, see
[claude-code-quickstart.md](claude-code-quickstart.md).

## Install

```bash
git clone https://github.com/tushargg-gif/tracewall-Recorder
cd tracewall-Recorder
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
tracewall --help
```

## Put it in front of Claude Code (recommended)

From the project you'll work in:

```bash
tracewall init           # creates .tracewall/
tracewall install-hook   # adds Pre/PostToolUse hooks to .claude/settings.json
```

Restart Claude Code (terminal or VS Code). Every tool call now passes through
Tracewall. With zero further config it will:

- **deny** reads of secret files (`.env`, `*.pem`, …)
- **ask** you before installs, web fetches, destructive commands, and consequential MCP tools
- **allow** the safe majority

See what it captured:

```bash
tracewall flow            # the action timeline, attributed to the agent
tracewall review          # allow/block review (opens in your browser)
tracewall policy          # every rule currently in force
```

## Teach it (policy by demonstration)

In `tracewall review`, mark anything you want stopped as **Block** (or approved as
**Allow**), then:

```bash
tracewall recommend --accept   # turns your verdicts into reusable rules
```

Next time, what you blocked is **denied automatically**, with your reason attached.
`ask` becomes `deny`/`allow` as you teach it.

## How decisions are made

1. **Your learned policy wins** (anything you've allowed/blocked).
2. Otherwise **safe defaults**: deny secrets; ask on risky; allow the rest.

No ML deciding "good vs bad" — a small deterministic denylist plus *your* decisions.

## Orchestrating agents directly (library)

If you drive worker agents yourself, route their actions through the `Gateway` so
every action is recorded, attributed, and policy-checked by construction:

```python
from tracewall.gateway import Gateway
gw = Gateway(run_id, policy_mode="block")          # observe | alert | block
gw.command("worker-1", ["pytest", "-q"])           # recorded + gated
gw.tool_call("worker-1", "jira", "create_issue", {"title": "bug"})
```

## Verification & reports (optional)

```bash
tracewall verify --json     # check a run against its task contract
tracewall report --print    # markdown / json trust report
```

## Useful commands

```bash
tracewall install-hook --global     # install for every project (~/.claude)
tracewall review --export out.html  # static review page (shareable)
tracewall policy --export pol.html  # static policy page
tracewall verdict --seq 3 --decision block   # set a verdict from a script/editor
tracewall mcp stdio --run-id <id> --server-name jira -- <server cmd>
```
