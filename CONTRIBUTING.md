# Contributing

Thanks for considering a contribution to AgentProof Recorder.

This project is early alpha. The best contributions are focused, testable, and directly related to evidence capture, verification, reporting, or documentation.

## Development Setup

```bash
git clone https://github.com/tushargg-gif/AgentProof-Recorder
cd AgentProof-Recorder
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

## Compatibility Rules

Do not break these without a clear migration plan:

- Python import package: `agentproof`
- CLI command: `agentproof`
- CLI alias: `agentproof-recorder`
- local storage directory: `.agentproof`

## Pull Request Checklist

- Keep changes scoped.
- Add tests for behavior changes.
- Update docs when the user-facing workflow changes.
- Avoid unsupported production-grade claims.
- Use "tamper-evident" for local evidence, not "tamper-proof".
- Run `pytest` before opening the PR.

## Good First Contributions

- Add verifier checks for common failure modes.
- Add sanitized bad-agent cases under `examples/`.
- Improve report wording or structure.
- Add docs for real-world task contracts.
- Add tests around MCP policy decisions.

## Reporting Bad-Agent Cases

Use the bad-agent issue template when an agent failure should be detectable. Include:

- task prompt or summary
- task contract, if available
- changed files or sanitized diff
- commands or MCP/tool calls
- expected detection

Do not include secrets, proprietary code, customer data, or private logs.

