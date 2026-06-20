"""agentproofd — the always-on, local-first decision daemon (P0.1).

The per-invocation CLI pays a Python cold start *and* re-reads the policy from
disk on every agent action. This daemon flips that: it stays warm, holds the
active policy in memory (re-reading only when ``policy.json`` actually changes),
and answers allow / ask / deny decisions over a **Unix-domain socket** (the fast
local path the hook talks to) and a **localhost HTTP** endpoint (so editor- and
terminal-agnostic clients — VS Code, the local web UI, CI — share one engine).

It is deliberately thin: it reuses the existing engine (``hook.run_pre`` /
``enforce.evaluate_action``) and adds only a wrapper + a policy cache. The wire
format is newline-delimited JSON; one request, one response.

    request   {"op": "decide", "stdin": "<raw hook event json>",
               "cwd": "/path", "ask_mode": "native", "source": "claude-code",
               "phase": "pre"|"post"}
    response  <exactly what hook.run_pre/run_post returns>   (the host's permission JSON)

    request   {"op": "ping"}        response  {"ok": true, "pid": ..., "version": ...}

Runtime files live under ``$AGENTPROOF_HOME`` (default ``~/.agentproof``):
``daemon.sock`` (the UDS) and ``daemon.json`` (pid / port / version, for clients
to discover the daemon). The socket is created owner-only (0600) — the daemon is
privileged (it sees every action), so we don't expose it to other local users.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import http.server
import json
import os
import platform
import signal
import socket
import socketserver
import subprocess
import sys
import threading

from agentproof import enforce, hook
from agentproof.events import now_iso
from agentproof.recorder import paths_for_run, record_policy_event

try:  # version is best-effort metadata only
    from agentproof import __version__ as VERSION
except Exception:  # pragma: no cover
    VERSION = "0"

DEFAULT_HTTP_PORT = 8787


# --- runtime location ------------------------------------------------------

def home() -> Path:
    """User-global runtime dir for the daemon (overridable for tests/CI)."""
    return Path(os.environ.get("AGENTPROOF_HOME") or (Path.home() / ".agentproof"))


def socket_path() -> Path:
    return home() / "daemon.sock"


def info_path() -> Path:
    return home() / "daemon.json"


# --- in-memory policy cache (the speed win) --------------------------------

class PolicyCache:
    """Holds the active policy per project, re-reading only when it changes.

    Keyed by the project's ``.agentproof`` dir; invalidated by ``policy.json``'s
    mtime so a freshly-accepted rule is picked up on the next action without a
    full reload on every call.
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[Any, dict[str, Any]]] = {}
        self._fingerprints: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, agentproof_dir: Path) -> dict[str, Any]:
        key = str(agentproof_dir)
        # Signature includes the mode, so a chmod (e.g. to world-writable) also
        # invalidates the cache and re-triggers the trust check, not just edits.
        try:
            st = enforce.policy_path(agentproof_dir).stat()
            sig: Any = (st.st_mtime, st.st_mode)
        except OSError:
            sig = None
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == sig:
                return cached[1]
        policy = enforce.load_active_policy(agentproof_dir)
        fingerprint = enforce.policy_fingerprint(agentproof_dir)
        with self._lock:
            previous = self._fingerprints.get(key)
            self._cache[key] = (sig, policy)
            self._fingerprints[key] = fingerprint
        if policy.get("untrusted") or previous != fingerprint:
            self._record_change(Path(agentproof_dir), previous, fingerprint, policy)
        return policy

    def _record_change(self, agentproof_dir: Path, previous: str | None,
                        fingerprint: str, policy: dict[str, Any]) -> None:
        """Tamper-evidence (P0.6): the daemon logs every policy change it observes
        (and any refusal to trust a world-writable policy) to the project's
        hash-chained policy audit log. Best-effort — never break a decision over
        an audit write."""
        try:
            if policy.get("untrusted"):
                record_policy_event(agentproof_dir, "policy.rejected",
                                    {"reason": policy.get("reason"), "fingerprint": fingerprint})
            elif previous is not None:
                record_policy_event(agentproof_dir, "policy.changed",
                                    {"previous_fingerprint": previous, "fingerprint": fingerprint,
                                     "rules": len(policy.get("rules") or [])})
        except Exception:
            pass

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# --- request handling (transport-agnostic) ---------------------------------

