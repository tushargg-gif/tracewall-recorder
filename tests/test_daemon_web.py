from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from agentproof import daemon, recorder
from agentproof.hook import run_pre


def _serve() -> tuple[daemon._HTTPServer, int]:
    server = daemon._HTTPServer(("127.0.0.1", 0), daemon.PolicyCache())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _get(port: int, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
        return response.status, response.read()


def test_daemon_serves_review_page_and_api(tmp_path: Path):
    run_pre(json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}}), tmp_path)
    run_id = recorder.latest_run_id(tmp_path)
    recorder.record_event("command_finished", {"command": "echo hi", "exit_code": 0}, run_id=run_id, cwd=tmp_path)
    server, port = _serve()
    q = f"?cwd={quote(str(tmp_path))}"
    try:
        status, body = _get(port, f"/review{q}")
        assert status == 200 and b"AgentProof" in body          # editor-agnostic page

        status, body = _get(port, f"/api/state{q}")
        state = json.loads(body)
        assert status == 200 and state.get("actions")            # JSON for the extension

        seq = state["actions"][0]["seq"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/verdict{q}",
            data=json.dumps({"seq": seq, "decision": "allow"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
            assert "actions" in json.loads(response.read())      # verdict accepted, state returned
    finally:
        server.shutdown(); server.server_close()


def test_daemon_review_404_for_project_with_no_runs(tmp_path: Path):
    server, port = _serve()
    try:
        try:
            _get(port, f"/api/state?cwd={quote(str(tmp_path))}")
            raise AssertionError("expected a 404 for a project with no runs")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown(); server.server_close()
