from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3

from agentproof.events import normalize_event
from agentproof.events import redact_secrets


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT,
    agent TEXT,
    orchestrator TEXT,
    control_mode TEXT,
    status TEXT,
    run_dir TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_hash TEXT,
    prev_event_hash TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT,
    category TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    severity TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    request_json TEXT NOT NULL,
    response_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mcp_proxies (
    proxy_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    server_name TEXT NOT NULL,
    transport TEXT NOT NULL,
    target_url TEXT,
    headers_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    path TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "agentproof.sqlite3"
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(SCHEMA)

    def upsert_run(self, run: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, task_id, agent, orchestrator, control_mode, status,
                    run_dir, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    control_mode=excluded.control_mode,
                    orchestrator=excluded.orchestrator
                """,
                (
                    run.get("run_id"),
                    run.get("task_id"),
                    run.get("agent"),
                    run.get("orchestrator", ""),
                    run.get("control_mode", "observe"),
                    run.get("status"),
                    run.get("run_dir", ""),
                    run.get("start_time") or run.get("created_at"),
                    run.get("end_time") or run.get("updated_at") or run.get("start_time"),
                ),
            )

    def append_event(self, run_id: str, events_file: Path, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        previous_hash = self.last_event_hash(run_id, events_file)
        event = normalize_event(run_id, event_type, payload, prev_event_hash=previous_hash)
        events_file.parent.mkdir(parents=True, exist_ok=True)
        with events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    event_id, run_id, event_type, timestamp, event_hash,
                    prev_event_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    run_id,
                    event["event_type"],
                    event["timestamp"],
                    event["event_hash"],
                    event.get("prev_event_hash"),
                    json.dumps(event["payload"], sort_keys=True),
                ),
            )
        return event

    def last_event_hash(self, run_id: str, events_file: Path) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT event_hash FROM events WHERE run_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if row and row["event_hash"]:
                return str(row["event_hash"])
        if not events_file.exists():
            return None
        last_hash = None
        for line in events_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last_hash = json.loads(line).get("event_hash")
        return last_hash

    def store_verification(self, run_id: str, verification: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM checks WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM violations WHERE run_id = ?", (run_id,))
            for check in verification.get("checks") or []:
                connection.execute(
                    "INSERT INTO checks (run_id, name, status, severity, category, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        check.get("name"),
                        check.get("status"),
                        check.get("severity"),
                        check.get("category"),
                        json.dumps(check, sort_keys=True),
                    ),
                )
            for violation in verification.get("policy_violations") or []:
                connection.execute(
                    "INSERT INTO violations (run_id, policy_id, severity, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        run_id,
                        violation.get("policy_id"),
                        violation.get("severity"),
                        json.dumps(violation, sort_keys=True),
                    ),
                )

    def create_approval(self, approval: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO approvals (
                    approval_id, run_id, status, request_json, response_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval["approval_id"],
                    approval["run_id"],
                    approval["status"],
                    json.dumps(approval["request"], sort_keys=True),
                    json.dumps(approval.get("response"), sort_keys=True),
                    approval["created_at"],
                    approval["updated_at"],
                ),
            )

    def update_approval(self, approval_id: str, status: str, response: dict[str, Any], updated_at: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE approvals SET status = ?, response_json = ?, updated_at = ? WHERE approval_id = ?",
                (status, json.dumps(response, sort_keys=True), updated_at, approval_id),
            )
            return cursor.rowcount > 0

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return approval_row_to_dict(row) if row else None

    def pending_approvals(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        return [approval_row_to_dict(row) for row in rows]

    def create_mcp_proxy(self, proxy: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO mcp_proxies (
                    proxy_id, run_id, server_name, transport, target_url,
                    headers_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proxy["proxy_id"],
                    proxy["run_id"],
                    proxy["server_name"],
                    proxy["transport"],
                    proxy.get("target_url"),
                    json.dumps(redact_secrets(proxy.get("headers") or {}), sort_keys=True),
                    proxy["created_at"],
                ),
            )

    def get_mcp_proxy(self, proxy_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM mcp_proxies WHERE proxy_id = ?",
                (proxy_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "proxy_id": row["proxy_id"],
            "run_id": row["run_id"],
            "server_name": row["server_name"],
            "transport": row["transport"],
            "target_url": row["target_url"],
            "headers": json.loads(row["headers_json"] or "{}"),
            "created_at": row["created_at"],
        }


def approval_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "approval_id": row["approval_id"],
        "run_id": row["run_id"],
        "status": row["status"],
        "request": json.loads(row["request_json"]),
        "response": json.loads(row["response_json"]) if row["response_json"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def default_store_for_project(project_root: Path) -> Store:
    return Store(project_root / ".agentproof")
