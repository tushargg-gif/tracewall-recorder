# AgentProof Recorder

<p align="center"><strong>Tamper-evident evidence for AI agent work.</strong></p>

<p align="center">
  AgentProof Recorder verifies whether agents followed policy, even when an agent claims it did.
</p>

<p align="center">
  <a href="https://github.com/tushargg-gif/AgentProof-Recorder/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/tushargg-gif/AgentProof-Recorder/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg"></a>
  <a href="pyproject.toml"><img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue.svg"></a>
  <a href="https://github.com/tushargg-gif/AgentProof-Recorder/stargazers"><img alt="github stars" src="https://img.shields.io/github/stars/tushargg-gif/AgentProof-Recorder?style=social"></a>
</p>

<p align="center">
  <a href="https://raw.githubusercontent.com/tushargg-gif/AgentProof-Recorder/main/assets/demo.mp4">Demo Video</a> &middot;
  <a href="docs/quickstart.md">Docs</a> &middot;
  <a href="docs/quickstart.md">Quickstart</a> &middot;
  <a href="docs/examples.md">Examples</a> &middot;
  <a href="docs/security-model.md">Security Model</a> &middot;
  <a href="ROADMAP.md">Roadmap</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

AgentProof Recorder is a tamper-evident evidence layer for AI agent work. It records what agents actually did - file changes, commands, tests, policy decisions, MCP/tool calls, and final responses - then verifies that evidence against the task policy.

> Early alpha: AgentProof Recorder is designed for local experimentation, agent-run evidence capture, and verification workflows. It does not claim to make local agents tamper-proof.
>
> Demo note: the Rogue Agent demo uses scripted Python agents for reproducibility. It does not call an LLM to choose policy or perform work. The real test is AgentProof Recorder's evidence capture, tamper-evident event chain, attribution, verification, and report generation.

## Demo: Rogue Agent Caught

<p align="center">
  <a href="https://raw.githubusercontent.com/tushargg-gif/AgentProof-Recorder/main/assets/demo.mp4">
    <img src="assets/demo.gif" alt="AgentProof Recorder demo: Rogue Agent Caught">
  </a>
</p>

