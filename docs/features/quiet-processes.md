# Quiet processes and automatic hotkeys

## Behavior

Windows child processes started by the server and installer use hidden startup
information and `CREATE_NO_WINDOW`. Headless GUI children are attached to the
named Win32 desktop and never create a visible terminal or switch the user's
input desktop. Targeted `press_keys` accepts `hwnd` or `window_title`; it uses
AutoHotkey `ControlSend` when installed and falls back to Win32 messages without
focusing the target.

The GUI installer runs `uv sync`, installs AutoHotkey through `winget` when it
is missing, removes the retired HTTP registration, and removes any old logon
launcher. The Electron client repairs the Python environment in the background
on Windows startup and uses the Cheap Version for local tool calls.

## Failure modes

Raw-input applications may ignore Win32 messages. If AutoHotkey is unavailable,
the targeted operation remains available through the Win32 fallback; an
unqualified hotkey remains an intentionally foreground operation.

## Verification

`test_headless_multi_agent.py` verifies hotkey translation and the non-Windows
process policy. `test_cheap_entry.py` verifies that transport endpoints are not
accidentally exposed as cheap tools. Windows verification should additionally
inspect that a child launch does not change the active desktop or create a
console window.
