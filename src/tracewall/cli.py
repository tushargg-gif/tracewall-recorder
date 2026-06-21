from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from tracewall.contracts import load_contract, write_default_contract
from tracewall.events import parse_payload
from tracewall import enforce
from tracewall.enforce import POLICY_FILENAME
from tracewall.flow import action_flow, render_flow
from tracewall.guard import run_guard
from tracewall.hook import run_post, run_pre
from tracewall.observe import run_observe
from tracewall.mcp_stdio import run_stdio_proxy
from tracewall.recommend import (
    accept_recommendation,
    recommend_policy,
    render_recommendations,
    save_recommended_policy,
)
from tracewall.review import export_review_html, review_state, serve_review, set_verdict
from tracewall.recorder import (
    create_run,
    latest_run_id,
    paths_for_run,
    record_event,
    record_command,
    stop_run,
)
from tracewall.reports import generate_report
from tracewall.verifier import verify_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracewall",
        description="tracewall Recorder: record, verify, score, and report on agent work.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="Create a starter tracewall Recorder task contract.")
    init.add_argument("--force", action="store_true", help="Overwrite existing task contract.")

    start = subcommands.add_parser("start", help="Start recording an agent run.")
    start.add_argument("--task-file", default=".tracewall/task.yml", help="Task contract path.")
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

    guard = subcommands.add_parser("guard", help="Run an agent inside an OS sandbox (deny secret reads for it and all it spawns).")
    guard.add_argument("--source", default="agent", help="Name of the agent being guarded (recorded on the session).")
    guard.add_argument("agent_command", nargs=argparse.REMAINDER, help="-- <agent command to run under the sandbox>")

    observe = subcommands.add_parser("observe", help="Run an agent and record everything its process tree does (Linux/strace).")
    observe.add_argument("--source", default="agent", help="Name of the agent being observed (recorded on each effect).")
    observe.add_argument("agent_command", nargs=argparse.REMAINDER, help="-- <agent command to observe>")

    hook = subcommands.add_parser("hook", help="Coding-agent hook entrypoint (reads a tool event on stdin).")
    hook.add_argument("--post", action="store_true", help="Record a PostToolUse outcome instead of gating.")
    hook.add_argument("--ask-mode", choices=["native", "deny", "defer"], default="native",
                      help="How to handle 'ask' decisions: native (Claude Code), deny, or defer to the host's approval (Codex).")
    hook.add_argument("--source", default="claude-code", help="Which coding agent this hook serves (claude-code, codex, …); recorded on every action.")
    hook.add_argument("--no-daemon", action="store_true", help="Decide in-process instead of routing to the running daemon.")

    daemon = subcommands.add_parser("daemon", help="Run the always-on local decision daemon (tracewalld).")
    daemon_sub = daemon.add_subparsers(dest="daemon_command", required=True)
    d_run = daemon_sub.add_parser("run", help="Run the daemon in the foreground (used by the OS service).")
    d_run.add_argument("--http-port", type=int, default=None, help="Localhost HTTP port (default 8787; falls back to an ephemeral port if taken).")
    d_run.add_argument("--no-http", action="store_true", help="UDS only; do not serve localhost HTTP.")
    daemon_sub.add_parser("status", help="Show whether the daemon is running, and where.")
    daemon_sub.add_parser("stop", help="Stop the running daemon.")
    daemon_sub.add_parser("install", help="Install the daemon as an always-on OS service (launchd on macOS, systemd --user on Linux).")
    daemon_sub.add_parser("uninstall", help="Remove the daemon's OS service.")

    install_hook = subcommands.add_parser("install-hook", help="Install tracewall as a Claude Code hook (.claude/settings.json).")
    install_hook.add_argument("--global", dest="global_install", action="store_true", help="Install to ~/.claude instead of the project.")

    install_codex = subcommands.add_parser("install-codex", help="Install tracewall as a Codex hook (.codex/hooks.json).")
    install_codex.add_argument("--global", dest="global_install", action="store_true", help="Install to ~/.codex instead of the project.")
    install_codex.add_argument("--ask-mode", choices=["deny", "defer"], default="defer",
                               help="Codex hooks can't 'ask': deny risky actions, or defer to Codex's own approval (default).")

    recommend = subcommands.add_parser("recommend", help="Recommend policy rules (with reasons) from the review verdicts.")
    recommend.add_argument("--run-id", default=None)
    recommend.add_argument("--json", action="store_true", dest="json_rec", help="Print the recommended policy as JSON.")
    recommend.add_argument("--accept", action="store_true", help="Merge the recommended rules into the active project policy.")

    mcp = subcommands.add_parser("mcp", help="Run MCP proxy modes.")
    mcp_subcommands = mcp.add_subparsers(dest="mcp_command", required=True)
    stdio = mcp_subcommands.add_parser("stdio", help="Proxy a stdio MCP server: record + policy-gate its tool calls.")
    stdio.add_argument("--run-id", default=None, help="Attach to a run (defaults to the active run, created if needed).")
    stdio.add_argument("--server-name", required=True)
    stdio.add_argument("--ask-mode", choices=["native", "deny", "defer"], default="defer",
                       help="How to treat 'ask' decisions for tool calls (proxy can't prompt mid-stream).")
    stdio.add_argument("--source", default="codex", help="Which coding agent is calling through this proxy (recorded on every tool call).")
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
        if args.command == "guard":
            return cmd_guard(args)
        if args.command == "observe":
            return cmd_observe(args)
        if args.command == "hook":
            return cmd_hook(args)
        if args.command == "daemon":
            return cmd_daemon(args)
        if args.command == "install-hook":
            return cmd_install_hook(args)
        if args.command == "install-codex":
            return cmd_install_codex(args)
        if args.command == "recommend":
            return cmd_recommend(args)
        if args.command == "mcp":
            return cmd_mcp(args)
    except Exception as exc:
        print(f"tracewall: error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    paths = paths_for_run(cwd=Path.cwd())
    task_path = paths.tracewall_dir / "task.yml"
    created = write_default_contract(task_path, force=args.force)
    if created:
        print(f"Created task contract: {task_path}")
    else:
        print(f"Task contract already exists: {task_path}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    contract = load_contract(Path(args.task_file))
    run = create_run(contract, args.agent, cwd=Path.cwd(), enforce=args.enforce)
    print(f"Started tracewall Recorder run: {run['run_id']}")
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
        raise ValueError("Usage: tracewall run -- <command>")
    return record_command(command, cwd=Path.cwd(), enforce=args.enforce, policy_mode=args.policy_mode)


def cmd_event(args: argparse.Namespace) -> int:
    payload = parse_payload(args.payload)
    event = record_event(args.event_type, payload, run_id=args.run_id, cwd=Path.cwd())
    print(f"Recorded event: {event['event_type']} ({event['event_id']})")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    run = stop_run(args.run_id, args.final_response, cwd=Path.cwd())
    print(f"Stopped tracewall Recorder run: {run['run_id']}")
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


def cmd_guard(args: argparse.Namespace) -> int:
    command = list(args.agent_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("Usage: tracewall guard -- <agent command>")
    return run_guard(command, cwd=Path.cwd(), source=args.source)


def cmd_observe(args: argparse.Namespace) -> int:
    command = list(args.agent_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("Usage: tracewall observe -- <agent command>")
    return run_observe(command, cwd=Path.cwd(), source=args.source)


def cmd_hook(args: argparse.Namespace) -> int:
    stdin_text = sys.stdin.read()
    out = None
    if not args.no_daemon:
        # Fast path: let the warm daemon decide (no Python engine cold start, no
        # policy reload). If it isn't running or errors, fall through in-process.
        try:
            from tracewall import daemon
            if daemon.is_running():
                out = daemon.decide_via_daemon(
                    stdin_text, Path.cwd(), args.ask_mode, args.source,
                    phase="post" if args.post else "pre",
                )
        except Exception:
            out = None
    if out is None:
        out = run_post(stdin_text, Path.cwd(), source=args.source) if args.post \
            else run_pre(stdin_text, Path.cwd(), ask_mode=args.ask_mode, source=args.source)
    print(json.dumps(out))
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    from tracewall import daemon
    if args.daemon_command == "run":
        port = None if args.no_http else (args.http_port if args.http_port is not None else daemon.DEFAULT_HTTP_PORT)
        try:
            daemon.serve(http_port=port)
        except KeyboardInterrupt:
            pass
        return 0
    if args.daemon_command == "status":
        st = daemon.status()
        print(json.dumps(st, indent=2))
        return 0 if st.get("running") else 1
    if args.daemon_command == "stop":
        print("stopped" if daemon.stop_daemon() else "not running")
        return 0
    if args.daemon_command == "install":
        info = daemon.install_service()
        if info["loaded"]:
            print(f"tracewall daemon installed as a {info['backend']} service and started ({info['path']}).")
        else:
            print(f"Wrote {info['backend']} unit to {info['path']}.")
            if info["hint"]:
                print(f"To start it: {info['hint']}")
        return 0
    if args.daemon_command == "uninstall":
        info = daemon.uninstall_service()
        print(f"Removed {info['backend']} unit ({info['path']})." if info["removed"] else "No service unit found.")
        return 0
    return 1


def cmd_install_codex(args: argparse.Namespace) -> int:
    base = Path.home() if args.global_install else Path.cwd()
    codex_dir = base / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    command = f"{sys.executable} -m tracewall hook --source codex --ask-mode {args.ask_mode}"

    # 1. hooks.json — Codex PreToolUse currently only fires for Bash
    hooks_path = codex_dir / "hooks.json"
    data: dict = {}
    if hooks_path.exists():
        try:
            data = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    hooks = data.setdefault("hooks", {})

    def ensure(event: str, cmd: str) -> None:
        groups = hooks.setdefault(event, [])
        for group in groups:
            for h in group.get("hooks", []):
                if "tracewall" in str(h.get("command", "")):
                    return
        groups.append({"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]})

    ensure("PreToolUse", command)
    ensure("PostToolUse", command + " --post")
    hooks_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # 2. config.toml — hooks are behind a feature flag
    config_path = codex_dir / "config.toml"
    config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if "codex_hooks" not in config_text:
        block = "\n[features]\ncodex_hooks = true\n" if config_text and not config_text.endswith("\n") else "[features]\ncodex_hooks = true\n"
        config_path.write_text((config_text + ("\n" if config_text and not config_text.endswith("\n") else "") + block).lstrip("\n"), encoding="utf-8")

    print(f"Installed tracewall Codex hook → {hooks_path}")
    print(f"Enabled codex_hooks in → {config_path}")
    print(f"ask-mode = {args.ask_mode}  (Codex hooks can't 'ask'; deny = block risky, defer = let Codex prompt)")
    print("Note: Codex's PreToolUse only intercepts Bash today — it catches `cat .env`, installs, etc.,")
    print("but not the Read/WebSearch tools. Route MCP tool calls through `tracewall mcp stdio` for those.")
    print("Restart Codex to load it.")
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
    command = f"{sys.executable} -m tracewall hook --source claude-code"
    hooks = data.setdefault("hooks", {})

    def ensure(event: str, cmd: str) -> None:
        groups = hooks.setdefault(event, [])
        for group in groups:
            for h in group.get("hooks", []):
                if "tracewall" in str(h.get("command", "")):
                    return
        groups.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})

    ensure("PreToolUse", command)
    ensure("PostToolUse", command + " --post")
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Installed tracewall hook → {settings}")
    print("Every Claude Code tool call (terminal or VS Code) now passes through tracewall.")
    print("Restart Claude Code or run /hooks to load it.")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    tracewall_dir = paths_for_run(cwd=Path.cwd()).tracewall_dir
    policy = enforce.load_active_policy(tracewall_dir)
    if args.export:
        from tracewall.review import export_policy_html
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
            print(f"Accepted {len(policy['rules'])} rule(s) into the active policy (.tracewall/{POLICY_FILENAME}).")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    if args.mcp_command == "stdio":
        command = list(args.server_command)
        if command and command[0] == "--":
            command = command[1:]
        return run_stdio_proxy(args.server_name, command, cwd=Path.cwd(),
                               run_id=args.run_id, ask_mode=args.ask_mode, source=args.source)
    raise ValueError(f"Unknown MCP command: {args.mcp_command}")
