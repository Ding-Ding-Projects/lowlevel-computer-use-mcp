# TOOLS.md — Exhaustive tool reference (all 53)

Every tool returns a JSON string. Common shape: `{"ok": true, ...}` or
`{"ok": false, "error": "..."}`. `*` marks required parameters. Platform column:
**X** = cross-platform, **W** = Windows-only, **L** = Linux-only.

---

## Mouse & keyboard (X)

### `get_screen_size` (X)
No params. → `{ok, width, height}` — primary screen resolution.

### `get_cursor_position` (X)
No params. → `{ok, x, y}` — current cursor position (screen pixels).

### `mouse_move` (X)
- `*x` int ≥0, `*y` int ≥0 — target screen coordinate.
- `confirm_focus_disruption` bool (default false) — required after explicit user consent.
- `duration` float 0–10 (default 0) — seconds to animate; `0` uses the visible smooth default.
- `instant` bool (default false) — set true only when you intentionally want a jump.
→ `{ok, x, y, duration}`.

### `mouse_click` (X)
- `x`, `y` int — click location (screen px in foreground mode; **omit to click at
  the current cursor**). In background mode these are **client** coords of the target.
- `button` `"left"|"right"|"middle"` (default left).
- `clicks` int 1–5 (default 1; 2 = double-click).
- `interval` float (default 0) — seconds between clicks.
- `move_duration` float 0–10 (default 0) — foreground only; `0` uses the visible smooth default before clicking.
- `instant_move` bool (default false) — foreground only; jump to `x`/`y` before clicking.
- `hwnd` int — **BACKGROUND TARGET**: post the click to this window without focusing it.
- `window_title` str — background target by title substring (if `hwnd` omitted).
- `display` int — *Linux only*: X display number of the target (e.g. Xvfb 99).
→ foreground: `{ok, button, clicks, x, y}`; background: `{ok, mode:"background", window_hwnd, target_hwnd, client_x, client_y, ...}`.
Background click requires explicit `x`/`y`.

### `mouse_drag` (X)
- `start_x`, `start_y` int — omit to start at current cursor.
- `*end_x`, `*end_y` int — release point.
- `button` (default left), `duration` float 0–10 (default 0.25).
→ `{ok, end_x, end_y, button}`.

### `mouse_scroll` (X)
- `*amount` int — positive = up, negative = down (wheel clicks).
- `x`, `y` int — move here before scrolling.
- `move_duration` float 0–10 (default 0) — `0` uses the visible smooth default.
- `instant_move` bool (default false) — jump to `x`/`y` before scrolling.
→ `{ok, scrolled}`.

### `type_text` (X)
- `*text` str — text to type.
- `interval` float 0–2 (default 0) — seconds between keystrokes.
- `hwnd` / `window_title` — **BACKGROUND TARGET**: send WM_CHAR (Win) / XSendEvent
  (Linux) to that window's focused control without focusing it.
- `display` int — *Linux only*.
→ `{ok, typed_chars}` or background `{ok, mode:"background", window_hwnd, chars}`.
For reliable background text entry into an edit control, prefer `win_set_control_text`.

### `press_keys` (X)
- `*keys` list[str], 1–6 — pyautogui key names. One element = single key; multiple =
  combo pressed together. Examples: `["enter"]`, `["ctrl","c"]`, `["win","d"]`,
  `["alt","tab"]`, `["f5"]`.
→ `{ok, keys}`.

---

## Shell (X)

### `run_command` (X, destructive)
- `*command` str — command line.
- `shell` bool (default true) — run via system shell; if false, `command` is split argv.
- `cwd` str — working directory.
- `timeout` float 1–3600 (default 60).
→ `{ok, returncode, stdout, stderr, timed_out}`.

---

## Window management (X)

### `list_windows` (X)
- `title_filter` str — only windows whose title contains this (case-insensitive).
- `include_empty_titles` bool (default false).
→ `{ok, count, windows:[{title, handle, left, top, width, height, is_minimized,
   is_maximized, is_active}]}`. `handle` is the HWND (Windows) / X11 window id (Linux).

### `get_active_window` (X)
No params. → `{ok, window:{...}|null}`.

### `move_window` (X)
- `*x`, `*y` int — new top-left position.
- `title` str (substring) **or** `handle` int — identify the window (handle preferred).
- `display` int — *Linux only*.
→ `{ok, window:{...}}`.

### `resize_window` (X)
- `*width` int ≥1, `*height` int ≥1.
- `title`/`handle`, `display` (Linux).
→ `{ok, window:{...}}`.

