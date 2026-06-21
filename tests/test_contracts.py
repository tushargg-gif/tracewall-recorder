from pathlib import Path

from tracewall.contracts import TaskContract, load_contract, match_command, match_path


def test_path_matching_supports_recursive_patterns():
    assert match_path("src/auth/refresh.py", "src/auth/**")
    assert match_path("src/auth", "src/auth/**")
    assert not match_path("src/payments/pay.py", "src/auth/**")


def test_command_matching_allows_exact_or_prefixed_commands():
    assert match_command("pytest tests/auth", "pytest")
    assert match_command("npm test", "npm test")
    assert not match_command("curl https://prod.example.com", "pytest")


def test_load_contract_from_yaml(tmp_path: Path):
    contract_path = tmp_path / "task.yml"
    contract_path.write_text(
        """
task_id: AUTH-142
title: Fix expired JWT refresh bug
allowed_paths:
  - src/auth/**
forbidden_paths:
  - .env
allowed_commands:
  - pytest
success_criteria:
  - regression test added
risk_level: medium
human_approval_required: true
""",
        encoding="utf-8",
    )
    contract = load_contract(contract_path)
    assert isinstance(contract, TaskContract)
    assert contract.task_id == "AUTH-142"
    assert contract.path_is_allowed("src/auth/token.py")
    assert not contract.path_is_allowed("src/payments/pay.py")
    assert contract.path_is_forbidden(".env")
