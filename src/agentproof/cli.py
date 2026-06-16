from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from agentproof.contracts import load_contract, write_default_contract
from agentproof.events import parse_payload
from agentproof import enforce
from agentproof.enforce import POLICY_FILENAME
from agentproof.flow import action_flow, render_flow
from agentproof.hook import run_post, run_pre
from agentproof.mcp_stdio import run_stdio_proxy
from agentproof.recommend import (
    accept_recommendation,
    recommend_policy,
    render_recommendations,
    save_recommended_policy,
)
from agentproof.review import export_review_html, review_state, serve_review, set_verdict
from agentproof.recorder import (
    create_run,
    latest_run_id,
    paths_for_run,
    record_event,
    record_command,
    stop_run,
)
from agentproof.reports import generate_report
from agentproof.verifier import verify_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentproof",
        description="AgentProof Recorder: record, verify, score, and report on agent work.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="Create a starter AgentProof Recorder task contract.")
    init.add_argument("--force", action="store_true", help="Overwrite existing task contract.")

    start = subcommands.add_parser("start", help="Start recording an agent run.")
    start.add_argument("--task-file", default=".agentproof/task.yml", help="Task contract path.")
    start.add_argument("--agent", default="unknown", help="Agent name or provider.")
    start.add_argument(
        "--enforce",
        action="store_true",
        help="Block (not just flag) reads/writes/deletes of sensitive files for recorded commands.",
    )

    run = subcommands.add_parser("run", help="Run and record a command.")
    run.add_argument(
        "--enforce",
        dest="enforce",
        action="store_true",
        default=None,
        help="Force sandbox enforcement for this command (overrides run mode).",
    )
    run.add_argument(
        "--no-enforce",
        dest="enforce",
        action="store_false",
        help="Disable enforcement for this command (overrides run mode).",
    )
    run.add_argument(
        "--policy-mode",
        choices=["observe", "alert", "block"],
        default="observe",
        help="Enforce the active learned policy: observe (record), alert (warn), or block (stop).",
    )
    run.add_argument("wrapped_command", nargs=argparse.REMAINDER)

    event = subcommands.add_parser("event", help="Record a universal agent event.")
    event.add_argument("event_type", help="Event type, e.g. network.request or artifact.created.")
    event.add_argument("--payload", default="{}", help="JSON object payload for the event.")
    event.add_argument("--run-id", default=None, help="Run ID. Defaults to the active run.")

    stop = subcommands.add_parser("stop", help="Stop the active agent run.")
    stop.add_argument("--run-id", default=None)
    stop.add_argument("--final-response", default="", help="Final response or summary from the agent.")

    verify = subcommands.add_parser("verify", help="Verify a stopped or current run.")
    verify.add_argument("--run-id", default=None)
    verify.add_argument("--json", action="store_true", help="Print full verification JSON.")

    report = subcommands.add_parser("report", help="Generate a Markdown and JSON report.")
    report.add_argument("--run-id", default=None)
    report.add_argument("--print", action="store_true", dest="print_report", help="Print Markdown report.")
    report.add_argument("--json", action="store_true", dest="json_report", help="Print JSON report.")

    flow = subcommands.add_parser("flow", help="Show the ordered action flow (commands + tool calls) for a run.")
    flow.add_argument("--run-id", default=None)
    flow.add_argument("--json", action="store_true", dest="json_flow", help="Print the action flow as JSON.")

    review = subcommands.add_parser("review", help="Open the allow/block review timeline for a run.")
    review.add_argument("--run-id", default=None)
    review.add_argument("--host", default="127.0.0.1")
    review.add_argument("--port", default=8898, type=int)
    review.add_argument("--export", default=None, metavar="PATH", help="Write a static review HTML file instead of serving.")
    review.add_argument("--json", action="store_true", dest="json_review", help="Print the review state (run + flow + risk + policy coverage) as JSON.")

    verdict = subcommands.add_parser("verdict", help="Record an allow/block verdict for one action (used by editors/scripts).")
    verdict.add_argument("--run-id", default=None)
    verdict.add_argument("--seq", required=True, type=int, help="The action's seq number from the flow.")
    verdict.add_argument("--decision", required=True, choices=["allow", "block", "clear"])
    verdict.add_argument("--note", default="")

    policy = subcommands.add_parser("policy", help="View every rule in the active policy, in one place.")
    policy.add_argument("--json", action="store_true", dest="json_policy", help="Print the active policy as JSON.")
    policy.add_argument("--export", default=None, metavar="PATH", help="Write a standalone policies HTML page.")

    hook = subcommands.add_parser("hook", help="Claude Code hook entrypoint (reads a tool event on stdin).")
    hook.add_argument("--post", action="store_true", help="Record a PostToolUse outcome instead of gating.")

    install_hook = subcommands.add_parser("install-hook", help="Install AgentProof as a Claude Code hook (.claude/settings.json).")
    install_hook.add_argument("--global", dest="global_install", action="store_true", help="Install to ~/.claude instead of the project.")

    recommend = subcommands.add_parser("recommend", help="Recommend policy rules (with reasons) from the review verdicts.")
    recommend.add_argument("--run-id", default=None)
    recommend.add_argument("--json", action="store_true", dest="json_rec", help="Print the recommended policy as JSON.")
    recommend.add_argument("--accept", action="store_true", help="Merge the recommended rules into the active project policy.")

    mcp = subcommands.add_parser("mcp", help="Run MCP proxy modes.")
    mcp_subcommands = mcp.add_subparsers(dest="mcp_command", required=True)
    stdio = mcp_subcommands.add_parser("stdio", help="Proxy a stdio MCP server and record its tool calls.")
    stdio.add_argument("--run-id", required=True)
    stdio.add_argument("--server-name", required=True)
    stdio.add_argument("server_command", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "start":
            return cmd_start(args)
        if args.command == "run":
            return cmd_run(args)
        if args.command == "event":
            return cmd_event(args)
        if args.command == "stop":
            return cmd_stop(args)
        if args.command == "verify":
            return cmd_verify(args)
        if args.command == "report":
            return cmd_report(args)
        if args.command == "flow":
            return cmd_flow(args)
        if args.command == "review":
            return cmd_review(args)
        if args.command == "verdict":
            return cmd_verdict(args)
        if args.command == "policy":
            return cmd_policy(args)
        if args.command == "hook":
            return cmd_hook(args)
        if args.command == "install-hook":
            return cmd_install_hook(args)
        if args.command == "recommend":
            return cmd_recommend(args)
        if args.command == "mcp":
            return cmd_mcp(args)
    except Exception as exc:
        print(f"agentproof: error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    paths = paths_for_run(cwd=Path.cwd())
    task_path = paths.agentproof_dir / "task.yml"
    created = write_default_contract(task_path, force=args.force)
    if created:
        print(f"Created task contract: {task_path}")
    else:
        print(f"Task contract already exists: {task_path}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    contract = load_contract(Path(args.task_file))
    run = create_run(contract, args.agent, cwd=Path.cwd(), enforce=args.enforce)
    print(f"Started AgentProof Recorder run: {run['run_id']}")
    print(f"Task: {run['task_id']} - {run['task_title']}")
    if args.enforce:
        enforcement = run["enforcement"]
        backend = enforcement["backend"]
        if backend == "none":
            print(
                "WARNING: --enforce requested but no sandbox backend is available on this host. "
                "Recorded commands will fail closed (refuse to run)."
            )
        else:
            print(f"Enforcement: ON (backend={backend}). Sensitive reads/writes/deletes will be blocked.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    command = list(args.wrapped_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("Usage: agentproof run -- <command>")
    return record_command(command, cwd=Path.cwd(), enforce=args.enforce, policy_mode=args.policy_mode)


def cmd_event(args: argparse.Namespace) -> int:
    payload = parse_payload(args.payload)
    event = record_event(args.event_type, payload, run_id=args.run_id, cwd=Path.cwd())
    print(f"Recorded event: {event['event_type']} ({event['event_id']})")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    run = stop_run(args.run_id, args.final_response, cwd=Path.cwd())
    print(f"Stopped AgentProof Recorder run: {run['run_id']}")
    print(f"Changed files: {len(run.get('changed_files') or [])}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    verification = verify_run(args.run_id, cwd=Path.cwd())
    if args.json:
        print(json.dumps(verification, indent=2, sort_keys=True))
    else:
        print(f"Verification: {verification['verdict']}")
        print(f"Score: {verification['score']}/100")
        print(f"Risk: {verification['risk']}")
        print(f"Policy violations: {len(verification['policy_violations'])}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run_id = args.run_id or latest_run_id(Path.cwd())
    paths = generate_report(run_id, cwd=Path.cwd())
    if args.print_report:
        print(paths["markdown"].read_text(encoding="utf-8"))
    elif args.json_report:
        print(paths["json"].read_text(encoding="utf-8"))
    else:
        print(f"Markdown report: {paths['markdown']}")
        print(f"JSON report: {paths['json']}")
    return 0


def cmd_flow(args: argparse.Namespace) -> int:
    run_id = args.run_id or latest_run_id(Path.cwd())
    flow = action_flow(run_id, cwd=Path.cwd())
    if args.json_flow:
        print(json.dumps(flow, indent=2, sort_keys=True))
    else:
        print(render_flow(flow))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    run_id = args.run_id or latest_run_id(Path.cwd())
    if args.json_review:
        print(json.dumps(review_state(run_id, cwd=Path.cwd())))
        return 0
    if args.export:
        out = export_review_html(run_id, Path(args.export), cwd=Path.cwd())
        print(f"Review page written: {out}")
        return 0
    serve_review(run_id, host=args.host, port=args.port, cwd=Path.cwd())
    return 0


def cmd_verdict(args: argparse.Namespace) -> int:
    run_id = args.run_id or latest_run_id(Path.cwd())
    set_verdict(run_id, args.seq, args.decision, note=args.note, cwd=Path.cwd())
    print(json.dumps({"run_id": run_id, "seq": args.seq, "decision": args.decision}))
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    stdin_text = sys.stdin.read()
    out = run_post(stdin_text, Path.cwd()) if args.post else run_pre(stdin_text, Path.cwd())
    print(json.dumps(out))
    return 0


def cmd_install_hook(args: argparse.Namespace) -> int:
    base = Path.home() if args.global_install else Path.cwd()
    settings = base / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    command = f"{sys.executable} -m agentproof hook"
    hooks = data.setdefault("hooks", {})

    def ensure(event: str, cmd: str) -> None:
        groups = hooks.setdefault(event, [])
        for group in groups:
            for h in group.get("hooks", []):
                if "agentproof" in str(h.get("command", "")):
                    return
        groups.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})

    ensure("PreToolUse", command)
    ensure("PostToolUse", command + " --post")
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Installed AgentProof hook → {settings}")
    print("Every Claude Code tool call (terminal or VS Code) now passes through AgentProof.")
    print("Restart Claude Code or run /hooks to load it.")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    agentproof_dir = paths_for_run(cwd=Path.cwd()).agentproof_dir
    policy = enforce.load_active_policy(agentproof_dir)
    if args.export:
        from agentproof.review import export_policy_html
        out = export_policy_html(policy, Path(args.export))
        print(f"Policies page written: {out}")
        return 0
    if args.json_policy:
        print(json.dumps({"summary": enforce.policy_summary(policy), "rules": policy.get("rules", [])}, indent=2, sort_keys=True))
    else:
        print(enforce.render_policy(policy))
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    run_id = args.run_id or latest_run_id(Path.cwd())
    recommendation = recommend_policy(run_id, cwd=Path.cwd())
    path = save_recommended_policy(run_id, recommendation, cwd=Path.cwd())
    if args.accept:
        policy = accept_recommendation(run_id, recommendation, cwd=Path.cwd())
    if args.json_rec:
        print(json.dumps(recommendation, indent=2, sort_keys=True))
    else:
        print(render_recommendations(recommendation))
        print(f"\nSaved: {path}")
        if args.accept:
            print(f"Accepted {len(policy['rules'])} rule(s) into the active policy (.agentproof/{POLICY_FILENAME}).")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    if args.mcp_command == "stdio":
        command = list(args.server_command)
        if command and command[0] == "--":
            command = command[1:]
        return run_stdio_proxy(args.run_id, args.server_name, command, cwd=Path.cwd())
    raise ValueError(f"Unknown MCP command: {args.mcp_command}")
