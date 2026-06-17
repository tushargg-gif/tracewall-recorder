from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from agentproof.hook import action_from_event, decide


ROOT = Path(__file__).resolve().parents[1]


def _cli(cwd: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy(); env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, "-m", "agentproof", *args], cwd=cwd, text=True,
                          capture_output=True, env=env, input=stdin, check=False)


def test_ask_mode_maps_for_codex(tmp_path: Path):
    action, label = action_from_event("Bash", {"command": "pip install requests"})
    assert decide(action, label, tmp_path, ask_mode="native")["permission"] == "ask"
    assert decide(action, label, tmp_path, ask_mode="deny")["permission"] == "deny"
    assert decide(action, label, tmp_path, ask_mode="defer")["permission"] == "allow"
    # secrets are denied regardless of ask-mode
    sa, sl = action_from_event("Bash", {"command": "cat .env"})
    assert decide(sa, sl, tmp_path, ask_mode="defer")["permission"] == "deny"


def test_install_codex_writes_hooks_and_feature_flag(tmp_path: Path):
    assert _cli(tmp_path, "install-codex", "--ask-mode", "defer").returncode == 0
    hooks = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    pre = hooks["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "Bash"
    assert "agentproof" in pre["hooks"][0]["command"] and "--ask-mode defer" in pre["hooks"][0]["command"]
    assert "codex_hooks = true" in (tmp_path / ".codex" / "config.toml").read_text()


def test_mcp_proxy_blocks_a_tool_call(tmp_path: Path):
    # a fresh project + a policy that blocks send_email
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "codex").returncode == 0
    from agentproof.enforce import accept_rules
    accept_rules(tmp_path / ".agentproof", [
        {"id": "block_tool_send_email", "decision": "block",
         "match": {"kind": "tool_call", "tool": "send_email"}, "reason": "no mass email"},
    ])
    mock = tmp_path / "mock_mcp.py"
    mock.write_text(
        "import sys, json\n"
        "for line in sys.stdin:\n"
        "    line=line.strip()\n"
        "    if not line: continue\n"
        "    req=json.loads(line); i=req.get('id')\n"
        "    print(json.dumps({'jsonrpc':'2.0','id':i,'result':{'ok':True}})); sys.stdout.flush()\n",
        encoding="utf-8",
    )
    reqs = (
        '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"create_issue","arguments":{}}}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"send_email","arguments":{"to":"all@co"}}}\n'
    )
    out = _cli(tmp_path, "mcp", "stdio", "--server-name", "jira", "--", sys.executable, str(mock), stdin=reqs)
    assert out.returncode == 0, out.stderr
    responses = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
    by_id = {r["id"]: r for r in responses}
    assert "error" not in by_id[1]          # create_issue forwarded
    assert "error" in by_id[2]              # send_email blocked by policy
    assert by_id[2]["error"]["code"] == -32001