def handle_request(req: dict[str, Any], cache: PolicyCache) -> dict[str, Any]:
    op = req.get("op") or "decide"
    if op == "decide":
        cwd = Path(req.get("cwd") or ".")
        stdin_text = req.get("stdin") or "{}"
        ask_mode = req.get("ask_mode") or "native"
        source = req.get("source") or hook.AGENT
        if req.get("phase") == "post":
            return hook.run_post(stdin_text, cwd, source=source)
        agentproof_dir = paths_for_run(cwd=cwd).agentproof_dir
        policy = cache.get(agentproof_dir)
        return hook.run_pre(stdin_text, cwd, ask_mode=ask_mode, source=source, policy=policy)
    if op in ("ping", "status"):
        return {"ok": True, "pid": os.getpid(), "version": VERSION, "cached_projects": cache.size()}
    return {"error": f"unknown op: {op}"}


# --- servers ---------------------------------------------------------------

class _UDSHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        try:
            req = json.loads(line.decode("utf-8"))
        except ValueError:
            req = {}
        try:
            resp = handle_request(req, self.server.cache)  # type: ignore[attr-defined]
        except Exception as exc:  # never crash the daemon on one bad request
            resp = {"error": str(exc)}
        self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


class _UDSServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, path: str, cache: PolicyCache) -> None:
        if os.path.exists(path):
            os.unlink(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(path, _UDSHandler)
        os.chmod(path, 0o600)
        self.cache = cache


class _HTTPHandler(http.server.BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("/status", "/ping"):
            self._send(200, handle_request({"op": "status"}, self.server.cache))  # type: ignore[attr-defined]
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            req = json.loads(raw or b"{}")
        except ValueError:
            req = {}
        self._send(200, handle_request(req, self.server.cache))  # type: ignore[attr-defined]

    def log_message(self, *args: Any) -> None:  # silence default stderr logging
        return


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], cache: PolicyCache) -> None:
        super().__init__(addr, _HTTPHandler)
        self.cache = cache


# --- lifecycle -------------------------------------------------------------

def serve(http_port: int | None = DEFAULT_HTTP_PORT, on_ready: Callable[[int | None, str], None] | None = None) -> None:
    """Run the daemon in the foreground until SIGTERM/SIGINT.

    ``http_port=None`` disables HTTP (UDS only). Falls back to an ephemeral port
    if the requested one is taken. ``on_ready`` is for tests.
    """
    h = home()
    h.mkdir(parents=True, exist_ok=True)
    sock = str(socket_path())
    cache = PolicyCache()
    uds = _UDSServer(sock, cache)

    http_srv: _HTTPServer | None = None
    actual_port: int | None = None
    if http_port is not None:
        try:
            http_srv = _HTTPServer(("127.0.0.1", int(http_port)), cache)
        except OSError:
            http_srv = _HTTPServer(("127.0.0.1", 0), cache)
        actual_port = http_srv.server_address[1]

    info_path().write_text(json.dumps({
        "pid": os.getpid(), "socket": sock, "http_port": actual_port,
        "version": VERSION, "started_at": now_iso(),
    }, indent=2), encoding="utf-8")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    threading.Thread(target=uds.serve_forever, daemon=True).start()
    if http_srv is not None:
        threading.Thread(target=http_srv.serve_forever, daemon=True).start()
    if on_ready is not None:
        on_ready(actual_port, sock)
    try:
        stop.wait()
    finally:
        uds.shutdown(); uds.server_close()
        if http_srv is not None:
            http_srv.shutdown(); http_srv.server_close()
        for p in (sock, str(info_path())):
            try:
                os.unlink(p)
            except OSError:
                pass


def status() -> dict[str, Any]:
    info = info_path()
    if not info.exists():
        return {"running": False}
    try:
        data = json.loads(info.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"running": False}
    data["running"] = is_running()
    return data


def stop_daemon() -> bool:
    info = info_path()
    if not info.exists():
        return False
    try:
        pid = json.loads(info.read_text(encoding="utf-8")).get("pid")
    except (ValueError, OSError):
        return False
    if not pid:
        return False
    try:
        os.kill(int(pid), signal.SIGTERM)
        return True
    except OSError:
        return False


# --- client ----------------------------------------------------------------

def request(req: dict[str, Any], sock_path: str | None = None, timeout: float = 2.0) -> dict[str, Any] | None:
    """Send one request to the daemon over its UDS. Returns None if unreachable."""
    path = sock_path or str(socket_path())
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8") or "{}")
    except (OSError, ValueError):
        return None
    finally:
        s.close()


