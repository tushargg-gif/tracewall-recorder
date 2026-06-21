from __future__ import annotations

import pytest

from tracewall.mcp_targets import validate_mcp_target_url


@pytest.mark.parametrize(
    "target_url",
    [
        "https://mcp.example.com/rpc",
        "http://mcp.example.com/rpc",
    ],
)
def test_validate_mcp_target_url_allows_http_and_https_external_hosts(target_url: str):
    assert validate_mcp_target_url(target_url) == target_url


@pytest.mark.parametrize(
    "target_url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "http://localhost:3000/mcp",
        "http://127.0.0.1:3000/mcp",
        "http://0.0.0.0:3000/mcp",
        "http://10.0.0.5/mcp",
        "http://172.16.0.5/mcp",
        "http://192.168.1.5/mcp",
        "not-a-url",
        "",
    ],
)
def test_validate_mcp_target_url_rejects_unsafe_targets(target_url: str):
    with pytest.raises(ValueError):
        validate_mcp_target_url(target_url)


def test_validate_mcp_target_url_applies_allowlist():
    assert (
        validate_mcp_target_url(
            "https://mcp.example.com/rpc",
            allowed_hosts=["mcp.example.com"],
        )
        == "https://mcp.example.com/rpc"
    )
    with pytest.raises(ValueError, match="allowed host"):
        validate_mcp_target_url(
            "https://other.example.com/rpc",
            allowed_hosts=["mcp.example.com"],
        )


def test_validate_mcp_target_url_still_rejects_private_allowlisted_ip():
    with pytest.raises(ValueError, match="private/internal"):
        validate_mcp_target_url(
            "http://127.0.0.1:3000/mcp",
            allowed_hosts=["127.0.0.1"],
        )
