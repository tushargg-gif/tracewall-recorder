"""Tests for real-time sensitive-file enforcement.

These tests are backend-aware. The pure-Python parts (profile matching,
fail-closed behavior) run everywhere. The parts that exercise a real OS sandbox
run only when a *functional* backend is present, probed at runtime rather than
assumed -- macOS ``sandbox-exec`` denies with EPERM, while Linux ``bubblewrap``
masks (a read returns empty, a write/delete fails). We therefore assert the
security *property* (no leak / mutation prevented) per backend, not a shared
exit code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentproof.events import verify_event_chain

ROOT = Path(__file__).resolve().parents[1]

from agentproof.enforcement import (
    ENFORCEMENT_UNAVAILABLE,
    GuardProfile,
    guard_backend,
    run_guarded,
)


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _backend_usable() -> bool:
    """Probe whether the host's sandbox backend can actually launch a process."""
    backend = guard_backend()
    if backend == "none":
        return False
    try:
        result = run_guarded(_py("print('ok')"), GuardProfile(project_root=Path.cwd()))
    except Exception:
        return False
    return result.enforced and result.exit_code == 0 and "ok" in result.stdout


needs_backend = pytest.mark.skipif(
    not _backend_usable(), reason="no functional OS sandbox backend on this host"
)


@pytest.fixture
def sensitive_tree(tmp_path: Path) -> Path:
    (tmp_path / ".env").write_text("SECRET=hunter2\n")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "token.txt").write_text("tok_live_123\n")
    (tmp_path / "key.pem").write_text("-----BEGIN-----\n")
    (tmp_path / "app.py").write_text("print('app')\n")
    return tmp_path


# ---- pure-Python: profile matching ----------------------------------------
def test_profile_matches_sensitive_and_skips_allowed(sensitive_tree: Path) -> None:
    profile = GuardProfile(project_root=sensitive_tree)
    assert profile.matches(sensitive_tree / ".env")
    assert profile.matches(sensitive_tree / "secrets" / "token.txt")
    assert profile.matches(sensitive_tree / "key.pem")
    assert not profile.matches(sensitive_tree / "app.py")


def test_profile_matches_future_dotenv_variant(sensitive_tree: Path) -> None:
    # A file that does not exist yet still matches by pattern (regex backends
    # cover paths created after launch).
    assert GuardProfile(project_root=sensitive_tree).matches(sensitive_tree / ".env.local")


def test_sensitive_targets_enumeration(sensitive_tree: Path) -> None:
    files, dirs = GuardProfile(project_root=sensitive_tree).sensitive_targets()
    names = {p.name for p in files}
    assert {".env", "token.txt", "key.pem"} <= names
    assert any(d.name == "secrets" for d in dirs)
    assert "app.py" not in names


# ---- fail-closed (no backend) ---------------------------------------------
def test_fail_closed_does_not_run_command(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agentproof.enforcement.guard_backend", lambda: "none")
    sentinel = tmp_path / "ran.txt"
    profile = GuardProfile(project_root=tmp_path)
    result = run_guarded(
        _py(f"open(r'{sentinel}', 'w').write('x')"),
        profile,
        require_enforcement=True,
    )
    assert result.enforced is False
    assert result.exit_code == ENFORCEMENT_UNAVAILABLE
    assert not sentinel.exists(), "command must not run when enforcement is unavailable"


# ---- real backend: security properties ------------------------------------
@needs_backend
def test_read_of_secret_does_not_leak(sensitive_tree: Path) -> None:
    profile = GuardProfile(project_root=sensitive_tree)
    result = run_guarded(
        _py(f"print(open(r'{sensitive_tree / '.env'}').read())"), profile
    )
    assert "hunter2" not in result.stdout


@needs_backend
def test_write_to_secret_is_prevented(sensitive_tree: Path) -> None:
    env = sensitive_tree / ".env"
    before = env.read_text()
    profile = GuardProfile(project_root=sensitive_tree)
    run_guarded(_py(f"open(r'{env}', 'w').write('TAMPERED')"), profile)
    assert env.read_text() == before, "sensitive file content must be unchanged"


@needs_backend
def test_delete_of_secret_is_prevented(sensitive_tree: Path) -> None:
    token = sensitive_tree / "secrets" / "token.txt"
    profile = GuardProfile(project_root=sensitive_tree)
    run_guarded(_py(f"import os; os.remove(r'{token}')"), profile)
    assert token.exists(), "sensitive file must survive a delete attempt"


@needs_backend
def test_allowed_file_is_untouched(sensitive_tree: Path) -> None:
    app = sensitive_tree / "app.py"
    profile = GuardProfile(project_root=sensitive_tree)
    result = run_guarded(_py(f"print(open(r'{app}').read().strip())"), profile)
    assert result.exit_code == 0
    assert "print('app')" in result.stdout


@needs_backend
def test_sandbox_exec_reports_blocked(sensitive_tree: Path) -> None:
    # The clean EPERM "blocked" signal is specific to the macOS backend.
    if guard_backend() != "sandbox-exec":
        pytest.skip("blocked-flag semantics are sandbox-exec specific")
    profile = GuardProfile(project_root=sensitive_tree)
    result = run_guarded(
        _py(f"open(r'{sensitive_tree / '.env'}').read()"), profile
    )
    assert result.blocked is True
    assert result.exit_code != 0


# ---- end-to-end: enforce mode records decisions into the chain -------------
def _run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "agentproof", *args],
        cwd=cwd, text=True, capture_output=True, env=env, check=False,
    )


@needs_backend
def test_enforce_mode_records_decision_in_chain(tmp_path: Path) -> None:
    assert _run_cli(tmp_path, "init").returncode == 0
    start = _run_cli(tmp_path, "start", "--agent", "test", "--enforce")
    assert start.returncode == 0, start.stderr
    assert "Enforcement: ON" in start.stdout

    # benign, allowed command -> works under either backend
    run = _run_cli(tmp_path, "run", "--", sys.executable, "-c", "print('hi')")
    assert run.returncode == 0, run.stderr

    run_id = (tmp_path / ".agentproof" / "active_run").read_text().strip()
    events_file = tmp_path / ".agentproof" / "runs" / run_id / "events.jsonl"
    events = [json.loads(line) for line in events_file.read_text().splitlines() if line.strip()]
    types = [e["event_type"] for e in events]
    assert "enforcement_started" in types
    assert "enforcement_decision" in types
    decision = next(e for e in events if e["event_type"] == "enforcement_decision")
    assert decision["payload"]["action_taken"] == "allowed"
    # adding enforcement events must not break the tamper-evident chain
    assert verify_event_chain(events)["valid"] is True


def test_block_list_matches_flag_list() -> None:
    # The enforcer must block exactly what the verifier flags: one source.
    from agentproof import enforcement, sensitive, verifier

    assert enforcement.DEFAULT_SENSITIVE_PATTERNS == sensitive.SECRET_PATTERNS
    assert verifier.SECRET_PATTERNS == sensitive.SECRET_PATTERNS
    assert verifier.looks_secret_path is sensitive.looks_secret_path


def test_start_without_enforce_stays_observe(tmp_path: Path) -> None:
    assert _run_cli(tmp_path, "init").returncode == 0
    assert _run_cli(tmp_path, "start", "--agent", "test").returncode == 0
    run_id = (tmp_path / ".agentproof" / "active_run").read_text().strip()
    run = json.loads((tmp_path / ".agentproof" / "runs" / run_id / "run.json").read_text())
    assert run["control_mode"] == "observe"
    assert run["enforcement"]["enabled"] is False
