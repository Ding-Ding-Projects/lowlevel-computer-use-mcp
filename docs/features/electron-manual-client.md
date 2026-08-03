# Electron Material 3 manual client

## Behavior

The `electron/` app provides browser-style tabs for Workspaces, Tool runner,
History, Settings, and Manual. Workspaces create project/agent-namespaced
headless desktops and launch GUI apps. Tool runner invokes the same Cheap Version
functions as the MCP server. History is stored locally under Electron's user-data
directory and can be exported as Markdown.

The Workspaces tab can explicitly start/stop the trusted-LAN HTTP API, show its
`/mcp` and `/health` URLs, and install or remove a hidden Windows logon task for
the selected host and port. The startup action is user-triggered and the server
itself prefers a headless desktop.

Settings persist language mode, independent English/Cantonese funny levels,
theme, density, accent, and font scale. History has plain-text search by default
and an opt-in bounded JavaScript regex builder with pattern, flags, sample, and
validation feedback.

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

Run `node --check main.cjs`, `node --check preload.cjs`, and `node --check
renderer/app.js` from `electron/`. Full Electron runtime verification requires
an installed Electron dependency and a Windows desktop session.
