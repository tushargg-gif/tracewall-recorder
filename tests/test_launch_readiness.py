from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_tracewall_recorder_alias_help_works():
    primary = Path(sys.executable).with_name("tracewall")
    primary_result = subprocess.run(
        [str(primary), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert primary_result.returncode == 0, primary_result.stderr
    assert "tracewall Recorder" in primary_result.stdout

    alias = Path(sys.executable).with_name("tracewall-recorder")
    result = subprocess.run(
        [str(alias), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "tracewall Recorder" in result.stdout
