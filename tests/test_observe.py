from __future__ import annotations

from pathlib import Path

from agentproof.flow import build_action_flow
from agentproof.observe import parse_strace


def test_parse_strace_extracts_effects(tmp_path: Path):
    root = str(tmp_path)
    trace = "\n".join([
        f'11    execve("/usr/bin/cat", ["cat", "{root}/.env"], 0x0) = 0',
        f'11    openat(AT_FDCWD, "{root}/.env", O_RDONLY) = 3',
        f'12    openat(AT_FDCWD, "{root}/out.log", O_WRONLY|O_CREAT) = 4',
        '13    openat(AT_FDCWD, "/usr/lib/libc.so", O_RDONLY) = 5',   # system noise -> dropped
        f'13    openat(AT_FDCWD, "{root}/missing", O_RDONLY) = -1 ENOENT',  # failed -> dropped
        '14    connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.2.3.4")}, 16) = 0',
    ])
    events = parse_strace(trace, tmp_path, source="openclaw")
    kinds = [e[0] for e in events]
    assert kinds.count("process.exec") == 1
    assert ("file.read", {"source": "openclaw", "path": f"{root}/.env"}) in events
    assert ("file.write", {"source": "openclaw", "path": f"{root}/out.log"}) in events
    assert not any(p.get("path", "").startswith("/usr/lib") for _, p in events)  # noise dropped
    assert not any("missing" in p.get("path", "") for _, p in events)            # failed open dropped
    net = [p for t, p in events if t == "net.connect"][0]
    assert net["host"] == "1.2.3.4" and net["port"] == 443


def test_effects_surface_in_flow():
    events = [
        {"event_type": "process.exec", "event_id": "e1", "timestamp": "2026-06-16T10:00:00",
         "payload": {"source": "openclaw", "path": "/usr/bin/curl"}},
        {"event_type": "file.read", "event_id": "e2", "timestamp": "2026-06-16T10:00:01",
         "payload": {"source": "openclaw", "path": "/proj/.env"}},
        {"event_type": "net.connect", "event_id": "e3", "timestamp": "2026-06-16T10:00:02",
         "payload": {"source": "openclaw", "host": "1.2.3.4", "port": 443}},
    ]
    actions = build_action_flow(events)
    assert [a["kind"] for a in actions] == ["exec", "file", "network"]
    assert all(a["source"] == "openclaw" and a["status"] == "ok" for a in actions)
    assert "curl" in actions[0]["title"] and ".env" in actions[1]["title"] and "1.2.3.4" in actions[2]["title"]
