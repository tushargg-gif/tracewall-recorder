"""Unified action flow.

Reduces a run's raw event log into one ordered list of *intent* actions — the
things the agent tried to do — across capture channels:

- recorded commands (`agentproof run -- ...`)
- MCP/tool calls (via the stdio proxy)

This is the substrate the review UX and the policy recommender read from. It is
intentionally a pure function over events: no I/O except the thin `action_flow`
wrapper that loads a run's events.
"""

from __future__ import annotations

from typing import Any
import json

from agentproof.recorder import read_events

# Events that end one action and start the search window for the next.
_BOUNDARY_EVENTS = {"command_finished", "mcp.tool.call.started"}


def action_flow(run_id: str, cwd=None) -> dict[str, Any]:
    """Load a run's events and return its unified action flow."""
    events = read_events(run_id, cwd)
    actions = build_action_flow(events)
    return {"run_id": run_id, "action_count": len(actions), "actions": actions}


def build_action_flow(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure reducer: ordered events -> ordered list of normalized actions."""
    actions: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        event_type = event.get("event_type")
        payload = event.get("payload") or {}
        if event_type == "command_finished":
            actions.append(_command_action(event, payload))
        elif event_type == "mcp.tool.call.started":
            actions.append(_tool_action(event, payload, _tool_status(events, index)))

    for seq, action in enumerate(actions, start=1):
        action["seq"] = seq
    return actions


def _decision_is_block(event: dict[str, Any]) -> bool:
    """A policy.decision event is a block, tolerant of both event shapes:
    proxy nests {"decision": {"action": ...}}, gateway uses {"decision": "block"}."""
    dec = (event.get("payload") or {}).get("decision")
    action = dec.get("action") if isinstance(dec, dict) else dec
    return action == "block"


def render_flow(flow: dict[str, Any]) -> str:
    """Human-readable rendering of an action flow."""
    actions = flow.get("actions") or []
    header = f"Action flow for {flow.get('run_id')} — {len(actions)} action(s)"
    lines = [header, "=" * len(header)]
    if not actions:
        lines.append("(no commands or tool calls recorded yet)")
        return "\n".join(lines)
    mark = {"ok": "ok", "failed": "FAILED", "blocked": "BLOCKED", "pending": "pending", "unknown": "?"}
    for action in actions:
        status = action.get("status", "unknown")
        lines.append(
            f"{action['seq']:>2}. [{action['kind']:<9}] {action['title']}  ({mark.get(status, status)})"
        )
        detail = action.get("detail")
        if detail:
            lines.append(f"      {detail}")
    return "\n".join(lines)


# --- action builders -------------------------------------------------------

def _command_action(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    command_text = str(payload.get("command") or "")
    exit_code = payload.get("exit_code")
    if payload.get("blocked"):
        status = "blocked"
    elif exit_code == 0:
        status = "ok"
    elif exit_code is None:
        status = "unknown"
    else:
        status = "failed"
    return {
        "kind": "command",
        "actor": payload.get("agent") or "shell",
        "title": _shorten(command_text) or "(empty command)",
        "detail": command_text if command_text != _shorten(command_text) else "",
        "status": status,
        "duration": payload.get("duration_seconds"),
        "timestamp": event.get("timestamp"),
        "source_event_ids": [event.get("event_id")],
    }


def _tool_action(event: dict[str, Any], payload: dict[str, Any], status: str) -> dict[str, Any]:
    request = payload.get("request") or {}
    params = request.get("params") or {}
    server = str(payload.get("server_name") or "mcp")
    tool_name = str(params.get("name") or "tool")
    arguments = params.get("arguments")
    return {
        "kind": "tool_call",
        "actor": payload.get("agent") or server,
        "title": f"{server}:{tool_name}",
        "detail": _compact(arguments),
        "status": status,
        "timestamp": event.get("timestamp"),
        "source_event_ids": [event.get("event_id")],
    }


def _tool_status(events: list[dict[str, Any]], start: int) -> str:
    """Determine a tool call's outcome from its surrounding events.

    The policy decision can be recorded just *before* the started event (the MCP
    proxy) or just *after* it (the Gateway), so we look on both sides.
    """
    blocked = start - 1 >= 0 and events[start - 1].get("event_type") == "policy.decision" \
        and _decision_is_block(events[start - 1])
    for event in events[start + 1:]:
        event_type = event.get("event_type")
        if event_type == "policy.decision":
            blocked = blocked or _decision_is_block(event)
        elif event_type == "mcp.tool.call.finished":
            return "ok"
        elif event_type == "mcp.error":
            return "blocked" if (blocked or (event.get("payload") or {}).get("rule_id")) else "failed"
        elif event_type in _BOUNDARY_EVENTS:
            break
    return "pending"


# --- helpers ---------------------------------------------------------------

def _shorten(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _compact(value: Any, limit: int = 80) -> str:
    if value is None:
        return ""
    try:
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        rendered = str(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"
