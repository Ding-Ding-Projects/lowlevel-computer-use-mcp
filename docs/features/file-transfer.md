# Electron file transfer

## Behavior

The Electron Tool runner exposes a **Send and receive files** card for the
selected local process or saved LAN computer. Sending reads a user-selected
local file and calls the existing `upload_file` tool. Receiving calls
`download_file`, then opens a native Save dialog so the returned bytes are
written only where the user chooses. Both directions use the same target
connection selector as the rest of the runner.

Transfers are limited to 50 MiB. The UI reports encoding, transfer failure,
cancelled saves, and the final local path without claiming success for a
partial operation.

## Configuration

Choose a file with the native file input, enter the destination path on the
computer, and select **Send file**. For a receive, enter the source path on the
computer and select **Receive file**. The native save dialog's suggested name
comes from the source basename.

## Failure modes

Missing paths, files over 50 MiB, malformed tool responses, cancelled saves,
and tool errors remain visible in the status line and notification history.
Base64 payloads are validated and bounded in the Electron main process before
bytes are written.

## Security

The feature does not add a second transport or a hidden filesystem writer. It
uses the existing explicit tool route and saved trusted-LAN connection. Local
receives require a user-initiated Save dialog; the renderer cannot choose an
arbitrary output path through Node APIs.

## Verification

`npm run check --prefix electron` covers the IPC and renderer wiring, while the
off-screen Electron capture covers the visible runner surface. Python tool
tests cover the underlying bounded `upload_file` and `download_file` routes.
An end-to-end second-computer transfer remains host-specific evidence.

## Suggested articles

- [Trusted-LAN API](trusted-lan-api.md)
- [Electron manual client](electron-manual-client.md)
- [Quick launch and path browsers](quick-launch-browser.md)
