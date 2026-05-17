from __future__ import annotations

from copy import deepcopy
from typing import Any


PACKAGE_FILES = [
    "Cargo.lock",
    "Cargo.toml",
    "Gemfile",
    "Gemfile.lock",
    "Pipfile",
    "Pipfile.lock",
    "go.mod",
    "go.sum",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "yarn.lock",
]


def build_policy_from_template(
    template_id: str,
    task_id: str,
    title: str,
    workers: list[dict[str, Any]],
    test_command: str,
) -> dict[str, Any]:
    if template_id != "docs_only":
        raise ValueError(f"Unknown policy template: {template_id}")
    worker_scopes = {
        str(worker["name"]): worker_scope_from_role(worker, test_command)
        for worker in workers
    }
    contract = {
        "task_id": task_id,
        "title": title,
        "repository": "agent-demo/.workspace",
        "allowed_paths": ["README.md", "docs/**"],
        "forbidden_paths": [
            ".env",
            ".env.*",
            "secrets/**",
            "infra/**",
            ".github/workflows/**",
            "auth/**",
            "security/**",
            *PACKAGE_FILES,
        ],
        "allowed_commands": [test_command],
        "forbidden_actions": [
            "install_new_package",
            "access_sensitive_material",
            "modify_ci",
            "network_call",
            "modify_auth",
            "modify_security",
        ],
        "success_criteria": [
            "README demo section updated",
            "docs demo note added",
            "examples demo note added after policy amendment",
            "exact test command recorded",
            "no dependency file changed",
            "no forbidden paths changed",
            "no network calls recorded",
        ],
        "verification": {"tests": [test_command]},
        "network_policy": {
            "allowed_domains": [],
            "forbidden_domains": [],
            "require_https": True,
            "max_requests": 0,
        },
        "mcp_policy": {"forbidden_tool_names": ["delete_all"]},
        "policy_template": template_id,
        "policy_version": 1,
        "policy_versions": [
            {
                "version": 1,
                "reason": "Initial policy from docs_only template.",
                "allowed_paths": ["README.md", "docs/**"],
            }
        ],
        "worker_scopes": worker_scopes,
        "risk_level": "medium",
        "human_approval_required": True,
    }
    return {
        "policy_id": task_id,
        "created_by": "Master Agent",
        "template_id": template_id,
        "task": title,
        "task_contract": contract,
    }


def worker_scope_from_role(worker: dict[str, Any], test_command: str) -> dict[str, Any]:
    role = str(worker.get("role") or "").lower()
    base = {
        "role": str(worker.get("role") or ""),
        "task": str(worker.get("task") or ""),
        "allowed_paths": [],
        "forbidden_paths": ["package.json", "pyproject.toml", "requirements.txt", ".env", ".env.*", "secrets/**"],
        "allowed_commands": [],
    }
    if role == "product":
        base["allowed_paths"] = ["docs/**"]
    elif role == "copywriter":
        base["allowed_paths"] = ["README.md"]
    elif role == "tester":
        base["allowed_commands"] = [test_command]
    elif role == "rogue":
        base["allowed_paths"] = ["docs/**"]
    return base


def apply_automatic_amendment(
    policy: dict[str, Any],
    reason: str,
    add_allowed_paths: list[str] | None = None,
    worker_scope_updates: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(policy)
    contract = updated["task_contract"]
    previous_version = int(contract.get("policy_version") or 1)
    next_version = previous_version + 1
    added_paths = add_allowed_paths or []
    contract["allowed_paths"] = unique([*string_list(contract.get("allowed_paths")), *added_paths])

    worker_scopes = dict(contract.get("worker_scopes") or {})
    scope_updates = worker_scope_updates or {}
    for agent, changes in scope_updates.items():
        scope = dict(worker_scopes.get(agent) or {})
        scope["allowed_paths"] = unique(
            [
                *string_list(scope.get("allowed_paths")),
                *string_list(changes.get("allowed_paths_add")),
            ]
        )
        scope["allowed_commands"] = unique(
            [
                *string_list(scope.get("allowed_commands")),
                *string_list(changes.get("allowed_commands_add")),
            ]
        )
        worker_scopes[agent] = scope

    contract["worker_scopes"] = worker_scopes
    contract["policy_version"] = next_version
    contract["policy_versions"] = [
        *list(contract.get("policy_versions") or []),
        {
            "version": next_version,
            "reason": reason,
            "added_allowed_paths": added_paths,
            "worker_scope_updates": scope_updates,
        },
    ]

    amendment = {
        "mode": "automatic",
        "from_version": previous_version,
        "to_version": next_version,
        "reason": reason,
        "added_allowed_paths": added_paths,
        "worker_scope_updates": scope_updates,
    }
    return updated, amendment


def policy_template_selected_payload(policy: dict[str, Any]) -> dict[str, Any]:
    contract = policy["task_contract"]
    return {
        "template_id": policy.get("template_id"),
        "task_id": contract.get("task_id"),
        "allowed_paths": contract.get("allowed_paths") or [],
        "worker_count": len(contract.get("worker_scopes") or {}),
    }


def policy_version_payload(policy: dict[str, Any]) -> dict[str, Any]:
    contract = policy["task_contract"]
    return {
        "policy_id": policy.get("policy_id"),
        "version": contract.get("policy_version"),
        "template_id": contract.get("policy_template"),
        "allowed_paths": contract.get("allowed_paths") or [],
        "worker_scopes": contract.get("worker_scopes") or {},
    }


def worker_registered_payload(agent: str, scope: dict[str, Any]) -> dict[str, Any]:
    return {"agent": agent, "scope": scope}


def worker_delegated_payload(agent: str, task: str, policy_version: int, scope: dict[str, Any]) -> dict[str, Any]:
    return {"agent": agent, "task": task, "policy_version": policy_version, "scope": scope}


def worker_completed_payload(
    agent: str,
    summary: str,
    reported_files: list[str],
    actual_changed_files: list[str],
    policy_version: int,
    scope: dict[str, Any],
    safe: bool,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "summary": summary,
        "reported_files": reported_files,
        "actual_changed_files": actual_changed_files,
        "policy_version": policy_version,
        "scope": scope,
        "safe": safe,
    }


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    return [str(value)]


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
