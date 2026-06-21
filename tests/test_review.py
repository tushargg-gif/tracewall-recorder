from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from tracewall.review import (
    export_review_html,
    handle_api,
    load_verdicts,
    render_review_html,
    review_state,
    set_verdict,
)


ROOT = Path(__file__).resolve().parents[1]


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "tracewall", *args],
        cwd=cwd, text=True, capture_output=True, env=env, check=False,
    )


def _make_run(tmp_path: Path) -> str:
    assert _cli(tmp_path, "init").returncode == 0
    assert _cli(tmp_path, "start", "--agent", "test").returncode == 0
    assert _cli(tmp_path, "run", "--", "echo", "hi").returncode == 0
    assert _cli(tmp_path, "stop", "--final-response", "done").returncode == 0
    return json.loads(_cli(tmp_path, "flow", "--json").stdout)["run_id"]


def test_verdict_store_persists_allow_block_clear(tmp_path: Path):
    rid = _make_run(tmp_path)
    set_verdict(rid, 1, "allow", cwd=tmp_path)
    assert load_verdicts(rid, cwd=tmp_path)["verdicts"]["1"]["decision"] == "allow"
    set_verdict(rid, 1, "block", note="touches prod", cwd=tmp_path)
    assert load_verdicts(rid, cwd=tmp_path)["verdicts"]["1"]["decision"] == "block"
    set_verdict(rid, 1, "clear", cwd=tmp_path)
    assert load_verdicts(rid, cwd=tmp_path)["verdicts"] == {}


def test_invalid_decision_rejected(tmp_path: Path):
    rid = _make_run(tmp_path)
    try:
        set_verdict(rid, 1, "maybe", cwd=tmp_path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_api_get_state_and_post_verdict(tmp_path: Path):
    rid = _make_run(tmp_path)
    status, ctype, body = handle_api("GET", "/api/state", b"", rid, tmp_path)
    assert status == 200 and "json" in ctype
    state = json.loads(body)
    assert state["action_count"] >= 1
    assert state["reviewed"] == 0

    status, _, body = handle_api(
        "POST", "/api/verdict", json.dumps({"seq": 1, "decision": "allow"}).encode(), rid, tmp_path
    )
    assert status == 200
    assert json.loads(body)["allowed"] == 1

    # overwrite with block
    status, _, body = handle_api(
        "POST", "/api/verdict", json.dumps({"seq": 1, "decision": "block"}).encode(), rid, tmp_path
    )
    state = json.loads(body)
    assert state["blocked"] == 1 and state["allowed"] == 0


def test_api_rejects_bad_request_and_unknown_route(tmp_path: Path):
    rid = _make_run(tmp_path)
    status, _, _ = handle_api("POST", "/api/verdict", b"{}", rid, tmp_path)
    assert status == 400
    status, _, _ = handle_api("GET", "/api/nope", b"", rid, tmp_path)
    assert status == 404


def test_cli_review_json_and_verdict(tmp_path: Path):
    rid = _make_run(tmp_path)
    out = _cli(tmp_path, "review", "--json")
    assert out.returncode == 0, out.stderr
    state = json.loads(out.stdout)
    assert state["run_id"] == rid and "actions" in state and "policy" in state
    v = _cli(tmp_path, "verdict", "--seq", "1", "--decision", "block")
    assert v.returncode == 0, v.stderr
    assert load_verdicts(rid, cwd=tmp_path)["verdicts"]["1"]["decision"] == "block"


def test_html_renders_actions_and_export(tmp_path: Path):
    rid = _make_run(tmp_path)
    html = render_review_html(review_state(rid, cwd=tmp_path), live=True)
    assert "echo hi" in html
    assert "tracewall" in html
    out = export_review_html(rid, tmp_path / "review.html", cwd=tmp_path)
    assert out.exists()
    assert "echo hi" in out.read_text(encoding="utf-8")
