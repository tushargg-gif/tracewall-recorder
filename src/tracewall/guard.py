"""`tracewall guard -- <agent>` — run a coding agent inside an OS sandbox.

The ground-truth layer: instead of trusting the agent to report what it does, we
launch it under a kernel sandbox (macOS sandbox-exec / Linux bubblewrap) so the OS
denies reads/writes of secret files for the agent **and everything it spawns** —
even actions buried inside an approved command. Thin on purpose: the profile and
the sandbox already live in enforcement.py; this only builds the profile from the
active policy, launches with inherited stdio, and records the session.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
import subprocess
import sys

from tracewall.enforce import load_active_policy
from tracewall.enforcement import ENFORCEMENT_UNAVAILABLE, GuardProfile, guard_argv, guard_backend
from tracewall.hook import ensure_run
from tracewall.recorder import append_event, paths_for_run

# Seatbelt deny line, e.g.: "Sandbox: cat(123) deny(1) file-read-data /proj/.env"
_DENY_RE = re.compile(r"([\w.\-]+)\((\d+)\)\s+deny\(\d+\)\s+(\S+)\s+(/.*)")


def parse_sandbox_denials(log_text: str, project_root: Path, source: str) -> list[dict]:
    """Pure: macOS unified-log ndjson -> os.file.denied payloads under our root."""
    root = str(Path(project_root).resolve())
    out: list[dict] = []
    for line in log_text.splitlines():
        line = line.strip()
        if "{" not in line:
            continue
        try:
            msg = (json.loads(line).get("eventMessage")) or ""
        except ValueError:
            continue
        m = _DENY_RE.search(msg)
        if not m:
            continue
        process, pid, operation, path = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        if not path.startswith(root):
            continue
        out.append({"source": source, "process": process, "pid": int(pid),
                    "operation": operation, "path": path, "action_taken": "blocked"})
    return out


def _collect_macos_denials(since: str, project_root: Path, source: str) -> list[dict]:
    # ponytail: best-effort; the predicate/level may need tuning per macOS version,
    # and the structured-event upgrade path is the Endpoint Security framework.
    try:
        out = subprocess.run(
            ["log", "show", "--start", since, "--info", "--style", "ndjson",
             "--predicate", 'eventMessage CONTAINS "deny("'],
            capture_output=True, text=True, timeout=20,
        )
        return parse_sandbox_denials(out.stdout, project_root, source)
    except (OSError, subprocess.SubprocessError):
        return []


def _profile(cwd: Path, policy: dict) -> GuardProfile:
    # GuardProfile already denies every secret path (SECRET_PATTERNS); add any
    # specific paths a learned block rule named so OS enforcement matches policy.
    extra = [
        (rule.get("match") or {}).get("arg_glob")
        for rule in policy.get("rules", [])
        if rule.get("decision") == "block" and (rule.get("match") or {}).get("arg_glob")
    ]
    return GuardProfile(project_root=cwd, extra_paths=tuple(p for p in extra if p))


def run_guard(command: list[str], cwd: Path | None = None, source: str = "agent") -> int:
    """Launch ``command`` under the OS sandbox. Fail-closed if no backend."""
    cwd = Path(cwd or Path.cwd())
    backend = guard_backend()
    if backend == "none":
        print("tracewall guard: no sandbox backend on this host "
              "(needs macOS sandbox-exec or Linux bwrap). Refusing to run unprotected.",
              file=sys.stderr)
        return ENFORCEMENT_UNAVAILABLE

    profile = _profile(cwd, load_active_policy(paths_for_run(cwd=cwd).tracewall_dir))
    run_id = ensure_run(cwd, agent=source)
    paths = paths_for_run(run_id, cwd)
    append_event(paths, "guard.started",
                 {"source": source, "backend": backend, "command": command,
                  "deny": profile.deny_regexes})
    since = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # inherited stdio so the agent stays interactive; the kernel enforces the jail
    completed = subprocess.run(guard_argv(command, profile, backend, cwd), cwd=str(cwd))
    # record what the kernel actually denied, so the run shows it (macOS unified log)
    if backend == "sandbox-exec":
        for denial in _collect_macos_denials(since, cwd, source):
            append_event(paths, "os.file.denied", denial)
    append_event(paths, "guard.stopped",
                 {"source": source, "backend": backend, "exit_code": completed.returncode})
    return completed.returncode
