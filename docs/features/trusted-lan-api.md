# Trusted-LAN MCP API

## Behavior

Run `uv run lowlevel-computer-use-mcp --http --legacy-http --host 0.0.0.0 --port 8765` only
when a compatibility client explicitly requires the retired HTTP path. The Cheap
Version is the primary local route and does not listen on a port. Compatibility
clients connect to the Streamable HTTP MCP endpoint at
`http://<computer-ip>:8765/mcp`; `/health` is a simple liveness check.
The Electron manual can use the convenience JSON endpoint
`POST http://<computer-ip>:8765/api/execute` with
`{"tool":"list_headless_desktops","arguments":{}}`; it delegates to the
same registered tool functions as MCP.

## Consent and security

This mode intentionally has no API key because the operator has agreed to use it
on a trusted LAN. Every reachable client can invoke the server's unsandboxed
tools, run all commands, and upload/download files (base64 transfers are capped
at 50 MiB per call) with the Windows user's privileges. Keep the port on a private network,
restrict it with Windows Firewall as appropriate, and never port-forward it to
the public internet.

HTTP mode creates `LowLevelCURemote` as the preferred Windows headless workspace
without switching the user's input desktop. For concurrent projects, call
`create_headless_desktops` with project/agent-specific names and use those names
for launches and window actions.

## Failure modes

- The GUI installer does not enable this transport or install it at logon.
- `install-startup` refuses unless `--legacy-http` is explicitly supplied.
- A client using the wrong path should use `/mcp`, not `/health`.
- A bound address that is not reachable is usually a firewall, routing, or
  Windows network-profile issue rather than an MCP tool failure.
- The default host remains `127.0.0.1` when `--host` is omitted.

## Verification

The health route is registered in the FastMCP application. Verify it from a
second trusted LAN computer with `curl http://<computer-ip>:8765/health`, then
connect the MCP client to `/mcp` and run a read-only tool before any action tool.
