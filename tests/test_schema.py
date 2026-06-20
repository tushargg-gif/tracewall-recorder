from __future__ import annotations

import json
from pathlib import Path

from agentproof import recorder
from agentproof.events import (
    EVENT_SCHEMA_V1,
    normalize_event,
    validate_event,
    verify_event_chain,
    verify_event_stream,
)
from agentproof.hook import run_pre

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "schema" / "agent-action-event.v1.json"

# One representative event_type from each writer channel. Every writer funnels
# through events.normalize_event, so validating these covers the write paths.
WRITER_EVENTS = [
    ("command_started", {"command": "cat .env"}),                              # recorder / hook (Bash)
    ("policy.decision", {"decision": {"action": "block"}}),                    # hook / daemon
    ("mcp.tool.call.started", {"server_name": "fs",
                               "request": {"params": {"name": "read"}}}),      # mcp_stdio proxy
    ("os.file.denied", {"path": "/p/.env", "operation": "read",
                        "source": "openclaw"}),                                # guard (sandbox denial)
    ("process.exec", {"source": "openclaw", "path": "/usr/bin/curl"}),         # observe (effect)
]


def test_published_schema_matches_canonical():
    # The .json artifact (for external tooling) must never drift from the dict
    # the code actually validates against.
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == EVENT_SCHEMA_V1


def test_normalize_event_stamps_v1_and_validates():
    event = normalize_event("run_x", "command_started", {"command": "ls"})
    assert event["schema_version"] == "1"
    assert validate_event(event) == []


def test_every_writer_event_type_is_v1_valid_and_chains():
    prev = None
    chain = []
    for event_type, payload in WRITER_EVENTS:
        event = normalize_event("run_x", event_type, payload, prev_event_hash=prev)
        assert validate_event(event) == [], (event_type, validate_event(event))
        prev = event["event_hash"]
        chain.append(event)
    assert verify_event_chain(chain)["valid"] is True


def test_real_recorded_events_validate(tmp_path: Path):
    # Drive the real on-disk write path (the Claude Code hook), then validate
    # every event that actually landed in the JSONL log.
    run_pre(json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}}), tmp_path)
    run_id = recorder.latest_run_id(tmp_path)
    events = recorder.read_events(run_id, tmp_path)
    assert events, "hook should have recorded at least one event"
    for event in events:
        assert validate_event(event) == [], event
    assert verify_event_chain(events)["valid"] is True


def test_malformed_events_are_rejected():
    missing = {"event_id": "x", "run_id": "r", "event_type": "t", "timestamp": "now",
               "payload": {}, "prev_event_hash": None, "event_hash": "h"}
    assert "missing required field: schema_version" in validate_event(missing)

    wrong_version = normalize_event("r", "t", {})
    wrong_version["schema_version"] = "2"
    assert any("schema_version" in problem for problem in validate_event(wrong_version))

    wrong_type = normalize_event("r", "t", {})
    wrong_type["payload"] = "not-an-object"
    assert any("payload" in problem for problem in validate_event(wrong_type))


def _chain(n: int = 3):
    prev = None
    out = []
    for i in range(n):
        event = normalize_event("run_x", "command_started", {"command": f"echo {i}"}, prev_event_hash=prev)
        prev = event["event_hash"]
        out.append(event)
    return out


def test_ingest_accepts_a_valid_chain():
    result = verify_event_stream(_chain())
    assert result["accepted"] is True
    assert result["event_count"] == 3


def test_ingest_rejects_empty_stream():
    assert verify_event_stream([])["accepted"] is False


def test_ingest_rejects_tampered_payload():
    # Mutating a payload after it was hashed must break the chain on ingest.
    chain = _chain()
    chain[1]["payload"] = {"command": "rm -rf /"}
    result = verify_event_stream(chain)
    assert result["accepted"] is False
    assert "chain" in result["reason"] and result["index"] == 1


def test_ingest_rejects_malformed_event():
    chain = _chain()
    del chain[1]["schema_version"]
    result = verify_event_stream(chain)
    assert result["accepted"] is False
    assert "invalid" in result["reason"]
