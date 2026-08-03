# Handoff

The pulled `main` checkout now contains multi-agent headless desktop APIs,
quiet child-process launch helpers, automatic AutoHotkey installation in the GUI
installer, a trusted-LAN Streamable HTTP API with command/file transfer routes,
and an Electron Material 3 manual client under `electron/`. The client can host
or schedule the API, save named remote computers, and route later tool calls to
one of those saved connections.

The untracked `Tools/Windows 11.iso` file was pre-existing user data and was
preserved without inspection or staging. The next verification pass should run
the Windows-only headless desktop tests and a second-computer LAN check. Static
Python compilation and model tests do not prove those runtime boundaries.

## Current task: console-free, headless-first, focus-safe operation

Implemented in the working tree:

- Central Windows hidden-process policy (`CREATE_NO_WINDOW` + `SW_HIDE`).
- `pythonw.exe` registration for Claude, Codex, and OpenCode.
- UTF-16 per-user Startup launcher for the local HTTP MCP; elevated task is opt-in.
- Default focus guards on all foreground-affecting MCP paths.
- Win32 headless launch no longer requests a new console.
- Bounded local Python `re` builder and categorized feature/API documentation.

Verification so far:

- Full local suite: 27 tests passed on Windows with one expected non-Windows branch
  skipped; `compileall`, `uv build`, and `git diff --check` passed.
- Live off-screen GUI probe preserved the foreground HWND.
- Live `pythonw.exe` HTTP startup bound port 8765, owned zero top-level windows,
  and preserved the foreground HWND.
- Claude, Codex, OpenCode stdio registrations and OpenCode boot HTTP status were
  observed connected.
- Streamable HTTP initialize returned 200 with a session ID, initialized returned
  202, and tools/list returned 200.
- GitHub Discussions and wiki support were enabled; rolling progress is Discussion #1.
- GitHub Project access is externally blocked because the configured owner token
  lacks `read:project`/`project`; no focus-stealing browser authorization was opened.

## Remote handoff

- This file ships in the integration commit. Discussion #1 is the rolling source
  for its exact pushed hash, Actions run, release, Pages, and wiki evidence.
- The final pre-push issue rescan found zero open issues.
- Remote CI/release state is intentionally not predicted in this commit; the
  Discussion records it as running, failed, or verified after the push.
- The sole pre-existing stash contains hydrated ISO/Docker binaries and is unrelated
  to this task. It is retained because deleting or integrating it without owner
  context would risk data loss.
