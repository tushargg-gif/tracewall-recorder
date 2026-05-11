from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyViolation:
    policy_id: str
    severity: str
    message: str
    evidence: dict[str, Any]
    action_taken: str = "flagged"

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
            "action_taken": self.action_taken,
        }


def violations_from_checks(checks: list[dict[str, Any]]) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for check in checks:
        if check.get("status") not in {"failed", "warning"}:
            continue
        policy_id = check.get("policy_id")
        if not policy_id:
            continue
        violations.append(
            PolicyViolation(
                policy_id=str(policy_id),
                severity=str(check.get("severity") or "medium"),
                message=str(check.get("message") or check.get("name")),
                evidence=dict(check.get("evidence") or {}),
                action_taken=str(check.get("action_taken") or "flagged"),
            )
        )
    return violations
