from __future__ import annotations

import json
from pathlib import Path

from tracewall import enforce, recorder
from tracewall.hook import run_pre
from tracewall.recommend import recommend_policy

SRC = Path(__file__).resolve().parents[1] / "src" / "tracewall"

# Outbound network *clients*. The daemon serving localhost HTTP (http.server) and
# the UDS socket are local IPC, not these — so they're intentionally not listed.
BANNED = ("urllib.request", "urlopen", "import requests", "import httpx",
          "http.client", "aiohttp", "socket.create_connection")


def test_no_outbound_network_client_in_sources():
    offenders = []
    for py in SRC.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        offenders += [(py.name, token) for token in BANNED if token in text]
    assert offenders == [], f"outbound network client found on a local path: {offenders}"


def test_full_loop_runs_offline_with_no_account(tmp_path: Path):
    # record + decide via the hook — no account, no network, fresh project.
    decision = run_pre(json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat .env"}}), tmp_path)
    assert decision and isinstance(decision, dict)

    run_id = recorder.latest_run_id(tmp_path)
    assert recorder.read_events(run_id, tmp_path), "the action should be recorded locally"

    # recommend runs locally and returns a result (no service call).
    assert isinstance(recommend_policy(run_id, tmp_path), dict)

    # enforce: accept a rule and prove it blocks — entirely local.
    tracewall_dir = recorder.paths_for_run(cwd=tmp_path).tracewall_dir
    enforce.accept_rules(tracewall_dir, [{"id": "b", "decision": "block",
                                           "match": {"kind": "command", "touches_secret": True}}])
    policy = enforce.load_active_policy(tracewall_dir)
    verdict = enforce.evaluate_action(enforce.action_from_command("cat .env"), policy)
    assert verdict["decision"] == "block"


def test_home_override_is_the_only_env_knob(tmp_path: Path):
    # The one environment variable we read is a path override, never a gate.
    from tracewall import daemon
    import os
    os.environ["TRACEWALL_HOME"] = str(tmp_path / "home")
    try:
        assert daemon.home() == tmp_path / "home"
    finally:
        del os.environ["TRACEWALL_HOME"]
