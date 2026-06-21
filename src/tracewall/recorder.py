from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import shlex
import subprocess
import time
import uuid

from tracewall import enforce as policy_engine
from tracewall.contracts import TaskContract
from tracewall.enforcement import (
    DEFAULT_SENSITIVE_PATTERNS,
    GuardProfile,
    guard_backend,
    run_guarded,
)
from tracewall.events import normalize_event, now_iso
from tracewall.gitutils import git_diff, git_info, git_root


TRACEWALL_DIR = ".tracewall"
ACTIVE_RUN_FILE = "active_run"
IGNORE_DIRS = {
    ".tracewall",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    "coverage",
}


@dataclass(frozen=True)
class RunPaths:
    project_root: Path
    tracewall_dir: Path
    runs_dir: Path
    run_dir: Path
    run_file: Path
    events_file: Path
    active_file: Path


def discover_project_root(cwd: Path | None = None) -> Path:
    cwd = (cwd or Path.cwd()).resolve()
    root = git_root(cwd)
    if root is not None:
        return root.resolve()
    current = cwd
    for candidate in [current, *current.parents]:
        if (candidate / TRACEWALL_DIR).exists():
            return candidate.resolve()
    return cwd


def paths_for_run(run_id: str | None = None, cwd: Path | None = None) -> RunPaths:
    project_root = discover_project_root(cwd)
    tracewall_dir = project_root / TRACEWALL_DIR
    runs_dir = tracewall_dir / "runs"
    run_dir = runs_dir / run_id if run_id else runs_dir
    return RunPaths(
        project_root=project_root,
        tracewall_dir=tracewall_dir,
        runs_dir=runs_dir,
        run_dir=run_dir,
        run_file=run_dir / "run.json",
        events_file=run_dir / "events.jsonl",
        active_file=tracewall_dir / ACTIVE_RUN_FILE,
    )


def create_run(
    contract: TaskContract,
    agent: str,
    cwd: Path | None = None,
    enforce: bool = False,
) -> dict[str, Any]:
    project_root = discover_project_root(cwd)
    tracewall_dir = project_root / TRACEWALL_DIR
    tracewall_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = tracewall_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = tracewall_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    paths = paths_for_run(run_id, project_root)
    paths.run_dir.mkdir(parents=True, exist_ok=False)
    baseline_snapshot = snapshot_files(project_root)
    write_json(paths.run_dir / "baseline_snapshot.json", baseline_snapshot)
    git_evidence = git_info(project_root)
    write_json(paths.run_dir / "git_start.json", git_evidence)
    diff = git_diff(project_root)
    write_text(paths.run_dir / "git_diff_start.patch", str(diff.get("diff") or ""))

    run = {
        "run_id": run_id,
        "task_id": contract.task_id,
        "task_title": contract.title,
        "agent": agent,
        "status": "running",
        "risk_level": contract.risk_level,
        "human_approval_required": contract.human_approval_required,
        "project_root": str(project_root),
        "run_dir": str(paths.run_dir),
        "orchestrator": "",
        "control_mode": "enforce" if enforce else "observe",
        "enforcement": {
            "enabled": enforce,
            "backend": guard_backend() if enforce else "none",
            "sensitive_patterns": list(DEFAULT_SENSITIVE_PATTERNS),
        },
        "start_time": now_iso(),
        "end_time": None,
        "duration_seconds": None,
        "contract": contract.to_dict(),
        "git": git_evidence,
    }
    write_json(paths.run_file, run)
    paths.events_file.touch()
    paths.active_file.write_text(run_id, encoding="utf-8")
    append_event(
        paths,
        "run_started",
        {"agent": agent, "task_id": contract.task_id, "control_mode": run["control_mode"]},
    )
    if enforce:
        append_event(
            paths,
            "enforcement_started",
            {
                "backend": run["enforcement"]["backend"],
                "sensitive_patterns": run["enforcement"]["sensitive_patterns"],
                "fail_closed": True,
            },
        )
    return run


