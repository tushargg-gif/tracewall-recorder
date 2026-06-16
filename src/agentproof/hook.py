"""AgentProof as a Claude Code hook — the gateway, in front of a real agent.

Claude Code calls this *before* every tool runs (PreToolUse), passing the tool
name and its input on stdin. We map that to a normalized action, decide
**allow / ask / deny**, record it to the run's tamper-evident log, and return
Claude Code's permission JSON. A PostToolUse call records the outcome.

Decision order:
  1. The learned **active policy** (your demonstrated allow/block/ask rules) wins.
  2. Otherwise, safe **defaults**: deny reading secret files; ask on the genuinely
     risky (web calls, installs, egress, destructive, consequential tool calls);
     allow the safe majority.

So on day one it already stops the `.env` read and escalates the risky few — and
it gets quieter as it learns from your answers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from agentproof import enforce
from agentproof.contracts import load_contract, write_default_contract
from agentproof.events import redact_secrets
from agentproof.insight import analyze_action
from agentproof.recorder import append_event, create_run, latest_run_id, paths_for_run, read_json

AGENT = "claude-code"
_PERMISSION = {"block": "deny", "ask": "ask", "allow": "allow", "none": "allow"}


# --- map a Claude Code tool event to a normalized action -------------------

def action_from_event(tool_name: str, tool_input: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return (normalized action, human label) for a Claude Code tool call."""
    t = tool_name or ""
    inp = tool_input or {}
    if t == "Bash":
        cmd = str(inp.get("command") or "")
        return enforce.action_from_command(cmd), cmd or "(empty)"
    if t == "Read":
        p = str(inp.get("file_path") or inp.get("path") or "")
        return enforce.action_from_file("read", p), f"Read {p}"
    if t in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = str(inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or "")
        return enforce.action_from_file("write", p), f"Write {p}"
    if t == "WebFetch":
        url = str(inp.get("url") or "")
        a = enforce.action_from_tool("web", "fetch"); a["url"] = url
        return a, f"WebFetch {url}"
    if t == "WebSearch":
        a = enforce.action_from_tool("web", "search")
        return a, f"WebSearch {inp.get('query') or ''}"
    if t.startswith("mcp__"):
        parts = t.split("__")
        server = parts[1] if len(parts) > 1 else "mcp"
        tool = parts[2] if len(parts) > 2 else "tool"
        return enforce.action_from_tool(server, tool), f"{server}:{tool}"
    # other built-ins (Glob, Grep, TodoWrite, Task, …) — low-risk by default
    return enforce.action_from_tool("claude-code", t.lower()), t


# --- decide allow / ask / deny ---------------------------------------------

def decide(action: dict[str, Any], label: str, cwd: Path) -> dict[str, Any]:
    policy = enforce.load_active_policy(paths_for_run(cwd=cwd).agentproof_dir)
    learned = enforce.evaluate_action(action, policy)
    if learned["decision"] != "none":
        decision, reason, rule_id, source = learned["decision"], learned["reason"], learned["rule_id"], "policy"
    else:
        decision, reason = _default_decision(action, label)
        rule_id, source = None, "default"
    return {
        "decision": decision,
        "permission": _PERMISSION.get(decision, "allow"),
        "reason": reason,
        "rule_id": rule_id,
        "source": source,
    }


def _default_decision(action: dict[str, Any], label: str) -> tuple[str, str]:
    # 1. reading/writing a secret file — never, by default
    if action.get("secret_targets"):
        return "block", "Touches a secret/credential file (.env, *.pem, …) — blocked by default."
    # 2. anything reaching out to the web — ask first
    if action.get("kind") == "tool_call" and action.get("server") == "web":
        return "ask", "Reaches out to the web — approve before it fetches/searches externally."
    # 3. risk-rank everything else; escalate only the genuinely risky
    pseudo = {"kind": action.get("kind"), "title": _insight_title(action, label), "detail": ""}
    res = analyze_action(pseudo)
    if res["risk"] == "high":
        return "ask", f"Risky action — approve first. {res['reason']}"
    return "allow", ""


