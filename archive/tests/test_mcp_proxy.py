from __future__ import annotations

from pathlib import Path
import io
import json
import threading
import time

from fastapi.testclient import TestClient

from tracewall.contracts import TaskContract
from tracewall.mcp_stdio import handle_stdio_message
from tracewall.recorder import create_run, paths_for_run, read_json, write_json
from tracewall.sidecar import create_app


class FakeProcess:
    def __init__(self, response: dict):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(json.dumps(response) + "\n")


def create_mcp_run(tmp_path: Path, control_mode: str, mcp_policy: dict):
    contract = TaskContract.from_mapping(
        {
            "task_id": "MCP-1",
            "title": "MCP task",
            "allowed_paths": [],
            "allowed_commands": [],
            "success_criteria": [],
            "verification": {},
            "mcp_policy": mcp_policy,
        }
    )
    run = create_run(contract, "master-agent", cwd=tmp_path)
    run["control_mode"] = control_mode
    run["orchestrator"] = "test"
    paths = paths_for_run(run["run_id"], tmp_path)
    write_json(paths.run_file, run)
    return run


def test_stdio_mcp_allowed_tool_records_started_and_finished(tmp_path: Path):
    run = create_mcp_run(tmp_path, "observe", {"allowed_tool_names": ["safe_tool"]})
    process = FakeProcess({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    response = handle_stdio_message(
        run,
        TaskContract.from_mapping(run["contract"]),
        tmp_path,
        run["run_id"],
        "fake",
        process,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "safe_tool"}}),
    )
    assert response["result"]["ok"] is True
    events = (tmp_path / ".tracewall" / "runs" / run["run_id"] / "events.jsonl").read_text(encoding="utf-8")
    assert "mcp.tool.call.started" in events
    assert "mcp.tool.call.finished" in events


def test_stdio_mcp_blocks_forbidden_critical_tool(tmp_path: Path):
    run = create_mcp_run(tmp_path, "block_critical", {"forbidden_tool_names": ["delete_all"]})
    response = handle_stdio_message(
        run,
        TaskContract.from_mapping(run["contract"]),
        tmp_path,
        run["run_id"],
        "fake",
        FakeProcess({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "delete_all"}}),
    )
    assert response["error"]["code"] == -32001


def test_stdio_mcp_malformed_json_records_error(tmp_path: Path):
    run = create_mcp_run(tmp_path, "observe", {})
    response = handle_stdio_message(
        run,
        TaskContract.from_mapping(run["contract"]),
        tmp_path,
        run["run_id"],
        "fake",
        FakeProcess({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
        "{not-json",
    )
    assert response["error"]["code"] == -32700
    events = (tmp_path / ".tracewall" / "runs" / run["run_id"] / "events.jsonl").read_text(encoding="utf-8")
    assert "mcp.error" in events


def test_http_mcp_proxy_forwards_and_redacts_headers(monkeypatch, tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".tracewall"))
    run = client.post(
        "/v1/runs",
        json={
            "agent": "master",
            "orchestrator": "orch",
            "control_mode": "observe",
            "task_contract": {
                "task_id": "HTTP-MCP",
                "title": "HTTP MCP",
                "allowed_paths": [],
                "allowed_commands": [],
                "verification": {},
                "mcp_policy": {"allowed_tool_names": ["safe_tool"]},
            },
        },
    ).json()
    captured = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers

            class Response:
                def json(self):
                    return {"jsonrpc": "2.0", "id": json["id"], "result": {"ok": True}}

            return Response()

    monkeypatch.setattr("tracewall.sidecar.httpx.AsyncClient", FakeAsyncClient)
    proxy = client.post(
        "/v1/mcp/proxies",
        json={
            "run_id": run["run_id"],
            "server_name": "remote-tools",
            "transport": "streamable_http",
            "target_url": "https://tools.example.com/mcp",
            "headers": {"Authorization": "Bearer raw-secret"},
        },
    ).json()
    response = client.post(
        f"/mcp/{proxy['proxy_id']}",
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "safe_tool"}},
        headers={"Mcp-Session-Id": "session-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["ok"] is True
    assert captured["url"] == "https://tools.example.com/mcp"
    assert captured["headers"]["Authorization"] == "Bearer raw-secret"
    assert captured["headers"]["mcp-session-id"] == "session-1"
    events = (tmp_path / ".tracewall" / "runs" / run["run_id"] / "events.jsonl").read_text(encoding="utf-8")
    assert "raw-secret" not in events
    assert "mcp.tool.call.finished" in events


def test_http_mcp_proxy_rejects_localhost_target(tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".tracewall"))
    run = client.post(
        "/v1/runs",
        json={
            "agent": "master",
            "orchestrator": "orch",
            "control_mode": "observe",
            "task_contract": {"task_id": "LOCAL", "title": "Local", "verification": {}},
        },
    ).json()
    response = client.post(
        "/v1/mcp/proxies",
        json={
            "run_id": run["run_id"],
            "server_name": "local-tools",
            "transport": "streamable_http",
            "target_url": "http://localhost:3000/mcp",
        },
    )
    assert response.status_code == 400
    assert "localhost" in response.text


