from __future__ import annotations

from datetime import datetime
from typing import Any
import hashlib
import json
import uuid


REDACTED = "[REDACTED]"
SECRET_KEYS = (
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "cookie",
    "set-cookie",
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_event(
    run_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    timestamp: str | None = None,
    event_id: str | None = None,
    prev_event_hash: str | None = None,
) -> dict[str, Any]:
    if not event_type or not event_type.strip():
        raise ValueError("Event type is required.")
    event = {
        "event_id": event_id or f"evt_{uuid.uuid4().hex[:12]}",
        "run_id": run_id,
        "event_type": event_type.strip(),
        "timestamp": timestamp or now_iso(),
        "payload": redact_secrets(payload or {}),
        "prev_event_hash": prev_event_hash,
    }
    event["event_hash"] = event_hash(event)
    return event


def parse_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Payload must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Payload JSON must be an object.")
    return payload


def event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def event_hash(event: dict[str, Any]) -> str:
    material = {key: value for key, value in event.items() if key != "event_hash"}
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def value_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if is_secret_key(str(key)):
                redacted[key] = {"redacted": True, "sha256": value_hash(item)}
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(secret in lowered for secret in SECRET_KEYS)


def verify_event_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    previous_hash: str | None = None
    for index, event in enumerate(events):
        expected_previous = event.get("prev_event_hash")
        actual_hash = event.get("event_hash")
        if expected_previous != previous_hash:
            return {
                "valid": False,
                "index": index,
                "reason": "previous hash mismatch",
                "expected_prev_event_hash": previous_hash,
                "actual_prev_event_hash": expected_previous,
            }
        if actual_hash != event_hash(event):
            return {
                "valid": False,
                "index": index,
                "reason": "event hash mismatch",
                "expected_event_hash": event_hash(event),
                "actual_event_hash": actual_hash,
            }
        previous_hash = actual_hash
    return {"valid": True, "event_count": len(events), "last_event_hash": previous_hash}
