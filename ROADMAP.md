# Roadmap

## Delivered in the current task

- Multi-desktop creation/listing with project/agent naming.
- Hidden Windows child-process policy and background targeted hotkeys.
- Automatic Python dependency repair and AutoHotkey installation from the GUI installer.
- Trusted-LAN Streamable HTTP API with `/health` and explicit no-key consent warning.
- Electron Material 3 manual client foundation with tabs, local history, settings,
  export, regex search, and headless workspace controls.
- Inline Quick launch app browsing plus Tool runner file/folder path browsing.
- Labeled Quick launch Browse control plus bounded Electron file send/receive with native save selection.
- Complete local Git-history changelog, independent tab regex state, notification
  history, command palette tool catalog, and Squirrel.Windows packaging.
- Persistent tab groups, searchable tab context menus, reviewable bulk close with
  optional regex, and public catalog-backed release code names.
- Named local memory checkpoints for settings, connections, agent lanes, and tab
  layout, with Git-backed restore revisions.
- Per-target appearance editing with typography spacing, color translation,
  built-in presets, user presets, reset, export, and renderer self-tests.

## Evidence still required

- Windows runtime capture proving multiple simultaneous desktops, no active-desktop
  change, and no console windows across representative GUI and console children.
- A second-computer LAN MCP connection test and firewall verification.
- Full Electron packaging/installer is locally verified; accessibility audit,
  interactive native-dialog proof, and second-computer LAN verification remain.
- Expansion of advanced shared-memory UI requirements beyond the shipped client foundation.

## Shipped

- Headless-first Windows and Linux GUI automation.
- Background HWND/window targeting and per-window capture.
- Console-free Windows child processes, client registration, and user startup.
- Default focus guards for foreground input, window activation, UAC, and desktop handoff.
- Local bounded Python regex builder with guided and raw modes.

## Next

- Add a packaged Windows installer so startup does not depend on a mutable checkout.
- Add authenticated non-loopback HTTP deployment guidance and tests.
- Expand Linux live verification across X11 compositors and Xvfb versions.

Items remain proposals until code, tests, and release artifacts are linked from
`HANDOFF.md`.
