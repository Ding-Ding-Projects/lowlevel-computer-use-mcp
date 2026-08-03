# Console-free, headless-first execution

## Behavior

Windows child processes are launched with `CREATE_NO_WINDOW` and a `STARTUPINFO`
request for `SW_HIDE`. GUI automation starts on an off-screen Win32 desktop; Linux
automation starts on Xvfb. Windows stdio clients and the boot HTTP service invoke
the server through `pythonw.exe`.

Foreground pointer, keyboard, window-action, window-reveal, UAC, and desktop-switch
operations are blocked unless `confirm_focus_disruption=true`. That confirmation
is valid only after the user explicitly requests an interactive handoff. On Linux,
background clicking is focus-safe only when an Xvfb `display` is supplied.

## Configuration

- `install-startup` creates a UTF-16 VBS launcher in the current user's Startup
  folder and starts `pythonw.exe -m lowlevel_computer_use_mcp.server --http`.
- `install-startup --admin-task` opts into an elevated Scheduled Task and UAC.
- The default endpoint is `http://127.0.0.1:8765/mcp`.
- Claude, Codex, and OpenCode registrations should use the active environment's
  `pythonw.exe`, not `uv.exe` or a console-script `.exe`.

## Failure modes

- If `pythonw.exe` is unavailable, installation fails closed instead of falling
  back to a console executable.
- Applications using raw input may reject background messages. Report that
  limitation instead of activating their visible window.
- A user-approved UAC prompt or desktop reveal necessarily interrupts focus; the
  default guards prevent accidental use.
- Windows Script Host requires the startup script's UTF-16 BOM. UTF-8 scripts may
  return status 1 without useful diagnostics.

## Security

The HTTP server binds to localhost by default and has no application-layer
authentication. Do not expose it to another interface without an authenticated
reverse proxy and explicit network review. Patterns, samples, screenshots, and
command output remain local unless another tool explicitly sends them elsewhere.

## Verification

`tests/test_focus_and_process_safety.py` checks process flags, protected tools,
startup generation, and headless-first MCP instructions. Live Windows verification
records the foreground HWND before and after launching a real off-screen GUI and
the `pythonw.exe` HTTP service, checks that the handle is unchanged, and enumerates
zero top-level windows for the server process.