[Open the full MP4 demo](https://raw.githubusercontent.com/tushargg-gif/AgentProof-Recorder/main/assets/demo.mp4)

In the demo, a scripted Master Agent delegates documentation work to several scripted worker agents. Most workers stay inside their assigned scopes.

Then the Rogue Agent secretly changes `package.json`, while claiming no risky files changed. AgentProof checks the actual before-and-after file evidence, attributes `package.json` to the Rogue Agent, and returns:

```text
Final verdict: FAIL
Violating agent: Rogue Agent
Changed file: package.json
```

Run the same local demo:

```bash
python3 agent-demo/master_agent_demo.py --demo
```

Generated evidence:

- [agent-demo/generated/policy.json](agent-demo/generated/policy.json)
- [agent-demo/generated/events.jsonl](agent-demo/generated/events.jsonl)
- [agent-demo/generated/agentproof_report.json](agent-demo/generated/agentproof_report.json)

## Why This Matters

AI coding agents can claim success while:

- skipping required tests
- touching forbidden files
- modifying unrelated paths
- changing dependency files
- making unsafe tool calls
- producing output without evidence

The bottleneck is moving from writing code to verifying agent work. AgentProof Recorder gives reviewers local evidence before code moves into review or merge.

It does not replace CI, tests, or code review. It makes the handoff easier to inspect.

## What AgentProof Recorder Does

AgentProof Recorder records:

- file changes
- commands
- tests
- final response
- policy violations
- MCP/tool calls
- tamper-evident local event chain

Then it verifies the run against a task contract and generates a trust report.

```text
task contract -> agent run -> evidence capture -> verification -> trust report
```

## 60-Second Example

```bash
git clone https://github.com/tushargg-gif/AgentProof-Recorder
cd AgentProof-Recorder
pip install -e ".[dev]"

agentproof init
agentproof start --agent "claude-code"
agentproof run -- pytest
agentproof stop --final-response "Fixed auth bug"
agentproof verify
agentproof report --print
```

The package keeps the stable CLI command:

```bash
agentproof --help
```

It also installs the optional alias:

```bash
agentproof-recorder --help
```

## Example Report

```text
AgentProof Recorder Report

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

A bad-agent example report is available at [report.md](report.md), with structured examples under [examples/](examples/). The local orchestrator demo publishes a current test-harness result at [agent-demo/RESULTS.md](agent-demo/RESULTS.md).

## Core Concepts

**Task contract**

A YAML file that says what the agent is allowed to touch, which commands count as evidence, and what success means.

**Evidence recorder**

Local run capture for file changes, command executions, final responses, universal events, and MCP/tool activity.

**Verification engine**

Checks the recorded run against the task contract and produces pass, partial pass, or fail results.

**Trust report**

Markdown and JSON output that summarizes score, risk, policy violations, changed files, commands, and observed events.

## What It Can Catch Today

- forbidden path changes
- unrelated file changes
- secret-like file changes
- dependency file changes
- missing or failed test commands
- bad data or artifact outputs
- unsafe network/browser events
- forbidden MCP tools
- MCP targets that point at local/private networks
- local event-log tampering

## Local Sidecar And MCP Proxy

AgentProof Recorder can run as a local sidecar for a master agent or orchestrator:

```bash
agentproof sidecar --host 127.0.0.1 --port 8797 --root .agentproof
```

For sidecar APIs exposed beyond localhost, use an auth token:

```bash
agentproof sidecar --host 0.0.0.0 --port 8797 --auth-token "$AGENTPROOF_TOKEN"
```

MCP HTTP proxy targets are validated to reduce SSRF/local-network forwarding risk. You can also restrict proxy registration to known hosts:

```bash
agentproof sidecar --auth-token test --allowed-mcp-target-host mcp.example.com
```

Read more in [docs/mcp-proxy.md](docs/mcp-proxy.md) and [docs/security-model.md](docs/security-model.md).

## Documentation

- [Quickstart](docs/quickstart.md)
- [Task contracts](docs/task-contracts.md)
- [Verification model](docs/verification-model.md)
- [MCP proxy](docs/mcp-proxy.md)
- [Security model](docs/security-model.md)
- [Limitations](docs/limitations.md)
- [Examples](docs/examples.md)
- [Orchestrator demo results](agent-demo/RESULTS.md)

## Project Status

AgentProof Recorder is early alpha. The current focus is a useful local developer workflow:

- record coding-agent runs
- verify work against explicit task contracts
- produce evidence reports for human review
- support MCP proxy evidence capture for orchestrators

See [ROADMAP.md](ROADMAP.md) for planned work.

## Repository Layout

```text
src/agentproof/        Python package. Import name stays agentproof.
tests/                 Automated tests.
docs/                  User and contributor documentation.
examples/              Good, bad, and MCP-focused example runs.
agent-demo/            Orchestrator demo test harness and publishable evidence.
.github/               CI, issue templates, and PR template.
.agentproof/           Local runtime evidence directory, created by the CLI.
```

## What AgentProof Recorder Is Not

AgentProof Recorder is not:

- a coding agent
- a replacement for CI
- a replacement for code review
- a full sandbox
- a hosted observability platform
- an insurance product
- a guarantee that agent output is correct
- tamper-proof storage

It is a local evidence and verification layer for agent work.

## Contributing

Contributions are welcome while the project is still small and sharp. Good first areas:

- more verifier checks
- adversarial bad-agent examples
- report readability
- MCP policy coverage
- GitHub/GitLab workflow integrations
- docs and task-contract templates

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Security

Do not open a public issue for sensitive vulnerabilities. Read [SECURITY.md](SECURITY.md) for reporting guidance.

## License

Apache-2.0. See [LICENSE](LICENSE).
