from __future__ import annotations

from tracewall.events import redact_secrets
from tracewall.orchestration import apply_automatic_amendment, build_policy_from_template


def demo_workers():
    return [
        {"name": "Product Agent", "role": "product", "task": "write docs"},
        {"name": "Copywriter Agent", "role": "copywriter", "task": "write README"},
        {"name": "Code Agent", "role": "example_writer", "task": "update example"},
        {"name": "Test Agent", "role": "tester", "task": "run probe"},
        {"name": "Rogue Agent", "role": "rogue", "task": "attempt dependency change"},
    ]


def test_docs_only_policy_template_creates_contract_and_worker_scopes():
    policy = build_policy_from_template(
        "docs_only",
        "DEMO-DOCS-001",
        "Update docs",
        demo_workers(),
        "/usr/bin/python demo_test_probe.py",
    )
    contract = policy["task_contract"]

    assert contract["policy_template"] == "docs_only"
    assert contract["policy_source"] == "template_registry"
    assert contract["llm_generated_policy"] is False
    assert policy["llm_generated_policy"] is False
    assert contract["policy_version"] == 1
    assert contract["allowed_paths"] == ["README.md", "docs/**"]
    assert "package.json" in contract["forbidden_paths"]
    assert contract["worker_scopes"]["Copywriter Agent"]["allowed_paths"] == ["README.md"]
    assert contract["worker_scopes"]["Code Agent"]["allowed_paths"] == []
    assert contract["worker_scopes"]["Test Agent"]["allowed_commands"] == ["/usr/bin/python demo_test_probe.py"]


def test_automatic_policy_amendment_versions_policy_and_worker_scope():
    policy = build_policy_from_template(
        "docs_only",
        "DEMO-DOCS-001",
        "Update docs",
        demo_workers(),
        "/usr/bin/python demo_test_probe.py",
    )
    updated, amendment = apply_automatic_amendment(
        policy,
        "Code Agent needs examples scope.",
        add_allowed_paths=["examples/**"],
        worker_scope_updates={"Code Agent": {"allowed_paths_add": ["examples/**"]}},
    )

    contract = updated["task_contract"]
    assert amendment["mode"] == "automatic"
    assert amendment["from_version"] == 1
    assert amendment["to_version"] == 2
    assert contract["policy_version"] == 2
    assert "examples/**" in contract["allowed_paths"]
    assert contract["worker_scopes"]["Code Agent"]["allowed_paths"] == ["examples/**"]
    assert len(contract["policy_versions"]) == 2


def test_policy_metadata_booleans_with_secret_in_key_are_not_redacted():
    redacted = redact_secrets(
        {
            "secrets_access_allowed": False,
            "api_key": "real-secret",
        }
    )

    assert redacted["secrets_access_allowed"] is False
    assert redacted["api_key"]["redacted"] is True
