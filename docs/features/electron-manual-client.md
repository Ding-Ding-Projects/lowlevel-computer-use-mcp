# Electron Material 3 manual client

## Behavior

The `electron/` app provides browser-style tabs for Workspaces, Tool runner,
History, Settings, Notifications, Changelog, and Manual. Workspaces create
project/agent-namespaced headless desktops, persist subagent lanes, and launch
GUI apps. Tool runner invokes the same Cheap Version functions as the MCP
server, accepts saved LAN connections, and offers native app, file, folder, and
project-folder browsers for path fields. Quick launch has its own inline app
browser beside the command field, so choosing an executable never requires
leaving the workspace. Its Send and receive files card transfers bounded files
through the selected computer and uses a native Save dialog for receives.
History is stored locally under Electron's user-data directory. The History tab
combines text/regex search with a date range and action filters derived from the
actual recorded entries, and exports the currently filtered view as Markdown.

The Workspaces tab can explicitly start/stop the trusted-LAN HTTP API, show its
`/mcp` and `/health` URLs, and install or remove a hidden Windows logon task for
the selected host and port. The startup action is user-triggered and the server
itself prefers a headless desktop.

Settings persist language mode, independent English/Cantonese funny levels,
theme, density, accent, font scale, appearance values, tab state, connections,
agents, notifications, and history. Every searchable surface keeps plain-text
search as the default and exposes an opt-in bounded JavaScript regex builder
with pattern, flags, sample, and validation feedback. The appearance editor
  includes a continuous color field, editable HEX/HEX8/RGB/RGBA/alpha/HSL/HSV/
  HWB/CIELab/LCH/OKLab/OKLCH/CMYK/CSS-name representations, contrast and gamut
  readouts, and copy actions. Conversion is local and preserves alpha.

The Changelog tab reads the complete local Git history, links every entry to its
exact commit, filters by date and text, and exports the filtered view. The
packaged Windows build uses the Squirrel target and is smoke-tested through the
same off-screen capture path as development runs.

The Manual surface also shows the build's factual dim-sum code name and a link
to the verified public catalog photo. The release workflow selects the next
unused dish from `Ding-Ding-Projects/dim-sum-photos` and injects the same
metadata into the packaged client and release notes; it never copies the photo
into this repository.

Tab management is first-class rather than decorative. The Settings tab exposes
independent current-strip, group-tab, group-name, and master-tab searches; each
keeps its own regex state. Users can create, rename, collapse, and expand groups,
move tabs between groups, pin tabs, reorder them, and open a searchable tab
context menu. The bulk-close controls match only visible tab labels, default to
plain text, optionally use the anchored regex builder, preview the exact count
and labels, exclude pinned tabs by default, and require the app's two-key plus
slider confirmation before closing. The active tab is protected if a request
would otherwise close every page.

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
The current local evidence includes 36 Python tests, nine real off-screen
renderer captures, the fresh-profile memory Git self-test, a successful
Squirrel package, and a packaged executable smoke test. A second-computer LAN
check, full accessibility audit, and simultaneous multi-agent desktop proof
remain host-specific follow-up evidence.

Memory checkpoints are named snapshots of settings, saved connections, agent
lanes, and tab layout. A restore is recorded as a new revision. The version
snapshot is kept in an isolated Git repository inside the app's own data
directory, never inside a user's project folder; if Git is unavailable, the
checkpoint remains available as a snapshot-only record and the failure is shown
in its metadata.

## Suggested articles

- [Headless desktops](headless-desktops.md)
- [Trusted-LAN API](trusted-lan-api.md)
- [Subagent lanes](subagent-lanes.md)
- [Tab groups and bulk close](tab-management.md)
- [Memory checkpoints and local revisions](memory-checkpoints.md)
- [Electron file transfer](file-transfer.md)
- [Quiet processes](quiet-processes.md)
