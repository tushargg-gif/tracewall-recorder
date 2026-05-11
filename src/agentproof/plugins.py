from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import csv
import fnmatch
import json
import struct

from agentproof.checks import check, sanitize_name
from agentproof.contracts import TaskContract, match_command
from agentproof.recorder import sha256_file


def run_verifier_plugins(
    contract: TaskContract,
    run: dict[str, Any],
    paths,
    events: list[dict[str, Any]],
    command_events: list[dict[str, Any]],
    changed_files: list[str],
) -> list[dict[str, Any]]:
    return [
        *script_checks(contract, command_events),
        *data_checks(contract, paths.project_root),
        *artifact_checks(contract, paths.project_root, events),
        *network_checks(contract, events),
        *browser_checks(contract, events),
        *mcp_checks(contract, events),
    ]


def script_checks(
    contract: TaskContract,
    command_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    policy = contract.script_policy or {}
    checks: list[dict[str, Any]] = []
    if not policy:
        return checks

    required_commands = string_list(policy.get("required_commands"))
    forbidden_patterns = string_list(policy.get("forbidden_command_patterns"))
    max_duration = policy.get("max_command_duration_seconds")
    command_texts = [str(command.get("command") or "") for command in command_events]

    if required_commands:
        missing = [
            required
            for required in required_commands
            if not any(match_command(command, required) for command in command_texts)
        ]
        checks.append(
            check(
                "script_required_commands",
                "failed" if missing else "passed",
                "Required script commands were not recorded."
                if missing
                else "All required script commands were recorded.",
                {"missing": missing, "required": required_commands},
                policy_id="script_required_command_missing",
                severity="medium",
                category="script",
            )
        )

    if forbidden_patterns:
        forbidden = [
            command
            for command in command_texts
            if any(fnmatch.fnmatch(command, pattern) for pattern in forbidden_patterns)
        ]
        checks.append(
            check(
                "script_forbidden_commands",
                "failed" if forbidden else "passed",
                "Forbidden script commands were recorded."
                if forbidden
                else "No forbidden script commands were recorded.",
                {"commands": forbidden, "patterns": forbidden_patterns},
                policy_id="script_forbidden_command",
                severity="high",
                category="script",
            )
        )

    if max_duration is not None:
        try:
            max_duration_float = float(max_duration)
        except (TypeError, ValueError):
            max_duration_float = None
        if max_duration_float is not None:
            slow_commands = [
                command
                for command in command_events
                if float(command.get("duration_seconds") or 0) > max_duration_float
            ]
            checks.append(
                check(
                    "script_command_duration",
                    "warning" if slow_commands else "passed",
                    "One or more commands exceeded the duration policy."
                    if slow_commands
                    else "Recorded commands are within the duration policy.",
                    {
                        "max_command_duration_seconds": max_duration_float,
                        "commands": [command.get("command") for command in slow_commands],
                    },
                    policy_id="script_command_too_slow",
                    severity="medium",
                    category="script",
                )
            )

    return checks


def data_checks(contract: TaskContract, project_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for spec in contract.expected_data:
        path_value = str(spec.get("path") or "")
        if not path_value:
            continue
        relative_name = sanitize_name(path_value)
        path = project_root / path_value
        exists = path.exists() and path.is_file()
        checks.append(
            check(
                f"data_{relative_name}_exists",
                "passed" if exists else "failed",
                f"Expected data file exists: {path_value}"
                if exists
                else f"Expected data file is missing: {path_value}",
                {"path": path_value},
                policy_id="expected_data_missing",
                severity="high",
                category="data",
            )
        )
        if not exists:
            continue

        size = path.stat().st_size
        min_size = int(spec.get("min_size_bytes") or 1)
        checks.append(
            check(
                f"data_{relative_name}_size",
                "passed" if size >= min_size else "failed",
                "Data file size is within policy."
                if size >= min_size
                else "Data file is smaller than expected.",
                {"path": path_value, "size_bytes": size, "min_size_bytes": min_size},
                policy_id="expected_data_too_small",
                severity="medium",
                category="data",
            )
        )

        data_format = str(spec.get("format") or infer_data_format(path)).lower()
        if data_format == "csv":
            checks.extend(csv_checks(path, path_value, relative_name, spec))
        elif data_format == "json":
            checks.extend(json_checks(path, path_value, relative_name, spec))
        else:
            checks.append(
                check(
                    f"data_{relative_name}_format",
                    "warning",
                    f"No structured validator exists for data format: {data_format}",
                    {"path": path_value, "format": data_format},
                    policy_id="expected_data_unvalidated_format",
                    severity="low",
                    category="data",
                )
            )
    return checks


def csv_checks(
    path: Path,
    path_value: str,
    relative_name: str,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            columns = list(reader.fieldnames or [])
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [
            check(
                f"data_{relative_name}_csv_parse",
                "failed",
                "CSV data file could not be parsed.",
                {"path": path_value, "error": str(exc)},
                policy_id="expected_data_parse_failed",
                severity="high",
                category="data",
            )
        ]

    required_columns = string_list(spec.get("required_columns"))
    missing_columns = [column for column in required_columns if column not in columns]
    checks.append(
        check(
            f"data_{relative_name}_columns",
            "failed" if missing_columns else "passed",
            "CSV is missing required columns."
            if missing_columns
            else "CSV required columns are present.",
            {"path": path_value, "columns": columns, "missing_columns": missing_columns},
            policy_id="expected_data_schema_mismatch",
            severity="high",
            category="data",
        )
    )
    checks.append(row_count_check(relative_name, path_value, len(rows), spec, "csv"))
    return checks


def json_checks(
    path: Path,
    path_value: str,
    relative_name: str,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [
            check(
                f"data_{relative_name}_json_parse",
                "failed",
                "JSON data file could not be parsed.",
                {"path": path_value, "error": str(exc)},
                policy_id="expected_data_parse_failed",
                severity="high",
                category="data",
            )
        ]

    checks: list[dict[str, Any]] = []
    required_keys = string_list(spec.get("required_keys"))
    missing_keys: list[str] = []
    if isinstance(payload, dict):
        missing_keys = [key for key in required_keys if key not in payload]
    elif required_keys:
        missing_keys = required_keys
    checks.append(
        check(
            f"data_{relative_name}_keys",
            "failed" if missing_keys else "passed",
            "JSON is missing required keys."
            if missing_keys
            else "JSON required keys are present.",
            {"path": path_value, "missing_keys": missing_keys},
            policy_id="expected_data_schema_mismatch",
            severity="high",
            category="data",
        )
    )

    item_count = len(payload) if isinstance(payload, list | dict) else 1
    checks.append(row_count_check(relative_name, path_value, item_count, spec, "json"))
    return checks


def row_count_check(
    relative_name: str,
    path_value: str,
    count: int,
    spec: dict[str, Any],
    data_format: str,
) -> dict[str, Any]:
    min_rows = spec.get("min_rows", spec.get("min_items"))
    max_rows = spec.get("max_rows", spec.get("max_items"))
    too_few = min_rows is not None and count < int(min_rows)
    too_many = max_rows is not None and count > int(max_rows)
    return check(
        f"data_{relative_name}_count",
        "failed" if too_few or too_many else "passed",
        f"{data_format.upper()} row/item count is outside policy."
        if too_few or too_many
        else f"{data_format.upper()} row/item count is within policy.",
        {
            "path": path_value,
            "count": count,
            "min": min_rows,
            "max": max_rows,
        },
        policy_id="expected_data_count_mismatch",
        severity="medium",
        category="data",
    )


def artifact_checks(
    contract: TaskContract,
    project_root: Path,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    artifact_events = artifact_event_map(events)
    for spec in contract.expected_artifacts:
        path_value = str(spec.get("path") or "")
        if not path_value:
            continue
        relative_name = sanitize_name(path_value)
        path = project_root / path_value
        exists = path.exists() and path.is_file()
        checks.append(
            check(
                f"artifact_{relative_name}_exists",
                "passed" if exists else "failed",
                f"Expected artifact exists: {path_value}"
                if exists
                else f"Expected artifact is missing: {path_value}",
                {"path": path_value},
                policy_id="expected_artifact_missing",
                severity="high",
                category="artifact",
            )
        )
        if not exists:
            continue

        size = path.stat().st_size
        min_size = int(spec.get("min_size_bytes") or 1)
        checks.append(
            check(
                f"artifact_{relative_name}_size",
                "passed" if size >= min_size else "failed",
                "Artifact size is within policy."
                if size >= min_size
                else "Artifact is smaller than expected.",
                {"path": path_value, "size_bytes": size, "min_size_bytes": min_size},
                policy_id="expected_artifact_too_small",
                severity="medium",
                category="artifact",
            )
        )

        expected_hash = str(spec.get("sha256") or "")
        if expected_hash:
            digest = sha256_file(path)
            checks.append(
                check(
                    f"artifact_{relative_name}_hash",
                    "passed" if digest == expected_hash else "failed",
                    "Artifact hash matches expected value."
                    if digest == expected_hash
                    else "Artifact hash does not match expected value.",
                    {"path": path_value, "actual_sha256": digest, "expected_sha256": expected_hash},
                    policy_id="expected_artifact_hash_mismatch",
                    severity="high",
                    category="artifact",
                )
            )

        artifact_type = str(spec.get("type") or infer_artifact_type(path)).lower()
        metadata = artifact_events.get(path_value, {})
        checks.extend(media_checks(path, path_value, relative_name, artifact_type, spec, metadata))
    return checks


def media_checks(
    path: Path,
    path_value: str,
    relative_name: str,
    artifact_type: str,
    spec: dict[str, Any],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if artifact_type == "image":
        info = detect_image_info(path)
        expected_width = optional_int(spec.get("width"))
        expected_height = optional_int(spec.get("height"))
        format_ok = info is not None
        dimension_ok = True
        if info and expected_width is not None:
            dimension_ok = dimension_ok and info.get("width") == expected_width
        if info and expected_height is not None:
            dimension_ok = dimension_ok and info.get("height") == expected_height
        checks.append(
            check(
                f"artifact_{relative_name}_image",
                "passed" if format_ok and dimension_ok else "failed",
                "Image artifact matches expected media policy."
                if format_ok and dimension_ok
                else "Image artifact failed format or dimension checks.",
                {
                    "path": path_value,
                    "detected": info,
                    "expected_width": expected_width,
                    "expected_height": expected_height,
                },
                policy_id="expected_artifact_media_mismatch",
                severity="medium",
                category="artifact",
            )
        )
    elif artifact_type == "video":
        expected_duration = optional_float(spec.get("duration_seconds"))
        actual_duration = optional_float(metadata.get("duration_seconds"))
        extension_ok = path.suffix.lower() in {".mp4", ".mov", ".webm", ".avi", ".mkv"}
        duration_ok = expected_duration is None or actual_duration == expected_duration
        checks.append(
            check(
                f"artifact_{relative_name}_video",
                "passed" if extension_ok and duration_ok else "failed",
                "Video artifact matches expected media policy."
                if extension_ok and duration_ok
                else "Video artifact failed extension or metadata checks.",
                {
                    "path": path_value,
                    "metadata": metadata,
                    "expected_duration_seconds": expected_duration,
                },
                policy_id="expected_artifact_media_mismatch",
                severity="medium",
                category="artifact",
            )
        )
    return checks


def network_checks(contract: TaskContract, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    policy = contract.network_policy or {}
    network_events = [
        event
        for event in events
        if str(event.get("event_type") or "") in {"network.request", "http.request"}
    ]
    configured = network_policy_configured(policy)
    if not configured and not network_events:
        return []

    urls = [event_url(event) for event in network_events]
    urls = [url for url in urls if url]
    domains = [hostname_from_url(url) for url in urls]
    domains = [domain for domain in domains if domain]
    checks: list[dict[str, Any]] = [
        check(
            "network_events_recorded",
            "passed" if network_events else "warning",
            f"{len(network_events)} network URL event(s) recorded."
            if network_events
            else "No network URL events were recorded.",
            {"urls": urls},
            severity="low",
            category="network",
        )
    ]

    allowed_domains = string_list(policy.get("allowed_domains"))
    forbidden_domains = string_list(policy.get("forbidden_domains"))
    require_https = bool(policy.get("require_https"))
    max_requests = policy.get("max_requests")

    if allowed_domains:
        outside_allowed = [
            url for url in urls if not domain_matches_any(hostname_from_url(url), allowed_domains)
        ]
        checks.append(
            check(
                "network_allowed_domains",
                "failed" if outside_allowed else "passed",
                "Network requests included domains outside the allowlist."
                if outside_allowed
                else "All network requests matched the allowlist.",
                {"urls": outside_allowed, "allowed_domains": allowed_domains},
                policy_id="network_domain_not_allowed",
                severity="high",
                category="network",
            )
        )

    if forbidden_domains:
        forbidden = [
            url for url in urls if domain_matches_any(hostname_from_url(url), forbidden_domains)
        ]
        checks.append(
            check(
                "network_forbidden_domains",
                "failed" if forbidden else "passed",
                "Network requests included forbidden domains."
                if forbidden
                else "No forbidden network domains were requested.",
                {"urls": forbidden, "forbidden_domains": forbidden_domains},
                policy_id="network_forbidden_domain",
                severity="critical",
                category="network",
            )
        )

    if require_https:
        insecure = [url for url in urls if urlparse(url).scheme != "https"]
        checks.append(
            check(
                "network_https_required",
                "failed" if insecure else "passed",
                "Network requests included non-HTTPS URLs."
                if insecure
                else "All network requests used HTTPS.",
                {"urls": insecure},
                policy_id="network_https_required",
                severity="high",
                category="network",
            )
        )

    if max_requests is not None:
        max_requests_int = int(max_requests)
        checks.append(
            check(
                "network_request_count",
                "warning" if len(network_events) > max_requests_int else "passed",
                "Network request count exceeded policy."
                if len(network_events) > max_requests_int
                else "Network request count is within policy.",
                {"count": len(network_events), "max_requests": max_requests_int},
                policy_id="network_request_limit_exceeded",
                severity="medium",
                category="network",
            )
        )

    return checks


def browser_checks(contract: TaskContract, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    policy = contract.browser_policy or {}
    browser_events = [
        event
        for event in events
        if str(event.get("event_type") or "").startswith("browser.")
    ]
    configured = browser_policy_configured(policy)
    if not configured and not browser_events:
        return []

    navigation_urls = [
        event_url(event)
        for event in browser_events
        if str(event.get("event_type") or "") == "browser.navigate"
    ]
    navigation_urls = [url for url in navigation_urls if url]
    final_url = navigation_urls[-1] if navigation_urls else ""
    required_domains = string_list(policy.get("required_visited_domains"))
    forbidden_domains = string_list(policy.get("forbidden_domains"))
    expected_final_url = str(policy.get("expected_final_url") or "")
    required_final_text = string_list(policy.get("required_final_text"))
    all_text = "\n".join(
        str((event.get("payload") or {}).get(key) or "")
        for event in browser_events
        for key in ("text", "title", "body")
    )

    checks: list[dict[str, Any]] = [
        check(
            "browser_events_recorded",
            "passed" if browser_events else "warning",
            f"{len(browser_events)} browser event(s) recorded."
            if browser_events
            else "No browser events were recorded.",
            {"event_count": len(browser_events)},
            severity="low",
            category="browser",
        )
    ]

    if required_domains:
        missing_domains = [
            domain
            for domain in required_domains
            if not any(domain_matches(hostname_from_url(url), domain) for url in navigation_urls)
        ]
        checks.append(
            check(
                "browser_required_domains",
                "failed" if missing_domains else "passed",
                "Browser did not visit required domains."
                if missing_domains
                else "Browser visited all required domains.",
                {"missing_domains": missing_domains, "navigation_urls": navigation_urls},
                policy_id="browser_required_domain_missing",
                severity="medium",
                category="browser",
            )
        )

    if forbidden_domains:
        forbidden = [
            url for url in navigation_urls if domain_matches_any(hostname_from_url(url), forbidden_domains)
        ]
        checks.append(
            check(
                "browser_forbidden_domains",
                "failed" if forbidden else "passed",
                "Browser visited forbidden domains."
                if forbidden
                else "Browser did not visit forbidden domains.",
                {"urls": forbidden},
                policy_id="browser_forbidden_domain",
                severity="critical",
                category="browser",
            )
        )

    if expected_final_url:
        checks.append(
            check(
                "browser_expected_final_url",
                "failed" if final_url != expected_final_url else "passed",
                "Browser final URL did not match expected URL."
                if final_url != expected_final_url
                else "Browser final URL matched expected URL.",
                {"actual_final_url": final_url, "expected_final_url": expected_final_url},
                policy_id="browser_final_url_mismatch",
                severity="medium",
                category="browser",
            )
        )

    if required_final_text:
        missing_text = [text for text in required_final_text if text not in all_text]
        checks.append(
            check(
                "browser_required_final_text",
                "failed" if missing_text else "passed",
                "Browser final text evidence is missing required text."
                if missing_text
                else "Browser text evidence contains required text.",
                {"missing_text": missing_text},
                policy_id="browser_required_text_missing",
                severity="medium",
                category="browser",
            )
        )

    return checks


def mcp_checks(contract: TaskContract, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    decision_events = [
        event for event in events if str(event.get("event_type") or "") == "policy.decision"
    ]
    mcp_events = [
        event for event in events if str(event.get("event_type") or "").startswith("mcp.")
    ]
    approval_events = [
        event for event in events if str(event.get("event_type") or "").startswith("approval.")
    ]
    if not decision_events and not mcp_events and not approval_events:
        return checks

    checks.append(
        check(
            "mcp_events_recorded",
            "passed" if mcp_events else "warning",
            f"{len(mcp_events)} MCP event(s) recorded."
            if mcp_events
            else "No MCP events were recorded.",
            {"event_count": len(mcp_events)},
            severity="low",
            category="mcp",
        )
    )

    for index, event in enumerate(decision_events):
        payload = event.get("payload") or {}
        decision = payload.get("decision") or {}
        for violation_index, violation_item in enumerate(decision.get("violations") or []):
            policy_id = str(violation_item.get("policy_id") or "mcp_policy_violation")
            severity = str(violation_item.get("severity") or "medium")
            checks.append(
                check(
                    f"mcp_policy_{sanitize_name(policy_id)}_{index}_{violation_index}",
                    "failed",
                    f"MCP policy violation recorded: {policy_id}",
                    {
                        "server_name": payload.get("server_name"),
                        "method": payload.get("method"),
                        "tool_name": payload.get("tool_name"),
                        "decision_action": decision.get("action"),
                        "evidence": violation_item.get("evidence") or {},
                    },
                    policy_id=policy_id,
                    severity=severity,
                    category="mcp",
                )
            )

    for event in approval_events:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") or {}
        if event_type == "approval.approved":
            checks.append(
                check(
                    f"mcp_approval_approved_{sanitize_name(str(payload.get('approval_id') or 'unknown'))}",
                    "warning",
                    "Risky MCP action was approved by a reviewer.",
                    payload,
                    policy_id="mcp_approved_risky_action",
                    severity="medium",
                    category="mcp",
                )
            )
        elif event_type in {"approval.denied", "approval.timed_out"}:
            checks.append(
                check(
                    f"mcp_approval_not_granted_{sanitize_name(str(payload.get('approval_id') or 'unknown'))}",
                    "failed",
                    "MCP action approval was denied or timed out.",
                    payload,
                    policy_id="mcp_approval_not_granted",
                    severity="high",
                    category="mcp",
                )
            )

    max_duration = (contract.mcp_policy or {}).get("max_tool_call_duration_seconds")
    if max_duration is not None:
        try:
            max_duration_float = float(max_duration)
        except (TypeError, ValueError):
            max_duration_float = None
        if max_duration_float is not None:
            slow_calls = [
                event.get("payload") or {}
                for event in events
                if str(event.get("event_type") or "") == "mcp.tool.call.finished"
                and float((event.get("payload") or {}).get("duration_seconds") or 0) > max_duration_float
            ]
            checks.append(
                check(
                    "mcp_tool_call_duration",
                    "warning" if slow_calls else "passed",
                    "One or more MCP tool calls exceeded the duration policy."
                    if slow_calls
                    else "MCP tool calls are within the duration policy.",
                    {"max_tool_call_duration_seconds": max_duration_float, "slow_calls": slow_calls},
                    policy_id="mcp_tool_call_too_slow",
                    severity="medium",
                    category="mcp",
                )
            )

    return checks


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    return [str(value)]


def network_policy_configured(policy: dict[str, Any]) -> bool:
    return bool(
        string_list(policy.get("allowed_domains"))
        or string_list(policy.get("forbidden_domains"))
        or policy.get("require_https")
        or policy.get("max_requests") is not None
    )


def browser_policy_configured(policy: dict[str, Any]) -> bool:
    return bool(
        string_list(policy.get("required_visited_domains"))
        or string_list(policy.get("forbidden_domains"))
        or str(policy.get("expected_final_url") or "")
        or string_list(policy.get("required_final_text"))
    )


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def infer_data_format(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return "csv"
    if path.suffix.lower() == ".json":
        return "json"
    return path.suffix.lower().lstrip(".") or "unknown"


def infer_artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "image"
    if suffix in {".mp4", ".mov", ".webm", ".avi", ".mkv"}:
        return "video"
    return "file"


def artifact_event_map(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for event in events:
        if str(event.get("event_type") or "") != "artifact.created":
            continue
        payload = dict(event.get("payload") or {})
        path = str(payload.get("path") or "")
        if path:
            mapping[path] = payload
    return mapping


def detect_image_info(path: Path) -> dict[str, Any] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"format": "png", "width": width, "height": height}
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        if len(data) >= 10:
            width, height = struct.unpack("<HH", data[6:10])
            return {"format": "gif", "width": width, "height": height}
    if data.startswith(b"\xff\xd8"):
        info = detect_jpeg_info(data)
        if info:
            return info
    return None


def detect_jpeg_info(data: bytes) -> dict[str, Any] | None:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        segment_length = int.from_bytes(data[index:index + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 <= len(data):
                height = int.from_bytes(data[index + 3:index + 5], "big")
                width = int.from_bytes(data[index + 5:index + 7], "big")
                return {"format": "jpeg", "width": width, "height": height}
        index += segment_length
    return None


def event_url(event: dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    return str(payload.get("url") or payload.get("href") or payload.get("request_url") or "")


def hostname_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def domain_matches(hostname: str, pattern: str) -> bool:
    hostname = (hostname or "").lower()
    pattern = pattern.lower()
    return hostname == pattern or hostname.endswith("." + pattern)


def domain_matches_any(hostname: str, patterns: list[str]) -> bool:
    return any(domain_matches(hostname, pattern) for pattern in patterns)
