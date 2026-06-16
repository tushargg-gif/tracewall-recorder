# AgentProof

<p align="center"><strong>A guardrail in front of your coding agent.</strong></p>

<p align="center">
  Every action your agent takes — reading files, running commands, web fetches,
  MCP/tool calls — passes through AgentProof first: recorded, risk-checked, and
  <strong>allowed, blocked, or escalated to you</strong>. It learns what's safe from
  your own allow/block decisions, so it gets quieter over time.
</p>

<p align="center">
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg"></a>
  <a href="pyproject.toml"><img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue.svg"></a>
</p>

<p align="center">
  <a href="docs/claude-code-quickstart.md">Claude Code Quickstart</a> &middot;
  <a href="docs/quickstart.md">Quickstart</a> &middot;
  <a href="vscode-extension/">VS Code extension</a> &middot;
  <a href="docs/north-star.md">North Star</a> &middot;
  <a href="docs/audit-control-plane.md">Design</a>
</p>

> **Early alpha.** The Claude Code integration works and is tested; it has been
> validated against Claude Code's documented hook contract. Validate it against
> your own setup before trusting it in anger (see the quickstart smoke test).

---

## The problem

Coding agents (Claude Code, Codex, …) read `.env` like it's a README, install
packages, web-search, and call MCP tools — autonomously. Nobody is going to audit
every command, file read, and tool call. You need a layer that lets the agent move
fast on the safe 90% and stops or escalates the rest.

## The 30-second version (Claude Code)

```bash
pip install -e .          # from this repo
agentproof init           # creates .agentproof/ in your project
agentproof install-hook   # wires AgentProof into .claude/settings.json
```

Restart Claude Code (terminal **or** VS Code — same engine). Now, with no further
configuration:

| The agent tries to… | AgentProof |
|---|---|
| read `.env` / `*.pem` | **denies** it |
| `pip install …`, fetch a URL, `rm -rf …`, a consequential MCP tool | **asks you** first |
| `ls`, read `README.md`, list issues | **allows** it silently |

Full walkthrough + smoke test: **[docs/claude-code-quickstart.md](docs/claude-code-quickstart.md)**.

## How it works

AgentProof is the **gateway** the agent's actions flow through. As a Claude Code
`PreToolUse` hook it sees every tool call (Bash, Read/Write, WebSearch/WebFetch,
MCP) — the file path, the command, the args — *before* it runs, and returns
**allow / ask / deny**.

Decisions, in order:

1. **Your learned policy wins** — anything you've allowed or blocked is applied first.
2. Otherwise **safe defaults**: deny secret-file reads; ask on the genuinely risky;
   allow the safe majority. No ML deciding "good vs bad" — a tiny deterministic
   denylist plus *your* decisions.

Everything is recorded to a tamper-evident, hash-chained log, **attributed to the
agent**, including blocked attempts.

## The loop — policy by demonstration

```
record  →  review  →  learn  →  enforce  →  catch it next time
(gateway   (allow/    (rules    (observe→
 captures)  block      with      alert→
            timeline)  reasons)  block)
```

You never hand-write policy. Review a run, mark **allow/block**, and AgentProof
drafts reusable rules *with reasons* — so the next time, what you blocked is denied
automatically. The more you review, the more autonomy the agent earns, safely.

Rules are **precise**: blocking `cat .env` learns "block reading secret files
(.env, *.pem, …)", not "ban the `cat` binary" — so legitimate `cat README.md`
still works.

## CLI

```bash
agentproof install-hook        # install the Claude Code hook (Pre/PostToolUse)
agentproof hook                # the hook entrypoint (Claude Code calls this)

agentproof flow                # the captured action timeline, attributed to the agent
agentproof review              # allow/block review (browser); --json / --export also
agentproof recommend --accept  # turn your verdicts into active policy
agentproof policy              # every rule in force, in one place

agentproof verify              # check a run against its task contract
agentproof report --print      # markdown / json trust report
```

Also available: `init`, `start`, `run -- <cmd>`, `event`, `stop`, `verdict`,
`mcp stdio` (proxy an MCP server), and the `Gateway` library for orchestrating
agents directly.

## VS Code

A panel to review and govern the agent's actions inside the editor — timeline,
allow/block, policy view, and one-click hook install. See
[`vscode-extension/`](vscode-extension/).

## What it covers (and doesn't)

- ✅ **Claude Code** — terminal CLI, VS Code extension, JetBrains (one hook covers all).
- ⛔ **Codex / DeepSeek / Kimi** — not yet; they need a different mechanism (planned).
- 🛟 **Fail-open** — if the hook errors, the action is allowed (with a note); AgentProof can't brick your agent.
- ⚠️ It's a guardrail against careless/unintended actions, **not** a containment
  boundary for a fully attacker-controlled agent.

## Repository layout

```text
src/agentproof/        Python package (gateway, hook, policy engine, review, recommender).
vscode-extension/      VS Code review panel (TypeScript).
tests/                 Automated tests.
docs/                  Quickstarts, North Star, design doc, security model.
archive/               Parked experiments. Not part of the package.
.agentproof/           Per-project runtime: runs, policy.json, verdicts. Created by the CLI.
```

## Status

Alpha, Mac-first, intent-layer (it governs what the agent *does* through brokered
tools; the OS-level "ground truth" layer is future work). The record → review →
learn → enforce loop works end to end, including against a real LLM agent under live
enforcement. See [docs/north-star.md](docs/north-star.md) for where this is going and
[docs/audit-control-plane.md](docs/audit-control-plane.md) for the architecture.

## License

Apache-2.0. See [LICENSE](LICENSE).
