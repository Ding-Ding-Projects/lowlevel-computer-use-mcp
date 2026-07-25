---
name: lowlevel-computer-use
description: Drive the desktop with the lowlevel-computer-use MCP server — mouse, keyboard, shell, window management, processes, screenshots, cropping, screen recording, BACKGROUND/unfocused window targeting (no focus stealing), headless-with-GUI (Windows off-screen desktop / Linux Xvfb), show-for-login, AutoHotkey, ephemeral WSL Linux boxes, run-as-admin, and boot auto-start. Use whenever a task involves clicking/typing/automating a Windows or Linux GUI app, capturing or recording the screen, controlling a window without focusing it, running an app invisibly, killing/inspecting processes, running shell or Linux/WSL commands, or building a reusable desktop macro. Works on Windows and Linux.
---

# Low-Level Computer-Use — Full Feature Guide

This skill teaches you to use **every** tool of the `lowlevel-computer-use` MCP
server (tools appear as `mcp__lowlevel-computer-use__<tool>` or just `<tool>`).
There are **53 tools**. Each returns a JSON string: `{"ok": true, ...}` on success
or `{"ok": false, "error": "..."}` on failure — always read `ok`.

> ⚠️ Every tool performs **real, unsandboxed** actions on the host (clicking,
> typing, killing processes, elevated and Linux commands). Be deliberate.

## When to use this skill

Use it for any of: clicking/typing into a GUI app; controlling a window **without
focusing it**; capturing a screenshot or a single window; cropping; **recording**
the screen; **moving/resizing/closing** windows; **killing or listing** processes;
running **shell** or **elevated** commands; running an app **invisibly** (headless);
bringing a hidden app forward for a **login** then hiding it; **AutoHotkey** scripts;
spinning up a **throwaway WSL Linux** box; **auto-starting** the server on boot; or
saving a repeated UI sequence as a **macro skill**.

## Golden rules (read first)

1. **Look before you act.** Take a `screenshot` (or `screenshot` of the target
   window) to see current state before clicking/typing blind.
2. **Resolve handles at run time.** Window handles/ids change every launch. Always
   `list_windows` → `list_child_windows` to find the current `hwnd`; never hard-code.
3. **Prefer background targeting** (`hwnd`/`window_title` on click/type/screenshot,
   plus `win_set_control_text`) so you don't steal the user's focus.
4. **Coordinates:** foreground mouse tools use **screen** pixels; background clicks
   use **client** coordinates of the target window.
5. **Verify after acting.** Re-`screenshot` the window and confirm the change.
6. **Save repeated sequences as macros** — see "Macros as skills" below.
7. **Cross-platform:** the same tools work on Windows and Linux; on Linux `hwnd` is
   an X11 window id and you may pass a `display` to target an Xvfb virtual display.

## Tool map (all 53)

Detailed per-tool parameters: see [reference/TOOLS.md](reference/TOOLS.md).
Recipes and end-to-end flows: see [reference/WORKFLOWS.md](reference/WORKFLOWS.md).
Platform specifics and gotchas: see [reference/PLATFORMS.md](reference/PLATFORMS.md).

**Mouse & keyboard (cross-platform):** `get_screen_size`, `get_cursor_position`,
`mouse_move`, `mouse_click`, `mouse_drag`, `mouse_scroll`, `type_text`, `press_keys`.

**Shell:** `run_command` (capture stdout/stderr/exit code, timeout).

**Windows (cross-platform):** `list_windows`, `get_active_window`, `move_window`,
`resize_window`, `window_action` (focus/minimize/maximize/restore/close),
`show_window`, `hide_window`.

**Background / unfocused targeting:** `mouse_click`/`type_text`/`screenshot` with
`hwnd` or `window_title`; `list_child_windows`, `win_set_control_text`,
`win_send_keys`.

**Processes:** `list_processes`, `kill_process`.

**Screenshots & images:** `screenshot` (monitor / region / single window),
`crop_image`.

**Recording:** `start_screen_recording`, `stop_screen_recording`, `recording_status`.

**Headless-with-GUI (Windows off-screen desktop):** `create_headless_desktop`,
`launch_on_headless_desktop`, `list_headless_windows`, `close_headless_desktop`,
`show_headless_desktop`, `hide_headless_desktop`.

**Headless-with-GUI (Linux Xvfb):** `linux_status`, `create_virtual_display`,
`launch_on_virtual_display`, `list_virtual_display_windows`,
`screenshot_virtual_display`, `stop_virtual_display`.

