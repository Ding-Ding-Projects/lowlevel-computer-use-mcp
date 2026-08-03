# Subagent lanes

## Behavior

The Electron Workspaces surface stores a named subagent lane with a project,
agent name, generated desktop prefix, room count, creation time, and factual
status. Creating a lane calls `create_headless_desktops` using that namespace;
the saved record lets a later agent identify and reuse the same project/agent
room instead of inventing a second one.

## Configuration

Choose the project, agent, and number of rooms in **Subagent lanes**. The record
is stored in Electron user data as app-owned state and is included in settings
export. The API still exposes the underlying desktop list for agents that do
not use Electron.

## Failure modes

- Empty project or agent names are rejected before a desktop is created.
- Duplicate desktop names are rejected by the server.
- A failed desktop creation does not save a ready lane.

## Security

The lane record is coordination metadata, not a permission boundary. Every
room and command retains the MCP server user's local privileges. Trusted-LAN
clients must remain firewall-restricted.

## Verification

The renderer creates the lane through the real `create_headless_desktops` tool
and persists it through the Electron main process. Windows headless tests cover
the underlying multi-desktop creation; a live multi-agent run should verify
simultaneous lanes and cleanup.

## Suggested articles

[Headless desktops](headless-desktops.md) · [Electron manual client](electron-manual-client.md) · [Trusted-LAN API](trusted-lan-api.md)