### `window_action` (X, destructive for close)
- `*action` `"focus"|"minimize"|"maximize"|"restore"|"close"`.
- `title`/`handle`, `display` (Linux). (Linux `maximize` needs wmctrl.)
→ `{ok, action, window:{...}}` (or `{ok, action, closed:true}`).

### `show_window` (X)
- `hwnd`/`window_title`, `display` (Linux).
- `confirm_focus_disruption` bool (default false) — required.
- Restores + shows + foregrounds a hidden/minimized window. Use before an
  interactive **login**. → `{ok, hwnd, visible:true}`.

### `hide_window` (X)
- `hwnd`/`window_title`, `display` (Linux).
- `minimize` bool (default false) — minimize instead of fully hiding (SW_HIDE removes
  it from the taskbar). → `{ok, hwnd, visible:false, minimized}`.

---

## Background / unfocused targeting

### `list_child_windows` (X)
- `hwnd`/`window_title`, `display` (Linux).
- Enumerate child controls (Windows: real controls; Linux: child X windows).
→ `{ok, parent_hwnd, count, children:[{handle, class, text, left, top, width, height,
   visible}]}`. Coords are relative to the parent's top-left.

### `win_set_control_text` (X)
- `*text` str.
- `hwnd` (the control, preferred) / `window_title`, `display` (Linux).
- Windows: WM_SETTEXT (most reliable for edit controls, no focus). Linux: select-all +
  delete + type into the window. → `{ok, target_hwnd, text_len}`.

### `win_send_keys` (X)
- `*keys` list[str] 1–6 — e.g. `["enter"]`, `["ctrl","a"]`.
- `hwnd`/`window_title`, `display` (Linux).
- Posts keys to the window without focusing it. **Modifier combos are unreliable**
  via messages; prefer `win_set_control_text` for text. → `{ok, window_hwnd, keys}`.

---

## Processes (X)

### `list_processes` (X)
- `name_filter` str — substring (case-insensitive).
- `sort_by` `"memory"|"cpu"|"name"|"pid"` (default memory).
- `limit` int 1–1000 (default 50).
→ `{ok, count, processes:[{pid, name, username, memory_mb, cpu_percent}]}`.

### `kill_process` (X, destructive)
- `pid` int **or** `name` str (kills ALL by exact name; case-insensitive).
- `force` bool (default false) — hard kill vs graceful terminate.
→ `{ok, killed:[{pid, name}], count, errors?}`.

---

## Screenshots & images

### `screenshot` (X)
- `monitor` int (default 0) — 0 = all monitors combined, 1 = primary, 2 = secondary…
- `region` [left, top, width, height] — capture a pixel region (overrides monitor).
- `output_path` str — PNG path (auto-generated if omitted).
- `hwnd`/`window_title` — **BACKGROUND CAPTURE** of one window (Windows PrintWindow /
  Linux ImageMagick) even if occluded/minimized/off-screen.
- `client_only` bool (default false) — window capture without title bar/borders.
- `display` int — *Linux only*: X display of the target window.
→ `{ok, path, width, height}` (window mode adds `mode:"window", window_hwnd, rendered_ok`).

### `crop_image` (X)
- `*input_path` str, `*left`, `*top` int ≥0, `*width`, `*height` int ≥1.
- `output_path` str. → `{ok, path, width, height}`.

---

## Screen recording (X)

### `start_screen_recording` (X)
- `fps` int 1–60 (default 15), `monitor` int ≥1 (default 1).
- `region` [left, top, width, height] — record a region instead of a monitor.
- `output_path` str — mp4 path. Only one recording at a time.
→ `{ok, path, fps, monitor, recording:true}`.

### `stop_screen_recording` (X)
No params. → `{ok, path, frames, duration_seconds}`.

### `recording_status` (X)
No params. → `{ok, recording, path, frames, elapsed_seconds}`.

---

## Headless desktop — Windows (W)

### `create_headless_desktop` (W)
- `name` str (default "LowLevelCUHeadless"). → `{ok, name, handle, full}`.

### `launch_on_headless_desktop` (W, destructive)
- `name` str, `*command` str. → `{ok, desktop, pid, command}`.

### `list_headless_windows` (W)
- `name` str. → `{ok, name, count, windows:[{handle, process_id, thread_id, dpi, title, class, width, height}]}`.
- Identity and DPI are sampled during desktop enumeration. Unavailable values are
  returned as `0`; the window remains in the list.

### `close_headless_desktop` (W, destructive)
- `name` str. Close apps on it first. → `{ok, name, closed}`.

