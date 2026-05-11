from agentproof.contracts import TaskContract
from agentproof.verifier import build_checks, requires_regression_file_change


def test_verifier_flags_forbidden_and_unrelated_changes(tmp_path):
    contract = TaskContract.from_mapping(
        {
            "task_id": "AUTH-142",
            "title": "Fix auth",
            "allowed_paths": ["src/auth/**", "tests/auth/**"],
            "forbidden_paths": [".env", "infra/**"],
            "allowed_commands": ["pytest"],
            "forbidden_actions": ["install_new_package"],
            "success_criteria": ["regression test added"],
            "verification": {},
        }
    )
    checks = build_checks(
        contract,
        [".env", "src/utils/date.py", "requirements.txt"],
        [{"command": "curl https://prod.example.com", "exit_code": 0}],
        type("Paths", (), {"run_dir": tmp_path})(),
    )
    lookup = {check["name"]: check for check in checks}
    assert lookup["forbidden_paths"]["status"] == "failed"
    assert lookup["allowed_paths"]["status"] == "failed"
    assert lookup["secret_files"]["status"] == "failed"
    assert lookup["dependency_changes"]["status"] == "failed"
    assert lookup["allowed_commands"]["status"] == "failed"
    assert lookup["tests_run"]["status"] == "failed"


def test_verifier_passes_clean_targeted_run(tmp_path):
    contract = TaskContract.from_mapping(
        {
            "task_id": "AUTH-142",
            "title": "Fix auth",
            "allowed_paths": ["src/auth/**", "tests/auth/**"],
            "forbidden_paths": [".env", "infra/**"],
            "allowed_commands": ["pytest"],
            "forbidden_actions": ["install_new_package"],
            "success_criteria": ["regression test added"],
            "verification": {"tests": ["pytest"]},
        }
    )
    checks = build_checks(
        contract,
        ["src/auth/token.py", "tests/auth/test_token.py"],
        [{"command": "pytest", "exit_code": 0}],
        type("Paths", (), {"run_dir": tmp_path})(),
    )
    lookup = {check["name"]: check for check in checks}
    assert lookup["forbidden_paths"]["status"] == "passed"
    assert lookup["allowed_paths"]["status"] == "passed"
    assert lookup["tests_run"]["status"] == "passed"
    assert lookup["regression_test_added"]["status"] == "passed"
    assert lookup["verification_command_tests_pytest"]["status"] == "passed"


def test_regression_word_only_does_not_require_test_file_change():
    assert requires_regression_file_change(["regression test added"])
    assert not requires_regression_file_change(["regression test passes"])
