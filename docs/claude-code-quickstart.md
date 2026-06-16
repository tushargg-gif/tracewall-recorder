# AgentProof for Claude Code — install & smoke test

Put AgentProof in front of Claude Code so every tool call (bash, file reads,
web fetches, MCP) is recorded and gated — secret reads denied, risky actions
escalated to you, safe ones allowed — and the guardrail learns from your reviews.

Works the same in the **terminal CLI** and the **VS Code extension** (Claude Code
runs the same engine and reads the same `.claude/settings.json`).

---

## 1. Install AgentProof

```bash
pip install -e .          # from the agent-performance-monitor repo
agentproof --help         # confirm the CLI is on your PATH
```

## 2. Wire it into Claude Code (one command)

From the project you'll be working in:

```bash
agentproof init           # creates .agentproof/ (a starter task contract)
agentproof install-hook   # adds Pre/PostToolUse hooks to .claude/settings.json
```

`install-hook` merges into your existing `.claude/settings.json` (it won't clobber
other hooks). Use `--global` to install to `~/.claude/settings.json` for every
project.

Then **restart Claude Code** (or run `/hooks` inside it) so it loads the hook.

## 3. Smoke test (≈2 minutes)

Open Claude Code in this project and try these. You should see AgentProof act:

| Ask Claude Code to… | Expected |
|---|---|
| "read the `.env` file" | **Denied** — "Touches a secret/credential file… blocked by default." |
| "run `pip install requests`" | **Asks you** to approve (risky: installs a package) |
| "fetch https://example.com" | **Asks you** to approve (reaches the web) |
| "run `ls -la`" or "read README.md" | **Allowed** silently |

Then look at what was captured:

```bash
agentproof flow            # the ordered timeline, attributed to claude-code
agentproof review          # opens the allow/block review timeline in your browser
agentproof policy          # every rule currently in force
```

## 4. Teach it (policy by demonstration)

In `agentproof review`, mark anything you want stopped as **Block** (or approved as
**Allow**), then:

```bash
agentproof recommend --accept   # turns your verdicts into reusable rules
```

Now re-try the same action in Claude Code — what you blocked is **denied
automatically** next time, with your reason attached. The more you review, the
quieter it gets.

---

## How decisions are made (so there are no surprises)

1. **Your learned policy wins** — anything you've allowed/blocked is applied first.
2. Otherwise, **safe defaults**: deny secret-file reads; **ask** on installs, web
   calls, destructive commands, and consequential MCP tools; allow the rest.

No ML deciding "good vs bad" — a tiny deterministic denylist plus *your* decisions.

## Safety / troubleshooting

- **Fail-open:** if the hook ever errors, the action is **allowed** (with a note) —
  AgentProof can't brick your agent.
- **Hook not firing?** Restart Claude Code or run `/hooks`; confirm
  `.claude/settings.json` contains the `agentproof hook` commands; check `agentproof`
  is on the PATH Claude Code sees (the installer pins the absolute Python path).
- **Too chatty / too strict?** Review a run and accept rules — `ask` becomes
  `allow`/`deny` as you teach it. (A configurable default posture is on the roadmap.)
- **Remove it:** delete the AgentProof entries from `.claude/settings.json`.

## What this does and doesn't cover

- ✅ Claude Code (terminal + VS Code + JetBrains — same hook).
- ⛔ Codex / DeepSeek / Kimi — not yet (they need a different mechanism; planned).
- ⚠️ Validate on your machine before trusting it in anger: install, then confirm a
  real `.env` read is actually blocked end-to-end.
