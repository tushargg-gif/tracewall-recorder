from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import fnmatch
import json

import yaml


DEFAULT_TASK: dict[str, Any] = {
    "task_id": "TASK-001",
    "title": "Describe the coding-agent task here",
    "repository": "",
    "allowed_paths": ["src/**", "tests/**"],
    "forbidden_paths": [".env", ".env.*", "infra/**", "secrets/**"],
    "allowed_commands": ["pytest", "npm test", "npm run lint", "npm run typecheck"],
    "forbidden_actions": ["install_new_package", "access_secrets"],
    "success_criteria": [
        "targeted regression test added",
        "relevant test suite passes",
        "no unrelated files changed",
        "no new dependency added",
    ],
    "verification": {
        "tests": ["pytest"],
        "lint": [],
        "typecheck": [],
        "build": [],
    },
    "script_policy": {
        "required_commands": [],
        "forbidden_command_patterns": [],
        "max_command_duration_seconds": None,
    },
    "expected_data": [],
    "expected_artifacts": [],
    "network_policy": {
        "allowed_domains": [],
        "forbidden_domains": [],
        "require_https": False,
        "max_requests": None,
    },
    "browser_policy": {
        "required_visited_domains": [],
        "forbidden_domains": [],
        "expected_final_url": "",
        "required_final_text": [],
    },
    "mcp_policy": {
        "allowed_tool_names": [],
        "forbidden_tool_names": [],
        "allowed_domains": [],
        "forbidden_domains": [],
        "forbidden_resource_patterns": [],
        "approval_required_tools": [],
        "max_tool_call_duration_seconds": None,
        "approval_timeout_seconds": 300,
    },
    "policy_template": "",
    "policy_version": 1,
    "policy_versions": [],
    "worker_scopes": {},
    "risk_level": "medium",
    "human_approval_required": True,
}


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    title: str
    repository: str = ""
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    allowed_commands: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    verification: dict[str, list[str]] = field(default_factory=dict)
    script_policy: dict[str, Any] = field(default_factory=dict)
    expected_data: list[dict[str, Any]] = field(default_factory=list)
    expected_artifacts: list[dict[str, Any]] = field(default_factory=list)
    network_policy: dict[str, Any] = field(default_factory=dict)
    browser_policy: dict[str, Any] = field(default_factory=dict)
    mcp_policy: dict[str, Any] = field(default_factory=dict)
    policy_template: str = ""
    policy_version: int = 1
    policy_versions: list[dict[str, Any]] = field(default_factory=list)
    worker_scopes: dict[str, dict[str, Any]] = field(default_factory=dict)
    risk_level: str = "medium"
    human_approval_required: bool = True

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TaskContract":
        data = dict(DEFAULT_TASK)
        data.update(raw or {})
        verification = data.get("verification") or {}
        normalized_verification = {
            str(key): _string_list(value) for key, value in verification.items()
        }
        return cls(
            task_id=str(data.get("task_id") or "TASK-001"),
            title=str(data.get("title") or "Untitled agent task"),
            repository=str(data.get("repository") or ""),
            allowed_paths=_string_list(data.get("allowed_paths")),
            forbidden_paths=_string_list(data.get("forbidden_paths")),
            allowed_commands=_string_list(data.get("allowed_commands")),
            forbidden_actions=_string_list(data.get("forbidden_actions")),
            success_criteria=_string_list(data.get("success_criteria")),
            verification=normalized_verification,
            script_policy=_dict(data.get("script_policy")),
            expected_data=_dict_list(data.get("expected_data")),
            expected_artifacts=_dict_list(data.get("expected_artifacts")),
            network_policy=_dict(data.get("network_policy")),
            browser_policy=_dict(data.get("browser_policy")),
            mcp_policy=_dict(data.get("mcp_policy")),
            policy_template=str(data.get("policy_template") or ""),
            policy_version=_int(data.get("policy_version"), default=1),
            policy_versions=_dict_list(data.get("policy_versions")),
            worker_scopes=_nested_dict(data.get("worker_scopes")),
            risk_level=str(data.get("risk_level") or "medium"),
            human_approval_required=bool(data.get("human_approval_required", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "repository": self.repository,
            "allowed_paths": self.allowed_paths,
            "forbidden_paths": self.forbidden_paths,
            "allowed_commands": self.allowed_commands,
            "forbidden_actions": self.forbidden_actions,
            "success_criteria": self.success_criteria,
            "verification": self.verification,
            "script_policy": self.script_policy,
            "expected_data": self.expected_data,
            "expected_artifacts": self.expected_artifacts,
            "network_policy": self.network_policy,
            "browser_policy": self.browser_policy,
            "mcp_policy": self.mcp_policy,
            "policy_template": self.policy_template,
            "policy_version": self.policy_version,
            "policy_versions": self.policy_versions,
            "worker_scopes": self.worker_scopes,
            "risk_level": self.risk_level,
            "human_approval_required": self.human_approval_required,
        }

    def path_is_allowed(self, relative_path: str) -> bool:
        if not self.allowed_paths:
            return True
        return any(match_path(relative_path, pattern) for pattern in self.allowed_paths)

    def path_is_forbidden(self, relative_path: str) -> bool:
        return any(match_path(relative_path, pattern) for pattern in self.forbidden_paths)

    def command_is_allowed(self, command: str) -> bool:
        if not self.allowed_commands:
            return True
        return any(match_command(command, pattern) for pattern in self.allowed_commands)


def load_contract(path: Path) -> TaskContract:
    if not path.exists():
        raise FileNotFoundError(f"Task contract not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(raw_text)
    else:
        raw = yaml.safe_load(raw_text) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Task contract must be a mapping: {path}")
    return TaskContract.from_mapping(raw)


def write_default_contract(path: Path, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(DEFAULT_TASK, sort_keys=False), encoding="utf-8")
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    return [str(value)]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _nested_dict(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            output[str(key)] = dict(item)
    return output


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [dict(value)]
    if isinstance(value, list | tuple):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def match_path(path: str, pattern: str) -> bool:
    normalized_path = normalize_path(path)
    normalized_pattern = normalize_path(pattern)
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3]
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    return fnmatch.fnmatch(normalized_path, normalized_pattern)


def match_command(command: str, pattern: str) -> bool:
    command = " ".join(command.strip().split())
    pattern = " ".join(pattern.strip().split())
    if command == pattern:
        return True
    if command.startswith(pattern + " "):
        return True
    return fnmatch.fnmatch(command, pattern)
