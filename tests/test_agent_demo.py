from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_master_agent_demo_catches_rogue_worker():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "agent-demo/master_agent_demo.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Step 1: Master Agent reads repo context" in result.stdout
    assert "Step 6: Rogue Agent secretly changes package.json" in result.stdout
    assert "Step 8: Final decision: FAIL" in result.stdout
    assert "Harness status: PASS" in result.stdout
    assert "Verdict: Fail" in result.stdout
    assert "Violating agent: Rogue Agent" in result.stdout
    assert "agent-demo/generated/agentproof_report.json" in result.stdout

    generated = ROOT / "agent-demo" / "generated"
    policy_path = generated / "policy.json"
    events_path = generated / "events.jsonl"
    report_path = generated / "agentproof_report.json"
    assert policy_path.exists()
    assert events_path.exists()
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    verification = report["verification"]
    violation_ids = {item["policy_id"] for item in verification["policy_violations"]}
    assert verification["verdict"] == "Fail"
    assert "package.json" in verification["changed_files"]
    assert {
        "no_forbidden_path_change",
        "no_unrelated_file_change",
        "no_unapproved_dependency",
        "worker_scope_exceeded",
        "worker_forbidden_path_change",
    }.issubset(violation_ids)

    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rogue_events = [
        event
        for event in events
        if event.get("event_type") == "worker.completed"
        and (event.get("payload") or {}).get("agent") == "Rogue Agent"
    ]
    assert rogue_events
    assert "package.json" in rogue_events[0]["payload"]["actual_changed_files"]
    assert "package.json" not in rogue_events[0]["payload"]["reported_files"]

    checks = {check["name"]: check for check in verification["checks"]}
    assert checks["event_chain_integrity"]["status"] == "passed"
