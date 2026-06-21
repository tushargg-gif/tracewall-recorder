from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from tracewall.enforce import (
    accept_rules,
    action_from_command,
    action_from_tool,
    enforced_outcome,
    evaluate_action,
    load_active_policy,
)


ROOT = Path(__file__).resolve().parents[1]

POLICY = {"rules": [
    {"id": "block_tool_send_email", "decision": "block", "match": {"kind": "tool_call", "tool": "send_email"}, "reason": "no email"},
    {"id": "block_cmd_curl", "decision": "block", "match": {"kind": "command", "binary": "curl"}, "reason": "no egress"},
    {"id": "allow_cmd_echo", "decision": "allow", "match": {"kind": "command", "binary": "echo"}, "reason": "safe"},
]}


def test_evaluate_matches_command_and_tool():
    assert evaluate_action(action_from_command("curl http://x"), POLICY)["decision"] == "block"
    assert evaluate_action(action_from_command("echo hi"), POLICY)["decision"] == "allow"
    assert evaluate_action(action_from_command("ls -la"), POLICY)["decision"] == "none"
    assert evaluate_action(action_from_tool("shell", "send_email"), POLICY)["decision"] == "block"
    assert evaluate_action(action_from_tool("github", "create_issue"), POLICY)["decision"] == "none"


def test_touches_secret_matches_target_not_binary():
    policy = {"rules": [
        {"id": "block_cmd_secret_read", "decision": "block",
         "match": {"kind": "command", "touches_secret": True}, "reason": "no secrets"},
    ]}
    # any tool reading a secret path is blocked
    assert evaluate_action(action_from_command("cat .env"), policy)["decision"] == "block"
    assert evaluate_action(action_from_command("less config/.env"), policy)["decision"] == "block"
    assert evaluate_action(action_from_command("cat secrets/prod.pem"), policy)["decision"] == "block"
    # but ordinary use of the same binary is NOT blocked — the fix
    assert evaluate_action(action_from_command("cat README.md"), policy)["decision"] == "none"
    assert evaluate_action(action_from_command("less notes.txt"), policy)["decision"] == "none"
    # false positives a real LLM run hit: '.env' is a substring of 'os.environ'
    assert evaluate_action(action_from_command("grep -rn os.environ app"), policy)["decision"] == "none"
    assert evaluate_action(action_from_command("python3 -c 'import os; os.environ'"), policy)["decision"] == "none"


def test_enforced_outcome_modes():
    assert enforced_outcome("block", "block") == "blocked"
    assert enforced_outcome("block", "alert") == "alerted"
    assert enforced_outcome("block", "observe") == "allowed"
    assert enforced_outcome("allow", "block") == "allowed"
    assert enforced_outcome("none", "block") == "allowed"


def test_accept_rules_merges_by_id(tmp_path: Path):
    d = tmp_path / ".tracewall"
    d.mkdir()
    accept_rules(d, [POLICY["rules"][0]])
    assert len(load_active_policy(d)["rules"]) == 1
    # re-accepting the same id does not duplicate; a new id adds
    accept_rules(d, [POLICY["rules"][0], POLICY["rules"][1]])
    ids = {r["id"] for r in load_active_policy(d)["rules"]}
    assert ids == {"block_tool_send_email", "block_cmd_curl"}


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "tracewall", *args],
        cwd=cwd, text=True, capture_output=True, env=env, check=False,
    )


def test_closed_loop_block_on_next_run(tmp_path: Path):
    # Run 1: the agent runs a command; human reviews and blocks it.
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    assert _cli(tmp_path, "run", "--", "python3", "-c", "pass").returncode == 0
    assert _cli(tmp_path, "stop", "--final-response", "done").returncode == 0

    from tracewall.flow import action_flow
    from tracewall.review import set_verdict
    run1 = json.loads(_cli(tmp_path, "flow", "--json").stdout)["run_id"]
    seq = next(a["seq"] for a in action_flow(run1, tmp_path)["actions"] if "python3" in a["title"])
    set_verdict(run1, seq, "block", cwd=tmp_path)

    # Recommend + accept -> active policy now blocks the python3 binary.
    accepted = _cli(tmp_path, "recommend", "--accept")
    assert accepted.returncode == 0
    assert "block_cmd_python3" in (tmp_path / ".tracewall" / "policy.json").read_text()

    # Run 2: the same command is now blocked in block mode; an unrelated echo still runs.
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    blocked = _cli(tmp_path, "run", "--policy-mode", "block", "--", "python3", "-c", "pass")
    assert blocked.returncode == 126
    assert "BLOCKED" in blocked.stderr
    allowed = _cli(tmp_path, "run", "--policy-mode", "block", "--", "echo", "safe")
    assert allowed.returncode == 0


def test_observe_mode_records_but_does_not_block(tmp_path: Path):
    assert _cli(tmp_path, "init").returncode == 0
    # block echo in the active policy directly
    accept_rules(tmp_path / ".tracewall",
                 [{"id": "block_cmd_echo", "decision": "block",
                   "match": {"kind": "command", "binary": "echo"}, "reason": "x"}])
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    # observe mode: command still runs (returncode 0) even though policy blocks it
    res = _cli(tmp_path, "run", "--policy-mode", "observe", "--", "echo", "hi")
    assert res.returncode == 0
