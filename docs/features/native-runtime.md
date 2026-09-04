# Native Windows runtime and resilient MCP transport

## Behavior

Windows installations include two small C++ components. The in-process DLL owns
named desktop handles, creates or reopens desktops idempotently, launches child
processes with `CREATE_NO_WINDOW`, and optionally waits for a GUI message queue
with `WaitForInputIdle`. The GUI-subsystem supervisor proxies MCP stdio without
changing protocol bytes and restarts an unexpectedly terminated Python child
with bounded exponential backoff while the client transport remains open.

The direct `lowlevel-computer-use-cheap` command remains independent of the
supervisor. It can invoke any registered tool without MCP or a listening server.

## Configuration

Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-native.ps1`
from the repository root. The script initializes the installed Visual Studio C++
environment, builds with CMake and Ninja, and copies the DLL and supervisor into
the Python package. The installer registers the supervisor when it is present and
falls back to `pythonw.exe` when it is absent.

`LOWLEVEL_WIN32_NATIVE_DLL` may point at a reviewed alternate DLL for development.
The DLL must report the expected ABI version before it is used.

## Failure modes

- A missing, unloadable, or ABI-incompatible DLL selects the existing Python
  implementation and reports the exact reason through `native_backend_status`.
- A supervisor child that terminates repeatedly is restarted at most five times
  in a rolling 60-second window. The supervisor then returns the child's exit code.
- Parent stdin EOF is forwarded to the child, allowing a normal MCP client shutdown.
- Invalid desktop names are rejected before a Win32 desktop is created or opened.

## Security

The native components do not add privileges or a sandbox. Launched commands still
run with the server user's permissions. The supervisor inherits only the stdio
handles needed for the MCP transport, uses no shell, creates no console window,
and does not write protocol payloads to logs or files.

## Verification

`tests/test_native_win32_bridge.py` checks the ABI loader, packaged paths,
console-free flags, exact stdio byte forwarding, direct CLI independence,
desktop create/reopen/launch/close behavior, and invalid-name refusal. The focused
Windows suite also confirms that multiple named desktops remain independent and
that console children do not create a terminal window.

## Suggested articles

- [Headless desktops](headless-desktops.md)
- [Quiet processes](quiet-processes.md)
- [Direct local CLI](cheap-version.md)
