from __future__ import annotations

from pathlib import Path
from typing import Any

from agentproof.recorder import latest_run_id, paths_for_run, read_json, write_json
from agentproof.verifier import verify_run


def generate_report(run_id: str | None = None, cwd: Path | None = None) -> dict[str, Path]:
    resolved_run_id = run_id or latest_run_id(cwd)
    paths = paths_for_run(resolved_run_id, cwd)
    verification_path = paths.run_dir / "verification.json"
    verification = read_json(verification_path) if verification_path.exists() else verify_run(resolved_run_id, cwd)
    run = read_json(paths.run_file)
    markdown = render_markdown(run, verification)
    report_md = paths.run_dir / "report.md"
    report_json = paths.run_dir / "report.json"
    public_report_md = paths.agentproof_dir / "reports" / f"{resolved_run_id}.md"
    public_report_json = paths.agentproof_dir / "reports" / f"{resolved_run_id}.json"
    report_md.write_text(markdown, encoding="utf-8")
    public_report_md.write_text(markdown, encoding="utf-8")
    payload = {"run": run, "verification": verification}
    write_json(report_json, payload)
    write_json(public_report_json, payload)
    return {"markdown": report_md, "json": report_json, "public_markdown": public_report_md, "public_json": public_report_json}


def render_markdown(run: dict[str, Any], verification: dict[str, Any]) -> str:
    passed = [check for check in verification["checks"] if check["status"] == "passed"]
    problems = [
        check
        for check in verification["checks"]
        if check["status"] in {"failed", "warning"}
    ]
    lines = [
        "# AgentProof Recorder Report",
        "",
        f"Task: {run.get('task_title', run.get('task_id'))}",
        f"Task ID: {run.get('task_id')}",
        f"Agent: {run.get('agent')}",
        f"Run ID: {run.get('run_id')}",
        f"Repository: {run.get('project_root')}",
        f"Duration: {format_duration(run.get('duration_seconds'))}",
        f"Verdict: {verification.get('verdict')}",
        f"Score: {verification.get('score')}/100",
        f"Risk: {verification.get('risk')}",
        "",
        "## What Went Well",
    ]
    lines.extend(format_check_list(passed, empty="No passing checks recorded."))
    lines.extend(["", "## Problems"])
    lines.extend(format_check_list(problems, empty="No problems detected."))
    lines.extend(["", "## Policy Violations"])
    lines.extend(format_policy_violations(verification.get("policy_violations") or []))
    lines.extend(["", "## Changed Files"])
    lines.extend(format_plain_list(verification.get("changed_files") or [], empty="No file changes recorded."))
    lines.extend(["", "## Commands"])
    lines.extend(format_commands(verification.get("commands") or []))
    lines.extend(["", "## Observed Events"])
    lines.extend(format_event_summary(verification.get("event_summary") or {}))
    lines.extend(["", "## Score Dimensions"])
    dimensions = verification.get("dimensions") or {}
    for name, value in dimensions.items():
        lines.append(f"- {titleize(name)}: {value}/100")
    lines.extend(["", "## Recommended Action", recommendation(verification), ""])
    return "\n".join(lines)


def format_check_list(checks: list[dict[str, Any]], empty: str) -> list[str]:
    if not checks:
        return [f"- {empty}"]
    return [f"- {check['name']}: {check['message']}" for check in checks]


def format_policy_violations(violations: list[dict[str, Any]]) -> list[str]:
    if not violations:
        return ["- None"]
    return [
        f"- {violation['severity'].upper()} {violation['policy_id']}: {violation['message']}"
        for violation in violations
    ]


def format_plain_list(values: list[str], empty: str) -> list[str]:
    if not values:
        return [f"- {empty}"]
    return [f"- {value}" for value in values]


def format_commands(commands: list[dict[str, Any]]) -> list[str]:
    if not commands:
        return ["- No wrapped commands recorded."]
    return [
        f"- `{command.get('command')}` exited {command.get('exit_code')} in {command.get('duration_seconds')}s"
        for command in commands
    ]


def format_event_summary(event_summary: dict[str, int]) -> list[str]:
    if not event_summary:
        return ["- No events recorded."]
    return [f"- {event_type}: {count}" for event_type, count in event_summary.items()]


def recommendation(verification: dict[str, Any]) -> str:
    verdict = verification.get("verdict")
    violations = verification.get("policy_violations") or []
    if verdict == "Pass" and not violations:
        return "Safe to proceed with normal human review."
    if any(violation.get("severity") == "critical" for violation in violations):
        return "Do not merge or approve until critical policy violations are resolved."
    if verdict == "Partial Pass":
        return "Manual review required before merge or approval."
    return "Reject or rerun the agent task after addressing failed checks."


def format_duration(seconds: Any) -> str:
    if seconds is None:
        return "unknown"
    seconds = int(seconds)
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def titleize(value: str) -> str:
    return value.replace("_", " ").title()
