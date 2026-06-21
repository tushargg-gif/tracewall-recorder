from __future__ import annotations

from pathlib import Path
import struct

from tracewall.contracts import TaskContract
from tracewall.plugins import (
    artifact_checks,
    browser_checks,
    data_checks,
    network_checks,
    script_checks,
    worker_scope_checks,
)


def png_bytes(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00"


def lookup(checks):
    return {check["name"]: check for check in checks}


def test_script_policy_passes_required_commands():
    contract = TaskContract.from_mapping(
        {
            "script_policy": {
                "required_commands": ["python sync.py"],
                "forbidden_command_patterns": ["rm -rf *"],
                "max_command_duration_seconds": 5,
            }
        }
    )
    checks = lookup(
        script_checks(
            contract,
            [{"command": "python sync.py --limit 10", "duration_seconds": 1.5}],
        )
    )
    assert checks["script_required_commands"]["status"] == "passed"
    assert checks["script_forbidden_commands"]["status"] == "passed"
    assert checks["script_command_duration"]["status"] == "passed"


def test_script_policy_flags_forbidden_and_slow_commands():
    contract = TaskContract.from_mapping(
        {
            "script_policy": {
                "required_commands": ["python sync.py"],
                "forbidden_command_patterns": ["curl *prod*"],
                "max_command_duration_seconds": 1,
            }
        }
    )
    checks = lookup(
        script_checks(
            contract,
            [{"command": "curl https://prod.example.com", "duration_seconds": 2.0}],
        )
    )
    assert checks["script_required_commands"]["status"] == "failed"
    assert checks["script_forbidden_commands"]["status"] == "failed"
    assert checks["script_command_duration"]["status"] == "warning"


def test_data_plugin_validates_csv_schema_and_count(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "results.csv").write_text("id,score\n1,98\n", encoding="utf-8")
    contract = TaskContract.from_mapping(
        {
            "expected_data": [
                {
                    "path": "data/results.csv",
                    "format": "csv",
                    "required_columns": ["id", "score"],
                    "min_rows": 1,
                    "max_rows": 2,
                }
            ]
        }
    )
    checks = lookup(data_checks(contract, tmp_path))
    assert checks["data_data_results_csv_exists"]["status"] == "passed"
    assert checks["data_data_results_csv_columns"]["status"] == "passed"
    assert checks["data_data_results_csv_count"]["status"] == "passed"


def test_data_plugin_flags_missing_columns_and_bad_count(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "results.csv").write_text("id\n1\n", encoding="utf-8")
    contract = TaskContract.from_mapping(
        {
            "expected_data": [
                {
                    "path": "data/results.csv",
                    "format": "csv",
                    "required_columns": ["id", "score"],
                    "min_rows": 2,
                }
            ]
        }
    )
    checks = lookup(data_checks(contract, tmp_path))
    assert checks["data_data_results_csv_columns"]["status"] == "failed"
    assert checks["data_data_results_csv_count"]["status"] == "failed"


def test_artifact_plugin_validates_image_dimensions(tmp_path: Path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "hero.png").write_bytes(png_bytes(640, 360))
    contract = TaskContract.from_mapping(
        {
            "expected_artifacts": [
                {
                    "path": "outputs/hero.png",
                    "type": "image",
                    "width": 640,
                    "height": 360,
                    "min_size_bytes": 20,
                }
            ]
        }
    )
    checks = lookup(artifact_checks(contract, tmp_path, []))
    assert checks["artifact_outputs_hero_png_exists"]["status"] == "passed"
    assert checks["artifact_outputs_hero_png_image"]["status"] == "passed"


def test_artifact_plugin_flags_wrong_image_dimensions(tmp_path: Path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "hero.png").write_bytes(png_bytes(320, 200))
    contract = TaskContract.from_mapping(
        {
            "expected_artifacts": [
                {
                    "path": "outputs/hero.png",
                    "type": "image",
                    "width": 640,
                    "height": 360,
                }
            ]
        }
    )
    checks = lookup(artifact_checks(contract, tmp_path, []))
    assert checks["artifact_outputs_hero_png_image"]["status"] == "failed"


def test_network_plugin_validates_allowed_https_domains():
    contract = TaskContract.from_mapping(
        {
            "network_policy": {
                "allowed_domains": ["api.example.com"],
                "forbidden_domains": ["prod.example.com"],
                "require_https": True,
                "max_requests": 2,
            }
        }
    )
    events = [
        {
            "event_type": "network.request",
            "payload": {"url": "https://api.example.com/v1/data"},
        }
    ]
    checks = lookup(network_checks(contract, events))
    assert checks["network_allowed_domains"]["status"] == "passed"
    assert checks["network_forbidden_domains"]["status"] == "passed"
    assert checks["network_https_required"]["status"] == "passed"
    assert checks["network_request_count"]["status"] == "passed"


def test_network_plugin_does_not_count_browser_navigation_against_network_policy():
    contract = TaskContract.from_mapping(
        {
            "network_policy": {
                "allowed_domains": ["api.example.com"],
                "require_https": True,
                "max_requests": 1,
            }
        }
    )
    events = [
        {"event_type": "network.request", "payload": {"url": "https://api.example.com/data"}},
        {"event_type": "browser.navigate", "payload": {"url": "https://app.example.com/done"}},
    ]
    checks = lookup(network_checks(contract, events))
    assert checks["network_allowed_domains"]["status"] == "passed"
    assert checks["network_request_count"]["status"] == "passed"


def test_network_plugin_flags_forbidden_and_insecure_domains():
    contract = TaskContract.from_mapping(
        {
            "network_policy": {
                "allowed_domains": ["api.example.com"],
                "forbidden_domains": ["prod.example.com"],
                "require_https": True,
                "max_requests": 1,
            }
        }
    )
    events = [
        {"event_type": "network.request", "payload": {"url": "http://prod.example.com/a"}},
        {"event_type": "network.request", "payload": {"url": "https://evil.example.net/b"}},
    ]
    checks = lookup(network_checks(contract, events))
    assert checks["network_allowed_domains"]["status"] == "failed"
    assert checks["network_forbidden_domains"]["status"] == "failed"
    assert checks["network_https_required"]["status"] == "failed"
    assert checks["network_request_count"]["status"] == "warning"


def test_network_plugin_passes_when_zero_requests_are_expected():
    contract = TaskContract.from_mapping(
        {
            "network_policy": {
                "require_https": True,
                "max_requests": 0,
            }
        }
    )
    checks = lookup(network_checks(contract, []))
    assert checks["network_events_recorded"]["status"] == "passed"
    assert checks["network_https_required"]["status"] == "passed"
    assert checks["network_request_count"]["status"] == "passed"


def test_worker_scope_plugin_flags_actual_changes_outside_scope():
    contract = TaskContract.from_mapping(
        {
            "forbidden_paths": ["package.json"],
            "worker_scopes": {
                "Rogue Agent": {
                    "allowed_paths": ["docs/**"],
                    "forbidden_paths": ["package.json"],
                }
            },
        }
    )
    events = [
        {
            "event_type": "worker.completed",
            "payload": {
                "agent": "Rogue Agent",
                "reported_files": [],
                "actual_changed_files": ["package.json"],
            },
        }
    ]
    checks = lookup(worker_scope_checks(contract, events))
    assert checks["worker_scope_rogue_agent"]["status"] == "failed"
    assert checks["worker_forbidden_path_rogue_agent"]["status"] == "failed"


def test_browser_plugin_validates_final_state():
    contract = TaskContract.from_mapping(
        {
            "browser_policy": {
                "required_visited_domains": ["app.example.com"],
                "forbidden_domains": ["admin.example.com"],
                "expected_final_url": "https://app.example.com/done",
                "required_final_text": ["Success"],
            }
        }
    )
    events = [
        {"event_type": "browser.navigate", "payload": {"url": "https://app.example.com/start"}},
        {"event_type": "browser.navigate", "payload": {"url": "https://app.example.com/done"}},
        {"event_type": "browser.dom_snapshot", "payload": {"text": "Success"}},
    ]
    checks = lookup(browser_checks(contract, events))
    assert checks["browser_required_domains"]["status"] == "passed"
    assert checks["browser_forbidden_domains"]["status"] == "passed"
    assert checks["browser_expected_final_url"]["status"] == "passed"
    assert checks["browser_required_final_text"]["status"] == "passed"


def test_browser_plugin_flags_wrong_final_state():
    contract = TaskContract.from_mapping(
        {
            "browser_policy": {
                "required_visited_domains": ["app.example.com"],
                "forbidden_domains": ["admin.example.com"],
                "expected_final_url": "https://example.com/done",
                "required_final_text": ["Success"],
            }
        }
    )
    events = [
        {"event_type": "browser.navigate", "payload": {"url": "https://admin.example.com/root"}},
        {"event_type": "browser.dom_snapshot", "payload": {"text": "Denied"}},
    ]
    checks = lookup(browser_checks(contract, events))
    assert checks["browser_required_domains"]["status"] == "failed"
    assert checks["browser_forbidden_domains"]["status"] == "failed"
    assert checks["browser_expected_final_url"]["status"] == "failed"
    assert checks["browser_required_final_text"]["status"] == "failed"
