# MCP Proxy

AgentProof Recorder can sit between an orchestrator and MCP tools.

The goal is to record MCP evidence and enforce simple policies before tool calls are trusted.

## Sidecar

Start the local sidecar:

```bash
agentproof sidecar --host 127.0.0.1 --port 8797 --root .agentproof
```

Use an auth token if the sidecar is exposed beyond localhost:

```bash
agentproof sidecar --host 0.0.0.0 --port 8797 --auth-token "$AGENTPROOF_TOKEN"
```

## Streamable HTTP Proxy

Register a proxy:

```json
{
  "run_id": "run_123",
  "server_name": "remote-tools",
  "transport": "streamable_http",
  "target_url": "https://tools.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ..."
  }
}
```

The response includes a local `proxy_url`. Point the orchestrator at that URL instead of the real MCP server.

## Target Validation

MCP HTTP proxy targets are validated before registration.

Rejected by default:

- non-http schemes such as `file://`, `ftp://`, `gopher://`, and `unix://`
- malformed URLs
- empty hostnames
- localhost names
- loopback IPs
- private/internal IP ranges
- link-local, multicast, unspecified, and reserved literal IPs

DNS resolution is not currently performed. Hostname validation is intentionally simple in early alpha.

## Host Allowlist

Restrict proxy registration to known hosts:

```bash
agentproof sidecar \
  --auth-token test \
  --allowed-mcp-target-host mcp.example.com
```

Repeat the flag for multiple hosts.

Localhost and private IPs remain blocked even if allowlisted.

## Recorded Events

- `mcp.initialize`
- `mcp.tools.list`
- `mcp.tool.call.started`
- `mcp.tool.call.finished`
- `mcp.resources.list`
- `mcp.resource.read`
- `mcp.prompts.list`
- `mcp.prompt.get`
- `mcp.error`
- `policy.decision`
- `approval.requested`
- `approval.approved`
- `approval.denied`

Sensitive headers and secret-like fields are redacted before evidence is written.

