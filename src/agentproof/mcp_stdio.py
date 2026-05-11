from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import subprocess
import sys
import time
import uuid

from agentproof.contracts import TaskContract
from agentproof.events import now_iso, redact_secrets
from agentproof.mcp_policy import (
    approval_error,
    block_error,
    decision_event_payload,
    evaluate_mcp_request,
    method_event_type,
)
from agentproof.recorder import paths_for_run, read_json, record_event
from agentproof.store import default_store_for_project


def run_stdio_proxy(run_id: str, server_name: str, command: list[str], cwd: Path | None = None) -> int:
    if not command:
        raise ValueError("MCP stdio proxy requires a server command.")
    project_root = Path(cwd or Path.cwd()).resolve()
    run = load_run(run_id, project_root)
    contract = TaskContract.from_mapping(run["contract"])
    process = subprocess.Popen(
        command,
        cwd=project_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    record_event("mcp.proxy.created", {"run_id": run_id, "server_name": server_name, "transport": "stdio", "command": command}, run_id=run_id, cwd=project_root)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            response = handle_stdio_message(run, contract, project_root, run_id, server_name, process, line)
            if response is not None:
                sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")
                sys.stdout.flush()
    finally:
        if process.poll() is None:
            process.terminate()
    return process.wait() if process.poll() is not None else 0


def handle_stdio_message(
    run: dict[str, Any],
    contract: TaskContract,
    project_root: Path,
    run_id: str,
    server_name: str,
    process: subprocess.Popen[str],
    line: str,
) -> dict[str, Any] | None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        record_event("mcp.error", {"server_name": server_name, "error": f"Malformed JSON-RPC: {exc}"}, run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    if not isinstance(request, dict):
        record_event("mcp.error", {"server_name": server_name, "error": "JSON-RPC message must be an object"}, run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}

    method = str(request.get("method") or "")
    params = dict(request.get("params") or {})
    decision = evaluate_mcp_request(contract, server_name, method, params, str(run.get("control_mode") or "observe"))
    record_event("policy.decision", decision_event_payload(server_name, method, params, decision), run_id=run_id, cwd=project_root)

    if method == "tools/call":
        record_event("mcp.tool.call.started", {"server_name": server_name, "request": redact_secrets(request)}, run_id=run_id, cwd=project_root)
    else:
        record_event(method_event_type(method), {"server_name": server_name, "request": redact_secrets(request)}, run_id=run_id, cwd=project_root)

    if decision.action == "block":
        response = block_error(request.get("id"))
        record_event("mcp.error", {"server_name": server_name, "response": response}, run_id=run_id, cwd=project_root)
        return response
    if decision.action == "approval_required" and not wait_for_approval(project_root, run_id, server_name, method, params, contract):
        response = approval_error(request.get("id"))
        record_event("mcp.error", {"server_name": server_name, "response": response}, run_id=run_id, cwd=project_root)
        return response

    started = time.time()
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    response_line = process.stdout.readline()
    if not response_line:
        record_event("mcp.error", {"server_name": server_name, "error": "MCP server closed stdout"}, run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32004, "message": "MCP server closed"}}
    try:
        response = json.loads(response_line)
    except json.JSONDecodeError as exc:
        record_event("mcp.error", {"server_name": server_name, "error": f"Malformed MCP server response: {exc}"}, run_id=run_id, cwd=project_root)
        return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32005, "message": "Malformed MCP server response"}}
    if method == "tools/call":
        record_event(
            "mcp.tool.call.finished",
            {
                "server_name": server_name,
                "duration_seconds": round(time.time() - started, 3),
                "response": redact_secrets(response),
            },
            run_id=run_id,
            cwd=project_root,
        )
    return response


def wait_for_approval(
    project_root: Path,
    run_id: str,
    server_name: str,
    method: str,
    params: dict[str, Any],
    contract: TaskContract,
) -> bool:
    store = default_store_for_project(project_root)
    timeout = float((contract.mcp_policy or {}).get("approval_timeout_seconds") or 300)
    approval_id = f"approval_{uuid.uuid4().hex[:10]}"
    approval = {
        "approval_id": approval_id,
        "run_id": run_id,
        "status": "pending",
        "request": {"server_name": server_name, "method": method, "params": redact_secrets(params)},
        "response": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    store.create_approval(approval)
    record_event("approval.requested", approval, run_id=run_id, cwd=project_root)
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = store.get_approval(approval_id)
        if current and current["status"] == "approved":
            return True
        if current and current["status"] == "denied":
            return False
        time.sleep(0.05)
    store.update_approval(approval_id, "timed_out", {"approved": False, "reason": "timeout"}, now_iso())
    record_event("approval.timed_out", {"approval_id": approval_id}, run_id=run_id, cwd=project_root)
    return False


def load_run(run_id: str, project_root: Path) -> dict[str, Any]:
    paths = paths_for_run(run_id, project_root)
    if not paths.run_file.exists():
        raise RuntimeError(f"Run not found: {run_id}")
    return read_json(paths.run_file)
