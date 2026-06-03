from __future__ import annotations

from pathlib import Path
from typing import Any

from agentproof.checks import check, sanitize_name
from agentproof.contracts import TaskContract
from agentproof.events import event_type_counts, verify_event_chain
from agentproof.policy import violations_from_checks
from agentproof.plugins import run_verifier_plugins
from agentproof.recorder import (
    diff_snapshots,
    latest_run_id,
    paths_for_run,
    read_events,
    read_json,
    snapshot_files,
    write_json,
)
from agentproof.scoring import score_run
from agentproof.sensitive import SECRET_PATTERNS, looks_secret_path
from agentproof.store import default_store_for_project


PACKAGE_FILES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "Gemfile",
    "Gemfile.lock",
}

TEST_COMMAND_MARKERS = (
    "test",
    "pytest",
    "go test",
    "cargo test",
    "rspec",
    "jest",
    "vitest",
    "phpunit",
)


def verify_run(run_id: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
    resolved_run_id = run_id or latest_run_id(cwd)
    paths = paths_for_run(resolved_run_id, cwd)
    run = read_json(paths.run_file)
    contract = TaskContract.from_mapping(run["contract"])
    snapshot_diff = load_or_create_snapshot_diff(paths)
    events = read_events(resolved_run_id, cwd)
    command_events = [
        event["payload"]
        for event in events
        if event.get("event_type") == "command_finished"
    ]
    changed_files = snapshot_diff["files_changed"]
    checks = build_checks(contract, changed_files, command_events, paths)
    checks.append(event_integrity_check(events))
    checks.extend(run_verifier_plugins(contract, run, paths, events, command_events, changed_files))
    violations = [violation.to_dict() for violation in violations_from_checks(checks)]
    scoring = score_run(run, checks, violations, command_events, changed_files)
    verdict = verdict_from_score(scoring["score"], violations, checks)
    verification = {
        "verification_id": f"ver_{resolved_run_id}",
        "run_id": resolved_run_id,
        "task_id": run["task_id"],
        "verdict": verdict,
        "score": scoring["score"],
        "risk": scoring["risk"],
        "dimensions": scoring["dimensions"],
        "checks": checks,
        "policy_violations": violations,
        "changed_files": changed_files,
        "commands": command_events,
        "event_summary": event_type_counts(events),
    }
    write_json(paths.run_dir / "verification.json", verification)
    default_store_for_project(paths.project_root).store_verification(resolved_run_id, verification)
    run.update(
        {
            "status": f"verified_{verdict.lower().replace(' ', '_')}",
            "score": scoring["score"],
            "risk": scoring["risk"],
            "verdict": verdict,
        }
    )
    write_json(paths.run_file, run)
    default_store_for_project(paths.project_root).upsert_run(run)
    return verification


def event_integrity_check(events: list[dict[str, Any]]) -> dict[str, Any]:
    chain = verify_event_chain(events)
    return check(
        "event_chain_integrity",
        "passed" if chain.get("valid") else "failed",
        "Event hash chain is valid."
        if chain.get("valid")
        else "Event hash chain is invalid or has been tampered with.",
        chain,
        policy_id="event_chain_tampered",
        severity="critical",
        category="evidence",
    )


def load_or_create_snapshot_diff(paths) -> dict[str, list[str]]:
    diff_path = paths.run_dir / "snapshot_diff.json"
    if diff_path.exists():
        return read_json(diff_path)
    baseline_path = paths.run_dir / "baseline_snapshot.json"
    before = read_json(baseline_path) if baseline_path.exists() else {}
    after = snapshot_files(paths.project_root)
    snapshot_diff = diff_snapshots(before, after)
    write_json(diff_path, snapshot_diff)
    return snapshot_diff


def build_checks(
    contract: TaskContract,
    changed_files: list[str],
    command_events: list[dict[str, Any]],
    paths,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    forbidden_changes = [path for path in changed_files if contract.path_is_forbidden(path)]
    unrelated_changes = [
        path for path in changed_files if not contract.path_is_allowed(path)
    ]
    secret_changes = [path for path in changed_files if looks_secret_path(path)]
    package_changes = [path for path in changed_files if is_package_file(path)]
    failed_commands = [
        command for command in command_events if int(command.get("exit_code", 1)) != 0
    ]
    unapproved_commands = [
        command
        for command in command_events
        if not contract.command_is_allowed(str(command.get("command") or ""))
    ]
    test_commands = [
        command
        for command in command_events
        if looks_like_test_command(str(command.get("command") or ""))
    ]
    passed_test_commands = [
        command for command in test_commands if int(command.get("exit_code", 1)) == 0
    ]
    regression_required = requires_regression_file_change(contract.success_criteria)
    test_files_added_or_modified = [
        path for path in changed_files if looks_like_test_file(path)
    ]

    checks.append(
        check(
            "changed_files_recorded",
            "passed" if changed_files else "warning",
            f"{len(changed_files)} changed file(s) recorded.",
            {"changed_files": changed_files},
            severity="low",
        )
    )
    checks.append(
        check(
            "forbidden_paths",
            "failed" if forbidden_changes else "passed",
            "Forbidden paths were modified." if forbidden_changes else "No forbidden paths modified.",
            {"files": forbidden_changes},
            policy_id="no_forbidden_path_change",
            severity="critical",
        )
    )
    checks.append(
        check(
            "allowed_paths",
            "failed" if unrelated_changes else "passed",
            "Files outside allowed paths were modified."
            if unrelated_changes
            else "All changed files are inside allowed paths.",
            {"files": unrelated_changes},
            policy_id="no_unrelated_file_change",
            severity="medium",
        )
    )
    checks.append(
        check(
            "secret_files",
            "failed" if secret_changes else "passed",
            "Secret-like files were modified." if secret_changes else "No secret-like files modified.",
            {"files": secret_changes},
            policy_id="no_secret_access",
            severity="critical",
        )
    )
    dependency_forbidden = "install_new_package" in {
        action.lower() for action in contract.forbidden_actions
    }
    checks.append(
        check(
            "dependency_changes",
            "failed" if package_changes and dependency_forbidden else "warning" if package_changes else "passed",
            "Package/dependency files changed."
            if package_changes
            else "No package/dependency files changed.",
            {"files": package_changes},
            policy_id="no_unapproved_dependency",
            severity="high",
        )
    )
    checks.append(
        check(
            "allowed_commands",
            "failed" if unapproved_commands else "passed",
            "Commands outside allowed command list were run."
            if unapproved_commands
            else "All recorded commands are allowed.",
            {"commands": [command.get("command") for command in unapproved_commands]},
            policy_id="no_unapproved_command",
            severity="high",
        )
    )
    checks.append(
        check(
            "command_exit_codes",
            "failed" if failed_commands else "passed",
            "One or more recorded commands failed."
            if failed_commands
            else "All recorded commands exited successfully.",
            {"commands": [command.get("command") for command in failed_commands]},
            severity="high",
        )
    )
    if should_require_tests(contract, changed_files):
        checks.append(
            check(
                "tests_run",
                "passed" if passed_test_commands else "failed",
                "At least one test command passed."
                if passed_test_commands
                else "No passing test command was recorded.",
                {"commands": [command.get("command") for command in test_commands]},
                policy_id="test_required",
                severity="medium",
                category="coding",
            )
        )
    if regression_required:
        checks.append(
            check(
                "regression_test_added",
                "passed" if test_files_added_or_modified else "failed",
                "A test file was added or modified."
                if test_files_added_or_modified
                else "No test file change detected.",
                {"files": test_files_added_or_modified},
                policy_id="regression_test_required",
                severity="medium",
            )
        )

    for group, commands in contract.verification.items():
        for command in commands:
            matching = [
                event
                for event in command_events
                if str(event.get("command") or "") == command
                or str(event.get("command") or "").startswith(command + " ")
            ]
            checks.append(
                check(
                    f"verification_command_{group}_{sanitize_name(command)}",
                    "passed"
                    if any(int(event.get("exit_code", 1)) == 0 for event in matching)
                    else "failed",
                    f"Verification command ran successfully: {command}"
                    if matching
                    else f"Verification command was not recorded: {command}",
                    {"command": command},
                    policy_id="verification_command_required",
                    severity="medium",
                )
            )

    git_diff_path = paths.run_dir / "git_diff_end.patch"
    diff_line_count = count_diff_lines(git_diff_path)
    checks.append(
        check(
            "large_diff",
            "warning" if diff_line_count > 500 or len(changed_files) > 20 else "passed",
            "Large diff needs human review."
            if diff_line_count > 500 or len(changed_files) > 20
            else "Diff size is within the default review threshold.",
            {"diff_lines": diff_line_count, "changed_file_count": len(changed_files)},
            policy_id="no_large_diff_without_review",
            severity="medium",
        )
    )
    return checks


def is_package_file(path: str) -> bool:
    return Path(path).name in PACKAGE_FILES


def looks_like_test_command(command: str) -> bool:
    lowered = command.lower()
    return any(marker in lowered for marker in TEST_COMMAND_MARKERS)


def looks_like_test_file(path: str) -> bool:
    lowered = path.lower()
    name = Path(path).name.lower()
    return (
        lowered.startswith("test/")
        or lowered.startswith("tests/")
        or ".test." in name
        or "_test." in name
        or ".spec." in name
        or name.startswith("test_")
    )


def should_require_tests(contract: TaskContract, changed_files: list[str]) -> bool:
    configured_tests = contract.verification.get("tests") if contract.verification else []
    if configured_tests:
        return True
    criteria_text = " ".join(contract.success_criteria).lower()
    if "test" in criteria_text or "regression" in criteria_text:
        return True
    return any(looks_like_code_file(path) for path in changed_files)


def requires_regression_file_change(success_criteria: list[str]) -> bool:
    for criterion in success_criteria:
        lowered = criterion.lower()
        if "test added" in lowered:
            return True
        if "regression test added" in lowered:
            return True
        if "new regression" in lowered:
            return True
        if "add regression" in lowered:
            return True
    return False


def looks_like_code_file(path: str) -> bool:
    return Path(path).suffix.lower() in {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
    }


def count_diff_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        diff = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0
    return sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))


def verdict_from_score(
    score: int,
    violations: list[dict[str, Any]],
    checks: list[dict[str, Any]],
) -> str:
    severities = {violation.get("severity") for violation in violations}
    failed_checks = [check for check in checks if check.get("status") == "failed"]
    if "critical" in severities:
        return "Fail"
    if score >= 85 and not failed_checks:
        return "Pass"
    if score >= 60:
        return "Partial Pass"
    return "Fail"
