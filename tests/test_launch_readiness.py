from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_readme_referenced_report_exists():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "report.md" in readme
    report = ROOT / "report.md"
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "Verdict: Fail" in report_text
    assert "Score: 55/100" in report_text
    assert "Risk: high" in report_text
    assert "Policy violations: 18" in report_text
    assert "Event chain: passed" in report_text
    assert "Secret redaction: passed" in report_text
    assert "MCP blocked: yes" in report_text


def test_agentproof_recorder_alias_help_works():
    primary = Path(sys.executable).with_name("agentproof")
    primary_result = subprocess.run(
        [str(primary), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert primary_result.returncode == 0, primary_result.stderr
    assert "AgentProof Recorder" in primary_result.stdout

    alias = Path(sys.executable).with_name("agentproof-recorder")
    result = subprocess.run(
        [str(alias), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "AgentProof Recorder" in result.stdout


def test_agentproof_shell_command_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "agentproof", "shell"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "agentproof run -- <command>" in result.stdout