### `show_headless_desktop` (W)
- `name` str, `instruction` str (default "Complete the requested manual step.") — switch
  the live screen TO this off-screen desktop (for an interactive login). A topmost,
  non-dismissible banner shows the instruction and an EMERGENCY EXIT button that
  restores the normal desktop. → `{ok, name, visible:true, safety_banner:true, note}`.
- `confirm_focus_disruption` bool (default false) — required after explicit approval.

### `hide_headless_desktop` (W)
- `name` str — switch the live screen back to the normal desktop. → `{ok, restored:true}`.

---

## Headless / virtual display — Linux (L)

### `linux_status` (L)
No params. → `{ok, display, session_type, xdotool, wmctrl, xvfb, imagemagick_import, scrot}`.

### `create_virtual_display` (L)
- `display` int 1–9999 (default 99), `width` (default 1280), `height` (default 800),
  `depth` (default 24). Starts Xvfb. → `{ok, display:":99", size, pid}`.

### `launch_on_virtual_display` (L, destructive)
- `display` int (default 99), `*command` str. → `{ok, display, pid, command}`.

### `list_virtual_display_windows` (L)
- `display` int (default 99). → `{ok, display, count, windows:[...]}`.

### `screenshot_virtual_display` (L)
- `display` int (default 99), `output_path` str. → `{ok, path, width, height, display}`.

### `stop_virtual_display` (L, destructive)
- `display` int (default 99). Terminates apps + Xvfb. → `{ok, display, stopped}`.

> To DRIVE a window on a virtual display, pass `display` to `mouse_click` /
> `type_text` / `screenshot` / `win_send_keys` etc. so input is routed there.

---

## AutoHotkey (W)

### `ahk_status` (W)
No params. → `{ok, installed, path?, version?, hint?}`. Set `LOWLEVEL_CU_AHK` to point
at a specific interpreter.

### `run_ahk` (W, destructive)
- `*code` str — AHK script; **must call ExitApp** or be non-persistent.
- `args` list[str], `timeout` float 1–3600 (default 60), `exe_path` str.
- Emit output with `FileAppend ..., "*"`. → `{ok, returncode, stdout, stderr, exe}`.

### `ahk_control_send` (W)
- `*text` str, `*window` str (AHK target: `"ahk_id <hwnd>"`, `"ahk_exe notepad.exe"`,
  or a title), `control` str (blank = focused control), `as_keys` bool (interpret as
  key syntax like `^a{Del}`), `timeout` float. Reliable background input. → AHK result.

---

## Ephemeral WSL (W)

### `wsl_status` (W)
No params. → `{ok, available, version?, status?, reason?}`.

### `wsl_list_distros` (W)
No params. → `{ok, count, distros:[{name, state, version, default}]}`.

### `wsl_create_temp` (W)
- `name` str (auto if omitted), `rootfs_url` str (defaults to latest Alpine minirootfs),
  `clone_from` str (clone an existing distro), `base_tar` str (local .tar/.tar.gz),
  `timeout` float 10–7200 (default 1800). → `{ok, name, install_dir, source, version}`.

### `wsl_run` (W, destructive)
- `*distro` str, `*command` str, `user` str, `cwd` str, `timeout` float 1–3600.
→ `{ok, distro, returncode, stdout, stderr}`.

### `wsl_list_temp` (W)
No params. → `{ok, count, distros:[{name, install_dir, source, created_at}]}`.

### `wsl_destroy` (W, destructive — irreversible)
- `*name` str, `remove_files` bool (default true). → `{ok, name, destroyed:true}`.

### `wsl_destroy_all_temp` (W, destructive)
No params. Tears down every throwaway distro this session created. → `{ok, destroyed, count}`.

---

## Run-as-admin & retired startup compatibility (W)

### `is_admin` (W)
No params. → `{ok, is_admin, platform}`.

### `run_command_as_admin` (W, destructive)
- `*command` str, `timeout` float 1–3600 (default 120). Triggers UAC if not elevated.
→ `{ok, returncode, output, elevated_prompt}`.

### `install_startup` (W, destructive, retired)
- The default call refuses to install a launcher. This prevents a stale client from
  recreating the old persistent HTTP/logon path.
- Use the CLI command `lowlevel-computer-use-mcp install-startup --legacy-http`
  only for an existing compatibility client that cannot migrate yet.
  → `{ok:false, returncode:2, output}` for the normal tool call.

### `uninstall_startup` (W, destructive)
No params. Removes any retired user startup; removing an elevated task requires an
already elevated server and otherwise returns a permission error. → `{ok, task_name, output}`.

### `startup_status` (W)
No params. → `{ok, installed, details, task_name}`.
