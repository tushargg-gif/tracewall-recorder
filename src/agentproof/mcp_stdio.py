"""MCP stdio proxy — gateway for an agent's MCP tool calls.

Sits between an agent (Codex, or any MCP client) and a real MCP server, speaking
JSON-RPC over stdio. Every ``tools/call`` is evaluated by the same policy engine
the hook uses (learned policy + safe defaults), recorded, and **blocked** when the
decision is deny. Use it by configuring the agent to launch this proxy in place of
the real server:

    agentproof mcp stdio --server-name jira -- <real server command>

It attaches to the active AgentProof run (creating one if needed), so tool calls
land in the same timeline as everything else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import subprocess
import sys

from agentproof.enforce import action_from_tool
from agentproof.events import redact_secrets
from agentproof.hook import decide, ensure_run
from agentproof.mcp_policy import block_error, method_event_type
from agentproof.recorder import record_event


def run_stdio_proxy(server_name: str, command: list[str], cwd: Path | None = None,
                    run_id: str | None = None, ask_mode: str = "defer", source: str = "codex") -> int:
    if not command:
        raise ValueError("MCP stdio proxy requires a server command.")
    project_root = Path(cwd or Path.cwd()).resolve()
    if not run_id:
        run_id = ensure_run(project_root, agent=server_name or "agent")
    process = subprocess.Popen(
        command, cwd=project_root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=sys.stderr, text=True, bufsize=1,
    )
    record_event("mcp.proxy.created",
                 {"source": source, "server_name": server_name, "transport": "stdio", "command": command},
                 run_id=run_id, cwd=project_root)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            response = handle_stdio_message(project_root, run_id, server_name, process, line, ask_mode, source)
            if response is not None:
                sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")
                sys.stdout.flush()
    finally:
        if process.poll() is None:
            process.terminate()
    return process.wait() if process.poll() is not None else 0


def handle_stdio_message(project_root: Path, run_id: str, server_name: str,
                         process: "subprocess.Popen[str]", line: str, ask_mode: str,
                         source: str = "codex") -> dict[str, Any] | None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        record_event("mcp.error", {"server_name": server_name, "error": f"Malformed JSON-RPC: {exc}"},
                     run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}

    method = str(request.get("method") or "")
    params = dict(request.get("params") or {})
    req_id = request.get("id")

    if method == "tools/call":
        tool = str(params.get("name") or "tool")
        label = f"{server_name}:{tool}"
        record_event("mcp.tool.call.started",
                     {"agent": server_name, "source": source, "server_name": server_name, "request": redact_secrets(request)},
                     run_id=run_id, cwd=project_root)
        d = decide(action_from_tool(server_name, tool), label, project_root, ask_mode=ask_mode)
        record_event("policy.decision", {
            "agent": server_name, "source": source, "action": label, "match_kind": "tool_call",
            "decision": d["decision"], "rule_id": d["rule_id"], "reason": d["reason"],
            "policy_source": d["source"], "outcome": "blocked" if d["permission"] == "deny" else "allowed",
        }, run_id=run_id, cwd=project_root)
        if d["permission"] == "deny":
            record_event("policy.enforcement", {
                "agent": server_name, "source": source, "action": label, "rule_id": d["rule_id"],
                "reason": d["reason"], "action_taken": "blocked",
            }, run_id=run_id, cwd=project_root)
            record_event("mcp.error", {"agent": server_name, "source": source, "server_name": server_name,
                                       "error": "blocked by policy", "rule_id": d["rule_id"]},
                         run_id=run_id, cwd=project_root)
            return block_error(req_id, d["reason"] or "Blocked by AgentProof policy.")
    else:
        record_event(method_event_type(method),
                     {"agent": server_name, "source": source, "server_name": server_name, "request": redact_secrets(request)},
                     run_id=run_id, cwd=project_root)

    # forward to the real MCP server and relay its response
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    response_line = process.stdout.readline()
    if not response_line:
        record_event("mcp.error", {"server_name": server_name, "error": "MCP server closed stdout"},
                     run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32004, "message": "MCP server closed"}}
    try:
        response = json.loads(response_line)
    except json.JSONDecodeError as exc:
        record_event("mcp.error", {"server_name": server_name, "error": f"Malformed MCP server response: {exc}"},
                     run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32005, "message": "Malformed MCP server response"}}
    if method == "tools/call":
        record_event("mcp.tool.call.finished",
                     {"agent": server_name, "source": source, "server_name": server_name, "response": redact_secrets(response)},
                     run_id=run_id, cwd=project_root)
    return response