def is_running(sock_path: str | None = None) -> bool:
    resp = request({"op": "ping"}, sock_path=sock_path, timeout=1.0)
    return bool(resp and resp.get("ok"))


def decide_via_daemon(stdin_text: str, cwd: Path, ask_mode: str, source: str, phase: str = "pre") -> dict[str, Any] | None:
    return request({
        "op": "decide", "stdin": stdin_text, "cwd": str(cwd),
        "ask_mode": ask_mode, "source": source, "phase": phase,
    })


# --- OS service install (P0.2) ---------------------------------------------
# The daemon must run independently of any editor: as a launchd LaunchAgent on
# macOS, a systemd --user unit on Linux. It survives VS Code closing and covers
# terminal-only and background agents. Generation is pure (testable); loading is
# best-effort (we leave the unit + a hint if the loader isn't available).

SERVICE_LABEL = "dev.agentproof.daemon"
SYSTEMD_UNIT_NAME = "agentproof.service"

_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{out}</string>
  <key>StandardErrorPath</key><string>{err}</string>
</dict>
</plist>
"""

_SYSTEMD_UNIT = """[Unit]
Description=AgentProof local decision daemon (agentproofd)
After=default.target

[Service]
ExecStart={exec_start}
Restart=on-failure

[Install]
WantedBy=default.target
"""


def _exec_args() -> list[str]:
    """How the service launches the daemon: this Python running the package."""
    return [sys.executable, "-m", "agentproof", "daemon", "run"]


def service_spec(system: str | None = None, dest_dir: Path | None = None) -> tuple[Path, str, list[str]]:
    """Pure: (unit_path, file_content, loader_command) for this platform.
    macOS → launchd LaunchAgent; everything else → systemd --user unit."""
    system = system or platform.system()
    args = _exec_args()
    if system == "Darwin":
        dest = Path(dest_dir) if dest_dir else (Path.home() / "Library" / "LaunchAgents")
        path = dest / f"{SERVICE_LABEL}.plist"
        arg_xml = "\n".join(f"    <string>{a}</string>" for a in args)
        content = _PLIST.format(label=SERVICE_LABEL, args=arg_xml,
                                out=str(home() / "daemon.out.log"), err=str(home() / "daemon.err.log"))
        loader = ["launchctl", "load", "-w", str(path)]
    else:
        dest = Path(dest_dir) if dest_dir else (Path.home() / ".config" / "systemd" / "user")
        path = dest / SYSTEMD_UNIT_NAME
        content = _SYSTEMD_UNIT.format(exec_start=" ".join(args))
        loader = ["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT_NAME]
    return path, content, loader


def install_service(system: str | None = None, dest_dir: Path | None = None, run_loader: bool = True) -> dict[str, Any]:
    """Write the service unit (idempotent — overwrites) and ask the OS to load it.
    The loader step is best-effort: on failure we leave the unit + a hint."""
    system = system or platform.system()
    path, content, loader = service_spec(system, dest_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    backend = "launchd" if system == "Darwin" else "systemd"
    loaded, hint = False, ""
    if run_loader:
        try:
            result = subprocess.run(loader, capture_output=True, text=True)
            loaded = result.returncode == 0
            if not loaded:
                hint = (result.stderr or result.stdout or "").strip() or " ".join(loader)
        except FileNotFoundError:
            hint = f"{loader[0]} not found; load manually: {' '.join(loader)}"
    return {"backend": backend, "path": str(path), "loaded": loaded, "loader": " ".join(loader), "hint": hint}


def uninstall_service(system: str | None = None, dest_dir: Path | None = None, run_loader: bool = True) -> dict[str, Any]:
    """Unload the OS service (best-effort) and remove its unit file."""
    system = system or platform.system()
    path, _, _ = service_spec(system, dest_dir)
    unloader = (["launchctl", "unload", "-w", str(path)] if system == "Darwin"
                else ["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT_NAME])
    if run_loader:
        try:
            subprocess.run(unloader, capture_output=True, text=True)
        except FileNotFoundError:
            pass
    removed = False
    try:
        path.unlink()
        removed = True
    except OSError:
        pass
    return {"backend": "launchd" if system == "Darwin" else "systemd", "path": str(path), "removed": removed}
