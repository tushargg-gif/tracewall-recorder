from __future__ import annotations

from typing import Any


def check(
    name: str,
    status: str,
    message: str,
    evidence: dict[str, Any] | None = None,
    policy_id: str | None = None,
    severity: str = "medium",
    action_taken: str = "flagged",
    category: str = "general",
) -> dict[str, Any]:
    payload = {
        "name": name,
        "status": status,
        "message": message,
        "severity": severity,
        "category": category,
        "evidence": evidence or {},
    }
    if policy_id:
        payload["policy_id"] = policy_id
        payload["action_taken"] = action_taken
    return payload


def sanitize_name(value: str) -> str:
    sanitized = "".join(char if char.isalnum() else "_" for char in value)
    return sanitized.strip("_").lower() or "item"
