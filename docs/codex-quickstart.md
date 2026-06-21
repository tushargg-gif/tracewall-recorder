# Tracewall for Codex — install & smoke test

Put Tracewall in front of OpenAI Codex. Codex's hook system is newer and narrower
than Claude Code's, so coverage is split across two mechanisms:

- **Hook** — gates Codex's **Bash** commands (deny `cat .env`, installs, destructive
  shell, …) and records them.
- **MCP proxy** — gates Codex's **MCP tool calls** (deny/allow per policy).

> **Honest limits (Codex hooks are experimental, 2026):** `PreToolUse` only
> intercepts **Bash** today — not the Read tool, WebSearch, or Write — and it can
> only **deny** (Codex's hook can't "ask"). Codex's own sandbox + approval policy
> covers the rest; the universal OS-level layer (any agent, any action) is future
> work. A model can also write a script and run it via Bash to dodge command
> matching — treat the hook as a strong guardrail, not an airtight boundary.

---

## 1. Install Tracewall

```bash
pip install -e .
tracewall --help
```

## 2. Install the Codex hook

From your project:

```bash
tracewall init
tracewall install-codex                 # ask-mode defer (default)
# or: tracewall install-codex --ask-mode deny
```

This writes `.codex/hooks.json` (PreToolUse/PostToolUse, matcher `Bash`) and enables
`codex_hooks = true` in `.codex/config.toml`. Use `--global` for `~/.codex`.

**ask-mode** (Codex hooks can't "ask"):

- `defer` *(default)* — Tracewall **denies** known-bad (secret reads); for risky-but-
  -ambiguous it allows and lets **Codex's own approval prompt** handle it. Least friction.
- `deny` — Tracewall **blocks** risky-ambiguous outright too. Strictest.

Restart Codex.

## 3. Gate Codex's MCP tool calls

For each MCP server in your Codex config, launch it **through** Tracewall instead of
directly. In `~/.codex/config.toml`:

```toml
# before:
# [mcp_servers.jira]
# command = "jira-mcp-server"

[mcp_servers.jira]
command = "tracewall"
args = ["mcp", "stdio", "--server-name", "jira", "--ask-mode", "defer", "--", "jira-mcp-server"]
```

Now every `jira` tool call is recorded and policy-checked; denied calls return a
JSON-RPC error to Codex with the reason.

## 4. Smoke test

In Codex, ask it to:

| Action | Expected |
|---|---|
| run `cat .env` | **denied** (secret) |
| `pip install …`, `rm -rf …` | denied (`--ask-mode deny`) or deferred to Codex's approval (`defer`) |
| `ls`, `cat README.md` (via Bash) | allowed |
| call a gated MCP tool you've blocked | **denied** with your reason |

Then review and teach it:

```bash
tracewall flow                  # the captured timeline (Bash + MCP), attributed to the agent
tracewall review                # allow/block, then:
tracewall recommend --accept    # your verdicts become rules; applied on the next run
tracewall policy                # every rule in force
```

## What's covered

| Surface | Covered? | How |
|---|---|---|
| Bash commands (incl. `cat .env`, installs) | ✅ | Codex hook (deny only) |
| MCP tool calls | ✅ | `tracewall mcp stdio` proxy (deny/allow) |
| Read tool / WebSearch / Write | ⛔ not yet | needs OS-level layer; Codex's sandbox limits these natively |
| "Ask"/escalate via the hook | ⛔ | Codex hooks can't ask — use `--ask-mode`, or rely on Codex's approval |

For the cleaner, broader integration today, see
[claude-code-quickstart.md](claude-code-quickstart.md).
