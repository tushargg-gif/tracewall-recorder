from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from tracewall.enforce import accept_rules, load_active_policy, policy_summary, render_policy
from tracewall.review import render_policy_html


ROOT = Path(__file__).resolve().parents[1]
RULES = [
    {"id": "block_cmd_env", "decision": "block", "match": {"kind": "command", "binary": "env"}, "reason": "secrets"},
    {"id": "block_tool_send_email", "decision": "block", "match": {"kind": "tool_call", "tool": "send_email"}, "reason": "mass email"},
    {"id": "allow_cmd_echo", "decision": "allow", "match": {"kind": "command", "binary": "echo"}, "reason": "safe"},
]


def test_accept_stamps_added_at_and_source_run(tmp_path: Path):
    d = tmp_path / ".tracewall"; d.mkdir()
    accept_rules(d, RULES, source_run="run_abc")
    rules = {r["id"]: r for r in load_active_policy(d)["rules"]}
    assert rules["block_cmd_env"]["added_at"]
    assert rules["block_cmd_env"]["source_run"] == "run_abc"


def test_policy_summary_counts(tmp_path: Path):
    d = tmp_path / ".tracewall"; d.mkdir()
    accept_rules(d, RULES)
    s = policy_summary(load_active_policy(d))
    assert s == {"rules": 3, "blocks": 2, "allows": 1, "commands": 2, "tools": 1}


def test_render_policy_and_html(tmp_path: Path):
    d = tmp_path / ".tracewall"; d.mkdir()
    policy = accept_rules(d, RULES)
    text = render_policy(policy)
    assert "send_email" in text and "BLOCK" in text and "ALLOW" in text
    html = render_policy_html(policy)
    assert "Active Policy" in html and "send_email" in html


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy(); env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, "-m", "tracewall", *args], cwd=cwd, text=True, capture_output=True, env=env, check=False)


def test_cli_policy_lists_rules(tmp_path: Path):
    assert _cli(tmp_path, "init").returncode == 0
    accept_rules(tmp_path / ".tracewall", RULES)
    out = _cli(tmp_path, "policy", "--json")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["summary"]["blocks"] == 2
    assert {r["id"] for r in data["rules"]} == {r["id"] for r in RULES}