def stop_run(
    run_id: str | None = None,
    final_response: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    resolved_run_id = run_id or active_run_id(cwd)
    paths = paths_for_run(resolved_run_id, cwd)
    run = read_json(paths.run_file)
    end_snapshot = snapshot_files(paths.project_root)
    write_json(paths.run_dir / "end_snapshot.json", end_snapshot)
    snapshot_diff = diff_snapshots(
        read_json(paths.run_dir / "baseline_snapshot.json"),
        end_snapshot,
    )
    write_json(paths.run_dir / "snapshot_diff.json", snapshot_diff)
    git_evidence = git_info(paths.project_root)
    write_json(paths.run_dir / "git_end.json", git_evidence)
    diff = git_diff(paths.project_root)
    write_text(paths.run_dir / "git_diff_end.patch", str(diff.get("diff") or ""))

    start_time = datetime.fromisoformat(run["start_time"])
    end_time = datetime.now().astimezone()
    run.update(
        {
            "status": "stopped",
            "end_time": end_time.isoformat(timespec="seconds"),
            "duration_seconds": max(0, int((end_time - start_time).total_seconds())),
            "final_response": final_response or "",
            "git": git_evidence,
            "changed_files": snapshot_diff["files_changed"],
        }
    )
    write_json(paths.run_file, run)
    append_event(paths, "run_stopped", {"changed_files": snapshot_diff["files_changed"]})
    if paths.active_file.exists() and paths.active_file.read_text(encoding="utf-8").strip() == resolved_run_id:
        paths.active_file.unlink()
    return run


def active_run_id(cwd: Path | None = None) -> str:
    project_root = discover_project_root(cwd)
    active_file = project_root / TRACEWALL_DIR / ACTIVE_RUN_FILE
    if not active_file.exists():
        raise RuntimeError("No active tracewall Recorder run found. Start one with `tracewall start`.")
    run_id = active_file.read_text(encoding="utf-8").strip()
    if not run_id:
        raise RuntimeError("Active tracewall Recorder run file is empty.")
    return run_id


def latest_run_id(cwd: Path | None = None) -> str:
    paths = paths_for_run(cwd=cwd)
    if not paths.runs_dir.exists():
        raise RuntimeError("No tracewall Recorder runs found.")
    runs = sorted(
        [path for path in paths.runs_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not runs:
        raise RuntimeError("No tracewall Recorder runs found.")
    return runs[0].name


def enforcement_profile_for_run(run: dict[str, Any], project_root: Path) -> GuardProfile:
    """Build the sandbox profile for a run from its recorded enforcement config."""
    config = run.get("enforcement") or {}
    patterns = tuple(config.get("sensitive_patterns") or DEFAULT_SENSITIVE_PATTERNS)
    return GuardProfile(project_root=project_root, patterns=patterns)


def run_is_enforced(run: dict[str, Any]) -> bool:
    return bool((run.get("enforcement") or {}).get("enabled")) or run.get("control_mode") == "enforce"


def _apply_command_policy(paths: RunPaths, command_text: str, policy_mode: str) -> bool:
    """Evaluate the command against the active policy. Returns True if blocked."""
    policy = policy_engine.load_active_policy(paths.tracewall_dir)
    decision = policy_engine.evaluate_action(
        policy_engine.action_from_command(command_text), policy
    )
    if decision["decision"] == "none":
        return False
    outcome = policy_engine.enforced_outcome(decision["decision"], policy_mode)
    append_event(
        paths,
        "policy.decision",
        {
            "action": command_text,
            "match_kind": "command",
            "decision": decision["decision"],
            "rule_id": decision["rule_id"],
            "reason": decision["reason"],
            "mode": policy_mode,
            "outcome": outcome,
        },
    )
    if outcome == "blocked":
        append_event(
            paths,
            "policy.enforcement",
            {"command": command_text, "rule_id": decision["rule_id"],
             "reason": decision["reason"], "action_taken": "blocked"},
        )
        print(
            f"tracewall: BLOCKED by policy [{decision['rule_id']}] — {decision['reason']}",
            file=os.sys.stderr,
        )
        return True
    if outcome == "alerted":
        print(
            f"tracewall: ALERT [{decision['rule_id']}] — {decision['reason']} (running anyway; alert mode)",
            file=os.sys.stderr,
        )
    return False


def record_command(
    command: list[str],
    cwd: Path | None = None,
    enforce: bool | None = None,
    policy_mode: str = "observe",
) -> int:
    if not command:
        raise ValueError("No command provided.")
    run_id = active_run_id(cwd)
    paths = paths_for_run(run_id, cwd)
    run = read_json(paths.run_file)
    enforcing = run_is_enforced(run) if enforce is None else enforce
    started = time.time()
    command_text = shlex.join(command)

    # Policy enforcement at the command chokepoint (active learned policy).
    blocked = _apply_command_policy(paths, command_text, policy_mode)
    if blocked:
        return 126

    append_event(paths, "command_started", {"command": command_text, "enforced": enforcing})

    if enforcing:
        profile = enforcement_profile_for_run(run, paths.project_root)
        guarded = run_guarded(
            command,
            profile,
            cwd=Path(cwd or Path.cwd()),
            require_enforcement=True,
        )
        result = subprocess.CompletedProcess(
            command, guarded.exit_code, guarded.stdout, guarded.stderr
        )
        append_event(
            paths,
            "enforcement_decision",
            {
                "command": command_text,
                "backend": guarded.backend,
                "enforced": guarded.enforced,
                "action_taken": "blocked" if guarded.blocked else "allowed",
                "exit_code": guarded.exit_code,
            },
        )
    else:
        result = subprocess.run(
            command,
            cwd=Path(cwd or Path.cwd()),
            text=True,
            capture_output=True,
            check=False,
        )
    duration = round(time.time() - started, 3)
    command_id = f"cmd_{int(started)}_{uuid.uuid4().hex[:6]}"
    output_dir = paths.run_dir / "command_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{command_id}.stdout.log"
    stderr_path = output_dir / f"{command_id}.stderr.log"
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    payload = {
        "command_id": command_id,
        "command": command_text,
        "argv": command,
        "exit_code": result.returncode,
        "duration_seconds": duration,
        "enforced": enforcing,
        "stdout_path": str(stdout_path.relative_to(paths.project_root)),
        "stderr_path": str(stderr_path.relative_to(paths.project_root)),
    }
    append_event(paths, "command_finished", payload)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=os.sys.stderr)
    return result.returncode


def record_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    resolved_run_id = run_id or active_run_id(cwd)
    paths = paths_for_run(resolved_run_id, cwd)
    return _write_event(paths.events_file, resolved_run_id, event_type, payload)


def append_event(paths: RunPaths, event_type: str, payload: dict[str, Any]) -> None:
    _write_event(paths.events_file, paths.run_dir.name, event_type, payload)


def _last_event_hash(events_file: Path) -> str | None:
    """The tip of the hash chain: last event's hash, read from the JSONL log.

    The local hash-chained log is the single source of truth (see
    docs/adr-source-of-truth.md). Reading the file is fine for per-run sizes; if
    it ever shows up hot, the daemon can cache the tip in memory.
    """
    if not events_file.exists():
        return None
    last = None
    with events_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = line
    if not last:
        return None
    try:
        return json.loads(last).get("event_hash")
    except ValueError:
        return None


def _write_event(events_file: Path, run_id: str, event_type: str,
                 payload: dict[str, Any] | None) -> dict[str, Any]:
    """Append one hash-chained event to the JSONL log and return it."""
    event = normalize_event(run_id, event_type, payload, prev_event_hash=_last_event_hash(events_file))
    events_file.parent.mkdir(parents=True, exist_ok=True)
    with events_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def record_policy_event(tracewall_dir: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append a hash-chained entry to the project's policy audit log
    (``.tracewall/policy-events.jsonl``). Independent of any run — the daemon
    writes here when it observes a policy change or refuses an untrusted policy,
    so disabling the guardrail can't happen silently (P0.6)."""
    return _write_event(Path(tracewall_dir) / "policy-events.jsonl", "policy", event_type, payload)


def read_events(run_id: str, cwd: Path | None = None) -> list[dict[str, Any]]:
    paths = paths_for_run(run_id, cwd)
    if not paths.events_file.exists():
        return []
    events = []
    for line in paths.events_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def snapshot_files(root: Path) -> dict[str, dict[str, object]]:
    root = root.resolve()
    snapshot: dict[str, dict[str, object]] = {}
    if not root.exists():
        return snapshot
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if should_ignore(relative):
            continue
        try:
            digest = sha256_file(path)
            stat = path.stat()
        except OSError:
            continue
        snapshot[relative.as_posix()] = {"sha256": digest, "size": stat.st_size}
    return snapshot


def should_ignore(relative: Path) -> bool:
    return any(part in IGNORE_DIRS for part in relative.parts)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def diff_snapshots(
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
) -> dict[str, list[str]]:
    before_keys = set(before)
    after_keys = set(after)
    added = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    modified = sorted(
        key for key in before_keys & after_keys if before[key].get("sha256") != after[key].get("sha256")
    )
    return {
        "files_added": added,
        "files_modified": modified,
        "files_deleted": deleted,
        "files_changed": sorted(added + modified + deleted),
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
