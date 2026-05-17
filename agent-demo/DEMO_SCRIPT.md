# 2-Minute Screen Recording Script

## Terminal Commands

```bash
git clone https://github.com/tushargg-gif/AgentProof-Recorder
cd AgentProof-Recorder
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python3 agent-demo/master_agent_demo.py --demo
```

For a shorter retake after setup:

```bash
python3 agent-demo/master_agent_demo.py --demo
```

## Voiceover

**0:00-0:15**

"This is AgentProof Recorder. It gives a master agent an evidence layer while it delegates work to smaller agents."

**0:15-0:35**

"The Master Agent reads the local repo context, selects a docs-only policy, and starts an AgentProof run."

**0:35-0:55**

"Each worker gets a narrow scope. Product can write docs, Copywriter can edit the README, Code can update examples after a logged policy amendment, and the Test Agent can run one exact command."

**0:55-1:20**

"The safe workers finish inside their scopes. Then the Rogue Agent claims it changed no risky files, but secretly writes package.json."

**1:20-1:45**

"AgentProof does not trust the claim. It verifies actual before-and-after file evidence, sees package.json, and attributes the violation to the Rogue Agent."

**1:45-2:00**

"The final decision is Fail. That is the correct result: AgentProof caught a forbidden dependency-file change before review or merge."

## Key Moments To Zoom In On

- Step 2: `docs_only` policy selection.
- Step 4: worker scopes.
- Step 6: Rogue Agent reports no files but changes `package.json`.
- Step 8: final summary with verdict, score, risk, violating agent, and evidence files.

## Expected Final Screen

```text
Summary
  Verdict: Fail
  Score: 70/100
  Risk: high
  Violating agent: Rogue Agent
  File changed: package.json

Harness status: PASS
```
