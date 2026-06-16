# AgentProof for VS Code

A panel to **review and govern your coding agent's actions** without leaving the
editor. It shows the timeline AgentProof captured (attributed to the agent,
risk-flagged), lets you **Allow / Block** each action, shows **what the active
policy already blocks**, and turns your reviews into reusable rules.

It's a thin UI over the `agentproof` CLI — the extension shells out to it, so all
the logic (recording, risk analysis, policy) lives in one place.

## Prerequisites

- The **`agentproof` CLI** installed and on your PATH (`pip install -e .` from the
  main repo; verify with `agentproof --help`). If it isn't on PATH, set
  `agentproof.cliPath` in VS Code settings to its absolute path.
- For live capture, install the Claude Code hook (command: **AgentProof: Install
  Claude Code Hook**, or `agentproof install-hook`) — see `docs/claude-code-quickstart.md`.

## Run it (development)

```bash
cd vscode-extension
npm install
npm run compile
```

Then open this `vscode-extension` folder in VS Code and press **F5** — that launches
an *Extension Development Host* window with AgentProof loaded. Open a project that
has a `.agentproof/` directory (i.e. one you've used Claude Code in) and run the
commands below.

## Package it (to share / install)

```bash
npm install -g @vscode/vsce
vsce package          # produces agentproof-vscode-0.1.0.vsix
# In VS Code: Extensions → ⋯ → "Install from VSIX…"
```

## Commands (Cmd/Ctrl-Shift-P)

| Command | What it does |
|---|---|
| **AgentProof: Review Latest Run** | Opens the review panel — timeline + Allow/Block + policy coverage |
| **AgentProof: View Active Policy** | Lists every rule currently in force |
| **AgentProof: Install Claude Code Hook** | Wires AgentProof into `.claude/settings.json` |
| **AgentProof: Learn Policy from Reviews** | Turns your Allow/Block verdicts into rules |

There's also a **`$(shield) AgentProof`** status-bar button that opens the review panel.

## How it works

- The panel calls `agentproof review --json` to render the run, and
  `agentproof verdict --seq N --decision allow|block` when you click — so your
  decisions persist exactly as they would from the CLI or browser review.
- "Learn policy from my reviews" runs `agentproof recommend --accept`.

## Status

Early. The extension is a viewer/approver over captured runs; the real-time
allow/deny/**ask** prompts still surface through Claude Code's own permission UI
(driven by the `agentproof hook`). A native in-editor approval flow is future work.
