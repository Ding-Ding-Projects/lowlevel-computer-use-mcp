# Cheap Version as the primary local route

## Behavior

`lowlevel-computer-use-cheap` runs one registered desktop tool in-process and
prints its JSON result. It does not start MCP, Uvicorn, an HTTP listener, or a
logon daemon. The Electron Tool runner and ordinary local automation use this
route by default. The persistent `lowlevel-computer-use-mcp` entry point remains
available only for clients that explicitly need stdio MCP or the compatibility
HTTP transport.

## Configuration

Run `uv run lowlevel-computer-use-cheap --list` to inspect the bounded tool
catalog, then call a tool with named arguments or one `--json` object. The
hidden GUI entry point `lowlevel-computer-use-cheap-hidden` is available when a
Windows launcher must not allocate a console. The installer removes the legacy
`lowlevel-computer-use-http` registrations and old logon startup before
registering the quiet stdio compatibility server.

## Failure modes

- Unknown tool names return a structured error and a non-zero exit code.
- Transport endpoints such as `/health` and `/api/execute` are not exposed as
  Cheap Version tools.
- A missing dependency is reported by the same structured result path; the
  command does not silently start the retired HTTP server.
- The retired logon startup command refuses to install unless the caller passes
  the explicit `--legacy-http` compatibility opt-in.

## Security

Cheap Version calls still have the server user's local permissions. It is not a
sandbox and does not add authentication. Keep command arguments, screenshot
paths, and file-transfer destinations within the intended local scope, and use
the compatibility HTTP path only on a reviewed private network.

## Verification

`tests/test_cheap_entry.py` verifies that only registered MCP tools appear in
the catalog, transport endpoints stay excluded, and legacy client-registration
migration removes only the owned HTTP entry. The Windows process suite verifies
that logon startup is refused without the explicit compatibility flag and that
an opted-in legacy launcher still uses `pythonw.exe` plus hidden startup flags.

## Suggested articles

- [Quiet processes](quiet-processes.md)
- [Console-free, headless-first execution](runtime-safety/console-free-headless.md)
- [Electron manual client](electron-manual-client.md)
- [Trusted-LAN API](trusted-lan-api.md)
