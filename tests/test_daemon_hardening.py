from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from agentproof import enforce
from agentproof.daemon import PolicyCache, _UDSServer
from agentproof.events import verify_event_chain

ALLOW_CURL = {"id": "r1", "decision": "allow", "match": {"kind": "command", "binary": "curl"}}
BLOCK_SECRET = {"id": "r2", "decision": "block", "match": {"kind": "command", "touches_secret": True}}


def _ap(tmp_path: Path) -> Path:
    d = tmp_path / ".agentproof"
    d.mkdir()
    return d


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_world_writable_policy_is_not_trusted(tmp_path: Path):
    ap = _ap(tmp_path)
    enforce.save_active_policy(ap, {"rules": [ALLOW_CURL]})
    assert enforce.load_active_policy(ap)["rules"], "a normal-perms policy should load"

    os.chmod(enforce.policy_path(ap), 0o666)
    loaded = enforce.load_active_policy(ap)
    assert loaded["rules"] == []          # tampered allowlist not honored
    assert loaded.get("untrusted") is True


def test_policy_fingerprint_tracks_content(tmp_path: Path):
    ap = _ap(tmp_path)
    assert enforce.policy_fingerprint(ap) == "none"
    enforce.save_active_policy(ap, {"rules": []})
    fp_empty = enforce.policy_fingerprint(ap)
    enforce.accept_rules(ap, [BLOCK_SECRET])
    assert enforce.policy_fingerprint(ap) not in (fp_empty, "none")


def test_record_policy_event_is_hash_chained(tmp_path: Path):
    ap = _ap(tmp_path)
    enforce.save_active_policy(ap, {"rules": []})
    from agentproof.recorder import record_policy_event
    record_policy_event(ap, "policy.changed", {"fingerprint": "a"})
    record_policy_event(ap, "policy.changed", {"fingerprint": "b"})
    events = _read_jsonl(ap / "policy-events.jsonl")
    assert len(events) == 2
    assert events[1]["prev_event_hash"] == events[0]["event_hash"]
    assert verify_event_chain(events)["valid"] is True


def test_daemon_records_policy_change(tmp_path: Path):
    ap = _ap(tmp_path)
    enforce.save_active_policy(ap, {"rules": []})
    cache = PolicyCache()
    cache.get(ap)                                   # first observation: no change logged
    assert not (ap / "policy-events.jsonl").exists()

    enforce.accept_rules(ap, [BLOCK_SECRET])        # policy changes
    os.utime(enforce.policy_path(ap), (time.time() + 5, time.time() + 5))  # force cache miss
    cache.get(ap)

    events = _read_jsonl(ap / "policy-events.jsonl")
    assert any(e["event_type"] == "policy.changed" for e in events)
    assert verify_event_chain(events)["valid"] is True


def test_daemon_records_rejection_of_world_writable_policy(tmp_path: Path):
    ap = _ap(tmp_path)
    enforce.save_active_policy(ap, {"rules": [ALLOW_CURL]})
    os.chmod(enforce.policy_path(ap), 0o666)
    PolicyCache().get(ap)
    events = _read_jsonl(ap / "policy-events.jsonl")
    assert any(e["event_type"] == "policy.rejected" for e in events)


def test_decision_socket_is_owner_only():
    # AF_UNIX paths are capped (~108 chars); keep it short regardless of tmp depth.
    sock = f"/tmp/apd-{uuid.uuid4().hex[:8]}.sock"
    server = _UDSServer(sock, PolicyCache())
    try:
        assert oct(os.stat(sock).st_mode & 0o777) == oct(0o600)
    finally:
        server.server_close()
        if os.path.exists(sock):
            os.unlink(sock)
