"""`agentproof observe -- <agent>` — record everything the agent's process tree
actually does (not just what it reports, and not just what gets denied).

Ground-truth recording. Per ponytail we don't write an eBPF program; on Linux we
use `strace` (installed, no kernel work) to follow the process tree and capture
file opens, execs, and network connects, then record them as effect events.

ponytail ceiling: strace has runtime overhead, is evadable by a hostile binary,
and is Linux-only. The production upgrade path is eBPF (Falco/Tetragon) on Linux
and the Endpoint Security framework on macOS — both would emit these same events.
File events are scoped to the project root to cut system-library noise.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from agentproof.hook import ensure_run
from agentproof.recorder import append_event, paths_for_run

_EXEC = re.compile(r'execve\("([^"]+)"')
_OPENAT = re.compile(r'openat\([^,]+,\s*"([^"]+)",\s*([A-Z_|]+)')
_OPEN = re.compile(r'(?<![\w])open\("([^"]+)",\s*([A-Z_|]+)')
_PORT = re.compile(r"htons\((\d+)\)")
_ADDR = re.compile(r'inet_addr\("([^"]+)"\)')
_WRITE_FLAGS = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC")


def parse_strace(text: str, project_root: Path, source: str) -> list[tuple[str, dict]]:
    """Pure: strace -f output -> ordered (event_type, payload) effect events."""
    root = str(Path(project_root).resolve())
    events: list[tuple[str, dict]] = []
    for line in text.splitlines():
        m = _EXEC.search(line)
        if m and "= -1" not in line:
            events.append(("process.exec", {"source": source, "path": m.group(1)}))
            continue
        m = _OPENAT.search(line) or _OPEN.search(line)
        if m:
            if re.search(r"=\s*-1", line):   # failed open — skip (it didn't happen)
                continue
            path, flags = m.group(1), m.group(2)
            full = path if path.startswith("/") else str(Path(root) / path)
            if not full.startswith(root):    # scope to the project; drop system noise
                continue
            etype = "file.write" if any(f in flags for f in _WRITE_FLAGS) else "file.read"
            events.append((etype, {"source": source, "path": full}))
            continue
        if "connect(" in line and "AF_INET" in line:
            addr = _ADDR.search(line)
            if addr:
                port = _PORT.search(line)
                events.append(("net.connect", {"source": source, "host": addr.group(1),
                                                "port": int(port.group(1)) if port else None}))
    return events


def run_observe(command: list[str], cwd: Path | None = None, source: str = "agent") -> int:
    """Run ``command`` under strace and record its real effects to the timeline."""
    cwd = Path(cwd or Path.cwd())
    run_id = ensure_run(cwd, agent=source)
    paths = paths_for_run(run_id, cwd)

    if not shutil.which("strace"):
        print("agentproof observe: strace not found — recording session only. "
              "(Full observe is Linux/strace today; macOS via fs_usage/EndpointSecurity is next.)",
              file=sys.stderr)
        append_event(paths, "observe.started", {"source": source, "backend": "none", "command": command})
        rc = subprocess.run(command, cwd=str(cwd)).returncode
        append_event(paths, "observe.stopped", {"source": source, "backend": "none", "exit_code": rc})
        return rc

    append_event(paths, "observe.started", {"source": source, "backend": "strace", "command": command})
    with tempfile.NamedTemporaryFile("r", suffix=".strace", delete=True) as trace:
        wrapped = ["strace", "-f", "-o", trace.name, "-s", "256",
                   "-e", "trace=openat,open,execve,connect", "--", *command]
        completed = subprocess.run(wrapped, cwd=str(cwd))  # inherit stdio (interactive)
        for etype, payload in parse_strace(Path(trace.name).read_text(errors="replace"), cwd, source):
            append_event(paths, etype, payload)
    append_event(paths, "observe.stopped", {"source": source, "backend": "strace", "exit_code": completed.returncode})
    return completed.returncode