def test_http_mcp_proxy_allows_external_target_with_allowlist(tmp_path: Path):
    client = TestClient(
        create_app(
            tmp_path / ".tracewall",
            allowed_mcp_target_hosts=["tools.example.com"],
        )
    )
    run = client.post(
        "/v1/runs",
        json={
            "agent": "master",
            "orchestrator": "orch",
            "control_mode": "observe",
            "task_contract": {"task_id": "ALLOW", "title": "Allow", "verification": {}},
        },
    ).json()
    response = client.post(
        "/v1/mcp/proxies",
        json={
            "run_id": run["run_id"],
            "server_name": "remote-tools",
            "transport": "streamable_http",
            "target_url": "https://tools.example.com/mcp",
        },
    )
    assert response.status_code == 200, response.text


def test_http_mcp_proxy_rejects_non_allowlisted_target(tmp_path: Path):
    client = TestClient(
        create_app(
            tmp_path / ".tracewall",
            allowed_mcp_target_hosts=["tools.example.com"],
        )
    )
    run = client.post(
        "/v1/runs",
        json={
            "agent": "master",
            "orchestrator": "orch",
            "control_mode": "observe",
            "task_contract": {"task_id": "DENY", "title": "Deny", "verification": {}},
        },
    ).json()
    response = client.post(
        "/v1/mcp/proxies",
        json={
            "run_id": run["run_id"],
            "server_name": "remote-tools",
            "transport": "streamable_http",
            "target_url": "https://other.example.com/mcp",
        },
    )
    assert response.status_code == 400
    assert "allowed host" in response.text


def test_http_mcp_approval_timeout_returns_error(tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".tracewall"))
    run = client.post(
        "/v1/runs",
        json={
            "agent": "master",
            "orchestrator": "orch",
            "control_mode": "approval_gates",
            "task_contract": {
                "task_id": "APPROVAL",
                "title": "Approval",
                "allowed_paths": [],
                "allowed_commands": [],
                "verification": {},
                "mcp_policy": {"approval_required_tools": ["pay"], "approval_timeout_seconds": 0.05},
            },
        },
    ).json()
    proxy = client.post(
        "/v1/mcp/proxies",
        json={
            "run_id": run["run_id"],
            "server_name": "remote-tools",
            "transport": "streamable_http",
            "target_url": "https://tools.example.com/mcp",
        },
    ).json()
    response = client.post(
        f"/mcp/{proxy['proxy_id']}",
        json={"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "pay"}},
    )
    assert response.json()["error"]["code"] == -32002
    pending = client.get("/v1/approvals/pending")
    assert pending.status_code == 200


def test_approval_api_can_approve_pending_request(monkeypatch, tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".tracewall"))
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            class Response:
                def json(self):
                    return {"jsonrpc": "2.0", "id": json["id"], "result": {"approved_forward": True}}

            return Response()

    monkeypatch.setattr("tracewall.sidecar.httpx.AsyncClient", FakeAsyncClient)
    run = client.post(
        "/v1/runs",
        json={
            "agent": "master",
            "orchestrator": "orch",
            "control_mode": "approval_gates",
            "task_contract": {
                "task_id": "APPROVAL-OK",
                "title": "Approval OK",
                "allowed_paths": [],
                "allowed_commands": [],
                "verification": {},
                "mcp_policy": {"approval_required_tools": ["pay"], "approval_timeout_seconds": 1},
            },
        },
    ).json()
    proxy = client.post(
        "/v1/mcp/proxies",
        json={"run_id": run["run_id"], "server_name": "remote-tools", "transport": "streamable_http", "target_url": "https://tools.example.com/mcp"},
    ).json()

    result = {}

    def call_proxy():
        result["response"] = client.post(
            f"/mcp/{proxy['proxy_id']}",
            json={"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "pay"}},
        )

    thread = threading.Thread(target=call_proxy)
    thread.start()
    approval_id = None
    for _ in range(20):
        pending = client.get("/v1/approvals/pending").json()
        if pending:
            approval_id = pending[0]["approval_id"]
            break
        time.sleep(0.05)
    assert approval_id is not None
    approved = client.post(f"/v1/approvals/{approval_id}/approve", json={"reviewer": "test"})
    assert approved.status_code == 200
    thread.join(timeout=2)
    assert result["response"].json()["result"]["approved_forward"] is True


def test_verification_scores_mcp_observe_violation(tmp_path: Path):
    run = create_mcp_run(tmp_path, "observe", {"forbidden_tool_names": ["delete_all"]})
    response = handle_stdio_message(
        run,
        TaskContract.from_mapping(run["contract"]),
        tmp_path,
        run["run_id"],
        "fake",
        FakeProcess({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delete_all"}}),
    )
    assert response["result"]["ok"] is True
    from tracewall.verifier import verify_run

    verification = verify_run(run["run_id"], cwd=tmp_path)
    assert verification["risk"] == "high"
    assert any(item["policy_id"] == "mcp_forbidden_tool" for item in verification["policy_violations"])


def test_mcp_runtime_evidence_avoids_shell_command_reproducibility_penalty(tmp_path: Path):
    run = create_mcp_run(tmp_path, "observe", {"allowed_tool_names": ["safe_tool"]})
    response = handle_stdio_message(
        run,
        TaskContract.from_mapping(run["contract"]),
        tmp_path,
        run["run_id"],
        "fake",
        FakeProcess({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "safe_tool"}}),
    )
    assert response["result"]["ok"] is True
    from tracewall.verifier import verify_run

    verification = verify_run(run["run_id"], cwd=tmp_path)
    assert verification["dimensions"]["reproducibility"] == 100
