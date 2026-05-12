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

from agentproof.contracts import TaskContract
from agentproof.events import now_iso
from agentproof.gitutils import git_diff, git_info, git_root
from agentproof.store import default_store_for_project


AGENTPROOF_DIR = ".agentproof"
ACTIVE_RUN_FILE = "active_run"
IGNORE_DIRS = {
    ".agentproof",
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
    agentproof_dir: Path
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
        if (candidate / AGENTPROOF_DIR).exists():
            return candidate.resolve()
    return cwd


def paths_for_run(run_id: str | None = None, cwd: Path | None = None) -> RunPaths:
    project_root = discover_project_root(cwd)
    agentproof_dir = project_root / AGENTPROOF_DIR
    runs_dir = agentproof_dir / "runs"
    run_dir = runs_dir / run_id if run_id else runs_dir
    return RunPaths(
        project_root=project_root,
        agentproof_dir=agentproof_dir,
        runs_dir=runs_dir,
        run_dir=run_dir,
        run_file=run_dir / "run.json",
        events_file=run_dir / "events.jsonl",
        active_file=agentproof_dir / ACTIVE_RUN_FILE,
    )


def create_run(contract: TaskContract, agent: str, cwd: Path | None = None) -> dict[str, Any]:
    project_root = discover_project_root(cwd)
    agentproof_dir = project_root / AGENTPROOF_DIR
    agentproof_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = agentproof_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = agentproof_dir / "reports"
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
        "control_mode": "observe",
        "start_time": now_iso(),
        "end_time": None,
        "duration_seconds": None,
        "contract": contract.to_dict(),
        "git": git_evidence,
    }
    write_json(paths.run_file, run)
    default_store_for_project(project_root).upsert_run(run)
    paths.events_file.touch()
    paths.active_file.write_text(run_id, encoding="utf-8")
    append_event(paths, "run_started", {"agent": agent, "task_id": contract.task_id})
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
    default_store_for_project(paths.project_root).upsert_run(run)
    append_event(paths, "run_stopped", {"changed_files": snapshot_diff["files_changed"]})
    if paths.active_file.exists() and paths.active_file.read_text(encoding="utf-8").strip() == resolved_run_id:
        paths.active_file.unlink()
    return run


def active_run_id(cwd: Path | None = None) -> str:
    project_root = discover_project_root(cwd)
    active_file = project_root / AGENTPROOF_DIR / ACTIVE_RUN_FILE
    if not active_file.exists():
        raise RuntimeError("No active AgentProof Recorder run found. Start one with `agentproof start`.")
    run_id = active_file.read_text(encoding="utf-8").strip()
    if not run_id:
        raise RuntimeError("Active AgentProof Recorder run file is empty.")
    return run_id


def latest_run_id(cwd: Path | None = None) -> str:
    paths = paths_for_run(cwd=cwd)
    if not paths.runs_dir.exists():
        raise RuntimeError("No AgentProof Recorder runs found.")
    runs = sorted(
        [path for path in paths.runs_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not runs:
        raise RuntimeError("No AgentProof Recorder runs found.")
    return runs[0].name


def record_command(command: list[str], cwd: Path | None = None) -> int:
    if not command:
        raise ValueError("No command provided.")
    run_id = active_run_id(cwd)
    paths = paths_for_run(run_id, cwd)
    started = time.time()
    command_text = shlex.join(command)
    append_event(paths, "command_started", {"command": command_text})
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
        "stdout_path": str(stdout_path.relative_to(paths.project_root)),
        "stderr_path": str(stderr_path.relative_to(paths.project_root)),
    }
    append_event(paths, "command_finished", payload)
    append_event(paths, "process.exec", payload)
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
    return default_store_for_project(paths.project_root).append_event(
        resolved_run_id,
        paths.events_file,
        event_type,
        payload,
    )


def append_event(paths: RunPaths, event_type: str, payload: dict[str, Any]) -> None:
    default_store_for_project(paths.project_root).append_event(
        paths.run_dir.name,
        paths.events_file,
        event_type,
        payload,
    )


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
