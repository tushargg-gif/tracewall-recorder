# Master Agent Demo

This demo shows a local master-agent workflow using AgentProof Recorder as the evidence layer.

Important: this is a scripted test harness, not a live LLM-agent run. The Master Agent and workers are deterministic Python classes so the demo is reproducible. AgentProof Recorder's evidence capture, event chain, file attribution, verification, and report generation are real.

Run it from the repository root:

```bash
python3 agent-demo/master_agent_demo.py --demo
```

The scripted master agent will:

1. read the project README, docs, and examples
2. select the reusable `docs_only` policy template
3. start an AgentProof Recorder run
4. register five worker agents with scoped permissions
5. automatically amend the policy to let the Code Agent update examples
6. delegate work and record actual before/after file changes per worker
7. let the Rogue Agent attempt an unsafe `package.json` change while self-reporting no risky files
8. verify the run
9. assert AgentProof caught the expected violation

Generated files are written to:

```text
agent-demo/generated/
  README.md
  policy.json
  events.jsonl
  agentproof_report.json
```

The demo uses a throwaway workspace under `agent-demo/.workspace/`. That folder is ignored by git.

`scenario.json` contains the task, reusable policy template, and worker roster. The scripted Master Agent uses AgentProof orchestration helpers to build and amend policy, then exits successfully only when the expected Rogue Agent violation is detected.

The latest publishable result summary is in [RESULTS.md](RESULTS.md).

For a two-minute screen recording outline, use [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
