from __future__ import annotations

from datetime import datetime
from typing import Any
import hashlib
import json
import re
import uuid


SCHEMA_VERSION = "1"

# The frozen v1 event contract. `schema/agent-action-event.v1.json` is this same
# shape published as standalone JSON Schema for external tooling; a test asserts
# the two never drift. This dict is the single source of truth.
EVENT_SCHEMA_V1: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://tracewall.dev/schema/agent-action-event.v1.json",
    "title": "tracewall Agent Action Event",
    "description": "One hash-chained record of a single agent action (intent or effect).",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "event_id", "run_id", "event_type",
        "timestamp", "payload", "prev_event_hash", "event_hash",
    ],
    "properties": {
        "schema_version": {"const": "1", "description": "Event contract version."},
        "event_id": {"type": "string", "description": "Unique id, e.g. evt_ab12cd34ef56."},
        "run_id": {"type": "string", "description": "The run this event belongs to."},
        "event_type": {"type": "string", "minLength": 1, "description": "Dotted action/lifecycle type, e.g. command_started, mcp.tool.call.started, os.file.denied, process.exec, policy.decision."},
        "timestamp": {"type": "string", "description": "ISO 8601 local timestamp."},
        "payload": {"type": "object", "description": "Event-type-specific body; secrets are redacted before write."},
        "prev_event_hash": {"type": ["string", "null"], "description": "event_hash of the previous event in the run, or null for the first."},
        "event_hash": {"type": "string", "description": "sha256 over the canonical event minus this field; links the chain."},
    },
}


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
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id or f"evt_{uuid.uuid4().hex[:12]}",
        "run_id": run_id,
        "event_type": event_type.strip(),
        "timestamp": timestamp or now_iso(),
        "payload": redact_secrets(mask_secret_material(payload or {})),
        "prev_event_hash": prev_event_hash,
    }
    event["event_hash"] = event_hash(event)
    return event


def validate_event(event: Any) -> list[str]:
    """Check an event against the frozen v1 contract; return a list of problems
    (empty == valid). Deliberately minimal — required keys, declared types, and
    the schema_version const — so it needs no JSON-Schema engine. The published
    .json is full JSON Schema for anyone who wants to validate with standard tools.
    """
    if not isinstance(event, dict):
        return ["event is not an object"]
    errors: list[str] = []
    for key in EVENT_SCHEMA_V1["required"]:
        if key not in event:
            errors.append(f"missing required field: {key}")
    for key, spec in EVENT_SCHEMA_V1["properties"].items():
        if key not in event:
            continue
        value = event[key]
        if "const" in spec and value != spec["const"]:
            errors.append(f"{key} must equal {spec['const']!r}")
        if "type" in spec and not _json_type_ok(value, spec["type"]):
            errors.append(f"{key} has wrong type ({type(value).__name__})")
    return errors


_JSON_TYPES = {"string": str, "object": dict, "array": list, "integer": int, "number": (int, float), "boolean": bool}


def _json_type_ok(value: Any, types: Any) -> bool:
    for name in ([types] if isinstance(types, str) else types):
        if name == "null" and value is None:
            return True
        if name in ("integer", "number") and isinstance(value, _JSON_TYPES[name]) and not isinstance(value, bool):
            return True
        if name not in ("null", "integer", "number") and isinstance(value, _JSON_TYPES.get(name, ())):
            return True
    return False


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
            if is_secret_key(str(key)) and not isinstance(item, bool):
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


# Inline secret *material* (the values themselves), masked at write so the log
# never stores or hashes a raw credential. We deliberately do NOT mask sensitive
# *paths* like ".env" or "id_rsa": recording that an agent touched them is the
# point of the audit — the secret is the file's contents, which aren't here.
# Bounded + best-effort by design (north-star: honest, bounded claims).
_SECRET_MATERIAL = [
    (re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----[\s\S]*?-----END[^-]*PRIVATE KEY-----"), "[REDACTED-PRIVATE-KEY]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"), "[REDACTED-SECRET]"),
]


def mask_secret_material(value: Any) -> Any:
    """Recursively mask inline credential material (tokens, private keys) in
    string values. Idempotent. Used by `normalize_event` (so masking happens
    before the event is hashed) and by `redact_for_sync`."""
    if isinstance(value, dict):
        return {key: mask_secret_material(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_secret_material(item) for item in value]
    if isinstance(value, str):
        masked = value
        for pattern, replacement in _SECRET_MATERIAL:
            masked = pattern.sub(replacement, masked)
        return masked
    return value


def redact_for_sync(event: dict[str, Any]) -> dict[str, Any]:
    """The explicit pre-upload scrub (P0.7). Because redaction already happens at
    write time (`normalize_event`), on a correctly-written event this is a no-op
    and `event_hash` stays valid — the local hash-chained log never held a raw
    secret, so the mirror can verify the chain. It runs the same mask here as a
    fail-safe before anything leaves the machine."""
    synced = dict(event)
    synced["payload"] = mask_secret_material(event.get("payload") or {})
    return synced


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


def verify_event_stream(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Server-side ingest gate (P0.4). The cloud is a mirror: it accepts an
    uploaded run only if every event is v1-valid *and* the hash chain is intact,
    rejecting a malformed, broken, or forked chain. Pure (no I/O); reuses
    `validate_event` + `verify_event_chain`. This is the seed of P2 sync.
    """
    if not isinstance(events, list) or not events:
        return {"accepted": False, "reason": "empty or non-list event stream", "event_count": 0}
    for index, event in enumerate(events):
        problems = validate_event(event)
        if problems:
            return {"accepted": False, "reason": f"event {index} invalid: {problems[0]}",
                    "index": index, "event_count": len(events)}
    chain = verify_event_chain(events)
    if not chain.get("valid"):
        return {"accepted": False, "reason": f"chain broken: {chain.get('reason')}",
                "index": chain.get("index"), "event_count": len(events)}
    return {"accepted": True, "event_count": len(events), "last_event_hash": chain.get("last_event_hash")}
