from __future__ import annotations

from pathlib import Path
import json

import tracewall.guard as guard
from tracewall.enforcement import GuardProfile, build_macos_profile, guard_argv


def test_macos_profile_denies_secret_paths(tmp_path: Path):
    prof = build_macos_profile(GuardProfile(project_root=tmp_path))
    assert "deny file-read* file-write*" in prof
    assert ".env" in prof          # the secret patterns made it into the jail
    assert "pem" in prof


def test_guard_argv_wraps_with_sandbox_exec(tmp_path: Path):
    argv = guard_argv(["openclaw", "run"], GuardProfile(project_root=tmp_path), backend="sandbox-exec")
    assert argv[0] == "/usr/bin/sandbox-exec"
    assert argv[1] == "-p"
    assert argv[-2:] == ["openclaw", "run"]


def test_guard_fails_closed_without_a_backend(tmp_path: Path, monkeypatch):
    # no sandbox backend → guard refuses rather than run the agent unprotected
    monkeypatch.setattr(guard, "guard_backend", lambda: "none")
    rc = guard.run_guard(["openclaw"], cwd=tmp_path, source="openclaw")
    assert rc == 78  # ENFORCEMENT_UNAVAILABLE — nothing was spawned


def test_parses_macos_sandbox_denials(tmp_path: Path):
    root = str(tmp_path)
    log = "\n".join([
        json.dumps({"eventMessage": f"Sandbox: cat(123) deny(1) file-read-data {root}/.env"}),
        json.dumps({"eventMessage": f"Sandbox: python3(124) deny(1) file-read-data {root}/app/secrets/db.pem"}),
        json.dumps({"eventMessage": f"Sandbox: ls(125) deny(1) file-read-data {root}/README.md"}),  # not secret? still under root -> captured
        json.dumps({"eventMessage": "Sandbox: curl(126) deny(1) network-outbound /tmp/elsewhere"}),  # outside root -> ignored
        "not json",
    ])
    denials = guard.parse_sandbox_denials(log, tmp_path, source="openclaw")
    paths = [d["path"] for d in denials]
    assert f"{root}/.env" in paths
    assert f"{root}/app/secrets/db.pem" in paths
    assert all(p.startswith(root) for p in paths)        # scoped to the project
    assert all(d["action_taken"] == "blocked" for d in denials)
    assert denials[0]["process"] == "cat" and denials[0]["source"] == "openclaw"


def test_denied_event_shows_in_flow_as_blocked():
    from tracewall.flow import build_action_flow
    events = [{"event_type": "os.file.denied", "event_id": "e1", "timestamp": "2026-06-16T10:00:00",
               "payload": {"source": "openclaw", "process": "cat", "operation": "file-read-data",
                           "path": "/proj/.env", "action_taken": "blocked"}}]
    actions = build_action_flow(events)
    assert len(actions) == 1
    assert actions[0]["kind"] == "file" and actions[0]["status"] == "blocked"
    assert actions[0]["source"] == "openclaw" and ".env" in actions[0]["title"]
