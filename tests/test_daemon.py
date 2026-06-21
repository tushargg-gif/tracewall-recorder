"""P0.1 — tracewalld daemon: policy cache, decide parity, UDS round-trip, latency."""

from __future__ import annotations

import json
import statistics
import threading
import time
import uuid
from pathlib import Path

from tracewall import daemon, enforce, hook
from tracewall.recorder import paths_for_run


def _short_sock() -> str:
    # AF_UNIX paths are capped (~108 chars); keep the socket short regardless of
    # how deep the test's tmp dir is.
    return f"/tmp/apd-{uuid.uuid4().hex[:8]}.sock"


def _event(cmd: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


def _decision(resp: dict) -> str:
    return resp["hookSpecificOutput"]["permissionDecision"]


def test_policy_cache_invalidates_on_change(tmp_path: Path) -> None:
    adir = paths_for_run(cwd=tmp_path).tracewall_dir
    cache = daemon.PolicyCache()

    first = cache.get(adir)            # no policy file yet
    assert first is cache.get(adir)    # same object → not re-read

    enforce.save_active_policy(adir, {"rules": [
        {"id": "r1", "decision": "block", "match": {"kind": "command", "binary": "curl"}, "reason": "x"}
    ]})
    reloaded = cache.get(adir)
    assert reloaded is not first       # mtime changed → re-read
    assert reloaded.get("rules")


def test_handle_request_matches_in_process_hook(tmp_path: Path) -> None:
    cache = daemon.PolicyCache()
    for cmd, expected in [("cat .env", "deny"), ("git status", "allow")]:
        req = {"op": "decide", "stdin": _event(cmd), "cwd": str(tmp_path),
               "ask_mode": "native", "source": "claude-code"}
        via_daemon = _decision(daemon.handle_request(req, cache))
        in_process = _decision(hook.run_pre(_event(cmd), tmp_path, source="claude-code"))
        assert via_daemon == in_process == expected


def test_uds_roundtrip_ping_and_decide(tmp_path: Path) -> None:
    sock = _short_sock()
    server = daemon._UDSServer(sock, daemon.PolicyCache())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert daemon.is_running(sock_path=sock) is True

        deny = daemon.request({"op": "decide", "stdin": _event("cat .env"),
                               "cwd": str(tmp_path), "source": "claude-code"}, sock_path=sock)
        assert _decision(deny) == "deny"

        allow = daemon.request({"op": "decide", "stdin": _event("ls -la"),
                                "cwd": str(tmp_path), "source": "claude-code"}, sock_path=sock)
        assert _decision(allow) == "allow"
    finally:
        server.shutdown(); server.server_close()

    # client returns None cleanly once the daemon is gone (hook can fall back)
    assert daemon.request({"op": "ping"}, sock_path=sock) is None


def test_warm_decide_latency_under_20ms(tmp_path: Path) -> None:
    sock = _short_sock()
    server = daemon._UDSServer(sock, daemon.PolicyCache())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        payload = {"op": "decide", "stdin": _event("npm install left-pad"),
                   "cwd": str(tmp_path), "source": "claude-code"}
        daemon.request(payload, sock_path=sock)  # warm up
        samples = []
        for _ in range(50):
            t0 = time.perf_counter()
            daemon.request(payload, sock_path=sock)
            samples.append(time.perf_counter() - t0)
        median_ms = statistics.median(samples) * 1000
        assert median_ms < 20.0, f"median warm decide {median_ms:.2f}ms exceeds 20ms"
    finally:
        server.shutdown(); server.server_close()
