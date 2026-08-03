# Quick launch and path browsers

## Behavior

The Workspaces Quick launch card has an inline application browser beside its
command field. Selecting an executable, command script, or compatible launcher
places its path into the real hidden-desktop launch field. The Tool runner also
offers file and folder browsers that write a selected path into the JSON
parameters object without requiring manual escaping.

## Configuration

The Electron main process owns the native picker through an IPC handler. The
renderer receives only the selected path; Node integration remains disabled and
the picker never executes the selected file by itself.

## Failure modes

Canceling a picker leaves the existing field unchanged. An unavailable or
invalid path is reported by the ordinary launch/tool result, not treated as a
successful selection.

## Security

Browsing is user-triggered. The chosen path is passed to the existing hidden
desktop or tool route, which retains its normal process, focus, and trusted-LAN
privilege boundaries.

## Verification

The real off-screen Workspaces capture shows the inline button. Electron source
contract checks cover the picker IPC wiring, and the Python suite covers the
hidden launch primitive. A full interactive native-dialog accessibility check
remains Windows-host evidence.

## Suggested articles

- [Electron Material 3 manual client](electron-manual-client.md)
- [Headless desktops](headless-desktops.md)
- [Quiet processes](quiet-processes.md)