**AutoHotkey (Windows):** `ahk_status`, `run_ahk`, `ahk_control_send`.

**Ephemeral WSL (Windows host):** `wsl_status`, `wsl_list_distros`,
`wsl_create_temp`, `wsl_run`, `wsl_list_temp`, `wsl_destroy`, `wsl_destroy_all_temp`.

**Run-as-admin & boot:** `is_admin`, `run_command_as_admin`, `install_startup`,
`uninstall_startup`, `startup_status`.

## Five core patterns (quick)

**A. Foreground automation (simple).** `screenshot` → `mouse_click {x,y}` →
`type_text {text}` → `press_keys {keys:["ctrl","s"]}` → `screenshot` to verify.

**B. Background automation (no focus stealing).**
`list_windows {title_filter}` → `list_child_windows {window_title}` → pick the
control handle → `win_set_control_text {hwnd, text}` (or `mouse_click {hwnd, x, y}`
with client coords) → `screenshot {window_title}` to verify.

**C. Headless app (invisible).** Windows: `create_headless_desktop {name}` →
`launch_on_headless_desktop {name, command}` → `list_headless_windows {name}` →
drive via background tools + `screenshot {hwnd}`. Linux: `create_virtual_display
{display}` → `launch_on_virtual_display {display, command}` →
`list_virtual_display_windows {display}` → background tools with `display` set →
`screenshot_virtual_display {display}`.

**D. Show for login, then hide.** When automation hits a human-only login: Windows
window → `show_window {window_title}`; whole headless desktop →
`show_headless_desktop {name, instruction}`. Supply a short, concrete instruction
for the non-dismissible top banner; its EMERGENCY EXIT button returns the user to
the normal desktop. After the user signs in → `hide_window` /
`hide_headless_desktop`.

**E. Throwaway Linux box (Windows host).** `wsl_create_temp {}` →
`wsl_run {distro, command}` → `wsl_destroy {name}`.

## Macros as skills (IMPORTANT)

When you perform a multi-step UI sequence the user is likely to repeat, **capture it
as a reusable macro Skill** instead of leaving ad-hoc tool calls. Follow
[../../macros/MACRO_SKILL_TEMPLATE.md](../../macros/MACRO_SKILL_TEMPLATE.md):
name the goal, list the ordered tool calls, **resolve handles at run time** (never
hard-code), prefer background tools, parameterize what varies (text/file/app), and
verify with a screenshot.

## Safety & gotchas (must know)

- `run_command`, `run_command_as_admin`, `kill_process`, `run_ahk`,
  `window_action(close)`, `wsl_destroy`, and the launch/startup tools are
  **destructive or system-modifying** — confirm intent.
- **Background input limits:** Windows `PostMessage`/`WM_CHAR` and Linux
  `XSendEvent` are ignored by some apps (raw input / DirectInput / physical key-state
  checks; `xterm` with `allowSendEvents:false`). For those, use `win_set_control_text`
  / AHK `ControlSend` (Windows), or focus the window first.
- **PrintWindow** (Windows per-window capture) renders black on a few
  GPU-exclusive surfaces; fall back to a region `screenshot`.
- `pyautogui` fail-safe is **disabled** — moving the mouse to a corner won't abort.
- WSL and AHK tools are **Windows-only**; X11/Xvfb tools are **Linux-only**. Use
  `wsl_status` / `ahk_status` / `linux_status` to check availability first.
- Always pair headless/WSL **create** with **destroy/stop/close** to free resources.

## Cheap Version (no-MCP fallback)

If the MCP connection keeps failing, every tool can be run directly from the command
line — this is called the **Cheap Version**. It runs the same tool function and prints
the same JSON, with no MCP client/transport involved:

```bash
lowlevel-computer-use-cheap <tool> [--key value ...] [--json '{...}']
# e.g.
lowlevel-computer-use-cheap screenshot --monitor 1
lowlevel-computer-use-cheap mouse_click --x 960 --y 540 --clicks 2
lowlevel-computer-use-cheap press_keys --keys '["ctrl","s"]'
lowlevel-computer-use-cheap --list      # list all tools
```

You can run these via the `run_command` tool, the Bash tool, or a terminal. Every
parameter in [reference/TOOLS.md](reference/TOOLS.md) is accepted as `--<param> <value>`
(values are parsed as JSON when possible) or via `--json`.

Read [reference/TOOLS.md](reference/TOOLS.md) for the exact parameters of every tool
before composing a non-trivial automation.
