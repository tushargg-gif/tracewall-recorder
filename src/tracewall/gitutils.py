from __future__ import annotations

from pathlib import Path
import subprocess


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def git_root(cwd: Path) -> Path | None:
    result = run_git(["rev-parse", "--show-toplevel"], cwd)
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return Path(path) if path else None


def git_info(root: Path) -> dict[str, object]:
    info: dict[str, object] = {
        "available": False,
        "root": str(root),
        "head": None,
        "branch": None,
        "dirty": None,
        "status": [],
    }
    if git_root(root) is None:
        return info

    info["available"] = True
    head = run_git(["rev-parse", "--verify", "HEAD"], root)
    if head.returncode == 0:
        info["head"] = head.stdout.strip()
    branch = run_git(["branch", "--show-current"], root)
    if branch.returncode == 0:
        info["branch"] = branch.stdout.strip()
    status = run_git(["status", "--porcelain"], root)
    if status.returncode == 0:
        lines = [line for line in status.stdout.splitlines() if line]
        info["status"] = lines
        info["dirty"] = bool(lines)
    return info


def git_diff(root: Path) -> dict[str, object]:
    if git_root(root) is None:
        return {"available": False, "name_status": "", "diff": ""}
    name_status = run_git(["diff", "--name-status"], root)
    diff = run_git(["diff", "--no-ext-diff"], root)
    staged_name_status = run_git(["diff", "--cached", "--name-status"], root)
    staged_diff = run_git(["diff", "--cached", "--no-ext-diff"], root)
    return {
        "available": True,
        "name_status": name_status.stdout if name_status.returncode == 0 else "",
        "diff": diff.stdout if diff.returncode == 0 else "",
        "staged_name_status": staged_name_status.stdout
        if staged_name_status.returncode == 0
        else "",
        "staged_diff": staged_diff.stdout if staged_diff.returncode == 0 else "",
    }
