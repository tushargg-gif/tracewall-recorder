from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
import fnmatch

from agentproof.contracts import TaskContract
from agentproof.events import is_secret_key, redact_secrets


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    severity: str
    violations: list[dict[str, Any]]
    approval_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "severity": self.severity,
            "violations": self.violations,
            "approval_required": self.approval_required,
        }


def evaluate_mcp_request(
    contract: TaskContract,
    server_name: str,
    method: str,
    params: dict[str, Any],
    control_mode: str,
) -> PolicyDecision:
    policy = contract.mcp_policy or {}
    violations: list[dict[str, Any]] = []
    tool_name = tool_name_from_request(method, params)
    resource_uri = resource_uri_from_request(method, params)
    arguments = dict(params.get("arguments") or {}) if isinstance(params.get("arguments"), dict) else params

    allowed_tools = string_list(policy.get("allowed_tool_names"))
    forbidden_tools = string_list(policy.get("forbidden_tool_names"))
    approval_tools = string_list(policy.get("approval_required_tools"))
    allowed_domains = string_list(policy.get("allowed_domains"))
    forbidden_domains = string_list(policy.get("forbidden_domains"))
    forbidden_resources = string_list(policy.get("forbidden_resource_patterns"))

    if tool_name:
        if allowed_tools and tool_name not in allowed_tools:
            violations.append(violation("mcp_tool_not_allowed", "high", {"tool_name": tool_name, "allowed_tool_names": allowed_tools}))
        if tool_name in forbidden_tools:
            violations.append(violation("mcp_forbidden_tool", "critical", {"tool_name": tool_name}))

    if resource_uri:
        matched_patterns = [pattern for pattern in forbidden_resources if fnmatch.fnmatch(resource_uri, pattern)]
        if matched_patterns:
            violations.append(violation("mcp_forbidden_resource", "critical", {"resource_uri": resource_uri, "patterns": matched_patterns}))

    urls = collect_urls(params)
    if allowed_domains:
        outside = [url for url in urls if not domain_matches_any(hostname(url), allowed_domains)]
        if outside:
            violations.append(violation("mcp_domain_not_allowed", "high", {"urls": outside, "allowed_domains": allowed_domains}))
    if forbidden_domains:
        forbidden = [url for url in urls if domain_matches_any(hostname(url), forbidden_domains)]
        if forbidden:
            violations.append(violation("mcp_forbidden_domain", "critical", {"urls": forbidden, "forbidden_domains": forbidden_domains}))

    if contains_secret_key(arguments):
        violations.append(violation("mcp_secret_argument", "critical", {"argument_keys": secret_key_paths(arguments)}))

    needs_approval = bool(tool_name and tool_name in approval_tools)
    if needs_approval:
        violations.append(violation("mcp_approval_required", "high", {"tool_name": tool_name}))

    severity = highest_severity([item["severity"] for item in violations])
    action = "allow"
    if control_mode == "block_critical" and severity == "critical":
        action = "block"
    elif control_mode == "approval_gates" and (needs_approval or severity in {"critical", "high"}):
        action = "approval_required"

    return PolicyDecision(
        action=action,
        severity=severity,
        violations=violations,
        approval_required=action == "approval_required",
    )


def tool_name_from_request(method: str, params: dict[str, Any]) -> str:
    if method == "tools/call":
        return str(params.get("name") or "")
    return ""


def resource_uri_from_request(method: str, params: dict[str, Any]) -> str:
    if method == "resources/read":
        return str(params.get("uri") or "")
    return ""


def method_event_type(method: str, suffix: str | None = None) -> str:
    mapping = {
        "initialize": "mcp.initialize",
        "tools/list": "mcp.tools.list",
        "tools/call": "mcp.tool.call",
        "resources/list": "mcp.resources.list",
        "resources/read": "mcp.resource.read",
        "prompts/list": "mcp.prompts.list",
        "prompts/get": "mcp.prompt.get",
    }
    base = mapping.get(method, "mcp.request")
    if base == "mcp.tool.call" and suffix:
        return f"{base}.{suffix}"
    return base


def decision_event_payload(
    server_name: str,
    method: str,
    params: dict[str, Any],
    decision: PolicyDecision,
) -> dict[str, Any]:
    return {
        "server_name": server_name,
        "method": method,
        "tool_name": tool_name_from_request(method, params),
        "resource_uri": resource_uri_from_request(method, params),
        "decision": decision.to_dict(),
        "params": redact_secrets(params),
    }


def block_error(request_id: Any, message: str = "AgentProof blocked critical MCP policy violation.") -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": message}}


def approval_error(request_id: Any, message: str = "AgentProof approval was denied or timed out.") -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32002, "message": message}}


def violation(policy_id: str, severity: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"policy_id": policy_id, "severity": severity, "evidence": evidence}


def highest_severity(severities: list[str]) -> str:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    if not severities:
        return "none"
    return max(severities, key=lambda item: order.get(item, 0))


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    return [str(value)]


def collect_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            urls.extend(collect_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.extend(collect_urls(item))
    elif isinstance(value, str) and value.startswith(("http://", "https://")):
        urls.append(value)
    return urls


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def domain_matches(hostname_value: str, pattern: str) -> bool:
    pattern = pattern.lower()
    return hostname_value == pattern or hostname_value.endswith("." + pattern)


def domain_matches_any(hostname_value: str, patterns: list[str]) -> bool:
    return any(domain_matches(hostname_value, pattern) for pattern in patterns)


def contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if is_secret_key(str(key)) or contains_secret_key(item):
                return True
    elif isinstance(value, list):
        return any(contains_secret_key(item) for item in value)
    return False


def secret_key_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if is_secret_key(str(key)):
                paths.append(path)
            paths.extend(secret_key_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(secret_key_paths(item, f"{prefix}[{index}]"))
    return paths
