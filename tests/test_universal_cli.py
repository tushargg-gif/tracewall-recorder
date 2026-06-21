from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "tracewall", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_cli_records_universal_events(tmp_path: Path):
    init = run_cli(tmp_path, "init")
    assert init.returncode == 0, init.stderr
    (tmp_path / ".tracewall" / "task.yml").write_text(
        """
task_id: NET-1
title: Fetch public data
allowed_paths: []
forbidden_paths:
  - .env
allowed_commands: []
success_criteria:
  - public API fetched
verification: {}
risk_level: medium
human_approval_required: true
""",
        encoding="utf-8",
    )
    start = run_cli(tmp_path, "start", "--agent", "browser-agent")
    assert start.returncode == 0, start.stderr
    event = run_cli(
        tmp_path,
        "event",
        "network.request",
        "--payload",
        '{"url":"https://api.example.com/data","status_code":200}',
    )
    assert event.returncode == 0, event.stderr
    stop = run_cli(tmp_path, "stop", "--final-response", "Fetched public data.")
    assert stop.returncode == 0, stop.stderr
    verify = run_cli(tmp_path, "verify", "--json")
    assert verify.returncode == 0, verify.stderr
    assert '"network.request": 1' in verify.stdout
    assert '"policy_violations": []' in verify.stdout
