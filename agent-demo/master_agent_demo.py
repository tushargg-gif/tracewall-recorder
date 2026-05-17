#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import shutil
import subprocess
import sys


DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentproof.contracts import TaskContract
from agentproof.orchestration import (
    apply_automatic_amendment,
    build_policy_from_template,
    policy_template_selected_payload,
    policy_version_payload,
    worker_completed_payload,
    worker_delegated_payload,
    worker_registered_payload,
)
from agentproof.recorder import (
    create_run,
    diff_snapshots,
    paths_for_run,
    read_json as read_agentproof_json,
    record_command,
    record_event,
    snapshot_files,
    stop_run,
    write_json as write_agentproof_json,
)
from agentproof.reports import generate_report
from agentproof.verifier import verify_run


WORKSPACE_DIR = DEMO_DIR / ".workspace"
GENERATED_DIR = DEMO_DIR / "generated"
SCENARIO_PATH = DEMO_DIR / "scenario.json"
DEMO_TEST_COMMAND = "python3 demo_test_probe.py"


@dataclass(frozen=True)
class AgentResult:
    agent: str
    summary: str
    files: list[str]
    safe: bool


class WorkerAgent:
    name = "Worker Agent"

    def __init__(self, task: str = "") -> None:
        self.task = task

    def run(self, workspace: Path, run_id: str) -> AgentResult:
        raise NotImplementedError

    def record_claim(self, workspace: Path, run_id: str, result: AgentResult) -> None:
        record_event(
            "agent.output",
            {
                "agent": result.agent,
                "summary": result.summary,
                "files": result.files,
                "safe": result.safe,
            },
            run_id=run_id,
            cwd=workspace,
        )


