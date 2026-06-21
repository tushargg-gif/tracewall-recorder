# tracewall for VS Code

A panel to **review and govern your coding agent's actions** without leaving the
editor. It shows the timeline tracewall captured (attributed to the agent,
risk-flagged), lets you **Allow / Block** each action, shows **what the active
policy already blocks**, and turns your reviews into reusable rules.

It's a thin UI over the `tracewall` CLI — the extension shells out to it, so all
the logic (recording, risk analysis, policy) lives in one place.

## Prerequisites

- The **`tracewall` CLI** installed and on your PATH (`pip install -e .` from the
  main repo; verify with `tracewall --help`). If it isn't on PATH, set
  `tracewall.cliPath` in VS Code settings to its absolute path.
- For live capture, install the Claude Code hook (command: **tracewall: Install
  Claude Code Hook**, or `tracewall install-hook`) — see `docs/claude-code-quickstart.md`.

## Run it (development)

```bash
cd vscode-extension
npm install
npm run compile
```

Then open this `vscode-extension` folder in VS Code and press **F5** — that launches
an *Extension Development Host* window with tracewall loaded. Open a project that
has a `.tracewall/` directory (i.e. one you've used Claude Code in) and run the
commands below.

## Package it (to share / install)

```bash
npm install -g @vscode/vsce
vsce package          # produces tracewall-vscode-0.1.0.vsix
# In VS Code: Extensions → ⋯ → "Install from VSIX…"
```

## Commands (Cmd/Ctrl-Shift-P)

| Command | What it does |
|---|---|
| **tracewall: Review Latest Run** | Opens the review panel — timeline + Allow/Block + policy coverage |
| **tracewall: View Active Policy** | Lists every rule currently in force |
| **tracewall: Install Claude Code Hook** | Wires tracewall into `.claude/settings.json` |
| **tracewall: Learn Policy from Reviews** | Turns your Allow/Block verdicts into rules |

There's also a **`$(shield) tracewall`** status-bar button that opens the review panel.

## How it works

- The panel calls `tracewall review --json` to render the run, and
  `tracewall verdict --seq N --decision allow|block` when you click — so your
  decisions persist exactly as they would from the CLI or browser review.
- "Learn policy from my reviews" runs `tracewall recommend --accept`.

## Status

Early. The extension is a viewer/approver over captured runs; the real-time
allow/deny/**ask** prompts still surface through Claude Code's own permission UI
(driven by the `tracewall hook`). A native in-editor approval flow is future work.
