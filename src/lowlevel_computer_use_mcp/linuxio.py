"""Linux (X11) backend: window management, background input, per-window capture,
and Xvfb virtual displays for headless-but-with-GUI.

Mirrors the Windows winio.py capabilities using standard X11 CLI tools so the same
MCP tools work natively on Linux:

  * Window mgmt / background input -> xdotool (+ wmctrl)
  * Per-window capture            -> ImageMagick `import -window` (fallback: mss region)
  * Headless GUI                  -> Xvfb virtual display + DISPLAY routing

Notes / caveats:
  * Targets X11. Under Wayland, most apps run via XWayland and still work, but pure
    Wayland windows are not controllable this way (no portable equivalent of these
    APIs exists); `available()` reports the session type.
  * Background TYPING/KEYS use XSendEvent (xdotool --window) and work for most apps;
    a few that ignore synthetic events need a real focus (use window_action focus).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from .process import popen_hidden, run_hidden

# display num -> {"proc": Popen, "apps": [Popen, ...], "display": ":N"}
_VIRTUAL_DISPLAYS: dict[int, dict[str, Any]] = {}


class LinuxIOError(RuntimeError):
    pass


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _run(cmd: list[str], env: Optional[dict] = None, timeout: float = 30.0,
         input_text: Optional[str] = None) -> subprocess.CompletedProcess:
    return run_hidden(
        cmd, capture_output=True, text=True, env=env, timeout=timeout, input=input_text
    )


def _need(tool: str) -> None:
    if not _have(tool):
        raise LinuxIOError(
            f"'{tool}' is required for this operation. Install it "
            f"(e.g. `sudo apt install {tool}` / `sudo dnf install {tool}`)."
        )


def available() -> dict[str, Any]:
    """Report which Linux automation tools are present and the session type."""
    return {
        "platform": "linux",
        "display": os.environ.get("DISPLAY"),
        "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "xdotool": _have("xdotool"),
        "wmctrl": _have("wmctrl"),
        "xvfb": _have("Xvfb"),
        "imagemagick_import": _have("import"),
        "scrot": _have("scrot"),
    }


# --------------------------------------------------------------------------- #
# Window management (xdotool / wmctrl)
# --------------------------------------------------------------------------- #
def _xdo(args: list[str], env: Optional[dict] = None, timeout: float = 30.0) -> str:
    _need("xdotool")
    proc = _run(["xdotool", *args], env=env, timeout=timeout)
    if proc.returncode != 0:
        raise LinuxIOError(f"xdotool {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def _win_geometry(winid: int, env: Optional[dict] = None) -> dict[str, int]:
    out = _xdo(["getwindowgeometry", "--shell", str(winid)], env=env)
    g: dict[str, int] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                g[k.lower()] = int(v)
            except ValueError:
                pass
    return {
        "left": g.get("x", 0),
        "top": g.get("y", 0),
        "width": g.get("width", 0),
        "height": g.get("height", 0),
    }


def _win_name(winid: int, env: Optional[dict] = None) -> str:
    try:
        return _xdo(["getwindowname", str(winid)], env=env)
    except LinuxIOError:
        return ""


def _win_dict(winid: int, env: Optional[dict] = None, active_id: Optional[int] = None) -> dict[str, Any]:
    geo = _win_geometry(winid, env=env)
    return {
        "title": _win_name(winid, env=env),
        "handle": int(winid),
        "is_active": active_id is not None and int(winid) == int(active_id),
        **geo,
        "is_minimized": False,
        "is_maximized": False,
    }


def list_windows(title_filter: Optional[str] = None, include_empty: bool = False,
                 env: Optional[dict] = None) -> list[dict[str, Any]]:
    """List top-level windows via xdotool search."""
    out = _xdo(["search", "--onlyvisible", "--name", ""], env=env)
    ids = [int(x) for x in out.split() if x.strip().isdigit()]
    try:
        active = int(_xdo(["getactivewindow"], env=env) or 0)
    except LinuxIOError:
        active = None
    result = []
    for wid in ids:
        name = _win_name(wid, env=env)
        if not include_empty and not name.strip():
            continue
        if title_filter and title_filter.lower() not in name.lower():
            continue
        result.append(_win_dict(wid, env=env, active_id=active))
    return result


def get_active_window(env: Optional[dict] = None) -> Optional[dict[str, Any]]:
    try:
        wid = int(_xdo(["getactivewindow"], env=env))
    except LinuxIOError:
        return None
    return _win_dict(wid, env=env, active_id=wid)


def find_window(title: Optional[str], handle: Optional[int], env: Optional[dict] = None) -> int:
    if handle is not None:
        return int(handle)
    if not title:
        raise LinuxIOError("Provide a window title or handle.")
    out = _xdo(["search", "--name", title], env=env)
    ids = [int(x) for x in out.split() if x.strip().isdigit()]
    if not ids:
        raise LinuxIOError(f"No window whose title matches '{title}'.")
    return ids[0]


def move_window(winid: int, x: int, y: int, env: Optional[dict] = None) -> dict[str, Any]:
    _xdo(["windowmove", str(winid), str(x), str(y)], env=env)
    return _win_dict(winid, env=env)


def resize_window(winid: int, w: int, h: int, env: Optional[dict] = None) -> dict[str, Any]:
    _xdo(["windowsize", str(winid), str(w), str(h)], env=env)
    return _win_dict(winid, env=env)


def window_action(winid: int, action: str, env: Optional[dict] = None) -> dict[str, Any]:
    if action == "focus":
        _xdo(["windowactivate", str(winid)], env=env)
    elif action == "minimize":
        _xdo(["windowminimize", str(winid)], env=env)
    elif action == "restore":
        _xdo(["windowactivate", str(winid)], env=env)
    elif action == "maximize":
        if _have("wmctrl"):
            _run(["wmctrl", "-i", "-r", str(winid), "-b", "add,maximized_vert,maximized_horz"], env=env)
        else:
            raise LinuxIOError("maximize requires wmctrl.")
    elif action == "close":
        _xdo(["windowclose", str(winid)], env=env)
        return {"action": action, "closed": True}
    else:
        raise LinuxIOError(f"Unknown action '{action}'.")
    return {"action": action, "window": _win_dict(winid, env=env)}


def show_window(winid: int, env: Optional[dict] = None) -> dict[str, Any]:
    _xdo(["windowmap", str(winid)], env=env)
    _xdo(["windowactivate", str(winid)], env=env)
    return {"hwnd": int(winid), "visible": True}


def hide_window(winid: int, minimize: bool = False, env: Optional[dict] = None) -> dict[str, Any]:
    if minimize:
        _xdo(["windowminimize", str(winid)], env=env)
    else:
        _xdo(["windowunmap", str(winid)], env=env)
    return {"hwnd": int(winid), "visible": False, "minimized": minimize}


# --------------------------------------------------------------------------- #
# Background input
# --------------------------------------------------------------------------- #
_BUTTON_NUM = {"left": "1", "middle": "2", "right": "3"}


def send_click(winid: int, x: int, y: int, button: str = "left", double: bool = False,
               env: Optional[dict] = None) -> dict[str, Any]:
    """Move the pointer relative to the window and click. Best-effort for unfocused
    windows (X11 has no reliable occluded synthetic click; the window should be
    reachable on screen)."""
    btn = _BUTTON_NUM.get(button, "1")
    _xdo(["mousemove", "--window", str(winid), str(x), str(y)], env=env)
    _xdo(["click", "--window", str(winid), btn], env=env)
    if double:
        _xdo(["click", "--window", str(winid), btn], env=env)
    return {"target_hwnd": int(winid), "client_x": x, "client_y": y, "button": button, "double": double}


def send_text(winid: int, text: str, env: Optional[dict] = None) -> dict[str, Any]:
    """Type text into a specific window via XSendEvent (no focus required)."""
    _xdo(["type", "--window", str(winid), "--", text], env=env)
    return {"target_hwnd": int(winid), "chars": len(text)}


# our key names -> xdotool keysyms
_KEYMAP = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "del": "Delete", "delete": "Delete", "ins": "Insert", "insert": "Insert",
    "pageup": "Prior", "pagedown": "Next", "win": "super", "ctrl": "ctrl",
    "control": "ctrl", "alt": "alt", "shift": "shift", "space": "space",
    "backspace": "BackSpace", "tab": "Tab", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right", "home": "Home", "end": "End",
}


def _xkey(name: str) -> str:
    n = name.lower()
    if n in _KEYMAP:
        return _KEYMAP[n]
    if re.fullmatch(r"f\d{1,2}", n):
        return n.upper()
    return name


def send_keys(winid: int, keys: list[str], env: Optional[dict] = None) -> dict[str, Any]:
    """Send a key / key-combo to a window via xdotool key --window."""
    combo = "+".join(_xkey(k) for k in keys)
    _xdo(["key", "--window", str(winid), combo], env=env)
    return {"target_hwnd": int(winid), "keys": keys}


def set_control_text(winid: int, text: str, env: Optional[dict] = None) -> dict[str, Any]:
    """X11 has no WM_SETTEXT; select-all + delete + type into the window instead."""
    _xdo(["key", "--window", str(winid), "ctrl+a"], env=env)
    _xdo(["key", "--window", str(winid), "Delete"], env=env)
    _xdo(["type", "--window", str(winid), "--", text], env=env)
    return {"target_hwnd": int(winid), "ok": True, "text_len": len(text)}


def list_child_windows(winid: int, env: Optional[dict] = None) -> list[dict[str, Any]]:
    """List immediate child windows via xwininfo -children."""
    if not _have("xwininfo"):
        raise LinuxIOError("xwininfo (x11-utils) is required for list_child_windows.")
    proc = _run(["xwininfo", "-id", str(winid), "-children"], env=env)
    children = []
    for line in proc.stdout.splitlines():
        m = re.search(r"(0x[0-9a-fA-F]+).*?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line)
        if m:
            children.append(
                {
                    "handle": int(m.group(1), 16),
                    "class": "",
                    "text": line.strip()[:80],
                    "width": int(m.group(2)),
                    "height": int(m.group(3)),
                    "left": int(m.group(4)),
                    "top": int(m.group(5)),
                    "visible": True,
                }
            )
    return children


# --------------------------------------------------------------------------- #
# Per-window capture
# --------------------------------------------------------------------------- #
def capture_window(winid: int, client_only: bool = False, env: Optional[dict] = None):
    """Capture a window to a PIL Image. Prefers ImageMagick `import -window`."""
    from PIL import Image  # local import
    import io

    if _have("import"):
        proc = run_hidden(
            ["import", "-window", str(winid), "png:-"],
            capture_output=True, env=env, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            img = Image.open(io.BytesIO(proc.stdout)).convert("RGB")
            return img, True
    # Fallback: capture the window's screen region with mss.
    import mss

    geo = _win_geometry(winid, env=env)
    with mss.mss(display=(env or os.environ).get("DISPLAY")) as sct:
        raw = sct.grab({"left": geo["left"], "top": geo["top"], "width": geo["width"], "height": geo["height"]})
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    return img, True


# --------------------------------------------------------------------------- #
# Xvfb virtual display (headless-but-with-GUI)
# --------------------------------------------------------------------------- #
def _display_env(num: int) -> dict[str, str]:
    return {**os.environ, "DISPLAY": f":{num}"}


def create_virtual_display(num: int = 99, width: int = 1280, height: int = 800,
                           depth: int = 24) -> dict[str, Any]:
    """Start an Xvfb virtual display so GUI apps can run without a physical screen."""
    _need("Xvfb")
    if num in _VIRTUAL_DISPLAYS and _VIRTUAL_DISPLAYS[num]["proc"].poll() is None:
        return {"display": f":{num}", "already_running": True}
    proc = popen_hidden(
        ["Xvfb", f":{num}", "-screen", "0", f"{width}x{height}x{depth}", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.6)
    if proc.poll() is not None:
        raise LinuxIOError(f"Xvfb failed to start on :{num} (is the display already in use?).")
    _VIRTUAL_DISPLAYS[num] = {"proc": proc, "apps": [], "display": f":{num}",
                             "size": f"{width}x{height}x{depth}"}
    return {"display": f":{num}", "size": f"{width}x{height}x{depth}", "pid": proc.pid}


def launch_on_virtual_display(num: int, command: str) -> dict[str, Any]:
    """Launch a GUI app on the Xvfb display :num."""
    if num not in _VIRTUAL_DISPLAYS:
        create_virtual_display(num)
    import shlex

    app = popen_hidden(
        shlex.split(command), env=_display_env(num),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    _VIRTUAL_DISPLAYS[num]["apps"].append(app)
    return {"display": f":{num}", "pid": app.pid, "command": command}


def list_virtual_display_windows(num: int) -> list[dict[str, Any]]:
    """List windows present on the Xvfb display :num."""
    return list_windows(include_empty=False, env=_display_env(num))


def capture_virtual_display(num: int):
    """Capture the whole Xvfb display :num as a PIL Image."""
    from PIL import Image
    import mss

    with mss.mss(display=f":{num}") as sct:
        raw = sct.grab(sct.monitors[1])
        return Image.frombytes("RGB", raw.size, raw.rgb)


def stop_virtual_display(num: int) -> dict[str, Any]:
    """Terminate apps launched on :num and stop the Xvfb display."""
    info = _VIRTUAL_DISPLAYS.pop(num, None)
    if not info:
        return {"display": f":{num}", "stopped": False, "note": "not tracked"}
    for app in info["apps"]:
        try:
            app.terminate()
        except Exception:  # noqa: BLE001
            pass
    try:
        info["proc"].terminate()
    except Exception:  # noqa: BLE001
        pass
    return {"display": f":{num}", "stopped": True}
