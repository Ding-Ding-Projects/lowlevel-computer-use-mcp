# WORKFLOWS.md — End-to-end recipes

Concrete, copy-adaptable sequences. JSON shown is each tool's input. Always read the
returned `ok` and verify with a screenshot.

---

## 1. Simple foreground automation

```jsonc
screenshot { "monitor": 1 }                 // see the screen
mouse_click { "x": 960, "y": 540 }          // click a control
type_text { "text": "hello world" }         // type into the focused field
press_keys { "keys": ["ctrl", "s"] }        // save
screenshot { "monitor": 1 }                 // verify
```

## 2. Background automation (no focus stealing) — Notepad example

```jsonc
list_windows { "title_filter": "Notepad" }                 // get the window handle
list_child_windows { "window_title": "Notepad" }           // find the Edit control
win_set_control_text { "hwnd": 23924320, "text": "typed in the background" }
screenshot { "window_title": "Notepad" }                   // capture without focusing
```

For a background click (client coords of the window):

```jsonc
mouse_click { "window_title": "Notepad", "x": 200, "y": 120 }
```

For background keys into the focused control:

```jsonc
win_send_keys { "window_title": "Notepad", "keys": ["ctrl", "end"] }
```

## 3. Windows headless-with-GUI (off-screen desktop)

```jsonc
create_headless_desktop { "name": "work" }
launch_on_headless_desktop { "name": "work", "command": "notepad.exe" }
list_headless_windows { "name": "work" }                   // get handles
// drive it with background tools using the handle:
win_set_control_text { "hwnd": 2495156, "text": "running invisibly" }
screenshot { "hwnd": 2495156 }                             // capture the off-screen window
close_headless_desktop { "name": "work" }                  // (kill the app first)
```

## 4. Linux headless-with-GUI (Xvfb)

```jsonc
linux_status {}
create_virtual_display { "display": 99, "width": 1280, "height": 800 }
launch_on_virtual_display { "display": 99, "command": "xterm -e bash" }
list_virtual_display_windows { "display": 99 }             // get the X11 window id
// route input to the virtual display with the `display` field:
type_text { "hwnd": 2097164, "display": 99, "text": "echo hi" }
win_send_keys { "hwnd": 2097164, "display": 99, "keys": ["enter"] }
screenshot { "hwnd": 2097164, "display": 99 }              // or screenshot_virtual_display
stop_virtual_display { "display": 99 }
```

## 5. Show for an interactive login, then hide again

App on the normal desktop:

```jsonc
show_window { "window_title": "My App" }     // let the user sign in
hide_window { "window_title": "My App" }     // then tuck it away
```

App on a Windows headless desktop:

```jsonc
show_headless_desktop {
  "name": "work",
  "instruction": "Sign in, then tell the agent you are done."
}                                             // non-dismissible banner + emergency exit
hide_headless_desktop { "name": "work" }     // switch back after login
```

## 6. Screen recording

```jsonc
start_screen_recording { "fps": 15, "monitor": 1 }
recording_status {}
stop_screen_recording {}                     // → mp4 path
```

Record a region only:

```jsonc
start_screen_recording { "fps": 30, "region": [0, 0, 1280, 720] }
```

## 7. Screenshot then crop

```jsonc
screenshot { "monitor": 1 }                                  // note the returned path
crop_image { "input_path": "...screenshot-....png", "left": 0, "top": 0, "width": 400, "height": 300 }
```

## 8. Process control

```jsonc
list_processes { "name_filter": "chrome", "sort_by": "memory", "limit": 10 }
kill_process { "pid": 12345 }                 // or { "name": "notepad.exe", "force": true }
```

## 9. Throwaway WSL Linux box (Windows host)

```jsonc
wsl_status {}
wsl_create_temp {}                            // downloads latest Alpine minirootfs
wsl_run { "distro": "llcu-tmp-...", "command": "apk add --no-cache curl && curl --version" }
wsl_destroy { "name": "llcu-tmp-..." }        // irreversible cleanup
```

Clone an existing distro instead of downloading:

```jsonc
wsl_create_temp { "clone_from": "Ubuntu-24.04" }
```

## 10. AutoHotkey (reliable background input on Windows)

```jsonc
ahk_status {}
ahk_control_send { "text": "hello", "window": "ahk_id 0x1A2B3C" }
run_ahk { "code": "ControlSendText \"hi\", , \"ahk_exe notepad.exe\"\nExitApp" }
```

## 11. Run a command elevated

```jsonc
is_admin {}
run_command_as_admin { "command": "net session" }   // UAC prompt if not elevated
```

## 12. Auto-start the server on boot

```jsonc
install_startup {}                            // admin + HTTP on 127.0.0.1:8765
startup_status {}
uninstall_startup {}
```

---

## Decision guide: which input method?

| Situation | Use |
|-----------|-----|
| App is focused, simple | `mouse_click`/`type_text`/`press_keys` (foreground) |
| Don't want to steal focus, Windows edit control | `win_set_control_text` (WM_SETTEXT) |
| Don't want to steal focus, general Windows app | `mouse_click`/`type_text` with `hwnd`; if ignored → `ahk_control_send` |
| Linux background input | `type_text`/`win_send_keys` with `hwnd` (+`display`) |
| App ignores synthetic events (xterm, anti-cheat) | focus first (`window_action focus`) or AHK ControlSend |
| Invisible run | headless desktop (Win) / Xvfb (Linux) |
| Need Linux on Windows | `wsl_*` tools |