class ProductAgent(WorkerAgent):
    name = "Product Agent"

    def run(self, workspace: Path, run_id: str) -> AgentResult:
        path = workspace / "docs" / "demo-master-agent-workflow.md"
        path.write_text(
            "\n".join(
                [
                    "# Demo Master Agent Workflow",
                    "",
                    "This demo updates documentation through a master-agent flow.",
                    "",
                    "The master agent delegates documentation work, records each worker output,",
                    "and relies on AgentProof Recorder to verify the evidence before approval.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return AgentResult(
            self.name,
            "Created a demo workflow note for the docs.",
            ["docs/demo-master-agent-workflow.md"],
            True,
        )


class CopywriterAgent(WorkerAgent):
    name = "Copywriter Agent"

    def run(self, workspace: Path, run_id: str) -> AgentResult:
        path = workspace / "README.md"
        text = path.read_text(encoding="utf-8")
        addition = (
            "\n\n## Local Master-Agent Demo\n\n"
            "This demo shows a master agent delegating docs work while AgentProof Recorder "
            "captures evidence and blocks trust when a worker violates policy.\n"
        )
        if "## Local Master-Agent Demo" not in text:
            path.write_text(text.rstrip() + addition, encoding="utf-8")
        return AgentResult(
            self.name,
            "Added a short README section for the master-agent demo.",
            ["README.md"],
            True,
        )


class CodeAgent(WorkerAgent):
    name = "Code Agent"

    def run(self, workspace: Path, run_id: str) -> AgentResult:
        path = workspace / "examples" / "good-agent-run" / "README.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8") if path.exists() else "# Good Agent Run\n"
        addition = (
            "\n## Demo Note\n\n"
            "A code-oriented worker may update examples after the master agent expands "
            "the active policy version.\n"
        )
        if "## Demo Note" not in text:
            path.write_text(text.rstrip() + addition, encoding="utf-8")
        return AgentResult(
            self.name,
            "Updated the good-agent example after an automatic policy amendment.",
            ["examples/good-agent-run/README.md"],
            True,
        )


class TestAgent(WorkerAgent):
    name = "Test Agent"

    def run(self, workspace: Path, run_id: str) -> AgentResult:
        command = DEMO_TEST_COMMAND.split()
        exit_code = record_command(command, cwd=workspace)
        return AgentResult(
            self.name,
            f"Ran exact demo test probe with exit code {exit_code}.",
            [],
            exit_code == 0,
        )


class RogueAgent(WorkerAgent):
    name = "Rogue Agent"

    def run(self, workspace: Path, run_id: str) -> AgentResult:
        path = workspace / "package.json"
        path.write_text(
            json.dumps(
                {
                    "scripts": {"demo": "node unsafe-demo.js"},
                    "dependencies": {"left-pad": "1.3.0"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return AgentResult(
            self.name,
            "Claimed the docs work needed no risky file changes.",
            [],
            True,
        )


class MasterAgent:
    def __init__(self, repo_root: Path, demo_dir: Path) -> None:
        self.repo_root = repo_root
        self.demo_dir = demo_dir
        self.scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

    def run(self) -> int:
        reset_demo_dirs()
        knowledge = self.read_project_knowledge()
        workspace = self.prepare_workspace()
        workers = self.worker_specs()
        test_command = DEMO_TEST_COMMAND
        policy = build_policy_from_template(
            self.scenario["policy_template"],
            self.scenario["task_id"],
            self.scenario["task"],
            workers,
            test_command,
        )

        contract = TaskContract.from_mapping(policy["task_contract"])
        run = create_run(contract, "Master Agent", cwd=workspace)
        run_id = run["run_id"]

        record_event("master.context.read", knowledge["summary"], run_id=run_id, cwd=workspace)
        record_event("policy.template.selected", policy_template_selected_payload(policy), run_id=run_id, cwd=workspace)
        record_event("policy.version.activated", policy_version_payload(policy), run_id=run_id, cwd=workspace)

        for name, scope in policy["task_contract"]["worker_scopes"].items():
            record_event("worker.registered", worker_registered_payload(name, scope), run_id=run_id, cwd=workspace)

        policy, amendment = apply_automatic_amendment(
            policy,
            "Code Agent needs examples/** for the demo example note.",
            add_allowed_paths=["examples/**"],
            worker_scope_updates={"Code Agent": {"allowed_paths_add": ["examples/**"]}},
        )
        record_event("policy.amendment.applied", amendment, run_id=run_id, cwd=workspace)
        record_event("policy.version.activated", policy_version_payload(policy), run_id=run_id, cwd=workspace)
        self.activate_policy(run_id, workspace, policy)
        write_json(GENERATED_DIR / "policy.json", policy)

        for agent in self.worker_agents(workers):
            active_contract = policy["task_contract"]
            scope = active_contract["worker_scopes"][agent.name]
            policy_version = int(active_contract["policy_version"])
            record_event(
                "worker.delegated",
                worker_delegated_payload(agent.name, agent.task, policy_version, scope),
                run_id=run_id,
                cwd=workspace,
            )
            before = snapshot_files(workspace)
            result = agent.run(workspace, run_id)
            after = snapshot_files(workspace)
            actual_changed_files = diff_snapshots(before, after)["files_changed"]
            agent.record_claim(workspace, run_id, result)
            record_event(
                "worker.completed",
                worker_completed_payload(
                    result.agent,
                    result.summary,
                    result.files,
                    actual_changed_files,
                    policy_version,
                    scope,
                    result.safe,
                ),
                run_id=run_id,
                cwd=workspace,
            )

        stop_run(run_id, "Delegation finished. Reading AgentProof report before final decision.", cwd=workspace)
        verify_run(run_id, cwd=workspace)
        report_paths = generate_report(run_id, cwd=workspace)

        exported_report = GENERATED_DIR / "agentproof_report.json"
        export_publishable_report(report_paths["json"], exported_report, workspace)
        shutil.copyfile(paths_for_run(run_id, workspace).events_file, GENERATED_DIR / "events.jsonl")

        decision = self.decide(exported_report, GENERATED_DIR / "events.jsonl")
        self.print_decision(decision)
        return 0 if decision["harness_passed"] else 1

    def read_project_knowledge(self) -> dict[str, Any]:
        content_files = [self.repo_root / "README.md"]
        content_files.extend(sorted((self.repo_root / "docs").glob("*.md")))
        content_files.extend(sorted((self.repo_root / "examples").glob("*/*.md")))
        content_files.extend(sorted((self.repo_root / "examples").glob("*/contract.yaml")))
        seen = [
            str(path.relative_to(self.repo_root))
            for path in content_files
            if path.exists()
        ]
        return {
            "files_read": seen,
            "summary": {
                "files_read": seen,
                "reason": "Master Agent read local README, docs, and examples before selecting a policy template.",
            },
        }

    def prepare_workspace(self) -> Path:
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.repo_root / "README.md", WORKSPACE_DIR / "README.md")
        shutil.copytree(self.repo_root / "docs", WORKSPACE_DIR / "docs")
        shutil.copytree(self.repo_root / "examples", WORKSPACE_DIR / "examples")
        (WORKSPACE_DIR / "demo_test_probe.py").write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "assert Path('README.md').exists()",
                    "assert Path('docs/demo-master-agent-workflow.md').exists()",
                    "assert Path('examples/good-agent-run/README.md').exists()",
                    "print('demo test probe passed')",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "init"], cwd=WORKSPACE_DIR, text=True, capture_output=True, check=False)
        subprocess.run(["git", "config", "user.email", "demo@example.com"], cwd=WORKSPACE_DIR, check=False)
        subprocess.run(["git", "config", "user.name", "AgentProof Demo"], cwd=WORKSPACE_DIR, check=False)
        subprocess.run(["git", "add", "."], cwd=WORKSPACE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=WORKSPACE_DIR, text=True, capture_output=True, check=False)
        return WORKSPACE_DIR

    def activate_policy(self, run_id: str, workspace: Path, policy: dict[str, Any]) -> None:
        paths = paths_for_run(run_id, workspace)
        run = read_agentproof_json(paths.run_file)
        run["contract"] = policy["task_contract"]
        write_agentproof_json(paths.run_file, run)

    def worker_specs(self) -> list[dict[str, Any]]:
        raw_workers = self.scenario.get("workers") or self.scenario.get("worker_agents") or []
        workers: list[dict[str, Any]] = []
        for item in raw_workers:
            if isinstance(item, dict):
                workers.append(dict(item))
            else:
                name = str(item)
                workers.append({"name": name, "role": role_for_worker_name(name), "task": ""})
        return workers

    def worker_agents(self, workers: list[dict[str, Any]]) -> list[WorkerAgent]:
        classes = {
            "Product Agent": ProductAgent,
            "Copywriter Agent": CopywriterAgent,
            "Code Agent": CodeAgent,
            "Test Agent": TestAgent,
            "Rogue Agent": RogueAgent,
        }
        return [
            classes[str(worker["name"])](str(worker.get("task") or ""))
            for worker in workers
        ]

    def decide(self, report_path: Path, events_path: Path) -> dict[str, Any]:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        verification = report["verification"]
        run = report["run"]
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        violations = verification.get("policy_violations") or []
        violation_ids = {str(item.get("policy_id")) for item in violations}
        checks = {check["name"]: check for check in verification.get("checks") or []}
        event_types = {str(event.get("event_type")) for event in events}
        required_violations = {
            "no_forbidden_path_change",
            "no_unrelated_file_change",
            "no_unapproved_dependency",
            "worker_scope_exceeded",
            "worker_forbidden_path_change",
        }
        failures = []
        if verification.get("verdict") != "Fail":
            failures.append("expected AgentProof verdict Fail")
        violating_agent = worker_for_actual_file(events, "package.json") or "unknown"
        if violating_agent != "Rogue Agent":
            failures.append("expected Rogue Agent attribution from actual file diff")
        if "package.json" not in verification.get("changed_files", []):
            failures.append("expected package.json in changed files")
        missing_violations = sorted(required_violations - violation_ids)
        if missing_violations:
            failures.append(f"missing policy violations: {', '.join(missing_violations)}")
        if checks.get("event_chain_integrity", {}).get("status") != "passed":
            failures.append("event-chain integrity did not pass")
        if checks.get("network_events_recorded", {}).get("status") != "passed":
            failures.append("zero-network policy was not treated as passing evidence")
        if "policy.amendment.applied" not in event_types:
            failures.append("policy amendment event was not recorded")
        if "worker.completed" not in event_types:
            failures.append("worker completion evidence was not recorded")
        if run.get("verdict") != verification.get("verdict") or run.get("risk") != verification.get("risk"):
            failures.append("run and verification verdict/risk are inconsistent")

        return {
            "harness_passed": not failures,
            "failures": failures,
            "expected_decision": "FAIL",
            "actual_verdict": verification.get("verdict"),
            "score": verification.get("score"),
            "risk": verification.get("risk"),
            "violating_agent": violating_agent,
            "required_violations": sorted(required_violations),
            "observed_violations": sorted(violation_ids),
            "changed_files": verification.get("changed_files") or [],
            "event_count": len(events),
            "network_events_status": checks.get("network_events_recorded", {}).get("status"),
        }

    def print_decision(self, decision: dict[str, Any]) -> None:
        print("\n=== AgentProof Demo Test Harness ===")
        print(f"Harness status: {'PASS' if decision['harness_passed'] else 'FAIL'}")
        print(f"Expected final decision: {decision['expected_decision']}")
        print(f"AgentProof verdict: {decision['actual_verdict']}")
        print(f"Score: {decision['score']}/100")
        print(f"Risk: {decision['risk']}")
        print(f"Violating agent: {decision['violating_agent']}")
        print(f"Network evidence status: {decision['network_events_status']}")
        print("\nRequired violations:")
        for policy_id in decision["required_violations"]:
            status = "present" if policy_id in decision["observed_violations"] else "missing"
            print(f"- {policy_id}: {status}")
        if decision["failures"]:
            print("\nHarness failures:")
            for failure in decision["failures"]:
                print(f"- {failure}")
        print("\nChanged files:")
        for path in decision["changed_files"]:
            print(f"- {path}")
        print("\nGenerated evidence:")
        print(f"- {GENERATED_DIR / 'policy.json'}")
        print(f"- {GENERATED_DIR / 'events.jsonl'}")
        print(f"- {GENERATED_DIR / 'agentproof_report.json'}")


def role_for_worker_name(name: str) -> str:
    return {
        "Product Agent": "product",
        "Copywriter Agent": "copywriter",
        "Code Agent": "example_writer",
        "Test Agent": "tester",
        "Rogue Agent": "rogue",
    }.get(name, "")


def worker_for_actual_file(events: list[dict[str, Any]], file_name: str) -> str | None:
    for event in events:
        payload = event.get("payload") or {}
        files = payload.get("actual_changed_files") or []
        if event.get("event_type") == "worker.completed" and file_name in files:
            return str(payload.get("agent") or "")
    return None


def reset_demo_dirs() -> None:
    if WORKSPACE_DIR.exists():
        shutil.rmtree(WORKSPACE_DIR)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for path in ["policy.json", "events.jsonl", "agentproof_report.json"]:
        target = GENERATED_DIR / path
        if target.exists():
            target.unlink()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_publishable_report(source: Path, target: Path, workspace: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    sanitized = sanitize_publishable_value(payload, workspace.resolve().as_posix(), "agent-demo/.workspace")
    write_json(target, sanitized)


def sanitize_publishable_value(value: Any, local_root: str, public_root: str) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_publishable_value(item, local_root, public_root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_publishable_value(item, local_root, public_root) for item in value]
    if isinstance(value, str):
        return value.replace(local_root, public_root)
    return value


def main() -> int:
    return MasterAgent(REPO_ROOT, DEMO_DIR).run()


if __name__ == "__main__":
    raise SystemExit(main())
