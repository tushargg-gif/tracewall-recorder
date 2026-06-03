from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from agentproof.contracts import load_contract, write_default_contract
from agentproof.events import parse_payload
from agentproof.mcp_stdio import run_stdio_proxy
from agentproof.recorder import (
    create_run,
    latest_run_id,
    paths_for_run,
    record_event,
    record_command,
    stop_run,
)
from agentproof.reports import generate_report
from agentproof.sidecar import run_sidecar
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

    sidecar = subcommands.add_parser("sidecar", help="Run the local AgentProof Recorder sidecar service.")
    sidecar.add_argument("--host", default="127.0.0.1")
    sidecar.add_argument("--port", default=8797, type=int)
    sidecar.add_argument("--root", default=".agentproof")
    sidecar.add_argument("--auth-token", default=None, help="Require Bearer token auth for sidecar API requests.")
    sidecar.add_argument(
        "--allowed-mcp-target-host",
        action="append",
        default=[],
        help="Allow Streamable HTTP MCP proxy registration only for this target hostname. Repeatable.",
    )

    shell = subcommands.add_parser("shell", help="Show shell recording guidance.")
    shell.add_argument("--run-id", default=None, help="Run ID to attach guidance to. Defaults to the active run.")

    mcp = subcommands.add_parser("mcp", help="Run MCP proxy modes.")
    mcp_subcommands = mcp.add_subparsers(dest="mcp_command", required=True)
    stdio = mcp_subcommands.add_parser("stdio", help="Proxy a stdio MCP server.")
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
        if args.command == "sidecar":
            return cmd_sidecar(args)
        if args.command == "shell":
            return cmd_shell(args)
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
    return record_command(command, cwd=Path.cwd(), enforce=args.enforce)


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


def cmd_sidecar(args: argparse.Namespace) -> int:
    run_sidecar(
        args.host,
        args.port,
        args.root,
        auth_token=args.auth_token,
        allowed_mcp_target_hosts=args.allowed_mcp_target_host,
    )
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    run_id = args.run_id
    if not run_id:
        try:
            run_id = latest_run_id(Path.cwd())
        except RuntimeError:
            run_id = None
    print("agentproof shell is available as a lightweight placeholder.")
    if run_id:
        print(f"Current run: {run_id}")
    else:
        print("No active run found. Start one with `agentproof start --agent <name>`.")
    print("For now, record commands with `agentproof run -- <command>`.")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    if args.mcp_command == "stdio":
        command = list(args.server_command)
        if command and command[0] == "--":
            command = command[1:]
        return run_stdio_proxy(args.run_id, args.server_name, command, cwd=Path.cwd())
    raise ValueError(f"Unknown MCP command: {args.mcp_command}")
