"""MCP JSON-RPC helpers used by the stdio proxy.

The proxy gates `tools/call` through the real policy engine (`enforce` via
`hook.decide`); this module is now just the two thin MCP-protocol helpers the
proxy needs — mapping a method to an event type, and shaping a JSON-RPC block
error. The earlier standalone policy-evaluator that lived here was superseded by
`enforce.py` and removed.
"""

from __future__ import annotations

from typing import Any


def method_event_type(method: str, suffix: str | None = None) -> str:
    mapping = {
        "initialize": "mcp.initialize",
        "tools/list": "mcp.tools.list",
        "tools/call": "mcp.tool.call",
        "resources/list": "mcp.resources.list",
        "resources/read": "mcp.resource.read",
        "prompts/list": "mcp.prompts.list",
        "prompts/get": "mcp.prompt.get",
    }
    base = mapping.get(method, "mcp.request")
    if base == "mcp.tool.call" and suffix:
        return f"{base}.{suffix}"
    return base


def block_error(request_id: Any, message: str = "AgentProof Recorder blocked critical MCP policy violation.") -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": message}}
