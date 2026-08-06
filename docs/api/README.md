# Streamable HTTP API

The retired compatibility HTTP mode exposes the standard Model Context Protocol
Streamable HTTP endpoint at `http://127.0.0.1:8765/mcp` only after an explicit
`--legacy-http` launch. The primary local route is `lowlevel-computer-use-cheap`.
This is not a REST API: clients initialize a
JSON-RPC session, preserve any returned `MCP-Session-Id`, send the initialized
notification, and then call MCP methods such as `tools/list` or `tools/call`.

Use [the Postman collection](lowlevel-computer-use-mcp.postman_collection.json) for
a local initialize/list/safe-call flow. The collection stores the session ID only
in the active Postman environment. Do not change `baseUrl` to a non-loopback host
without adding authentication and reviewing DNS-rebinding protection.
