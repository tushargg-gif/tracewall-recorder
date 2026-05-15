# Quickstart

This guide gets AgentProof Recorder running locally against a repository.

## Install

```bash
git clone https://github.com/tushargg-gif/AgentProof-Recorder
cd AgentProof-Recorder
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Check the CLI:

```bash
agentproof --help
agentproof-recorder --help
```

## Run The Basic Flow

```bash
agentproof init
agentproof start --agent "claude-code"
agentproof run -- pytest
agentproof stop --final-response "Fixed auth bug"
agentproof verify
agentproof report --print
```

This creates a local `.agentproof/` directory with run evidence, verification output, and reports.

## How To Use With A Coding Agent

1. Create or edit `.agentproof/task.yml`.
2. Start a run with `agentproof start`.
3. Use your coding agent normally.
4. Run important commands through `agentproof run -- <command>`.
5. Stop the run with the agent's final response.
6. Verify and print the report.

AgentProof Recorder complements CI. It gives reviewers a local evidence report before code review or merge.

## Useful Commands

```bash
agentproof init --force
agentproof start --agent "cursor"
agentproof run -- python -m pytest
agentproof event network.request --payload '{"url":"https://api.example.com/data"}'
agentproof stop --final-response "Done"
agentproof verify --json
agentproof report --print
```

## Sidecar Mode

For a master agent or orchestrator:

```bash
agentproof sidecar --host 127.0.0.1 --port 8797 --root .agentproof
```

Use auth if binding beyond localhost:

```bash
agentproof sidecar --host 0.0.0.0 --port 8797 --auth-token "$AGENTPROOF_TOKEN"
```

Read [mcp-proxy.md](mcp-proxy.md) for MCP proxying.

