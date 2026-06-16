from __future__ import annotations

from urllib.parse import urlparse
import ipaddress


LOCALHOST_NAMES = {"localhost", "localhost.localdomain", "0.0.0.0"}


def validate_mcp_target_url(target_url: str, allowed_hosts: list[str] | None = None) -> str:
    if not target_url:
        raise ValueError("MCP target_url is required")

    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("MCP target_url must use http or https")
    if not parsed.hostname:
        raise ValueError("MCP target_url must include a hostname")

    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("MCP target_url has an invalid port") from exc

    host = parsed.hostname.rstrip(".").lower()
    if host in LOCALHOST_NAMES:
        raise ValueError("MCP target_url cannot point to localhost")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise ValueError("MCP target_url cannot point to private/internal IPs")

    allowed = {item.rstrip(".").lower() for item in (allowed_hosts or []) if item}
    if allowed and host not in allowed:
        raise ValueError("MCP target_url host is not in the allowed host list")

    return target_url
