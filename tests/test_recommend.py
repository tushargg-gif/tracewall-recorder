from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

from agentproof.flow import action_flow
from agentproof.recommend import recommend_policy, render_recommendations
from agentproof.review import set_verdict


ROOT = Path(__file__).resolve().parents[1]


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "agentproof", *args],
        cwd=cwd, text=True, capture_output=True, env=env, check=False,
    )


def _seq_by_substring(run_id: str, cwd: Path, needle: str) -> int:
    for action in action_flow(run_id, cwd)["actions"]:
        if needle in action["title"]:
            return action["seq"]
    raise AssertionError(f"no action matching {needle!r}")


def _run_with_actions(tmp_path: Path) -> str:
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    assert _cli(tmp_path, "run", "--", "echo", "build").returncode == 0
    _cli(tmp_path, "event", "mcp.tool.call.started",
         "--payload", '{"server_name":"shell","request":{"params":{"name":"send_email","arguments":{"to":"x@y.com"}}}}')
    _cli(tmp_path, "event", "mcp.tool.call.finished", "--payload", '{"server_name":"shell"}')
    assert _cli(tmp_path, "stop", "--final-response", "done").returncode == 0
    return _cli(tmp_path, "flow", "--json").stdout and \
        __import__("json").loads(_cli(tmp_path, "flow", "--json").stdout)["run_id"]


def test_induces_block_and_allow_rules_with_reasons(tmp_path: Path):
    run_id = _run_with_actions(tmp_path)
    set_verdict(run_id, _seq_by_substring(run_id, tmp_path, "echo"), "allow", cwd=tmp_path)
    set_verdict(run_id, _seq_by_substring(run_id, tmp_path, "send_email"), "block", cwd=tmp_path)

    rec = recommend_policy(run_id, cwd=tmp_path)
    by_target = {(r["decision"], r["match"].get("tool") or r["match"].get("binary")): r for r in rec["rules"]}

    assert ("block", "send_email") in by_target
    assert ("allow", "echo") in by_target
    # block rules sorted first
    assert rec["rules"][0]["decision"] == "block"
    # every rule has a non-empty plain-language reason
    for rule in rec["rules"]:
        assert rule["reason"] and "send_email" in by_target[("block", "send_email")]["reason"]
    assert rec["summary"]["blocks"] == 1 and rec["summary"]["allows"] == 1


def test_blocking_secret_read_induces_target_rule_not_binary(tmp_path: Path):
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    # the agent reads two different secret files with two different binaries
    _cli(tmp_path, "run", "--", "cat", ".env")
    _cli(tmp_path, "run", "--", "echo", "hi")  # benign use we'll allow
    assert _cli(tmp_path, "stop", "--final-response", "done").returncode == 0
    import json as _json
    run_id = _json.loads(_cli(tmp_path, "flow", "--json").stdout)["run_id"]
    for a in action_flow(run_id, tmp_path)["actions"]:
        set_verdict(run_id, a["seq"], "block" if ".env" in a["title"] else "allow", cwd=tmp_path)

    rec = recommend_policy(run_id, cwd=tmp_path)
    matches = [r["match"] for r in rec["rules"] if r["decision"] == "block"]
    # the block rule targets secret files, NOT the `cat` binary
    assert {"kind": "command", "touches_secret": True} in matches
    assert not any(m.get("binary") == "cat" for m in matches)


def test_conflict_when_same_target_allowed_and_blocked(tmp_path: Path):
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    for _ in range(2):
        _cli(tmp_path, "event", "mcp.tool.call.started",
             "--payload", '{"server_name":"s","request":{"params":{"name":"deploy"}}}')
        _cli(tmp_path, "event", "mcp.tool.call.finished", "--payload", '{"server_name":"s"}')
    assert _cli(tmp_path, "stop", "--final-response", "done").returncode == 0
    import json
    run_id = json.loads(_cli(tmp_path, "flow", "--json").stdout)["run_id"]
    seqs = [a["seq"] for a in action_flow(run_id, tmp_path)["actions"] if "deploy" in a["title"]]
    assert len(seqs) == 2
    set_verdict(run_id, seqs[0], "allow", cwd=tmp_path)
    set_verdict(run_id, seqs[1], "block", cwd=tmp_path)

    rec = recommend_policy(run_id, cwd=tmp_path)
    assert rec["summary"]["conflicts"] == 1
    assert not any(r["match"].get("tool") == "deploy" for r in rec["rules"])


def test_unreviewed_actions_are_reported(tmp_path: Path):
    run_id = _run_with_actions(tmp_path)
    # only review one of the two actions
    set_verdict(run_id, _seq_by_substring(run_id, tmp_path, "echo"), "allow", cwd=tmp_path)
    rec = recommend_policy(run_id, cwd=tmp_path)
    assert rec["summary"]["unreviewed"] == 1
    assert "send_email" in rec["unreviewed"][0]["title"]


def test_render_handles_empty(tmp_path: Path):
    run_id = _run_with_actions(tmp_path)
    text = render_recommendations(recommend_policy(run_id, cwd=tmp_path))
    assert "review the action flow first" in text
