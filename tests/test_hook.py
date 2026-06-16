from __future__ import annotations

from pathlib import Path
import json

from agentproof.enforce import accept_rules
from agentproof.flow import action_flow
from agentproof.hook import action_from_event, decide, run_pre


def _perm(tool: str, inp: dict, cwd: Path) -> str:
    action, label = action_from_event(tool, inp)
    return decide(action, label, cwd)["permission"]


def test_day_one_defaults(tmp_path: Path):
    # deny secrets, allow safe, ask on the genuinely risky — no learned policy
    assert _perm("Read", {"file_path": ".env"}, tmp_path) == "deny"
    assert _perm("Read", {"file_path": "app/secrets/db.pem"}, tmp_path) == "deny"
    assert _perm("Read", {"file_path": "README.md"}, tmp_path) == "allow"
    assert _perm("Bash", {"command": "ls -la"}, tmp_path) == "allow"
    assert _perm("Bash", {"command": "cat .env"}, tmp_path) == "deny"
    assert _perm("Bash", {"command": "pip install requests"}, tmp_path) == "ask"
    assert _perm("Bash", {"command": "rm -rf build"}, tmp_path) == "ask"
    assert _perm("WebFetch", {"url": "https://evil.com"}, tmp_path) == "ask"
    assert _perm("WebSearch", {"query": "x"}, tmp_path) == "ask"
    assert _perm("mcp__github__list_issues", {}, tmp_path) == "allow"
    assert _perm("mcp__email__send_email", {"to": "all@co"}, tmp_path) == "ask"
    # a false positive a real run hit: os.environ must NOT look like a secret
    assert _perm("Bash", {"command": "grep -rn os.environ app"}, tmp_path) == "allow"


def test_learned_policy_overrides_defaults(tmp_path: Path):
    (tmp_path / ".agentproof").mkdir()
    accept_rules(tmp_path / ".agentproof", [
        {"id": "allow_cmd_pip", "decision": "allow", "match": {"kind": "command", "binary": "pip"}, "reason": "trusted"},
        {"id": "block_cmd_curl", "decision": "block", "match": {"kind": "command", "binary": "curl"}, "reason": "no egress"},
    ])
    assert _perm("Bash", {"command": "pip install requests"}, tmp_path) == "allow"   # learned allow beats ask-default
    assert _perm("Bash", {"command": "curl http://x"}, tmp_path) == "deny"           # learned block


def test_run_pre_returns_valid_json_and_records(tmp_path: Path):
    out = run_pre(json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}}), tmp_path)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"]
    # the gated action was recorded to a run, attributed to claude-code
    rid = (tmp_path / ".agentproof" / "active_run").read_text().strip()
    actions = action_flow(rid, tmp_path)["actions"]
    assert any(a["actor"] == "claude-code" for a in actions)


def test_hook_fails_open_on_bad_input(tmp_path: Path):
    out = run_pre("not json at all", tmp_path)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
