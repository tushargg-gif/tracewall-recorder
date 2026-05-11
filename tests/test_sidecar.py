from __future__ import annotations

from pathlib import Path
import json

from fastapi.testclient import TestClient

from agentproof.sidecar import create_app


def create_run(client: TestClient, **overrides):
    body = {
        "agent": "master-agent",
        "orchestrator": "test-orchestrator",
        "control_mode": "observe",
        "task_contract": {
            "task_id": "ORCH-1",
            "title": "Orchestrated task",
            "allowed_paths": [],
            "allowed_commands": [],
            "verification": {},
        },
    }
    body.update(overrides)
    response = client.post("/v1/runs", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_sidecar_run_event_stop_verify_and_report(tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".agentproof"))
    run = create_run(client)
    event = client.post(
        f"/v1/runs/{run['run_id']}/events",
        json={"event_type": "network.request", "payload": {"url": "https://api.example.com/data"}},
    )
    assert event.status_code == 200, event.text
    stop = client.post(f"/v1/runs/{run['run_id']}/stop", json={"final_response": "done"})
    assert stop.status_code == 200, stop.text
    verify = client.post(f"/v1/runs/{run['run_id']}/verify")
    assert verify.status_code == 200, verify.text
    assert verify.json()["event_summary"]["network.request"] == 1
    markdown = client.get(f"/v1/runs/{run['run_id']}/report.md")
    assert markdown.status_code == 200
    assert "AgentProof Report" in markdown.text
    report_json = client.get(f"/v1/runs/{run['run_id']}/report.json")
    assert report_json.status_code == 200
    assert report_json.json()["run"]["run_id"] == run["run_id"]


def test_sidecar_invalid_run_returns_404(tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".agentproof"))
    response = client.get("/v1/runs/missing")
    assert response.status_code == 404


def test_sidecar_concurrent_runs_do_not_mix_events(tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".agentproof"))
    first = create_run(client, task_contract={"task_id": "ONE", "title": "one", "verification": {}, "allowed_paths": []})
    second = create_run(client, task_contract={"task_id": "TWO", "title": "two", "verification": {}, "allowed_paths": []})
    client.post(f"/v1/runs/{first['run_id']}/events", json={"event_type": "tool.call", "payload": {"tool": "first"}})
    client.post(f"/v1/runs/{second['run_id']}/events", json={"event_type": "tool.call", "payload": {"tool": "second"}})
    first_verify = client.post(f"/v1/runs/{first['run_id']}/verify").json()
    second_verify = client.post(f"/v1/runs/{second['run_id']}/verify").json()
    assert first_verify["run_id"] != second_verify["run_id"]
    first_events = (tmp_path / ".agentproof" / "runs" / first["run_id"] / "events.jsonl").read_text(encoding="utf-8")
    second_events = (tmp_path / ".agentproof" / "runs" / second["run_id"] / "events.jsonl").read_text(encoding="utf-8")
    assert "first" in first_events
    assert "second" not in first_events
    assert "second" in second_events


def test_event_hash_chain_and_redaction_detect_tampering(tmp_path: Path):
    client = TestClient(create_app(tmp_path / ".agentproof"))
    run = create_run(client)
    client.post(
        f"/v1/runs/{run['run_id']}/events",
        json={"event_type": "tool.call", "payload": {"api_key": "secret-value", "nested": {"token": "abc"}}},
    )
    events_path = tmp_path / ".agentproof" / "runs" / run["run_id"] / "events.jsonl"
    raw = events_path.read_text(encoding="utf-8")
    assert "secret-value" not in raw
    assert '"event_hash"' in raw
    assert '"prev_event_hash"' in raw

    lines = raw.splitlines()
    event = json.loads(lines[-1])
    event["payload"]["nested"]["extra"] = "tampered"
    lines[-1] = json.dumps(event, sort_keys=True)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verification = client.post(f"/v1/runs/{run['run_id']}/verify").json()
    lookup = {check["name"]: check for check in verification["checks"]}
    assert lookup["event_chain_integrity"]["status"] == "failed"
