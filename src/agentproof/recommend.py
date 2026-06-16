"""Policy recommender — step 4 of the policy-by-demonstration loop.

Reads a run's unified action flow (``flow.py``) and the human's allow/block
verdicts (``review.py``), then *induces* reusable policy rules — generalizing
individual decisions into rules keyed on the tool name or the command's binary —
and writes a plain-language reason for each.

The induction here is deterministic and dependency-free. The reason wording and
fuzzier generalization are a clean seam (`_reason`) where an LLM can later be
plugged in without changing the rule format or the callers. That matches the
"hidden engine, swap later" principle: the *experience* (demonstrate → recommend)
is stable; the cleverness behind the reasons can grow.

Rule format (the simple homegrown format the verifier/enforcer will read):

    {
      "id": "block_tool_send_email",
      "decision": "block" | "allow",
      "match": {"kind": "tool_call", "tool": "send_email"}
             | {"kind": "command",  "binary": "curl"},
      "reason": "plain language",
      "evidence_seqs": [4],
      "examples": 1,
      "origin": "recommended"
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentproof import enforce
from agentproof.flow import action_flow
from agentproof.recorder import paths_for_run, write_json
from agentproof.review import load_verdicts
from agentproof.sensitive import looks_secret_token


def recommend_policy(run_id: str, cwd: Path | None = None) -> dict[str, Any]:
    flow = action_flow(run_id, cwd)
    verdicts = load_verdicts(run_id, cwd)["verdicts"]

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    unreviewed: list[dict[str, Any]] = []

    for action in flow["actions"]:
        verdict = verdicts.get(str(action["seq"]))
        if not verdict or verdict.get("decision") not in ("allow", "block"):
            unreviewed.append({"seq": action["seq"], "title": action["title"]})
            continue
        key = _group_key(action)
        group = groups.setdefault(key, {"allow": [], "block": [], "example": action})
        group[verdict["decision"]].append(action["seq"])

    rules: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for (kind, name), group in groups.items():
        if group["allow"] and group["block"]:
            conflicts.append({
                "kind": kind,
                "name": name,
                "allow_seqs": sorted(group["allow"]),
                "block_seqs": sorted(group["block"]),
                "note": f"You both allowed and blocked `{name}` — needs a more specific rule than {kind} name.",
            })
            continue
        decision = "block" if group["block"] else "allow"
        seqs = sorted(group["block"] or group["allow"])
        rules.append(_make_rule(kind, name, decision, seqs, group["example"]))

    rules.sort(key=lambda r: (r["decision"] != "block", r["match"].get("tool") or r["match"].get("binary") or ""))

    return {
        "run_id": run_id,
        "rules": rules,
        "conflicts": conflicts,
        "unreviewed": unreviewed,
        "summary": {
            "rules": len(rules),
            "blocks": sum(1 for r in rules if r["decision"] == "block"),
            "allows": sum(1 for r in rules if r["decision"] == "allow"),
            "conflicts": len(conflicts),
            "unreviewed": len(unreviewed),
        },
    }


def save_recommended_policy(run_id: str, recommendation: dict[str, Any], cwd: Path | None = None) -> Path:
    path = paths_for_run(run_id, cwd).run_dir / "recommended_policy.json"
    write_json(path, recommendation)
    return path


def accept_recommendation(run_id: str, recommendation: dict[str, Any], cwd: Path | None = None) -> dict[str, Any]:
    """Merge the recommended rules into the project's active policy."""
    agentproof_dir = paths_for_run(run_id, cwd).agentproof_dir
    return enforce.accept_rules(agentproof_dir, recommendation.get("rules") or [], source_run=run_id)


