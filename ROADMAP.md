# Roadmap

## Delivered in the current task

- [x] Multi-desktop creation/listing with project/agent naming.
- [x] Native C++ desktop ownership, quiet launch readiness, and resilient stdio supervision with a direct CLI fallback.
- [x] Hidden Windows child-process policy and background targeted hotkeys.
- [x] Automatic Python dependency repair and AutoHotkey installation from the GUI installer.
- [x] Trusted-LAN Streamable HTTP API with `/health` and explicit no-key consent warning.
- [x] Electron Material 3 manual client foundation with tabs, local history, settings,
  export, regex search, and headless workspace controls.
- [x] Inline Quick launch app browsing plus Tool runner file/folder path browsing.
- [x] Labeled Quick launch Browse control plus bounded Electron file send/receive with native save selection.
- [x] Complete local Git-history changelog, independent tab regex state, notification
  history, command palette tool catalog, and Squirrel.Windows packaging.
- [x] Persistent tab groups, searchable tab context menus, reviewable bulk close with
  optional regex, and public catalog-backed release code names.
- [x] Named local memory checkpoints for settings, connections, agent lanes, and tab
  layout, with Git-backed restore revisions.
- [x] Per-target appearance editing with typography spacing, color translation,
  built-in presets, user presets, reset, export, and renderer self-tests.
- [x] Direct CLI execution as the primary local tool route, with registered-tool-only
  discovery and no persistent MCP/HTTP process for ordinary calls.
- [x] Retired legacy HTTP/logon startup, migration of old client registrations, and
  explicit opt-in gating for compatibility startup.

## Evidence still required

- [ ] Windows runtime capture proving multiple simultaneous desktops, no active-desktop
  change, and no console windows across representative GUI and console children.
- [ ] A second-computer LAN MCP connection test and firewall verification.
- [ ] Full Electron packaging/installer is locally verified; accessibility audit,
  interactive native-dialog proof, and second-computer LAN verification remain.
- [ ] Expansion of advanced shared-memory UI requirements beyond the shipped client foundation.

## Shipped

- [x] Headless-first Windows and Linux GUI automation.
- [x] Background HWND/window targeting and per-window capture.
- [x] Console-free Windows child processes and quiet compatibility client registration;
  the former user HTTP startup is retired.
- [x] Default focus guards for foreground input, window activation, UAC, and desktop handoff.
- [x] Local bounded Python regex builder with guided and raw modes.

## Next

- [ ] Add authenticated non-loopback HTTP deployment guidance and tests.
- [ ] Expand Linux live verification across X11 compositors and Xvfb versions.

Items remain proposals until code, tests, and release artifacts are linked from
`HANDOFF.md`.
