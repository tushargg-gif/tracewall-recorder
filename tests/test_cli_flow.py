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


def test_cli_records_verifies_and_reports_clean_run(tmp_path: Path):
    pytest_command = f"{sys.executable} -m pytest"
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "tests" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "token.py").write_text(
        "def refresh_ok():\n    return False\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "auth" / "test_token.py").write_text(
        "from src.auth.token import refresh_ok\n\n\ndef test_refresh_ok():\n    assert refresh_ok() is False\n",
        encoding="utf-8",
    )
    init = run_cli(tmp_path, "init")
    assert init.returncode == 0, init.stderr
    (tmp_path / ".tracewall" / "task.yml").write_text(
        f"""
task_id: AUTH-142
title: Fix expired JWT refresh bug
allowed_paths:
  - src/auth/**
  - tests/auth/**
forbidden_paths:
  - .env
  - infra/**
allowed_commands:
  - {pytest_command}
forbidden_actions:
  - install_new_package
success_criteria:
  - regression test added
  - relevant test suite passes
  - no unrelated files changed
verification:
  tests:
    - {pytest_command}
risk_level: medium
human_approval_required: true
""",
        encoding="utf-8",
    )
    start = run_cli(tmp_path, "start", "--agent", "codex-test")
    assert start.returncode == 0, start.stderr
    (tmp_path / "src" / "auth" / "token.py").write_text(
        "def refresh_ok():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "auth" / "test_token.py").write_text(
        "from src.auth.token import refresh_ok\n\n\ndef test_refresh_ok():\n    assert refresh_ok() is True\n",
        encoding="utf-8",
    )
    test_run = run_cli(tmp_path, "run", "--", sys.executable, "-m", "pytest")
    assert test_run.returncode == 0, test_run.stderr
    stop = run_cli(tmp_path, "stop", "--final-response", "Fixed auth and updated regression test.")
    assert stop.returncode == 0, stop.stderr
    verify = run_cli(tmp_path, "verify", "--json")
    assert verify.returncode == 0, verify.stderr
    assert '"verdict": "Pass"' in verify.stdout
    report = run_cli(tmp_path, "report", "--print")
    assert report.returncode == 0, report.stderr
    assert "tracewall Recorder Report" in report.stdout
    assert "Score:" in report.stdout