def _insight_title(action: dict[str, Any], label: str) -> str:
    if action.get("kind") == "tool_call":
        return f"{action.get('server', 'mcp')}:{action.get('tool', 'tool')}"
    return label


# --- record + run handling -------------------------------------------------

def _ensure_run(cwd: Path) -> str:
    paths = paths_for_run(cwd=cwd)
    active = paths.active_file
    if active.exists() and active.read_text(encoding="utf-8").strip():
        return active.read_text(encoding="utf-8").strip()
    task = paths.agentproof_dir / "task.yml"
    if not task.exists():
        write_default_contract(task)
    return create_run(load_contract(task), agent=AGENT, cwd=cwd)["run_id"]


def _record_pre(run_id: str, cwd: Path, action: dict[str, Any], label: str, decision: dict[str, Any], tool_input: dict[str, Any]):
    paths = paths_for_run(run_id, cwd)
    if action.get("kind") == "tool_call":
        append_event(paths, "mcp.tool.call.started", {
            "agent": AGENT, "server_name": action.get("server"),
            "request": {"params": {"name": action.get("tool"), "arguments": redact_secrets(tool_input)}},
        })
    else:
        append_event(paths, "command_started", {"agent": AGENT, "command": label})
    append_event(paths, "policy.decision", {
        "agent": AGENT, "action": label, "match_kind": action.get("kind"),
        "decision": decision["decision"], "rule_id": decision["rule_id"],
        "reason": decision["reason"], "source": decision["source"],
        "outcome": {"block": "blocked", "ask": "ask"}.get(decision["decision"], "allowed"),
    })
    if decision["decision"] == "block":
        append_event(paths, "policy.enforcement", {
            "agent": AGENT, "action": label, "rule_id": decision["rule_id"],
            "reason": decision["reason"], "action_taken": "blocked",
        })
        # the action is blocked and will never run/finish — record the attempt so
        # the flow shows "tried, blocked" instead of nothing.
        if action.get("kind") == "tool_call":
            append_event(paths, "mcp.error", {"agent": AGENT, "server_name": action.get("server"),
                                              "error": "blocked by policy", "rule_id": decision["rule_id"]})
        else:
            append_event(paths, "command_finished", {"agent": AGENT, "command": label,
                                                     "exit_code": None, "blocked": True})


# --- entrypoints (called by the CLI) ---------------------------------------

def run_pre(stdin_text: str, cwd: Path) -> dict[str, Any]:
    """Handle a PreToolUse event: decide, record, return Claude Code's JSON."""
    try:
        event = json.loads(stdin_text or "{}")
        action, label = action_from_event(event.get("tool_name", ""), event.get("tool_input") or {})
        d = decide(action, label, cwd)
        try:
            run_id = _ensure_run(cwd)
            _record_pre(run_id, cwd, action, label, d, event.get("tool_input") or {})
        except Exception:
            pass  # never let a recording hiccup break the agent
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": d["permission"],
            "permissionDecisionReason": d["reason"] or "Allowed by AgentProof.",
        }}
    except Exception as exc:  # fail-open: a broken hook must not brick the agent
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                       "permissionDecisionReason": f"AgentProof hook error (allowed): {exc}"}}


def run_post(stdin_text: str, cwd: Path) -> dict[str, Any]:
    """Handle a PostToolUse event: record the outcome so the flow is complete."""
    try:
        event = json.loads(stdin_text or "{}")
        action, label = action_from_event(event.get("tool_name", ""), event.get("tool_input") or {})
        run_id = paths_for_run(cwd=cwd).active_file
        run_id = run_id.read_text(encoding="utf-8").strip() if run_id.exists() else latest_run_id(cwd)
        paths = paths_for_run(run_id, cwd)
        if action.get("kind") == "tool_call":
            append_event(paths, "mcp.tool.call.finished", {"agent": AGENT, "server_name": action.get("server")})
        else:
            append_event(paths, "command_finished", {"agent": AGENT, "command": label, "exit_code": 0})
    except Exception:
        pass
    return {}
