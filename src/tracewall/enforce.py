"""Policy engine — step 5 of the policy-by-demonstration loop.

The hidden, deliberately-simple engine that evaluates a normalized action
against the *active* policy (the rules a human accepted from the recommender)
and decides allow / block. Enforcement graduates through three modes:

    observe  — record the decision, never interfere
    alert    — record + warn, but let the action run
    block    — record + stop the action

This module is intentionally pure: it imports nothing from ``recorder`` (which
imports *it*), takes explicit filesystem paths, and has no side effects beyond
reading/writing the active policy file. The same engine serves every channel —
commands today, MCP/tool calls next — because it evaluates a normalized action,
not a channel-specific shape.

Active policy lives at ``.tracewall/policy.json``:  {"rules": [ <rule>, ... ]}
using the rule format defined by the recommender (see ``recommend.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import fnmatch
import hashlib
import json
import shlex

from tracewall.events import now_iso
from tracewall.sensitive import looks_secret_token

POLICY_FILENAME = "policy.json"


# --- active policy storage -------------------------------------------------

def policy_path(tracewall_dir: Path) -> Path:
    return Path(tracewall_dir) / POLICY_FILENAME


def world_writable(path: Path) -> bool:
    """True if any local user could modify ``path`` (world-writable bit set)."""
    try:
        return bool(Path(path).stat().st_mode & 0o002)
    except OSError:
        return False


def policy_fingerprint(tracewall_dir: Path) -> str:
    """sha256 of the active policy file (``"none"`` if absent) — a stable id used
    to detect and record policy changes."""
    try:
        return hashlib.sha256(policy_path(tracewall_dir).read_bytes()).hexdigest()
    except OSError:
        return "none"


def load_active_policy(tracewall_dir: Path) -> dict[str, Any]:
    path = policy_path(tracewall_dir)
    if not path.exists():
        return {"rules": []}
    # Hardening (P0.6): a world-writable policy (or directory) can be edited by
    # any local user, so we refuse to *trust* it — we fall back to no rules
    # (default-safe decisions) rather than honor a possibly-tampered allowlist.
    if world_writable(path) or world_writable(path.parent):
        return {"rules": [], "untrusted": True,
                "reason": "policy file or its directory is world-writable; not trusted"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"rules": []}
    if not isinstance(data, dict):
        return {"rules": []}
    data.setdefault("rules", [])
    return data


def save_active_policy(tracewall_dir: Path, policy: dict[str, Any]) -> Path:
    path = policy_path(Path(tracewall_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True), encoding="utf-8")
    return path


def accept_rules(tracewall_dir: Path, rules: list[dict[str, Any]], source_run: str | None = None) -> dict[str, Any]:
    """Merge accepted rules into the active policy, keyed by rule id."""
    policy = load_active_policy(Path(tracewall_dir))
    by_id = {rule["id"]: rule for rule in policy["rules"]}
    for rule in rules:
        prev = by_id.get(rule["id"])
        by_id[rule["id"]] = {
            "id": rule["id"],
            "decision": rule["decision"],
            "match": rule["match"],
            "reason": rule.get("reason", ""),
            "origin": rule.get("origin", "recommended"),
            "added_at": prev.get("added_at") if prev else now_iso(),
            "source_run": (prev or {}).get("source_run") or source_run,
        }
    policy["rules"] = list(by_id.values())
    save_active_policy(tracewall_dir, policy)
    return policy


def policy_summary(policy: dict[str, Any]) -> dict[str, int]:
    rules = policy.get("rules") or []
    return {
        "rules": len(rules),
        "blocks": sum(1 for r in rules if r.get("decision") == "block"),
        "allows": sum(1 for r in rules if r.get("decision") == "allow"),
        "commands": sum(1 for r in rules if (r.get("match") or {}).get("kind") == "command"),
        "tools": sum(1 for r in rules if (r.get("match") or {}).get("kind") == "tool_call"),
    }


def render_policy(policy: dict[str, Any]) -> str:
    """Human-readable listing of every active rule, blocks first."""
    rules = policy.get("rules") or []
    s = policy_summary(policy)
    header = f"Active policy — {s['rules']} rule(s): {s['blocks']} block, {s['allows']} allow"
    lines = [header, "=" * len(header)]
    if not rules:
        lines.append("No rules yet. Accept recommendations with: tracewall recommend --accept")
        return "\n".join(lines)
    ordered = sorted(rules, key=lambda r: (r.get("decision") != "block",
                                           (r.get("match") or {}).get("kind", ""),
                                           match_label(r.get("match") or {})))
    for r in ordered:
        m = r.get("match") or {}
        target = match_label(m)
        tag = "BLOCK" if r.get("decision") == "block" else "ALLOW"
        lines.append(f"[{tag}] {m.get('kind','?'):<10} {target}")
        if r.get("reason"):
            lines.append(f"        {r['reason']}")
        meta = []
        if r.get("origin"):
            meta.append(str(r["origin"]))
        if r.get("added_at"):
            meta.append(f"added {r['added_at']}")
        if meta:
            lines.append(f"        ({' · '.join(meta)})")
    return "\n".join(lines)


# --- normalized actions ----------------------------------------------------

def action_from_command(command_text: str) -> dict[str, Any]:
    try:
        parts = shlex.split(command_text)
    except ValueError:
        parts = command_text.split()
    return {
        "kind": "command",
        "binary": parts[0] if parts else "",
        "args": parts[1:],
        # any token that names a secret/credential file — the *target*, not the tool
        "secret_targets": [tok for tok in parts if looks_secret_token(tok)],
    }


def action_from_tool(server_name: str, tool_name: str) -> dict[str, Any]:
    return {"kind": "tool_call", "tool": tool_name, "server": server_name}


def action_from_file(op: str, path: str) -> dict[str, Any]:
    """A file read/write (e.g. the agent's Read/Write tool) as a gateable action.
    Modeled as a command so the same secret-target matching applies to the path."""
    return {
        "kind": "command",
        "binary": op,
        "args": [path],
        "secret_targets": [path] if looks_secret_token(path) else [],
    }


# --- evaluation ------------------------------------------------------------

def evaluate_action(action: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Decide allow / ask / block for an action. Precedence: block > ask > allow."""
    rules = policy.get("rules") or []
    ordered = [r for r in rules if r.get("decision") == "block"] + \
              [r for r in rules if r.get("decision") == "ask"] + \
              [r for r in rules if r.get("decision") == "allow"]
    for rule in ordered:
        if _matches(rule.get("match") or {}, action):
            return {"decision": rule["decision"], "rule_id": rule.get("id"), "reason": rule.get("reason", "")}
    return {"decision": "none", "rule_id": None, "reason": ""}


def enforced_outcome(decision: str, mode: str) -> str:
    """Map a policy decision + enforcement mode to what actually happens."""
    if decision == "block":
        if mode == "block":
            return "blocked"
        if mode == "alert":
            return "alerted"
    return "allowed"


def _matches(match: dict[str, Any], action: dict[str, Any]) -> bool:
    if match.get("kind") != action.get("kind"):
        return False
    if action.get("kind") == "command":
        # A command rule may match on the target (a secret path / arg glob), the
        # binary, or both. All specified conditions must hold (AND); an empty
        # match never matches anything.
        conditions = 0
        if match.get("touches_secret"):
            conditions += 1
            if not action.get("secret_targets"):
                return False
        if "arg_glob" in match:
            conditions += 1
            if not any(fnmatch.fnmatch(a, match["arg_glob"]) for a in action.get("args", [])):
                return False
        if "binary" in match:
            conditions += 1
            if match["binary"] != action.get("binary"):
                return False
        return conditions > 0
    if action.get("kind") == "tool_call":
        return match.get("tool") == action.get("tool")
    return False


def match_label(match: dict[str, Any]) -> str:
    """Human-readable description of what a rule matches."""
    if (match or {}).get("kind") == "tool_call":
        return match.get("tool") or "tool"
    if match.get("touches_secret"):
        return "secret files (.env, *.pem, …)"
    binary = match.get("binary")
    if binary and match.get("arg_glob"):
        return f"{binary} {match['arg_glob']}"
    return binary or match.get("arg_glob") or "command"
