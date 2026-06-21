"""Risk analysis — anticipate what the reviewer needs to notice.

A flat allow/block list trains reviewers to rubber-stamp: ``echo`` and ``env``
look identical, so the one dangerous action slips through. This module does the
triage *for* the human — scoring each action, naming *why* it's risky in plain
language, and suggesting a verdict — so attention lands where it matters.

Everything here is deterministic and explainable (no model call): the reviewer
should always be able to see the exact reason behind a flag and overrule it.
"""

from __future__ import annotations

from typing import Any
import re

from tracewall.sensitive import looks_secret_token

# --- signal vocabularies (explainable, editable) ---------------------------

_SECRET_CMDS = {"env", "printenv", "set"}
_EGRESS_CMDS = {"curl", "wget", "nc", "ncat", "telnet", "scp", "sftp", "ssh", "rsync"}
_DESTRUCTIVE_CMDS = {"rm", "rmdir", "shred", "mkfs", "dd", "shutdown", "reboot", "kill", "killall"}
_PRIV_CMDS = {"sudo", "su", "doas"}
_INSTALL_CMDS = {"pip", "pip3", "npm", "yarn", "pnpm", "apt", "apt-get", "brew", "gem", "cargo"}

# tool-name fragments that imply a consequential, often irreversible action
_HIGH_TOOL_WORDS = ("send", "email", "delete", "remove", "drop", "deploy", "payment",
                    "transfer", "wire", "charge", "refund", "purchase", "terminate",
                    "shutdown", "grant", "revoke", "exec", "shell", "merge", "publish")
_MED_TOOL_WORDS = ("create", "update", "write", "post", "comment", "upload", "invite", "assign")
_SECRET_ARG_WORDS = ("api_key", "apikey", "token", "password", "secret", "authorization", "credential")
_BROAD_RECIPIENTS = ("all@", "everyone@", "@everyone", "team@", "staff@", "company.com")

_URL_RE = re.compile(r"https?://([^/\s\"']+)")
_PIPE_TO_SHELL = re.compile(r"\|\s*(sh|bash|zsh)\b")


def analyze_action(action: dict[str, Any]) -> dict[str, Any]:
    """Return {risk, tags, reason, suggestion} for one action."""
    if action.get("kind") == "tool_call":
        return _analyze_tool(action)
    return _analyze_command(action)


def analyze_run(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Run-level posture and the human-readable signals to surface up top."""
    per = [analyze_action(a) for a in actions]
    counts = {"high": 0, "medium": 0, "low": 0}
    tags: list[str] = []
    for result in per:
        counts[result["risk"]] = counts.get(result["risk"], 0) + 1
        for tag in result["tags"]:
            if tag not in tags:
                tags.append(tag)
    if counts["high"]:
        posture = "high"
    elif counts["medium"]:
        posture = "elevated"
    else:
        posture = "low"
    return {
        "posture": posture,
        "signals": [_SIGNAL_LABELS.get(t, t) for t in tags],
        "counts": counts,
        "flagged": [a["seq"] for a, r in zip(actions, per) if r["risk"] == "high"],
    }


_SIGNAL_LABELS = {
    "secrets": "Touched secrets / credentials",
    "egress": "Network egress (data could leave)",
    "destructive": "Destructive / irreversible action",
    "privilege": "Privilege escalation",
    "supply_chain": "Installed external packages",
    "broad_blast": "Broad blast radius (many recipients)",
    "external_url": "Called an external URL",
    "irreversible_tool": "Irreversible tool action",
}


# --- command analysis ------------------------------------------------------

def _analyze_command(action: dict[str, Any]) -> dict[str, Any]:
    text = str(action.get("detail") or action.get("title") or "")
    low = text.lower()
    binary = (text.split() or [""])[0].rsplit("/", 1)[-1]
    tags: list[str] = []
    reasons: list[str] = []

    if binary in _SECRET_CMDS or any(looks_secret_token(tok) for tok in low.split()):
        tags.append("secrets")
        reasons.append("can expose environment variables or secret files")
    if binary in _EGRESS_CMDS or _URL_RE.search(low) or _PIPE_TO_SHELL.search(low):
        tags.append("egress")
        reasons.append("opens a network connection — data could leave the machine")
    if _PIPE_TO_SHELL.search(low) or (binary in _EGRESS_CMDS and _PIPE_TO_SHELL.search(low)):
        tags.append("supply_chain")
        reasons.append("pipes downloaded content straight into a shell")
    if binary in _DESTRUCTIVE_CMDS or "rm -rf" in low or "--force" in low or " -rf" in low:
        tags.append("destructive")
        reasons.append("can delete or irreversibly change files")
    if binary in _PRIV_CMDS:
        tags.append("privilege")
        reasons.append("runs with elevated privileges")
    if binary in _INSTALL_CMDS and any(w in low for w in ("install", "add", "i ")):
        tags.append("supply_chain")
        reasons.append("installs third-party packages")

    risk = "high" if tags else "low"
    # a couple of medium cases that aren't outright high
    if not tags and binary in {"git", "mv", "cp", "chmod", "docker", "make"}:
        risk = "medium"
        reasons.append("changes project or system state")
    return _result(risk, tags, reasons, binary, kind="command")


# --- tool-call analysis ----------------------------------------------------

def _analyze_tool(action: dict[str, Any]) -> dict[str, Any]:
    title = str(action.get("title") or "")
    tool = title.split(":", 1)[1] if ":" in title else title
    low_tool = tool.lower()
    args = str(action.get("detail") or "").lower()
    tags: list[str] = []
    reasons: list[str] = []

    if any(w in low_tool for w in _HIGH_TOOL_WORDS):
        tags.append("irreversible_tool")
        reasons.append(f"`{tool}` can take a consequential, often irreversible action")
    if any(w in args for w in _SECRET_ARG_WORDS):
        tags.append("secrets")
        reasons.append("its arguments contain secret-like fields")
    if any(w in args for w in _BROAD_RECIPIENTS):
        tags.append("broad_blast")
        reasons.append("targets a broad audience (many recipients)")
    if _URL_RE.search(args):
        tags.append("external_url")
        reasons.append("references an external URL")

    if any(w in low_tool for w in _HIGH_TOOL_WORDS) or "secrets" in tags or "broad_blast" in tags:
        risk = "high"
    elif any(w in low_tool for w in _MED_TOOL_WORDS) or "external_url" in tags:
        risk = "medium"
        if not reasons:
            reasons.append("writes or changes external state")
    else:
        risk = "low"
    return _result(risk, tags, reasons, tool, kind="tool_call")


# --- shared ----------------------------------------------------------------

def _result(risk: str, tags: list[str], reasons: list[str], subject: str, kind: str) -> dict[str, Any]:
    if risk == "high":
        suggestion = "block"
    elif risk == "low":
        suggestion = "allow"
    else:
        suggestion = "review"
    noun = "command" if kind == "command" else "tool call"
    if reasons:
        reason = f"`{subject}` {noun}: " + "; ".join(dict.fromkeys(reasons)) + "."
    elif risk == "low":
        reason = f"`{subject}` {noun}: routine, no risky signals detected."
    else:
        reason = f"`{subject}` {noun}: review recommended."
    return {"risk": risk, "tags": tags, "reason": reason, "suggestion": suggestion}
