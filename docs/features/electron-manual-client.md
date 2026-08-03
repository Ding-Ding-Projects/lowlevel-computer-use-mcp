# Electron Material 3 manual client

## Behavior

The `electron/` app provides browser-style tabs for Workspaces, Tool runner,
History, Settings, Notifications, Changelog, and Manual. Workspaces create
project/agent-namespaced headless desktops, persist subagent lanes, and launch
GUI apps. Tool runner invokes the same Cheap Version functions as the MCP
server, accepts saved LAN connections, and offers native app, file, folder, and
project-folder browsers for path fields. Quick launch has its own inline app
browser beside the command field, so choosing an executable never requires
leaving the workspace. History is stored locally under
Electron's user-data directory and can be exported as Markdown.

The Workspaces tab can explicitly start/stop the trusted-LAN HTTP API, show its
`/mcp` and `/health` URLs, and install or remove a hidden Windows logon task for
the selected host and port. The startup action is user-triggered and the server
itself prefers a headless desktop.

Settings persist language mode, independent English/Cantonese funny levels,
theme, density, accent, font scale, appearance values, tab state, connections,
agents, notifications, and history. Every searchable surface keeps plain-text
search as the default and exposes an opt-in bounded JavaScript regex builder
with pattern, flags, sample, and validation feedback. The appearance editor
includes a continuous native color field, editable HEX/RGB/HSL/HSV/HWB/CMYK
representations, contrast readout, copy actions, and an honest capability note
for Lab-family spaces that this renderer does not yet convert.

The Changelog tab reads the complete local Git history, links every entry to its
exact commit, filters by date and text, and exports the filtered view. The
packaged Windows build uses the Squirrel target and is smoke-tested through the
same off-screen capture path as development runs.

## Configuration

```powershell
cd electron
npm install
npm start
```

The main process uses `windowsHide: true`, never enables shell execution, and
repairs the repository's `uv` environment quietly. The application deliberately
keeps destructive operations in the explicit Tool runner instead of hiding them
behind startup behavior.

## Verification

Run `npm run check`, `npm run capture`, and `npm run package` from `electron/`.
The current local evidence includes 35 Python tests, three real off-screen
renderer captures, a successful Squirrel package, and a packaged executable
smoke test. A second-computer LAN check, full accessibility audit, and
simultaneous multi-agent desktop proof remain host-specific follow-up evidence.

## Suggested articles

- [Headless desktops](headless-desktops.md)
- [Trusted-LAN API](trusted-lan-api.md)
- [Subagent lanes](subagent-lanes.md)
- [Quiet processes](quiet-processes.md)
