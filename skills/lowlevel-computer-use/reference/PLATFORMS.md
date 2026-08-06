# PLATFORMS.md — Platform specifics, availability & gotchas

## Availability matrix

| Capability | Windows | Linux |
|-----------|---------|-------|
| Mouse, keyboard, scroll, drag | ✅ pyautogui | ✅ pyautogui (X11) |
| `run_command` | ✅ | ✅ |
| Processes (list/kill) | ✅ psutil | ✅ psutil |
| Screenshots (monitor/region) | ✅ mss | ✅ mss (X11) |
| Screen recording (mp4) | ✅ | ✅ (needs working DISPLAY) |
| Crop images | ✅ | ✅ |
| Window mgmt (list/move/resize/action) | ✅ pygetwindow | ✅ xdotool/wmctrl |
| Show/hide window | ✅ ShowWindow | ✅ xdotool map/unmap |
| Background click/type/keys | ✅ PostMessage/WM_CHAR | ✅ xdotool XSendEvent |
| Per-window capture | ✅ PrintWindow | ✅ ImageMagick `import` |
| Headless-with-GUI | ✅ off-screen desktop | ✅ Xvfb virtual display |
| Show-for-login | ✅ window + SwitchDesktop | ✅ window (Xvfb has no live view) |
| AutoHotkey | ✅ | ❌ |
| Ephemeral WSL | ✅ (Windows host) | ❌ |
| Run-as-admin / boot startup | ✅ | ❌ |

Check at runtime: `linux_status`, `ahk_status`, `wsl_status`. On Windows the
`hwnd` is an HWND; on Linux it is an X11 window id.

## Windows notes

- **Background input** uses `PostMessage` (clicks to the deepest child control at a
  point) and `WM_CHAR`/`WM_SETTEXT`. Some apps that read raw input or check physical
  key state (`GetAsyncKeyState`) ignore these — use `win_set_control_text`, AutoHotkey
  `ahk_control_send`, or report the limitation. Do not focus it while the user is active.
- **PrintWindow** capture (`screenshot {hwnd}`) works on most GDI/Chromium/DWM windows
  with full-content rendering, even occluded or minimized; a few GPU-exclusive
  surfaces render black — fall back to a region `screenshot`.
- **Headless desktop** = a separate Win32 desktop in the same window station. Apps
  there have a real GUI but never appear on the visible desktop. `show_headless_desktop`
  uses `SwitchDesktop` to make the whole desktop interactive (e.g. for a login), then
  `hide_headless_desktop` switches back.
- **No-window policy**: Windows subprocesses use `CREATE_NO_WINDOW` plus `SW_HIDE`;
  compatibility client registration uses `pythonw.exe`; the retired user startup is
  not installed. Foreground calls require
  explicit `confirm_focus_disruption:true`.
- **AutoHotkey**: install with `winget install -e --id AutoHotkey.AutoHotkey`. The
  server auto-detects it (PATH / common dirs / `LOWLEVEL_CU_AHK`). Generated helpers
  target AHK v2; `run_ahk` runs whatever interpreter is found.
- **WSL**: `wsl_create_temp` downloads the latest Alpine minirootfs (a few MB) and
  imports it — existing distros are untouched. Always `wsl_destroy` when done.
- **Run-as-admin**: `run_command_as_admin` triggers a UAC prompt unless the server is
  already elevated. `is_admin` reports current state.

## Linux notes

- Requires an **X11** session (or XWayland). Install the helpers:
  `sudo apt install xdotool wmctrl x11-utils imagemagick xvfb` (Debian/Ubuntu) or the
  equivalent (`dnf`, `pacman`). `pyautogui` also needs `python3-xlib` + a screenshot
  backend for foreground mouse/keyboard.
- **Background typing** uses `XSendEvent`; most GTK/Qt apps accept it. Notable
  exception: `xterm` with its default `allowSendEvents: false` ignores synthetic
  events (launch it with `-xrm 'XTerm.vt100.allowSendEvents: true'` to allow, or
  report the limitation rather than stealing focus).
- **Xvfb virtual display** is the Linux headless mode. To DRIVE windows on it, pass the
  `display` field to `mouse_click` / `type_text` / `win_send_keys` / `screenshot` so
  input is routed to that X display; otherwise the default `:0` is used and the window
  won't be found.
- **Pure Wayland** windows (not XWayland) are not controllable — no portable API
  exists. `linux_status` reports `session_type`.
- `window_action maximize` needs `wmctrl`.

## Resource hygiene

- Pair every **create** with a **destroy/stop/close**:
  `create_headless_desktop`→`close_headless_desktop`,
  `create_virtual_display`→`stop_virtual_display`,
  `wsl_create_temp`→`wsl_destroy`, `start_screen_recording`→`stop_screen_recording`.
- An `--http` server (e.g. the boot service) keeps running until explicitly stopped.

## Capture output location

Screenshots and recordings default to `~/lowlevel-computer-use-captures`. Override
with the `LOWLEVEL_CU_CAPTURE_DIR` environment variable. Tools also accept an explicit
`output_path`.
