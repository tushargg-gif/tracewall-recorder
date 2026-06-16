from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from agentproof.flow import build_action_flow, render_flow


ROOT = Path(__file__).resolve().parents[1]


def _synthetic_events() -> list[dict]:
    return [
        {"event_type": "command_started", "payload": {"command": "echo hi"}},
        {"event_type": "command_finished", "payload": {"command": "echo hi", "exit_code": 0},
         "event_id": "e1", "timestamp": "t1"},
        {"event_type": "policy.decision", "payload": {"decision": {"action": "allow"}}},
        {"event_type": "mcp.tool.call.started",
         "payload": {"server_name": "github",
                     "request": {"params": {"name": "create_issue", "arguments": {"title": "x"}}}},
         "event_id": "e2", "timestamp": "t2"},
        {"event_type": "mcp.tool.call.finished", "payload": {"server_name": "github"}},
        {"event_type": "policy.decision", "payload": {"decision": {"action": "block"}}},
        {"event_type": "mcp.tool.call.started",
         "payload": {"server_name": "github",
                     "request": {"params": {"name": "delete_repo", "arguments": {}}}},
         "event_id": "e3", "timestamp": "t3"},
        {"event_type": "mcp.error", "payload": {}},
        {"event_type": "command_finished", "payload": {"command": "pytest", "exit_code": 1},
         "event_id": "e4", "timestamp": "t4"},
    ]


def test_flow_unifies_and_orders_commands_and_tool_calls():
    actions = build_action_flow(_synthetic_events())
    assert [a["seq"] for a in actions] == [1, 2, 3, 4]
    assert [a["kind"] for a in actions] == ["command", "tool_call", "tool_call", "command"]
    assert [a["title"] for a in actions] == [
        "echo hi", "github:create_issue", "github:delete_repo", "pytest",
    ]
    assert [a["status"] for a in actions] == ["ok", "ok", "blocked", "failed"]


def test_blocked_tool_call_requires_a_block_decision():
    # mcp.error following an *allowed* decision is a failure, not a block.
    events = [
        {"event_type": "policy.decision", "payload": {"decision": {"action": "allow"}}},
        {"event_type": "mcp.tool.call.started",
         "payload": {"server_name": "s", "request": {"params": {"name": "t"}}}},
        {"event_type": "mcp.error", "payload": {}},
    ]
    actions = build_action_flow(events)
    assert actions[0]["status"] == "failed"


def test_empty_flow_renders_placeholder():
    text = render_flow({"run_id": "run_x", "action_count": 0, "actions": []})
    assert "run_x" in text
    assert "no commands or tool calls" in text


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "agentproof", *args],
        cwd=cwd, text=True, capture_output=True, env=env, check=False,
    )


def test_cli_flow_lists_a_recorded_command(tmp_path: Path):
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    assert _cli(tmp_path, "run", "--", "echo", "hello").returncode == 0
    assert _cli(tmp_path, "stop", "--final-response", "done").returncode == 0
    result = _cli(tmp_path, "flow", "--json")
    assert result.returncode == 0, result.stderr
    flow = json.loads(result.stdout)
    assert flow["action_count"] >= 1
    kinds = [a["kind"] for a in flow["actions"]]
    assert "command" in kinds
    assert any("echo hello" in a["title"] for a in flow["actions"])