def render_recommendations(recommendation: dict[str, Any]) -> str:
    rules = recommendation.get("rules") or []
    conflicts = recommendation.get("conflicts") or []
    unreviewed = recommendation.get("unreviewed") or []
    summary = recommendation.get("summary") or {}

    header = f"Recommended policy for {recommendation.get('run_id')}"
    lines = [header, "=" * len(header)]
    if not rules and not conflicts:
        lines.append("No verdicts to learn from yet — review the action flow first (agentproof review).")
        return "\n".join(lines)

    for rule in rules:
        tag = "BLOCK" if rule["decision"] == "block" else "ALLOW"
        target = enforce.match_label(rule["match"])
        lines.append(f"[{tag}] {rule['match']['kind']}  {target}   (from {rule['examples']} example(s))")
        lines.append(f"       reason: {rule['reason']}")

    if conflicts:
        lines.append("")
        lines.append("Conflicts (need a finer rule — not auto-generated):")
        for c in conflicts:
            lines.append(f"  ! {c['name']}: allowed {c['allow_seqs']} but blocked {c['block_seqs']}")

    if unreviewed:
        lines.append("")
        lines.append(f"Unreviewed: {len(unreviewed)} action(s) had no verdict and were skipped.")

    lines.append("")
    lines.append(
        f"Summary: {summary.get('blocks', 0)} block, {summary.get('allows', 0)} allow, "
        f"{summary.get('conflicts', 0)} conflict, {summary.get('unreviewed', 0)} unreviewed."
    )
    return "\n".join(lines)


# --- induction helpers -----------------------------------------------------

# a synthetic group name: "this command read a secret/credential file"
SECRET_READ = "__secret_read__"


def _group_key(action: dict[str, Any]) -> tuple[str, str]:
    if action["kind"] == "tool_call":
        return ("tool_call", _tool_name(action))
    # Prefer the *target* over the tool: blocking `cat .env` means "don't read
    # that secret", not "ban cat". Collapses cat/less/grep of any secret path.
    if _reads_secret(action):
        return ("command", SECRET_READ)
    return ("command", _binary(action))


def _reads_secret(action: dict[str, Any]) -> bool:
    text = str(action.get("detail") or action.get("title") or "")
    try:
        tokens = __import__("shlex").split(text)
    except ValueError:
        tokens = text.split()
    return any(looks_secret_token(tok) for tok in tokens)


def _tool_name(action: dict[str, Any]) -> str:
    title = str(action.get("title") or "")
    return title.split(":", 1)[1] if ":" in title else title


def _binary(action: dict[str, Any]) -> str:
    title = str(action.get("title") or "")
    parts = title.split()
    return parts[0] if parts else title


def _make_rule(kind: str, name: str, decision: str, seqs: list[int], example: dict[str, Any]) -> dict[str, Any]:
    if kind == "command" and name == SECRET_READ:
        match: dict[str, Any] = {"kind": "command", "touches_secret": True}
        rule_id = f"{decision}_cmd_secret_read"
    elif kind == "tool_call":
        match = {"kind": "tool_call", "tool": name}
        rule_id = f"{decision}_tool_{name}"
    else:
        match = {"kind": "command", "binary": name}
        rule_id = f"{decision}_cmd_{name}"
    return {
        "id": rule_id,
        "decision": decision,
        "match": match,
        "reason": _reason(kind, name, decision, seqs, example),
        "evidence_seqs": seqs,
        "examples": len(seqs),
        "origin": "recommended",
    }


def _trim(text: str, limit: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _reason(kind: str, name: str, decision: str, seqs: list[int], example: dict[str, Any]) -> str:
    verb = "blocked" if decision == "block" else "approved"
    word = "Block" if decision == "block" else "Allow"
    if kind == "command":
        example_text = example.get("detail") or example.get("title") or name
    else:
        example_text = example.get("title") or name
    where = f"e.g. action {seqs[0]}: {_trim(example_text)}"
    count = f"{len(seqs)} time(s)" if len(seqs) > 1 else "during review"
    if kind == "command" and name == SECRET_READ:
        subject = "any command that reads a secret/credential file (e.g. .env, *.pem)"
    else:
        noun = "tool call" if kind == "tool_call" else "command"
        subject = f"the `{name}` {noun}"
    return f"{word} {subject} — you {verb} it {count} ({where})."
