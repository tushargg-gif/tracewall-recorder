from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

from agentproof.enforce import accept_rules
from agentproof.flow import action_flow
from agentproof.gateway import Gateway


ROOT = Path(__file__).resolve().parents[1]


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy(); env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, "-m", "agentproof", *args], cwd=cwd, text=True, capture_output=True, env=env, check=False)


def _start(tmp_path: Path) -> str:
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "orchestrator").returncode == 0
    return (tmp_path / ".agentproof" / "active_run").read_text().strip()


def test_gateway_records_and_attributes(tmp_path: Path):
    rid = _start(tmp_path)
    gw = Gateway(rid, cwd=tmp_path, policy_mode="observe")
    r = gw.command("doc-writer", ["echo", "hello"])
    assert r.allowed and r.exit_code == 0
    gw.tool_call("pm-agent", "jira", "create_issue", {"title": "x"}, handler=lambda t, a: {"id": "P-1"})

    actions = action_flow(rid, tmp_path)["actions"]
    assert [a["actor"] for a in actions] == ["doc-writer", "pm-agent"]
    assert any(a["kind"] == "tool_call" and a["title"] == "jira:create_issue" for a in actions)


def test_gateway_blocks_against_active_policy(tmp_path: Path):
    rid = _start(tmp_path)
    accept_rules(tmp_path / ".agentproof", [
        {"id": "block_cmd_cat", "decision": "block", "match": {"kind": "command", "binary": "cat"}, "reason": "no secrets"},
        {"id": "block_tool_send_email", "decision": "block", "match": {"kind": "tool_call", "tool": "send_email"}, "reason": "no mass email"},
    ])
    gw = Gateway(rid, cwd=tmp_path, policy_mode="block")

    blocked_cmd = gw.command("rogue", ["cat", ".env"])
    assert blocked_cmd.blocked and not blocked_cmd.allowed
    assert blocked_cmd.exit_code is None  # never executed

    blocked_tool = gw.tool_call("rogue", "email", "send_email", {"to": "all@acme.co"},
                                handler=lambda t, a: (_ for _ in ()).throw(AssertionError("must not run")))
    assert blocked_tool.blocked

    allowed = gw.command("tester", ["echo", "ok"])
    assert allowed.allowed
