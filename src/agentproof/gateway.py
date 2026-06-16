"""The Gateway — the single chokepoint every agent action flows through.

AgentProof is not a recorder a human drives by hand. The *AI is the orchestrator*;
it drives the agents. The **Gateway** is the broker the orchestrator routes every
worker-agent action through. A worker agent cannot run a command or call a tool
except *through* here — so capture, policy, and enforcement are guaranteed by
construction, and every action is attributed to the agent that took it.

For each action the gateway: records it (attributed to the agent) → evaluates the
active policy (allow / block, graduated by mode) → executes or blocks → returns.

This is the "one chokepoint that records and enforces" from the North Star, made
real. The flow / review / recommender / policy layers all sit on top of what the
gateway captures.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import shlex
import subprocess
import time

from agentproof import enforce
from agentproof.events import redact_secrets
from agentproof.recorder import append_event, paths_for_run


@dataclass
class BrokerResult:
    allowed: bool
    outcome: str               # "allowed" | "alerted" | "blocked"
    decision: dict[str, Any]   # {decision, rule_id, reason}
    output: Any = None
    exit_code: int | None = None

    @property
    def blocked(self) -> bool:
        return self.outcome == "blocked"


class Gateway:
    """The broker an orchestrator routes agent actions through."""

    def __init__(self, run_id: str, cwd: Path | None = None, policy_mode: str = "observe"):
        self.run_id = run_id
        self.paths = paths_for_run(run_id, cwd)
        self.policy_mode = policy_mode
        self.policy = enforce.load_active_policy(self.paths.agentproof_dir)

    # -- the two brokered capabilities ------------------------------------

    def command(self, agent: str, command: list[str] | str) -> BrokerResult:
        """Run a shell command on behalf of ``agent`` — brokered."""
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        label = shlex.join(argv)
        decision, outcome = self._gate(enforce.action_from_command(label), agent, label)
        if outcome == "blocked":
            return BrokerResult(False, outcome, decision)

        started = time.time()
        append_event(self.paths, "command_started", {"agent": agent, "command": label})
        result = subprocess.run(argv, cwd=self.paths.project_root, text=True, capture_output=True, check=False)
        append_event(self.paths, "command_finished", {
            "agent": agent, "command": label, "exit_code": result.returncode,
            "duration_seconds": round(time.time() - started, 3),
        })
        return BrokerResult(True, outcome, decision, output=result.stdout, exit_code=result.returncode)

    def tool_call(self, agent: str, server: str, tool: str,
                  arguments: dict[str, Any] | None = None,
                  handler: Callable[[str, dict[str, Any]], Any] | None = None) -> BrokerResult:
        """Call an MCP/tool on behalf of ``agent`` — brokered. ``handler`` performs
        the real call when allowed; omitted in dry demos."""
        arguments = arguments or {}
        label = f"{server}:{tool}"
        request = {"method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        append_event(self.paths, "mcp.tool.call.started",
                     {"agent": agent, "server_name": server, "request": redact_secrets(request)})
        decision, outcome = self._gate(enforce.action_from_tool(server, tool), agent, label)
        if outcome == "blocked":
            append_event(self.paths, "mcp.error",
                         {"agent": agent, "server_name": server, "error": "blocked by policy",
                          "rule_id": decision["rule_id"]})
            return BrokerResult(False, outcome, decision)

        result = handler(tool, arguments) if handler else {"ok": True}
        append_event(self.paths, "mcp.tool.call.finished",
                     {"agent": agent, "server_name": server, "response": redact_secrets({"result": result})})
        return BrokerResult(True, outcome, decision, output=result)

    # -- the gate ----------------------------------------------------------

    def _gate(self, action: dict[str, Any], agent: str, label: str) -> tuple[dict[str, Any], str]:
        decision = enforce.evaluate_action(action, self.policy)
        outcome = enforce.enforced_outcome(decision["decision"], self.policy_mode)
        append_event(self.paths, "policy.decision", {
            "agent": agent, "action": label, "match_kind": action["kind"],
            "decision": decision["decision"], "rule_id": decision["rule_id"],
            "reason": decision["reason"], "mode": self.policy_mode, "outcome": outcome,
        })
        if outcome == "blocked":
            append_event(self.paths, "policy.enforcement", {
                "agent": agent, "action": label, "rule_id": decision["rule_id"],
                "reason": decision["reason"], "action_taken": "blocked",
            })
        return decision, outcome
