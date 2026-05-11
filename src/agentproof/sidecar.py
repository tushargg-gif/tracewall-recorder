from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from agentproof.contracts import TaskContract
from agentproof.events import now_iso, redact_secrets
from agentproof.mcp_policy import (
    approval_error,
    block_error,
    decision_event_payload,
    evaluate_mcp_request,
    method_event_type,
)
from agentproof.recorder import create_run, paths_for_run, read_json, record_event, stop_run, write_json
from agentproof.reports import generate_report
from agentproof.store import Store
from agentproof.verifier import verify_run


def create_app(root: Path | str = ".agentproof") -> FastAPI:
    root_path = Path(root).resolve()
    project_root = root_path.parent if root_path.name == ".agentproof" else root_path
    agentproof_root = project_root / ".agentproof"
    store = Store(agentproof_root)
    app = FastAPI(title="AgentProof Sidecar")
    app.state.project_root = project_root
    app.state.store = store
    app.state.raw_proxy_headers = {}

    @app.post("/v1/runs")
    def create_sidecar_run(body: dict[str, Any]) -> dict[str, Any]:
        contract = TaskContract.from_mapping(body.get("task_contract") or {})
        run = create_run(contract, str(body.get("agent") or "unknown"), cwd=project_root)
        run.update(
            {
                "orchestrator": str(body.get("orchestrator") or ""),
                "control_mode": str(body.get("control_mode") or "observe"),
            }
        )
        paths = paths_for_run(run["run_id"], project_root)
        write_json(paths.run_file, run)
        store.upsert_run(run)
        record_event(
            "orchestrator.run_created",
            {
                "agent": run["agent"],
                "orchestrator": run["orchestrator"],
                "control_mode": run["control_mode"],
            },
            run_id=run["run_id"],
            cwd=project_root,
        )
        return run

    @app.post("/v1/runs/{run_id}/events")
    def append_run_event(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        ensure_run_exists(run_id, project_root)
        event = record_event(
            str(body.get("event_type") or ""),
            dict(body.get("payload") or {}),
            run_id=run_id,
            cwd=project_root,
        )
        return event

    @app.post("/v1/runs/{run_id}/stop")
    def stop_sidecar_run(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        ensure_run_exists(run_id, project_root)
        return stop_run(run_id, (body or {}).get("final_response", ""), cwd=project_root)

    @app.post("/v1/runs/{run_id}/verify")
    def verify_sidecar_run(run_id: str) -> dict[str, Any]:
        ensure_run_exists(run_id, project_root)
        return verify_run(run_id, cwd=project_root)

    @app.get("/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        paths = ensure_run_exists(run_id, project_root)
        run = read_json(paths.run_file)
        verification_path = paths.run_dir / "verification.json"
        if verification_path.exists():
            run["verification"] = read_json(verification_path)
        return run

    @app.get("/v1/runs/{run_id}/report.md")
    def get_markdown_report(run_id: str) -> PlainTextResponse:
        ensure_run_exists(run_id, project_root)
        report_paths = generate_report(run_id, cwd=project_root)
        return PlainTextResponse(report_paths["markdown"].read_text(encoding="utf-8"))

    @app.get("/v1/runs/{run_id}/report.json")
    def get_json_report(run_id: str) -> dict[str, Any]:
        ensure_run_exists(run_id, project_root)
        report_paths = generate_report(run_id, cwd=project_root)
        return read_json(report_paths["json"])

    @app.get("/v1/approvals/pending")
    def pending_approvals() -> list[dict[str, Any]]:
        return store.pending_approvals()

    @app.post("/v1/approvals/{approval_id}/approve")
    def approve(approval_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        updated = store.update_approval(
            approval_id,
            "approved",
            {"approved": True, **(body or {})},
            now_iso(),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Approval not found")
        approval = store.get_approval(approval_id)
        record_event("approval.approved", {"approval_id": approval_id}, run_id=approval["run_id"], cwd=project_root)
        return approval

    @app.post("/v1/approvals/{approval_id}/deny")
    def deny(approval_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        updated = store.update_approval(
            approval_id,
            "denied",
            {"approved": False, **(body or {})},
            now_iso(),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Approval not found")
        approval = store.get_approval(approval_id)
        record_event("approval.denied", {"approval_id": approval_id}, run_id=approval["run_id"], cwd=project_root)
        return approval

    @app.post("/v1/mcp/proxies")
    def create_mcp_proxy(body: dict[str, Any], request: Request) -> dict[str, Any]:
        run_id = str(body.get("run_id") or "")
        ensure_run_exists(run_id, project_root)
        proxy_id = f"mcp_proxy_{uuid.uuid4().hex[:10]}"
        proxy = {
            "proxy_id": proxy_id,
            "run_id": run_id,
            "server_name": str(body.get("server_name") or "mcp-server"),
            "transport": str(body.get("transport") or "streamable_http"),
            "target_url": str(body.get("target_url") or ""),
            "headers": dict(body.get("headers") or {}),
            "created_at": now_iso(),
        }
        if proxy["transport"] != "streamable_http":
            raise HTTPException(status_code=400, detail="Only streamable_http proxies are created over the sidecar API")
        if not proxy["target_url"]:
            raise HTTPException(status_code=400, detail="target_url is required")
        store.create_mcp_proxy(proxy)
        app.state.raw_proxy_headers[proxy_id] = proxy["headers"]
        record_event(
            "mcp.proxy.created",
            {**proxy, "headers": redact_secrets(proxy["headers"])},
            run_id=run_id,
            cwd=project_root,
        )
        base_url = str(request.base_url).rstrip("/")
        return {"proxy_id": proxy_id, "proxy_url": f"{base_url}/mcp/{proxy_id}"}

    @app.post("/mcp/{proxy_id}")
    async def streamable_http_proxy(proxy_id: str, request: Request) -> JSONResponse:
        proxy = store.get_mcp_proxy(proxy_id)
        if not proxy:
            raise HTTPException(status_code=404, detail="MCP proxy not found")
        request_payload = await request.json()
        response_payload = await handle_mcp_http_request(app, proxy, request_payload, request)
        return JSONResponse(response_payload)

    return app


async def handle_mcp_http_request(app: FastAPI, proxy: dict[str, Any], payload: dict[str, Any], request: Request) -> dict[str, Any]:
    project_root: Path = app.state.project_root
    run = load_run(proxy["run_id"], project_root)
    contract = TaskContract.from_mapping(run["contract"])
    method = str(payload.get("method") or "")
    params = dict(payload.get("params") or {})
    decision = evaluate_mcp_request(contract, proxy["server_name"], method, params, run.get("control_mode", "observe"))
    record_event("policy.decision", decision_event_payload(proxy["server_name"], method, params, decision), run_id=proxy["run_id"], cwd=project_root)

    if method == "tools/call":
        record_event("mcp.tool.call.started", {"server_name": proxy["server_name"], "request": redact_secrets(payload)}, run_id=proxy["run_id"], cwd=project_root)
    else:
        record_event(method_event_type(method), {"server_name": proxy["server_name"], "request": redact_secrets(payload)}, run_id=proxy["run_id"], cwd=project_root)

    if decision.action == "block":
        response = block_error(payload.get("id"))
        record_event("mcp.error", {"server_name": proxy["server_name"], "response": response}, run_id=proxy["run_id"], cwd=project_root)
        return response
    if decision.action == "approval_required":
        approved = await request_approval(app, proxy["run_id"], proxy["server_name"], method, params, contract)
        if not approved:
            response = approval_error(payload.get("id"))
            record_event("mcp.error", {"server_name": proxy["server_name"], "response": response}, run_id=proxy["run_id"], cwd=project_root)
            return response

    headers = merged_forward_headers(dict(request.headers), app.state.raw_proxy_headers.get(proxy["proxy_id"], {}))
    started = asyncio.get_running_loop().time()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            forwarded = await client.post(proxy["target_url"], json=payload, headers=headers)
        response_payload = forwarded.json()
    except Exception as exc:
        response_payload = {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32003, "message": str(exc)}}
        record_event("mcp.error", {"server_name": proxy["server_name"], "error": str(exc)}, run_id=proxy["run_id"], cwd=project_root)
        return response_payload

    if method == "tools/call":
        record_event(
            "mcp.tool.call.finished",
            {
                "server_name": proxy["server_name"],
                "duration_seconds": round(asyncio.get_running_loop().time() - started, 3),
                "response": redact_secrets(response_payload),
            },
            run_id=proxy["run_id"],
            cwd=project_root,
        )
    return response_payload


async def request_approval(
    app: FastAPI,
    run_id: str,
    server_name: str,
    method: str,
    params: dict[str, Any],
    contract: TaskContract,
) -> bool:
    store: Store = app.state.store
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
    record_event("approval.requested", approval, run_id=run_id, cwd=app.state.project_root)
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = store.get_approval(approval_id)
        if current and current["status"] == "approved":
            return True
        if current and current["status"] == "denied":
            return False
        await asyncio.sleep(0.05)
    store.update_approval(approval_id, "timed_out", {"approved": False, "reason": "timeout"}, now_iso())
    record_event("approval.timed_out", {"approval_id": approval_id}, run_id=run_id, cwd=app.state.project_root)
    return False


def ensure_run_exists(run_id: str, project_root: Path):
    if not run_id:
        raise HTTPException(status_code=404, detail="Run not found")
    paths = paths_for_run(run_id, project_root)
    if not paths.run_file.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return paths


def load_run(run_id: str, project_root: Path) -> dict[str, Any]:
    paths = ensure_run_exists(run_id, project_root)
    return read_json(paths.run_file)


def merged_forward_headers(incoming: dict[str, str], configured: dict[str, str]) -> dict[str, str]:
    session_headers = {
        key: value
        for key, value in incoming.items()
        if key.lower().startswith("mcp-") or key.lower() in {"last-event-id"}
    }
    return {**session_headers, **configured}


def run_sidecar(host: str, port: int, root: str) -> None:
    import uvicorn

    uvicorn.run(create_app(root), host=host, port=port)
