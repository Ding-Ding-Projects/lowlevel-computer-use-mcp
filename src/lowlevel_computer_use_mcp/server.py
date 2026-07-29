#!/usr/bin/env python3
"""Low-level computer-use MCP server.

Exposes low-level desktop control as MCP tools (stdio transport):

  * Mouse control      - move, click, double-click, drag, scroll, cursor position
  * Keyboard control   - type text, press hotkey combinations
  * Shell commands     - run arbitrary system/shell commands and capture output
  * Window management  - list / move / resize / focus / minimize / maximize / close windows
  * Process control    - list processes and kill them by PID or name
  * Screenshots        - capture full screen, a single monitor, or a region
  * Image cropping      - crop a saved screenshot to a sub-region
  * Screen recording   - record the screen (or a region) to an mp4 file

This server is intended for Windows but most tools degrade gracefully on other
platforms. It performs real, unsandboxed actions on the host machine - only run
it in a context where that is acceptable.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import inspect
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, get_type_hints

from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

from .processes import hidden_server_command, hidden_subprocess_kwargs, pythonw_executable

# --------------------------------------------------------------------------- #
# Optional / platform dependencies (imported lazily-safely so the server can
# still start and report a clear error if something is missing).
# --------------------------------------------------------------------------- #
try:
    import pyautogui

    pyautogui.FAILSAFE = False  # do not abort when the cursor hits a screen corner
    pyautogui.PAUSE = 0.0
except Exception:  # pragma: no cover - environment dependent
    pyautogui = None

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover
    gw = None

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

try:
    import mss
except Exception:  # pragma: no cover
    mss = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

# Win32 background-input / per-window capture / headless desktop (Windows only)
try:
    if os.name == "nt":
        from . import winio
    else:  # pragma: no cover
        winio = None
except Exception:  # pragma: no cover
    winio = None

# AutoHotkey add-in (cross-platform import; tools require AHK installed on Windows)
try:
    from . import ahk as ahk_addon
except Exception:  # pragma: no cover
    ahk_addon = None

# Ephemeral WSL provisioning (Windows host only; pure-stdlib import)
try:
    from . import wslio
except Exception:  # pragma: no cover
    wslio = None

# Linux (X11) backend: window mgmt, background input, capture, Xvfb
try:
    from . import linuxio
except Exception:  # pragma: no cover
    linuxio = None

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
_MIN_MOUSE_MOVE_DURATION = 0.05
_DEFAULT_MOUSE_MOVE_DURATION = max(
    _MIN_MOUSE_MOVE_DURATION,
    min(float(os.environ.get("LOWLEVEL_MOUSE_MOVE_DURATION", "0.25")), 10.0),
)
_MOUSE_MOVE_HZ = max(15, min(int(os.environ.get("LOWLEVEL_MOUSE_MOVE_HZ", "90")), 240))
_MOUSE_MOVE_STEP_PX = max(4, min(int(os.environ.get("LOWLEVEL_MOUSE_MOVE_STEP_PX", "22")), 120))


def _linux_env(display: Optional[int]):
    """Build an env dict pinned to an X display number (e.g. an Xvfb :99), or None."""
    if display is None:
        return None
    return {**os.environ, "DISPLAY": f":{display}"}


def _smooth_duration(requested: Optional[float], instant: bool = False) -> float:
    """Resolve requested movement duration.

    A zero/omitted value means "use the visible default" so normal agent calls move
    like a real pointer. Set the explicit instant flag when a jump is desired.
    """
    if instant:
        return 0.0
    if requested is not None and requested > 0:
        return min(float(requested), 10.0)
    return _DEFAULT_MOUSE_MOVE_DURATION


def _smooth_mouse_path(
    start_x: int,
    start_y: int,
    target_x: int,
    target_y: int,
    duration: float,
) -> list[tuple[int, int]]:
    distance = math.hypot(target_x - start_x, target_y - start_y)
    if duration <= 0 or distance < 1:
        return [(target_x, target_y)]

    steps_by_time = max(2, int(math.ceil(duration * _MOUSE_MOVE_HZ)))
    steps_by_distance = max(2, int(math.ceil(distance / _MOUSE_MOVE_STEP_PX)))
    steps = min(360, max(steps_by_time, steps_by_distance))
    path: list[tuple[int, int]] = []
    last_xy: tuple[int, int] | None = None

    for i in range(1, steps + 1):
        t = i / steps
        eased = t * t * (3 - 2 * t)
        nx = int(round(start_x + (target_x - start_x) * eased))
        ny = int(round(start_y + (target_y - start_y) * eased))
        if (nx, ny) != last_xy:
            path.append((nx, ny))
            last_xy = (nx, ny)

    if not path or path[-1] != (target_x, target_y):
        path.append((target_x, target_y))
    return path


def _smooth_mouse_move_to(x: int, y: int, *, duration: Optional[float] = None, instant: bool = False) -> None:
    """Move the OS cursor in visible steps instead of relying on backend tweening.

    PyAutoGUI can collapse short moves into a single SetCursorPos jump. This helper
    sends a bounded series of small absolute moves with smoothstep easing so the
    cursor visibly travels while remaining fast enough for automation.
    """
    if pyautogui is None:
        return
    target_x, target_y = int(x), int(y)
    pos = pyautogui.position()
    start_x, start_y = int(pos.x), int(pos.y)
    distance = math.hypot(target_x - start_x, target_y - start_y)
    resolved_duration = _smooth_duration(duration, instant)
    if resolved_duration <= 0 or distance < 1:
        pyautogui.moveTo(target_x, target_y, duration=0)
        return

    path = _smooth_mouse_path(start_x, start_y, target_x, target_y, resolved_duration)
    started = time.perf_counter()

    for index, (nx, ny) in enumerate(path, start=1):
        pyautogui.moveTo(nx, ny, duration=0)
        wake_at = started + resolved_duration * (index / len(path))
        delay = wake_at - time.perf_counter()
        if delay > 0:
            time.sleep(delay)


# --------------------------------------------------------------------------- #
# Server + constants
# --------------------------------------------------------------------------- #
SERVER_INSTRUCTIONS = """\
LOW-LEVEL COMPUTER-USE SERVER — 53 tools for real, unsandboxed desktop control on
Windows AND Linux. Every tool returns a JSON string: {"ok": true, ...} on success
or {"ok": false, "error": "..."} on failure — ALWAYS read `ok`. A companion Skill
named "lowlevel-computer-use" documents every feature in depth (SKILL.md +
reference/TOOLS.md, WORKFLOWS.md, PLATFORMS.md) — consult it for exact parameters.

GOLDEN RULES
  1. Look before acting: screenshot (full or screenshot(hwnd=...)) to see state.
  2. Resolve handles at run time (list_windows -> list_child_windows); NEVER
     hard-code handles — they change every launch.
  3. HEADLESS FIRST: launch GUI apps on a Windows off-screen desktop or Linux
     Xvfb. Keep the user's visible desktop, cursor, keyboard focus, and foreground
     application completely untouched.
  4. Use BACKGROUND targeting inside that headless desktop. Foreground tools are
     focus-protected by default and require explicit per-call confirmation.
  5. Foreground mouse uses SCREEN pixels; background clicks use CLIENT coords of
     the target window.
  6. Verify after acting (re-screenshot). 7. Pair every create with a destroy/stop.

FULL TOOL CATALOG (names are the tools)
- Mouse/keyboard (X-platform): get_screen_size, get_cursor_position, mouse_move,
  mouse_click, mouse_drag, mouse_scroll, type_text, press_keys.
- Shell: run_command (stdout/stderr/exit code, cwd, timeout).
- Windows (X-platform): list_windows, get_active_window, move_window, resize_window,
  window_action (focus/minimize/maximize/restore/close), show_window, hide_window.
- Background/unfocused targeting: mouse_click/type_text/screenshot accept hwnd or
  window_title; list_child_windows, win_set_control_text (most reliable text entry),
  win_send_keys.
- Processes: list_processes, kill_process (by pid or exact name; force option).
- Screens/images: screenshot (monitor 0=all/1=primary..., region, or single-window
  hwnd capture), crop_image.
- Recording: start_screen_recording, stop_screen_recording, recording_status (mp4).
- Headless-with-GUI (Windows off-screen desktop): create_headless_desktop,
  launch_on_headless_desktop, list_headless_windows, close_headless_desktop,
  show_headless_desktop / hide_headless_desktop (switch the live screen for a login).
- Headless-with-GUI (Linux Xvfb): linux_status, create_virtual_display,
  launch_on_virtual_display, list_virtual_display_windows, screenshot_virtual_display,
  stop_virtual_display.
- AutoHotkey (Windows): ahk_status, run_ahk, ahk_control_send.
- Ephemeral WSL (Windows host): wsl_status, wsl_list_distros, wsl_create_temp,
  wsl_run, wsl_list_temp, wsl_destroy, wsl_destroy_all_temp.
- Run-as-admin & boot: is_admin, run_command_as_admin, install_startup,
  uninstall_startup, startup_status.

BACKGROUND / UNFOCUSED CONTROL (first-class). Workflow:
  1. list_windows -> find the top-level window (title + handle).
  2. list_child_windows -> find the specific control (e.g. the Edit box) + rect.
  3. Drive it WITHOUT focus: mouse_click(hwnd=, x, y) [CLIENT coords],
     type_text(hwnd=), win_set_control_text(hwnd=) [most reliable], win_send_keys(hwnd=).
  4. screenshot(hwnd=) to see the result without bringing the window forward.
  Background input uses Win32 PostMessage/WM_CHAR (Windows) or XSendEvent (Linux);
  some apps ignore synthetic events (raw input / physical-key checks / xterm with
  allowSendEvents off) — do not fall back to focus while the user is active. Try
  win_set_control_text or AHK ahk_control_send, then report the limitation.

CROSS-PLATFORM. The same tools work on Windows and Linux. On Linux `hwnd` is an X11
window id; window mgmt/background input/per-window capture use xdotool/wmctrl/
ImageMagick. The Linux 'headless with GUI' is an Xvfb virtual display — pass the
`display` field to click/type/screenshot/keys to route input there. On a Windows
host you can spin up a throwaway Linux box with wsl_create_temp -> wsl_run ->
wsl_destroy. Check availability with linux_status / ahk_status / wsl_status.

SHOW-FOR-LOGIN. These tools intentionally interrupt the foreground and are locked
behind confirm_focus_disruption=true. Use them only after the user explicitly
requests the handoff. Prefer showing the headless desktop; hide it immediately
afterwards. Never use this fallback merely because background input failed.

MACROS AS SKILLS. When you perform a multi-step UI sequence the user is likely to
repeat ("open app X, click here, type this, save"), DO NOT leave it as ad-hoc tool
calls — capture it as a reusable macro Skill that records the ordered tool calls.
Use the skill-creator skill or write a SKILL.md following this repo's
macros/MACRO_SKILL_TEMPLATE.md: name the goal, list the exact tool calls in order
with run-time handle resolution (not hard-coded handles), note verification
screenshots, and parameterize what varies. Prefer background tools so replays don't
steal focus.

SAFETY. run_command, run_command_as_admin, kill_process, run_ahk,
window_action(close), wsl_destroy, and the launch/startup tools are destructive or
system-modifying — confirm intent. These tools act directly on the host with the
user's privileges.
"""

mcp = FastMCP("computer_use_mcp", instructions=SERVER_INSTRUCTIONS)

CAPTURE_DIR = Path(
    os.environ.get(
        "LOWLEVEL_CU_CAPTURE_DIR",
        str(Path.home() / "lowlevel-computer-use-captures"),
    )
)


def _capture_dir() -> Path:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    return CAPTURE_DIR


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


def _ok(**data: Any) -> str:
    return json.dumps({"ok": True, **data}, indent=2, default=str)


def _err(message: str, **data: Any) -> str:
    return json.dumps({"ok": False, "error": message, **data}, indent=2, default=str)


def _require(module: Any, name: str) -> Optional[str]:
    """Return an error JSON string if a required dependency is missing."""
    if module is None:
        return _err(
            f"Required dependency '{name}' is not available. "
            f"Install it (e.g. `pip install {name}`) and restart the server."
        )
    return None


def _focus_guard(confirmed: bool, operation: str) -> Optional[str]:
    """Block foreground-affecting actions unless the caller explicitly confirms."""
    if confirmed:
        return None
    return _err(
        f"{operation} is blocked by focus protection. Use a headless desktop and "
        "background hwnd/window_title targeting. Set confirm_focus_disruption=true "
        "only after the user explicitly asks to hand over the visible desktop.",
        focus_protected=True,
    )


# --------------------------------------------------------------------------- #
# Admin / elevation + boot-startup helpers (Windows)
# --------------------------------------------------------------------------- #
TASK_NAME = "LowLevelComputerUseMCP"
STARTUP_SCRIPT_NAME = f"{TASK_NAME}.vbs"
DEFAULT_HTTP_HOST = os.environ.get("LOWLEVEL_CU_HOST", "127.0.0.1")
DEFAULT_HTTP_PORT = int(os.environ.get("LOWLEVEL_CU_PORT", "8765"))


def _repo_dir() -> Path:
    """Path to the cloned repo root (parent of the src/ package)."""
    return Path(__file__).resolve().parents[2]


def _is_admin() -> bool:
    """Return True if the current process is running elevated (Windows admin)."""
    if os.name != "nt":
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except AttributeError:
            return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _server_launch_argument(http: bool, host: str, port: int) -> str:
    """Argument string passed to console-free Python for a scheduled task."""
    parts = ["-m", "lowlevel_computer_use_mcp.server"]
    if http:
        parts += ["--http", "--host", host, "--port", str(port)]
    return subprocess.list2cmdline(parts)


def _startup_script_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_SCRIPT_NAME


def _vbs_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _clean_transcript(text: str) -> str:
    """Strip PowerShell transcript header/footer noise, keeping the real output."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("Transcript started")), None)
    end = next((i for i, l in enumerate(lines) if "transcript end" in l.lower()), len(lines))
    body = lines[start + 1 : end] if start is not None else lines
    body = [l for l in body if l.strip() and set(l.strip()) != {"*"}]
    return "\n".join(body).strip()


def _run_powershell(body: str, require_admin: bool, timeout: float = 180.0) -> dict[str, Any]:
    """Run a PowerShell script.

    If require_admin is True and the process is not elevated, the script is
    relaunched through a UAC prompt (Start-Process -Verb RunAs) and its output is
    captured via a transcript file. Returns {ok, returncode, output}.
    """
    if os.name != "nt":
        return {"ok": False, "returncode": -1, "output": "Admin/startup features require Windows."}

    body = "$ErrorActionPreference = 'Stop'\n" + body

    if not require_admin or _is_admin():
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", body],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                **hidden_subprocess_kwargs(),
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "output": (proc.stdout + proc.stderr).strip(),
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "returncode": -1, "output": f"PowerShell timed out after {timeout}s"}

    # Not elevated: relaunch the script through UAC, capturing output via transcript.
    log_fd, log_path = tempfile.mkstemp(suffix=".log", prefix="llcu-")
    os.close(log_fd)
    ps1_fd, ps1_path = tempfile.mkstemp(suffix=".ps1", prefix="llcu-")
    os.close(ps1_fd)
    try:
        wrapped = (
            f"Start-Transcript -Path '{log_path}' -Force | Out-Null\n"
            f"try {{\n{body}\n}} catch {{ Write-Output \"ERROR: $($_.Exception.Message)\"; exit 1 }}\n"
            f"Stop-Transcript | Out-Null\n"
        )
        Path(ps1_path).write_text(wrapped, encoding="utf-8")
        launcher = (
            "$p = Start-Process powershell -ArgumentList "
            f"@('-NoProfile','-ExecutionPolicy','Bypass','-File','{ps1_path}') "
            "-Verb RunAs -Wait -WindowStyle Hidden -PassThru; exit $p.ExitCode"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", launcher],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        output = ""
        if Path(log_path).exists():
            output = _clean_transcript(Path(log_path).read_text(encoding="utf-8", errors="replace"))
        if proc.returncode != 0 and not output:
            output = (proc.stderr or "Elevation was cancelled or failed.").strip()
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "output": output}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "output": "Elevated PowerShell timed out (UAC prompt unanswered?)"}
    finally:
        for p in (log_path, ps1_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _install_startup(http: bool, host: str, port: int, run_as_admin: bool) -> dict[str, Any]:
    """Register a scheduled task that starts this server at user logon."""
    executable, _ = hidden_server_command()
    arg = _server_launch_argument(http, host, port).replace("'", "''")
    if not run_as_admin:
        path = _startup_script_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        command = subprocess.list2cmdline([executable]) + " " + _server_launch_argument(http, host, port)
        script = (
            "Option Explicit\n"
            "Dim shell\n"
            "Set shell = CreateObject(\"WScript.Shell\")\n"
            f"shell.CurrentDirectory = {_vbs_string(str(_repo_dir()))}\n"
            f"shell.Run {_vbs_string(command)}, 0, False\n"
        )
        # Windows Script Host reliably recognizes UTF-16LE with a BOM. UTF-8
        # BOM files are rejected without a useful diagnostic on some builds.
        path.write_text(script, encoding="utf-16")
        return {
            "ok": True,
            "returncode": 0,
            "output": f"Installed console-free user startup launcher at {path}.",
            "method": "startup-folder-pythonw",
        }
    executable_q = executable.replace("'", "''")
    repo_q = str(_repo_dir()).replace("'", "''")
    run_level = "Highest" if run_as_admin else "Limited"
    body = (
        "$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name\n"
        f"$action = New-ScheduledTaskAction -Execute '{executable_q}' -Argument '{arg}' -WorkingDirectory '{repo_q}'\n"
        "$trigger = New-ScheduledTaskTrigger -AtLogOn\n"
        f"$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel {run_level}\n"
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit (New-TimeSpan -Seconds 0) -StartWhenAvailable\n"
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger "
        "-Principal $principal -Settings $settings -Force | Out-Null\n"
        f"Write-Output 'Installed scheduled task {TASK_NAME} (RunLevel={run_level}, AtLogon).'\n"
    )
    return _run_powershell(body, require_admin=run_as_admin)


def _uninstall_startup() -> dict[str, Any]:
    """Remove the boot-startup scheduled task."""
    script = _startup_script_path()
    removed_script = script.exists()
    if removed_script:
        script.unlink()
    body = (
        f"if (Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue) {{\n"
        f"  Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false\n"
        f"  Write-Output 'Removed scheduled task {TASK_NAME}.'\n"
        f"}} else {{ Write-Output 'Task was not installed. Startup script removed={str(removed_script).lower()}.' }}\n"
    )
    # Never summon UAC during removal. A non-admin caller can remove the user
    # launcher; an elevated task returns a truthful permission error instead.
    return _run_powershell(body, require_admin=False)


def _startup_status() -> dict[str, Any]:
    """Report whether the boot-startup scheduled task is installed."""
    script = _startup_script_path()
    script_q = str(script).replace("'", "''")
    body = (
        f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue\n"
        "if ($t) {\n"
        "  $i = $t | Get-ScheduledTaskInfo\n"
        "  $lvl = $t.Principal.RunLevel\n"
        "  Write-Output \"INSTALLED|State=$($t.State)|RunLevel=$lvl|LastRun=$($i.LastRunTime)|NextRun=$($i.NextRunTime)\"\n"
        f"}} else {{ Write-Output 'STARTUP_SCRIPT|Installed={str(script.exists()).lower()}|Path={script_q}' }}\n"
    )
    return _run_powershell(body, require_admin=False)


# --------------------------------------------------------------------------- #
# Enums / shared models
# --------------------------------------------------------------------------- #
class MouseButton(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


# =========================================================================== #
# MOUSE + KEYBOARD
# =========================================================================== #
@mcp.tool(
    name="get_screen_size",
    annotations={
        "title": "Get Screen Size",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_screen_size() -> str:
    """Return the primary screen resolution in pixels.

    Returns:
        str: JSON like {"ok": true, "width": 1920, "height": 1080}.
    """
    if (e := _require(pyautogui, "pyautogui")):
        return e
    w, h = pyautogui.size()
    return _ok(width=int(w), height=int(h))


@mcp.tool(
    name="get_cursor_position",
    annotations={
        "title": "Get Cursor Position",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_cursor_position() -> str:
    """Return the current mouse cursor position in screen pixels.

    Returns:
        str: JSON like {"ok": true, "x": 100, "y": 200}.
    """
    if (e := _require(pyautogui, "pyautogui")):
        return e
    pos = pyautogui.position()
    return _ok(x=int(pos.x), y=int(pos.y))


class MoveInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    x: int = Field(..., description="Target X coordinate in screen pixels", ge=0)
    y: int = Field(..., description="Target Y coordinate in screen pixels", ge=0)
    duration: float = Field(
        default=0.0,
        description="Seconds to animate the move over. 0 uses the visible default duration.",
        ge=0,
        le=10,
    )
    instant: bool = Field(
        default=False,
        description="Set true only when you intentionally want the cursor to jump instantly.",
    )
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Must be true after explicit user consent; moving the shared cursor disrupts focus-sensitive activity.",
    )


@mcp.tool(
    name="mouse_move",
    annotations={
        "title": "Move Mouse",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def mouse_move(params: MoveInput) -> str:
    """Move the mouse cursor to an absolute screen coordinate.

    Args:
        params (MoveInput): x, y target and optional animation duration.

    Returns:
        str: JSON with the resulting cursor position.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Foreground mouse movement")):
        return e
    if (e := _require(pyautogui, "pyautogui")):
        return e
    _smooth_mouse_move_to(params.x, params.y, duration=params.duration, instant=params.instant)
    pos = pyautogui.position()
    return _ok(x=int(pos.x), y=int(pos.y), duration=_smooth_duration(params.duration, params.instant))


class ClickInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    x: Optional[int] = Field(
        default=None, description="X coordinate to click; omit to click at current cursor", ge=0
    )
    y: Optional[int] = Field(
        default=None, description="Y coordinate to click; omit to click at current cursor", ge=0
    )
    button: MouseButton = Field(default=MouseButton.LEFT, description="Which mouse button")
    clicks: int = Field(default=1, description="Number of clicks (2 = double-click)", ge=1, le=5)
    interval: float = Field(
        default=0.0, description="Seconds between successive clicks", ge=0, le=5
    )
    move_duration: float = Field(
        default=0.0,
        description="Foreground only: seconds to visibly move before clicking. 0 uses the smooth default.",
        ge=0,
        le=10,
    )
    instant_move: bool = Field(
        default=False,
        description="Foreground only: jump to x/y before clicking instead of visibly moving.",
    )
    hwnd: Optional[int] = Field(
        default=None,
        description="BACKGROUND TARGET: native window handle. When set, the click is "
        "posted to that window via Win32 messages WITHOUT focusing it, and x/y are "
        "treated as CLIENT coordinates relative to that window.",
    )
    window_title: Optional[str] = Field(
        default=None,
        description="BACKGROUND TARGET by title (substring). Like hwnd but resolves the "
        "top-level window by title; x/y are client coordinates of that window.",
    )
    display: Optional[int] = Field(
        default=None, description="Linux only: X display number of the target window (e.g. Xvfb 99)"
    )
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Required only for a foreground click after explicit user consent; background targets remain safe.",
    )


@mcp.tool(
    name="mouse_click",
    annotations={
        "title": "Mouse Click",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def mouse_click(params: ClickInput) -> str:
    """Click a mouse button, optionally at a specific coordinate.

    Use clicks=2 for a double-click. If x/y are omitted the click happens at the
    current cursor position.

    BACKGROUND TARGETING: set `hwnd` or `window_title` to click a specific window
    WITHOUT bringing it to the foreground (Win32 PostMessage). In that mode x/y are
    client coordinates of the target window and the deepest child control at that
    point receives the click.

    Args:
        params (ClickInput): position, button, click count, interval, optional target.

    Returns:
        str: JSON describing the click that was performed.
    """
    # Background / unfocused window targeting
    if params.hwnd is not None or params.window_title:
        if params.x is None or params.y is None:
            return _err("Background click requires explicit client x and y coordinates.")
        if IS_LINUX:
            if params.display is None:
                if (e := _focus_guard(
                    params.confirm_focus_disruption,
                    "X11 click on the user's visible display",
                )):
                    return e
            if (e := _require(linuxio, "linuxio")):
                return e
            try:
                env = _linux_env(params.display)
                wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
                res = linuxio.send_click(
                    wid, params.x, params.y, button=params.button.value, double=params.clicks >= 2, env=env
                )
                return _ok(mode="background", window_hwnd=wid, **res)
            except linuxio.LinuxIOError as exc:
                return _err(str(exc))
        if (e := _require(winio, "winio (Windows)")):
            return e
        try:
            top = winio.find_top_window(params.window_title, params.hwnd)
            res = winio.send_click(
                top, params.x, params.y, button=params.button.value, double=params.clicks >= 2
            )
            return _ok(mode="background", window_hwnd=top, **res)
        except winio.WinIOError as exc:
            return _err(str(exc))

    if (e := _focus_guard(params.confirm_focus_disruption, "Foreground mouse click")):
        return e
    if (e := _require(pyautogui, "pyautogui")):
        return e
    kwargs: dict[str, Any] = {
        "button": params.button.value,
        "clicks": params.clicks,
        "interval": params.interval,
    }
    if params.x is not None and params.y is not None:
        _smooth_mouse_move_to(
            params.x, params.y, duration=params.move_duration, instant=params.instant_move
        )
    pyautogui.click(**kwargs)
    pos = pyautogui.position()
    return _ok(
        button=params.button.value,
        clicks=params.clicks,
        x=int(pos.x),
        y=int(pos.y),
    )


class DragInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    start_x: Optional[int] = Field(default=None, description="Start X; omit to drag from current cursor", ge=0)
    start_y: Optional[int] = Field(default=None, description="Start Y; omit to drag from current cursor", ge=0)
    end_x: int = Field(..., description="End X coordinate", ge=0)
    end_y: int = Field(..., description="End Y coordinate", ge=0)
    button: MouseButton = Field(default=MouseButton.LEFT, description="Button held during drag")
    duration: float = Field(default=0.25, description="Seconds to animate the drag", ge=0, le=10)
    confirm_focus_disruption: bool = Field(default=False, description="Required after explicit user consent.")


@mcp.tool(
    name="mouse_drag",
    annotations={
        "title": "Mouse Drag",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def mouse_drag(params: DragInput) -> str:
    """Press a mouse button at a start point and release it at an end point.

    Args:
        params (DragInput): optional start, required end, button and duration.

    Returns:
        str: JSON describing the drag.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Foreground mouse drag")):
        return e
    if (e := _require(pyautogui, "pyautogui")):
        return e
    if params.start_x is not None and params.start_y is not None:
        _smooth_mouse_move_to(params.start_x, params.start_y)
    pyautogui.mouseDown(button=params.button.value)
    try:
        _smooth_mouse_move_to(params.end_x, params.end_y, duration=params.duration)
    finally:
        pyautogui.mouseUp(button=params.button.value)
    return _ok(end_x=params.end_x, end_y=params.end_y, button=params.button.value)


class ScrollInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    amount: int = Field(..., description="Scroll clicks; positive = up, negative = down")
    x: Optional[int] = Field(default=None, description="X to move to before scrolling", ge=0)
    y: Optional[int] = Field(default=None, description="Y to move to before scrolling", ge=0)
    move_duration: float = Field(
        default=0.0,
        description="Seconds to visibly move before scrolling. 0 uses the smooth default.",
        ge=0,
        le=10,
    )
    instant_move: bool = Field(default=False, description="Jump to x/y before scrolling.")
    confirm_focus_disruption: bool = Field(default=False, description="Required after explicit user consent.")


@mcp.tool(
    name="mouse_scroll",
    annotations={
        "title": "Mouse Scroll",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def mouse_scroll(params: ScrollInput) -> str:
    """Scroll the mouse wheel vertically.

    Args:
        params (ScrollInput): amount (positive up / negative down) and optional position.

    Returns:
        str: JSON confirming the scroll amount.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Foreground mouse scroll")):
        return e
    if (e := _require(pyautogui, "pyautogui")):
        return e
    if params.x is not None and params.y is not None:
        _smooth_mouse_move_to(params.x, params.y, duration=params.move_duration, instant=params.instant_move)
    pyautogui.scroll(params.amount)
    return _ok(scrolled=params.amount)


class TypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., description="Text to type at the current focus", min_length=1)
    interval: float = Field(default=0.0, description="Seconds between keystrokes", ge=0, le=2)
    hwnd: Optional[int] = Field(
        default=None,
        description="BACKGROUND TARGET: window/control handle. Text is posted via WM_CHAR "
        "to that window's focused control WITHOUT focusing the window.",
    )
    window_title: Optional[str] = Field(
        default=None, description="BACKGROUND TARGET by title (substring) instead of a handle."
    )
    display: Optional[int] = Field(
        default=None, description="Linux only: X display number of the target window (e.g. Xvfb 99)"
    )
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Required only for typing into the current foreground after explicit user consent.",
    )


@mcp.tool(
    name="type_text",
    annotations={
        "title": "Type Text",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def type_text(params: TypeInput) -> str:
    """Type a string of text into the currently focused window/control.

    BACKGROUND TARGETING: set `hwnd` or `window_title` to deliver the text to a
    specific window WITHOUT focusing it (Win32 WM_CHAR to its focused control).
    For edit controls, `win_set_control_text` is more reliable.

    Args:
        params (TypeInput): the text, optional per-key interval, optional target.

    Returns:
        str: JSON confirming how many characters were typed.
    """
    if params.hwnd is not None or params.window_title:
        if IS_LINUX:
            if (e := _require(linuxio, "linuxio")):
                return e
            try:
                env = _linux_env(params.display)
                wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
                res = linuxio.send_text(wid, params.text, env=env)
                return _ok(mode="background", window_hwnd=wid, **res)
            except linuxio.LinuxIOError as exc:
                return _err(str(exc))
        if (e := _require(winio, "winio (Windows)")):
            return e
        try:
            top = winio.find_top_window(params.window_title, params.hwnd)
            target = winio.focused_control(top)
            res = winio.send_text(target, params.text)
            return _ok(mode="background", window_hwnd=top, **res)
        except winio.WinIOError as exc:
            return _err(str(exc))

    if (e := _focus_guard(params.confirm_focus_disruption, "Foreground typing")):
        return e
    if (e := _require(pyautogui, "pyautogui")):
        return e
    pyautogui.typewrite(params.text, interval=params.interval)
    return _ok(typed_chars=len(params.text))


class HotkeyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    keys: list[str] = Field(
        ...,
        description="Keys to press together, e.g. ['ctrl','c'] or ['win','d']. "
        "Use pyautogui key names (ctrl, alt, shift, win, enter, tab, esc, f1...).",
        min_length=1,
        max_length=6,
    )
    confirm_focus_disruption: bool = Field(default=False, description="Required after explicit user consent.")


@mcp.tool(
    name="press_keys",
    annotations={
        "title": "Press Key Combination",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def press_keys(params: HotkeyInput) -> str:
    """Press a keyboard combination (hotkey), e.g. Ctrl+C or Alt+Tab.

    A single-element list presses one key; multiple elements are pressed together.

    Args:
        params (HotkeyInput): list of pyautogui key names.

    Returns:
        str: JSON confirming the keys pressed.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Foreground key press")):
        return e
    if (e := _require(pyautogui, "pyautogui")):
        return e
    keys = [k.lower() for k in params.keys]
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
    return _ok(keys=keys)


# =========================================================================== #
# SHELL COMMANDS
# =========================================================================== #
class RunCommandInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    command: str = Field(..., description="Command line to execute", min_length=1)
    shell: bool = Field(
        default=True,
        description="Run through the system shell (cmd/PowerShell/sh). If false, command is split into argv.",
    )
    cwd: Optional[str] = Field(default=None, description="Working directory for the command")
    timeout: float = Field(default=60.0, description="Max seconds to wait before killing", ge=1, le=3600)


@mcp.tool(
    name="run_command",
    annotations={
        "title": "Run Shell Command",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def run_command(params: RunCommandInput) -> str:
    """Run a system/shell command and capture its stdout, stderr and exit code.

    This executes arbitrary commands on the host with the server's privileges.

    Args:
        params (RunCommandInput): command, shell flag, cwd and timeout.

    Returns:
        str: JSON like {"ok": true, "returncode": 0, "stdout": "...", "stderr": "...",
             "timed_out": false}.
    """
    try:
        if params.shell:
            cmd: Any = params.command
        else:
            import shlex

            cmd = shlex.split(params.command, posix=(os.name != "nt"))
        proc = subprocess.run(
            cmd,
            shell=params.shell,
            cwd=params.cwd,
            capture_output=True,
            text=True,
            timeout=params.timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        return _ok(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _err(
            f"Command timed out after {params.timeout}s",
            timed_out=True,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )
    except Exception as exc:  # pragma: no cover
        return _err(f"{type(exc).__name__}: {exc}")


# =========================================================================== #
# WINDOW MANAGEMENT
# =========================================================================== #
def _window_to_dict(win: Any) -> dict[str, Any]:
    return {
        "title": win.title,
        "handle": getattr(win, "_hWnd", None),
        "left": win.left,
        "top": win.top,
        "width": win.width,
        "height": win.height,
        "is_minimized": bool(getattr(win, "isMinimized", False)),
        "is_maximized": bool(getattr(win, "isMaximized", False)),
        "is_active": bool(getattr(win, "isActive", False)),
    }


def _find_window(title: Optional[str], handle: Optional[int]) -> Any:
    """Find a single window by handle (exact) or title (case-insensitive substring)."""
    windows = gw.getAllWindows()
    if handle is not None:
        for w in windows:
            if getattr(w, "_hWnd", None) == handle:
                return w
        return None
    if title:
        title_l = title.lower()
        matches = [w for w in windows if w.title and title_l in w.title.lower()]
        return matches[0] if matches else None
    return None


class ListWindowsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title_filter: Optional[str] = Field(
        default=None, description="Only return windows whose title contains this (case-insensitive)"
    )
    include_empty_titles: bool = Field(
        default=False, description="Include windows that have no title text"
    )


@mcp.tool(
    name="list_windows",
    annotations={
        "title": "List Windows",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_windows(params: ListWindowsInput) -> str:
    """List top-level windows with their titles, handles, positions and sizes.

    Args:
        params (ListWindowsInput): optional title filter and empty-title toggle.

    Returns:
        str: JSON {"ok": true, "count": N, "windows": [{title, handle, left, top,
             width, height, is_minimized, is_maximized, is_active}, ...]}.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            wins = linuxio.list_windows(params.title_filter, params.include_empty_titles)
            return _ok(count=len(wins), windows=wins)
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(gw, "pygetwindow")):
        return e
    windows = gw.getAllWindows()
    out = []
    for w in windows:
        if not params.include_empty_titles and not (w.title and w.title.strip()):
            continue
        if params.title_filter and params.title_filter.lower() not in (w.title or "").lower():
            continue
        out.append(_window_to_dict(w))
    return _ok(count=len(out), windows=out)


@mcp.tool(
    name="get_active_window",
    annotations={
        "title": "Get Active Window",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_active_window() -> str:
    """Return information about the currently focused (active) window.

    Returns:
        str: JSON with the active window's title, handle, position and size,
             or {"ok": true, "window": null} if none is active.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            return _ok(window=linuxio.get_active_window())
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(gw, "pygetwindow")):
        return e
    win = gw.getActiveWindow()
    return _ok(window=_window_to_dict(win) if win else None)


class WindowTargetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: Optional[str] = Field(
        default=None, description="Window title (case-insensitive substring match)"
    )
    handle: Optional[int] = Field(
        default=None, description="Exact native window handle (HWND) / X11 window id from list_windows"
    )
    display: Optional[int] = Field(
        default=None, description="Linux only: target a specific X display number (e.g. Xvfb 99)"
    )


class MoveWindowInput(WindowTargetInput):
    x: int = Field(..., description="New left X position in pixels")
    y: int = Field(..., description="New top Y position in pixels")


@mcp.tool(
    name="move_window",
    annotations={
        "title": "Move Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def move_window(params: MoveWindowInput) -> str:
    """Move a window to a new top-left screen position.

    Identify the window by `handle` (preferred, exact) or `title` (substring).

    Args:
        params (MoveWindowInput): target window plus new x, y.

    Returns:
        str: JSON with the window's updated geometry, or an error if not found.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.title, params.handle, env=env)
            return _ok(window=linuxio.move_window(wid, params.x, params.y, env=env))
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(gw, "pygetwindow")):
        return e
    win = _find_window(params.title, params.handle)
    if win is None:
        return _err("No matching window found.", title=params.title, handle=params.handle)
    try:
        win.moveTo(params.x, params.y)
        return _ok(window=_window_to_dict(win))
    except Exception as exc:
        return _err(f"Failed to move window: {type(exc).__name__}: {exc}")


class ResizeWindowInput(WindowTargetInput):
    width: int = Field(..., description="New width in pixels", ge=1)
    height: int = Field(..., description="New height in pixels", ge=1)


@mcp.tool(
    name="resize_window",
    annotations={
        "title": "Resize Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def resize_window(params: ResizeWindowInput) -> str:
    """Resize a window to a new width and height.

    Args:
        params (ResizeWindowInput): target window plus new width, height.

    Returns:
        str: JSON with the window's updated geometry, or an error if not found.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.title, params.handle, env=env)
            return _ok(window=linuxio.resize_window(wid, params.width, params.height, env=env))
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(gw, "pygetwindow")):
        return e
    win = _find_window(params.title, params.handle)
    if win is None:
        return _err("No matching window found.", title=params.title, handle=params.handle)
    try:
        win.resizeTo(params.width, params.height)
        return _ok(window=_window_to_dict(win))
    except Exception as exc:
        return _err(f"Failed to resize window: {type(exc).__name__}: {exc}")


class WindowActionName(str, Enum):
    FOCUS = "focus"
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    RESTORE = "restore"
    CLOSE = "close"


class WindowActionInput(WindowTargetInput):
    action: WindowActionName = Field(..., description="Window action to perform")
    confirm_focus_disruption: bool = Field(default=False, description="Required after explicit user consent.")


@mcp.tool(
    name="window_action",
    annotations={
        "title": "Window Action",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def window_action(params: WindowActionInput) -> str:
    """Focus, minimize, maximize, restore or close a window.

    `close` is destructive - it sends the window a close request and the app may
    prompt to save. Identify the window by `handle` or `title`.

    Args:
        params (WindowActionInput): target window plus the action to run.

    Returns:
        str: JSON confirming the action, or an error if the window was not found.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Visible-desktop window action")):
        return e
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.title, params.handle, env=env)
            return _ok(**linuxio.window_action(wid, params.action.value, env=env))
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(gw, "pygetwindow")):
        return e
    win = _find_window(params.title, params.handle)
    if win is None:
        return _err("No matching window found.", title=params.title, handle=params.handle)
    try:
        action = params.action
        if action == WindowActionName.FOCUS:
            try:
                win.activate()
            except Exception:
                # activate() is flaky on Windows; restore+minimize toggle as fallback
                win.minimize()
                win.restore()
        elif action == WindowActionName.MINIMIZE:
            win.minimize()
        elif action == WindowActionName.MAXIMIZE:
            win.maximize()
        elif action == WindowActionName.RESTORE:
            win.restore()
        elif action == WindowActionName.CLOSE:
            win.close()
            return _ok(action=action.value, closed=True)
        return _ok(action=action.value, window=_window_to_dict(win))
    except Exception as exc:
        return _err(f"Failed to {params.action.value} window: {type(exc).__name__}: {exc}")


# =========================================================================== #
# PROCESS MANAGEMENT
# =========================================================================== #
class ListProcessesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name_filter: Optional[str] = Field(
        default=None, description="Only processes whose name contains this (case-insensitive)"
    )
    sort_by: str = Field(
        default="memory",
        description="Sort key: 'memory', 'cpu', 'name' or 'pid'",
    )
    limit: int = Field(default=50, description="Maximum number of processes to return", ge=1, le=1000)


@mcp.tool(
    name="list_processes",
    annotations={
        "title": "List Processes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_processes(params: ListProcessesInput) -> str:
    """List running processes with pid, name, memory and CPU usage.

    Args:
        params (ListProcessesInput): optional name filter, sort key and limit.

    Returns:
        str: JSON {"ok": true, "count": N, "processes": [{pid, name, username,
             memory_mb, cpu_percent}, ...]}.
    """
    if (e := _require(psutil, "psutil")):
        return e
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "memory_info", "cpu_percent"]):
        try:
            info = p.info
            name = info.get("name") or ""
            if params.name_filter and params.name_filter.lower() not in name.lower():
                continue
            mem = info.get("memory_info")
            procs.append(
                {
                    "pid": info.get("pid"),
                    "name": name,
                    "username": info.get("username"),
                    "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else None,
                    "cpu_percent": info.get("cpu_percent"),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = params.sort_by.lower()
    if key == "memory":
        procs.sort(key=lambda x: x["memory_mb"] or 0, reverse=True)
    elif key == "cpu":
        procs.sort(key=lambda x: x["cpu_percent"] or 0, reverse=True)
    elif key == "name":
        procs.sort(key=lambda x: (x["name"] or "").lower())
    elif key == "pid":
        procs.sort(key=lambda x: x["pid"] or 0)

    return _ok(count=len(procs[: params.limit]), processes=procs[: params.limit])


class KillProcessInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pid: Optional[int] = Field(default=None, description="Process ID to kill", ge=0)
    name: Optional[str] = Field(
        default=None,
        description="Kill ALL processes whose name matches exactly (case-insensitive). "
        "Use with care. Ignored if pid is given.",
    )
    force: bool = Field(
        default=False,
        description="Force kill (SIGKILL/terminate) instead of a graceful terminate request",
    )


@mcp.tool(
    name="kill_process",
    annotations={
        "title": "Kill Process",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def kill_process(params: KillProcessInput) -> str:
    """Kill a process by PID, or all processes matching an exact name.

    Provide either `pid` (preferred) or `name`. `force=true` kills hard; otherwise
    a graceful terminate is requested first. This is destructive and may cause the
    target application to lose unsaved data.

    Args:
        params (KillProcessInput): pid or name, and force flag.

    Returns:
        str: JSON {"ok": true, "killed": [{pid, name}], "count": N}, or an error.
    """
    if (e := _require(psutil, "psutil")):
        return e
    if params.pid is None and not params.name:
        return _err("Provide either 'pid' or 'name'.")

    targets: list[Any] = []
    if params.pid is not None:
        try:
            targets.append(psutil.Process(params.pid))
        except psutil.NoSuchProcess:
            return _err(f"No process with pid {params.pid}.")
    else:
        name_l = params.name.lower()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if (p.info.get("name") or "").lower() == name_l:
                    targets.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not targets:
            return _err(f"No running process named '{params.name}'.")

    killed = []
    errors = []
    for p in targets:
        try:
            pid, pname = p.pid, p.name()
            if params.force:
                p.kill()
            else:
                p.terminate()
            killed.append({"pid": pid, "name": pname})
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            errors.append({"pid": getattr(p, "pid", None), "error": type(exc).__name__})

    result: dict[str, Any] = {"killed": killed, "count": len(killed)}
    if errors:
        result["errors"] = errors
    return _ok(**result)


# =========================================================================== #
# SCREENSHOTS + CROPPING
# =========================================================================== #
class ScreenshotInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    monitor: int = Field(
        default=0,
        description="Monitor index: 0 = all monitors combined, 1 = primary, 2 = secondary, ...",
        ge=0,
    )
    region: Optional[list[int]] = Field(
        default=None,
        description="Optional [left, top, width, height] sub-region to capture (overrides monitor framing)",
        min_length=4,
        max_length=4,
    )
    output_path: Optional[str] = Field(
        default=None, description="Where to save the PNG; auto-generated in the capture dir if omitted"
    )
    hwnd: Optional[int] = Field(
        default=None,
        description="BACKGROUND CAPTURE: capture this specific window via PrintWindow, even if "
        "it is unfocused, occluded by other windows, or on an off-screen desktop.",
    )
    window_title: Optional[str] = Field(
        default=None, description="BACKGROUND CAPTURE by window title (substring) instead of a handle."
    )
    client_only: bool = Field(
        default=False, description="For window capture: capture only the client area (no title bar/borders)."
    )
    display: Optional[int] = Field(
        default=None, description="Linux only: X display number of the target window (e.g. Xvfb 99)"
    )


@mcp.tool(
    name="screenshot",
    annotations={
        "title": "Take Screenshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def screenshot(params: ScreenshotInput) -> str:
    """Capture a screenshot of a monitor (or a pixel region) and save it as PNG.

    BACKGROUND CAPTURE: set `hwnd` or `window_title` to capture one specific window
    via Win32 PrintWindow - this works even when the window is NOT focused, is hidden
    behind other windows, or runs on an off-screen/headless desktop.

    Args:
        params (ScreenshotInput): monitor index, optional region, output path, optional
            window target and client_only flag.

    Returns:
        str: JSON {"ok": true, "path": "...", "width": W, "height": H}.
    """
    # Per-window background capture
    if params.hwnd is not None or params.window_title:
        if (e := _require(Image, "pillow")):
            return e
        out = (
            Path(params.output_path)
            if params.output_path
            else _capture_dir() / f"window-{_timestamp()}.png"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        if IS_LINUX:
            if (e := _require(linuxio, "linuxio")):
                return e
            try:
                env = _linux_env(params.display)
                wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
                img, rendered = linuxio.capture_window(wid, client_only=params.client_only, env=env)
                img.save(out)
                return _ok(path=str(out), width=img.width, height=img.height,
                           mode="window", window_hwnd=wid, rendered_ok=rendered)
            except linuxio.LinuxIOError as exc:
                return _err(str(exc))
        if (e := _require(winio, "winio (Windows)")):
            return e
        try:
            top = winio.find_top_window(params.window_title, params.hwnd)
            img, rendered = winio.capture_window(top, client_only=params.client_only)
            img.save(out)
            return _ok(
                path=str(out), width=img.width, height=img.height,
                mode="window", window_hwnd=top, rendered_ok=rendered,
            )
        except winio.WinIOError as exc:
            return _err(str(exc))

    if (e := _require(mss, "mss")):
        return e
    out = Path(params.output_path) if params.output_path else _capture_dir() / f"screenshot-{_timestamp()}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with mss.mss() as sct:
        if params.region:
            left, top, width, height = params.region
            grab_area = {"left": left, "top": top, "width": width, "height": height}
        else:
            if params.monitor >= len(sct.monitors):
                return _err(
                    f"Monitor {params.monitor} not found; {len(sct.monitors) - 1} monitor(s) available."
                )
            grab_area = sct.monitors[params.monitor]
        img = sct.grab(grab_area)
        mss.tools.to_png(img.rgb, img.size, output=str(out))
    return _ok(path=str(out), width=img.size.width, height=img.size.height)


class CropInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    input_path: str = Field(..., description="Path to an existing image to crop", min_length=1)
    left: int = Field(..., description="Left X of the crop box", ge=0)
    top: int = Field(..., description="Top Y of the crop box", ge=0)
    width: int = Field(..., description="Crop width in pixels", ge=1)
    height: int = Field(..., description="Crop height in pixels", ge=1)
    output_path: Optional[str] = Field(
        default=None, description="Where to save the cropped image; auto-generated if omitted"
    )


@mcp.tool(
    name="crop_image",
    annotations={
        "title": "Crop Image",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crop_image(params: CropInput) -> str:
    """Crop an existing image file to a rectangular sub-region.

    Args:
        params (CropInput): source path, crop box (left/top/width/height), output path.

    Returns:
        str: JSON {"ok": true, "path": "...", "width": W, "height": H}.
    """
    if (e := _require(Image, "pillow")):
        return e
    src = Path(params.input_path)
    if not src.exists():
        return _err(f"Input image not found: {src}")
    out = (
        Path(params.output_path)
        if params.output_path
        else _capture_dir() / f"crop-{_timestamp()}{src.suffix or '.png'}"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        box = (params.left, params.top, params.left + params.width, params.top + params.height)
        cropped = im.crop(box)
        cropped.save(out)
        w, h = cropped.size
    return _ok(path=str(out), width=w, height=h)


# =========================================================================== #
# SCREEN RECORDING
# =========================================================================== #
class _Recorder:
    """Background thread that captures the screen to an mp4 file."""

    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.path: Optional[str] = None
        self.fps: int = 15
        self.region: Optional[dict[str, int]] = None
        self.monitor: int = 1
        self.frames: int = 0
        self.started_at: Optional[float] = None
        self.error: Optional[str] = None

    @property
    def active(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _run(self) -> None:
        import imageio.v2 as imageio

        frame_interval = 1.0 / self.fps
        try:
            with mss.mss() as sct:
                area = self.region if self.region else sct.monitors[self.monitor]
                writer = imageio.get_writer(
                    self.path, fps=self.fps, codec="libx264", quality=8, macro_block_size=None
                )
                try:
                    next_t = time.time()
                    while not self.stop_event.is_set():
                        img = sct.grab(area)
                        frame = np.asarray(img)[:, :, :3][:, :, ::-1]  # BGRA -> RGB
                        writer.append_data(frame)
                        self.frames += 1
                        next_t += frame_interval
                        sleep = next_t - time.time()
                        if sleep > 0:
                            time.sleep(sleep)
                        else:
                            next_t = time.time()
                finally:
                    writer.close()
        except Exception as exc:  # pragma: no cover
            self.error = f"{type(exc).__name__}: {exc}"


_recorder = _Recorder()


class StartRecordingInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    fps: int = Field(default=15, description="Frames per second to capture", ge=1, le=60)
    monitor: int = Field(default=1, description="Monitor index to record (1 = primary)", ge=1)
    region: Optional[list[int]] = Field(
        default=None,
        description="Optional [left, top, width, height] region to record instead of a full monitor",
        min_length=4,
        max_length=4,
    )
    output_path: Optional[str] = Field(
        default=None, description="Where to save the mp4; auto-generated in the capture dir if omitted"
    )


@mcp.tool(
    name="start_screen_recording",
    annotations={
        "title": "Start Screen Recording",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def start_screen_recording(params: StartRecordingInput) -> str:
    """Begin recording the screen to an mp4 file in a background thread.

    Only one recording can run at a time. Call `stop_screen_recording` to finish
    and flush the file.

    Args:
        params (StartRecordingInput): fps, monitor, optional region and output path.

    Returns:
        str: JSON {"ok": true, "path": "...", "fps": N, "recording": true}.
    """
    if (e := _require(mss, "mss")):
        return e
    if (e := _require(np, "numpy")):
        return e
    if _recorder.active:
        return _err("A recording is already in progress.", path=_recorder.path)

    out = Path(params.output_path) if params.output_path else _capture_dir() / f"recording-{_timestamp()}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    _recorder.__init__()  # reset state
    _recorder.path = str(out)
    _recorder.fps = params.fps
    _recorder.monitor = params.monitor
    _recorder.region = (
        {"left": params.region[0], "top": params.region[1], "width": params.region[2], "height": params.region[3]}
        if params.region
        else None
    )
    _recorder.started_at = time.time()
    _recorder.stop_event.clear()
    _recorder.thread = threading.Thread(target=_recorder._run, daemon=True)
    _recorder.thread.start()
    time.sleep(0.2)
    if _recorder.error:
        return _err(f"Recording failed to start: {_recorder.error}")
    return _ok(path=str(out), fps=params.fps, monitor=params.monitor, recording=True)


@mcp.tool(
    name="stop_screen_recording",
    annotations={
        "title": "Stop Screen Recording",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def stop_screen_recording() -> str:
    """Stop the active screen recording and finalize the mp4 file.

    Returns:
        str: JSON {"ok": true, "path": "...", "frames": N, "duration_seconds": S}.
    """
    if not _recorder.active and _recorder.path is None:
        return _err("No recording is in progress.")
    _recorder.stop_event.set()
    if _recorder.thread:
        _recorder.thread.join(timeout=30)
    duration = round(time.time() - _recorder.started_at, 2) if _recorder.started_at else None
    if _recorder.error:
        return _err(f"Recording error: {_recorder.error}", path=_recorder.path)
    return _ok(path=_recorder.path, frames=_recorder.frames, duration_seconds=duration)


@mcp.tool(
    name="recording_status",
    annotations={
        "title": "Recording Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def recording_status() -> str:
    """Report whether a screen recording is currently active.

    Returns:
        str: JSON {"ok": true, "recording": bool, "path": str|null, "frames": N,
             "elapsed_seconds": S|null}.
    """
    elapsed = round(time.time() - _recorder.started_at, 2) if (_recorder.active and _recorder.started_at) else None
    return _ok(
        recording=_recorder.active,
        path=_recorder.path,
        frames=_recorder.frames,
        elapsed_seconds=elapsed,
    )


# =========================================================================== #
# WIN32 BACKGROUND INPUT + HEADLESS DESKTOP
# =========================================================================== #
class WinTargetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    hwnd: Optional[int] = Field(default=None, description="Native window handle / X11 window id (from list_windows)")
    window_title: Optional[str] = Field(
        default=None, description="Top-level window title substring (used if hwnd is omitted)"
    )
    display: Optional[int] = Field(
        default=None,
        description="Linux only: target a specific X display number (e.g. an Xvfb virtual display 99)",
    )


@mcp.tool(
    name="list_child_windows",
    annotations={
        "title": "List Child Controls",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_child_windows(params: WinTargetInput) -> str:
    """Enumerate the child controls of a window (class, text, client rect, handle).

    Useful for finding the exact control handle to target with background input -
    e.g. the 'Edit' control inside Notepad - and its position for background clicks.

    Args:
        params (WinTargetInput): the parent window by hwnd or title.

    Returns:
        str: JSON {"ok": true, "parent_hwnd": N, "count": N, "children": [
             {handle, class, text, left, top, width, height, visible}, ...]}.
             Coordinates are relative to the parent window's top-left.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
            children = linuxio.list_child_windows(wid, env=env)
            return _ok(parent_hwnd=wid, count=len(children), children=children)
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        top = winio.find_top_window(params.window_title, params.hwnd)
        children = winio.list_child_windows(top)
        return _ok(parent_hwnd=top, count=len(children), children=children)
    except winio.WinIOError as exc:
        return _err(str(exc))


class WinSendKeysInput(WinTargetInput):
    keys: list[str] = Field(
        ...,
        description="Key names to send via WM_KEYDOWN/UP, e.g. ['enter'] or ['ctrl','a']. "
        "NOTE: message-based modifier combos are unreliable for apps that check physical "
        "key state; prefer win_set_control_text for text entry.",
        min_length=1,
        max_length=6,
    )


@mcp.tool(
    name="win_send_keys",
    annotations={
        "title": "Send Keys To Window (Background)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def win_send_keys(params: WinSendKeysInput) -> str:
    """Post key presses to a specific window WITHOUT focusing it (Win32 messages).

    Args:
        params (WinSendKeysInput): target window plus key names.

    Returns:
        str: JSON confirming the keys posted to the resolved control.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
            res = linuxio.send_keys(wid, params.keys, env=env)
            return _ok(window_hwnd=wid, **res)
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        top = winio.find_top_window(params.window_title, params.hwnd)
        target = params.hwnd if params.hwnd is not None else winio.focused_control(top)
        res = winio.send_keys(target, params.keys)
        return _ok(window_hwnd=top, **res)
    except winio.WinIOError as exc:
        return _err(str(exc))


class WinSetTextInput(WinTargetInput):
    text: str = Field(..., description="Text to set on the control")


@mcp.tool(
    name="win_set_control_text",
    annotations={
        "title": "Set Control Text (Background)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def win_set_control_text(params: WinSetTextInput) -> str:
    """Set a control's text directly via WM_SETTEXT (reliable, no focus needed).

    Pass the control's `hwnd` (from list_child_windows) - e.g. the Edit control of
    a background Notepad - to replace its text without bringing the window forward.

    Args:
        params (WinSetTextInput): target control by hwnd (preferred) or title, plus text.

    Returns:
        str: JSON {"ok": true, "target_hwnd": N, "text_len": N}.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = params.hwnd if params.hwnd is not None else linuxio.find_window(params.window_title, None, env=env)
            return _ok(**linuxio.set_control_text(wid, params.text, env=env))
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        target = (
            params.hwnd if params.hwnd is not None else winio.find_top_window(params.window_title, None)
        )
        res = winio.set_control_text(target, params.text)
        return _ok(**res)
    except winio.WinIOError as exc:
        return _err(str(exc))


class HeadlessDesktopInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(
        default="LowLevelCUHeadless",
        description="Name of the off-screen desktop",
        min_length=1,
        max_length=64,
    )


class ShowHeadlessDesktopInput(HeadlessDesktopInput):
    instruction: str = Field(
        default="Complete the requested manual step.",
        description="Short instruction displayed in the non-dismissible top safety banner",
        min_length=1,
        max_length=240,
    )
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Must be true after the user explicitly requests an interactive desktop handoff.",
    )


@mcp.tool(
    name="create_headless_desktop",
    annotations={
        "title": "Create Headless Desktop",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def create_headless_desktop(params: HeadlessDesktopInput) -> str:
    """Create an off-screen Win32 desktop for running GUI apps invisibly.

    Apps launched on this desktop have a real GUI (so they run and can be automated
    and captured via PrintWindow) but never appear on the visible desktop. This is
    the 'headless but with GUI' mode.

    Args:
        params (HeadlessDesktopInput): desktop name.

    Returns:
        str: JSON {"ok": true, "name": "...", "handle": N, "full": "WinSta0\\\\..."}.
    """
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        return _ok(**winio.create_desktop(params.name))
    except winio.WinIOError as exc:
        return _err(str(exc))


class LaunchHeadlessInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(default="LowLevelCUHeadless", description="Off-screen desktop name", min_length=1)
    command: str = Field(..., description="Command line of the GUI app to launch (e.g. 'notepad.exe')", min_length=1)


@mcp.tool(
    name="launch_on_headless_desktop",
    annotations={
        "title": "Launch App On Headless Desktop",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def launch_on_headless_desktop(params: LaunchHeadlessInput) -> str:
    """Launch a GUI application on an off-screen desktop (creates it if needed).

    The process runs with a full GUI on the hidden desktop. Use list_headless_windows
    to find its windows, then drive them with background input and capture them with
    screenshot(hwnd=...). The visible desktop is never touched.

    Args:
        params (LaunchHeadlessInput): desktop name and command line.

    Returns:
        str: JSON {"ok": true, "desktop": "...", "pid": N, "command": "..."}.
    """
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        return _ok(**winio.launch_on_desktop(params.name, params.command))
    except winio.WinIOError as exc:
        return _err(str(exc))


@mcp.tool(
    name="list_headless_windows",
    annotations={
        "title": "List Headless Desktop Windows",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_headless_windows(params: HeadlessDesktopInput) -> str:
    """List the top-level windows living on an off-screen desktop.

    Args:
        params (HeadlessDesktopInput): desktop name.

    Returns:
        str: JSON {"ok": true, "name": "...", "count": N, "windows": [
             {handle, title, class, width, height}, ...]}.
    """
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        wins = winio.list_desktop_windows(params.name)
        return _ok(name=params.name, count=len(wins), windows=wins)
    except winio.WinIOError as exc:
        return _err(str(exc))


@mcp.tool(
    name="close_headless_desktop",
    annotations={
        "title": "Close Headless Desktop",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def close_headless_desktop(params: HeadlessDesktopInput) -> str:
    """Release this server's handle to an off-screen desktop.

    The desktop is fully freed by Windows once no process is still running on it,
    so close any apps you launched there first.

    Args:
        params (HeadlessDesktopInput): desktop name.

    Returns:
        str: JSON {"ok": true, "name": "...", "closed": bool}.
    """
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        return _ok(**winio.close_desktop(params.name))
    except winio.WinIOError as exc:
        return _err(str(exc))


# =========================================================================== #
# TEMPORARY VISIBILITY (show for login, then hide again)
# =========================================================================== #
class ShowWindowInput(WinTargetInput):
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Must be true after the user explicitly requests a visible foreground handoff.",
    )


@mcp.tool(
    name="show_window",
    annotations={
        "title": "Show Window (Foreground)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def show_window(params: ShowWindowInput) -> str:
    """Make a hidden/minimized window visible and bring it to the foreground.

    Useful when an automated app on the normal desktop hits a step that needs the
    human - typically an interactive LOGIN. Show it, let the user sign in, then call
    `hide_window` to tuck it away and resume background automation.

    Args:
        params (WinTargetInput): the window by hwnd or title.

    Returns:
        str: JSON {"ok": true, "hwnd": N, "visible": true}.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Showing a foreground window")):
        return e
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
            return _ok(**linuxio.show_window(wid, env=env))
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        top = winio.find_top_window(params.window_title, params.hwnd)
        return _ok(**winio.show_window(top))
    except winio.WinIOError as exc:
        return _err(str(exc))


class HideWindowInput(WinTargetInput):
    minimize: bool = Field(
        default=False,
        description="Minimize instead of fully hiding (SW_HIDE removes it from the taskbar)",
    )


@mcp.tool(
    name="hide_window",
    annotations={
        "title": "Hide Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def hide_window(params: HideWindowInput) -> str:
    """Hide a window again after it was shown (e.g. once login is complete).

    Args:
        params (HideWindowInput): the window by hwnd or title, and a minimize flag.

    Returns:
        str: JSON {"ok": true, "hwnd": N, "visible": false}.
    """
    if IS_LINUX:
        if (e := _require(linuxio, "linuxio")):
            return e
        try:
            env = _linux_env(params.display)
            wid = linuxio.find_window(params.window_title, params.hwnd, env=env)
            return _ok(**linuxio.hide_window(wid, minimize=params.minimize, env=env))
        except linuxio.LinuxIOError as exc:
            return _err(str(exc))
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        top = winio.find_top_window(params.window_title, params.hwnd)
        return _ok(**winio.hide_window(top, minimize=params.minimize))
    except winio.WinIOError as exc:
        return _err(str(exc))


@mcp.tool(
    name="show_headless_desktop",
    annotations={
        "title": "Show Headless Desktop (Interactive)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def show_headless_desktop(params: ShowHeadlessDesktopInput) -> str:
    """Temporarily switch the live screen to a headless desktop for human interaction.

    The entire off-screen desktop (and the apps running on it) becomes interactive
    and visible, so a person can complete a LOGIN or any manual step. A topmost,
    non-dismissible banner explains what to do and provides an EMERGENCY EXIT button
    that immediately restores the normal desktop. Call `hide_headless_desktop` to
    switch back normally afterwards.

    Args:
        params (ShowHeadlessDesktopInput): desktop name and banner instruction.

    Returns:
        str: JSON {"ok": true, "name": "...", "visible": true,
        "safety_banner": true, "note": "..."}.
    """
    if (e := _focus_guard(params.confirm_focus_disruption, "Interactive desktop switch")):
        return e
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        return _ok(**winio.show_desktop(params.name, params.instruction))
    except winio.WinIOError as exc:
        return _err(str(exc))


@mcp.tool(
    name="hide_headless_desktop",
    annotations={
        "title": "Hide Headless Desktop",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def hide_headless_desktop(params: HeadlessDesktopInput) -> str:
    """Switch the live screen back to the normal desktop after show_headless_desktop.

    Args:
        params (HeadlessDesktopInput): the off-screen desktop name (for symmetry).

    Returns:
        str: JSON {"ok": true, "restored": true}.
    """
    if (e := _require(winio, "winio (Windows)")):
        return e
    try:
        return _ok(**winio.hide_desktop(params.name))
    except winio.WinIOError as exc:
        return _err(str(exc))


# =========================================================================== #
# AUTOHOTKEY ADD-IN
# =========================================================================== #
@mcp.tool(
    name="ahk_status",
    annotations={
        "title": "AutoHotkey Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ahk_status() -> str:
    """Report whether AutoHotkey is installed and where.

    Returns:
        str: JSON {"ok": true, "installed": bool, "path": "...", "version": "v2", ...}.
    """
    if (e := _require(ahk_addon, "ahk")):
        return e
    return _ok(**ahk_addon.status())


class RunAhkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., description="AutoHotkey script source to run", min_length=1)
    args: Optional[list[str]] = Field(default=None, description="Command-line args passed to the script")
    timeout: float = Field(default=60.0, description="Max seconds before the script is killed", ge=1, le=3600)
    exe_path: Optional[str] = Field(default=None, description="Override path to the AutoHotkey interpreter")


@mcp.tool(
    name="run_ahk",
    annotations={
        "title": "Run AutoHotkey Script",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def run_ahk(params: RunAhkInput) -> str:
    """Run an inline AutoHotkey script and capture its output.

    The script MUST terminate (call ExitApp, or be non-persistent) or it runs until
    the timeout. Emit output with FileAppend to the target "*" (stdout). AHK is ideal
    for reliable background input (ControlSend/ControlClick) and real hotkeys.

    Args:
        params (RunAhkInput): script source, optional args, timeout, optional exe path.

    Returns:
        str: JSON {"ok": bool, "returncode": int, "stdout": "...", "stderr": "...", "exe": "..."}.
    """
    if (e := _require(ahk_addon, "ahk")):
        return e
    try:
        return _ok(**ahk_addon.run_script(params.code, args=params.args, timeout=params.timeout, exe_path=params.exe_path))
    except ahk_addon.AhkError as exc:
        return _err(str(exc))


class AhkControlSendInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    text: str = Field(..., description="Text to send (or AHK key syntax if as_keys=true, e.g. '^a{Del}')")
    window: str = Field(
        ...,
        description="AHK window target: 'ahk_id <HWND>', 'ahk_exe notepad.exe', or a window title",
    )
    control: str = Field(default="", description="AHK control target (e.g. 'ahk_id <controlHWND>' or ClassNN); blank = focused control")
    as_keys: bool = Field(default=False, description="Interpret text as AHK key sequence instead of literal text")
    timeout: float = Field(default=30.0, description="Max seconds", ge=1, le=600)


@mcp.tool(
    name="ahk_control_send",
    annotations={
        "title": "AHK ControlSend (Background Input)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def ahk_control_send(params: AhkControlSendInput) -> str:
    """Send text or keystrokes to a background window/control via AutoHotkey ControlSend.

    Works without focusing the window and is often more reliable than raw WM_CHAR for
    complex apps. Target a HWND with 'ahk_id <handle>'.

    Args:
        params (AhkControlSendInput): text, window/control targets, as_keys, timeout.

    Returns:
        str: JSON with the AHK run result.
    """
    if (e := _require(ahk_addon, "ahk")):
        return e
    try:
        return _ok(
            **ahk_addon.control_send(
                params.text, params.window, control=params.control,
                as_keys=params.as_keys, timeout=params.timeout,
            )
        )
    except ahk_addon.AhkError as exc:
        return _err(str(exc))


# =========================================================================== #
# LINUX VIRTUAL DISPLAY (Xvfb headless-but-with-GUI)
# =========================================================================== #
@mcp.tool(
    name="linux_status",
    annotations={
        "title": "Linux Automation Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def linux_status() -> str:
    """Report Linux X11 automation tooling availability (xdotool, wmctrl, Xvfb, …).

    Returns:
        str: JSON {"ok": true, "display": ":0", "session_type": "x11", "xdotool": bool, ...}.
    """
    if (e := _require(linuxio, "linuxio")):
        return e
    return _ok(**linuxio.available())


class CreateVirtualDisplayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display: int = Field(default=99, description="Display number, e.g. 99 → ':99'", ge=1, le=9999)
    width: int = Field(default=1280, description="Virtual screen width", ge=16, le=16384)
    height: int = Field(default=800, description="Virtual screen height", ge=16, le=16384)
    depth: int = Field(default=24, description="Color depth", ge=8, le=32)


@mcp.tool(
    name="create_virtual_display",
    annotations={
        "title": "Create Virtual Display (Xvfb)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def create_virtual_display(params: CreateVirtualDisplayInput) -> str:
    """Start an Xvfb virtual display — the Linux 'headless but with GUI' mode.

    GUI apps launched on it run with a real X server but no physical screen, so they
    can be automated (xdotool) and screenshotted (mss) without occupying the visible
    desktop. The Linux counterpart of the Windows headless desktop.

    Args:
        params (CreateVirtualDisplayInput): display number, width, height, depth.

    Returns:
        str: JSON {"ok": true, "display": ":99", "size": "1280x800x24", "pid": N}.
    """
    if (e := _require(linuxio, "linuxio")):
        return e
    try:
        return _ok(**linuxio.create_virtual_display(params.display, params.width, params.height, params.depth))
    except linuxio.LinuxIOError as exc:
        return _err(str(exc))


class LaunchVirtualInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    display: int = Field(default=99, description="Xvfb display number to launch on", ge=1, le=9999)
    command: str = Field(..., description="Command line of the GUI app to launch", min_length=1)


@mcp.tool(
    name="launch_on_virtual_display",
    annotations={
        "title": "Launch App On Virtual Display",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def launch_on_virtual_display(params: LaunchVirtualInput) -> str:
    """Launch a GUI app on an Xvfb virtual display (creates it if needed).

    Args:
        params (LaunchVirtualInput): display number and command line.

    Returns:
        str: JSON {"ok": true, "display": ":99", "pid": N, "command": "..."}.
    """
    if (e := _require(linuxio, "linuxio")):
        return e
    try:
        return _ok(**linuxio.launch_on_virtual_display(params.display, params.command))
    except linuxio.LinuxIOError as exc:
        return _err(str(exc))


class VirtualDisplayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display: int = Field(default=99, description="Xvfb display number", ge=1, le=9999)


@mcp.tool(
    name="list_virtual_display_windows",
    annotations={
        "title": "List Virtual Display Windows",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_virtual_display_windows(params: VirtualDisplayInput) -> str:
    """List the windows present on an Xvfb virtual display.

    Args:
        params (VirtualDisplayInput): display number.

    Returns:
        str: JSON {"ok": true, "count": N, "windows": [...]}.
    """
    if (e := _require(linuxio, "linuxio")):
        return e
    try:
        wins = linuxio.list_virtual_display_windows(params.display)
        return _ok(display=f":{params.display}", count=len(wins), windows=wins)
    except linuxio.LinuxIOError as exc:
        return _err(str(exc))


class ScreenshotVirtualInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    display: int = Field(default=99, description="Xvfb display number to capture", ge=1, le=9999)
    output_path: Optional[str] = Field(default=None, description="Where to save the PNG")


@mcp.tool(
    name="screenshot_virtual_display",
    annotations={
        "title": "Screenshot Virtual Display",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def screenshot_virtual_display(params: ScreenshotVirtualInput) -> str:
    """Capture the whole Xvfb virtual display to a PNG.

    Args:
        params (ScreenshotVirtualInput): display number and output path.

    Returns:
        str: JSON {"ok": true, "path": "...", "width": W, "height": H}.
    """
    if (e := _require(linuxio, "linuxio")):
        return e
    if (e := _require(Image, "pillow")):
        return e
    out = Path(params.output_path) if params.output_path else _capture_dir() / f"xvfb-{_timestamp()}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = linuxio.capture_virtual_display(params.display)
        img.save(out)
        return _ok(path=str(out), width=img.width, height=img.height, display=f":{params.display}")
    except linuxio.LinuxIOError as exc:
        return _err(str(exc))


@mcp.tool(
    name="stop_virtual_display",
    annotations={
        "title": "Stop Virtual Display",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def stop_virtual_display(params: VirtualDisplayInput) -> str:
    """Stop an Xvfb virtual display and terminate the apps launched on it.

    Args:
        params (VirtualDisplayInput): display number.

    Returns:
        str: JSON {"ok": true, "display": ":99", "stopped": true}.
    """
    if (e := _require(linuxio, "linuxio")):
        return e
    try:
        return _ok(**linuxio.stop_virtual_display(params.display))
    except linuxio.LinuxIOError as exc:
        return _err(str(exc))


# =========================================================================== #
# EPHEMERAL WSL (Linux on a Windows host, on demand)
# =========================================================================== #
@mcp.tool(
    name="wsl_status",
    annotations={
        "title": "WSL Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wsl_status() -> str:
    """Report whether WSL is available on this Windows host.

    Returns:
        str: JSON {"ok": true, "available": bool, "version": "...", ...}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    return _ok(**wslio.available())


@mcp.tool(
    name="wsl_list_distros",
    annotations={
        "title": "List WSL Distros",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wsl_list_distros() -> str:
    """List installed WSL distros with state, version and default flag.

    Returns:
        str: JSON {"ok": true, "count": N, "distros": [{name, state, version, default}, ...]}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    try:
        d = wslio.list_distros()
        return _ok(count=len(d), distros=d)
    except wslio.WslError as exc:
        return _err(str(exc))


class WslCreateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: Optional[str] = Field(
        default=None, description="Name for the throwaway distro (auto-generated if omitted)"
    )
    rootfs_url: Optional[str] = Field(
        default=None, description="URL of a rootfs .tar.gz to import (defaults to latest Alpine minirootfs)"
    )
    clone_from: Optional[str] = Field(
        default=None, description="Instead of downloading, clone an existing distro by name (export+import)"
    )
    base_tar: Optional[str] = Field(
        default=None, description="Path to a local rootfs .tar or .tar.gz to import"
    )
    timeout: float = Field(default=1800.0, description="Max seconds for provisioning", ge=10, le=7200)


@mcp.tool(
    name="wsl_create_temp",
    annotations={
        "title": "Create Throwaway WSL Distro",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def wsl_create_temp(params: WslCreateInput) -> str:
    """Provision a throwaway WSL distro on demand for running Linux software.

    By default downloads a tiny Alpine minirootfs (a few MB) and imports it, leaving
    existing distros untouched. Use wsl_run to run commands in it and wsl_destroy to
    tear it down. Alternatively clone_from an existing distro or import base_tar.

    Args:
        params (WslCreateInput): optional name, rootfs_url, clone_from, base_tar, timeout.

    Returns:
        str: JSON {"ok": true, "name": "...", "install_dir": "...", "source": "alpine"}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    try:
        return _ok(
            **wslio.create_temp(
                name=params.name, rootfs_url=params.rootfs_url,
                clone_from=params.clone_from, base_tar=params.base_tar, timeout=params.timeout,
            )
        )
    except wslio.WslError as exc:
        return _err(str(exc))


class WslRunInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    distro: str = Field(..., description="Distro name to run in (e.g. from wsl_create_temp)", min_length=1)
    command: str = Field(..., description="Shell command to run inside the distro", min_length=1)
    user: Optional[str] = Field(default=None, description="Run as this Linux user (default: distro default)")
    cwd: Optional[str] = Field(default=None, description="Working directory inside the distro")
    timeout: float = Field(default=120.0, description="Max seconds", ge=1, le=3600)


@mcp.tool(
    name="wsl_run",
    annotations={
        "title": "Run Command In WSL",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def wsl_run(params: WslRunInput) -> str:
    """Run a shell command inside a WSL distro and capture stdout/stderr/exit code.

    Args:
        params (WslRunInput): distro, command, optional user, cwd and timeout.

    Returns:
        str: JSON {"ok": true, "distro": "...", "returncode": N, "stdout": "...", "stderr": "..."}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    try:
        res = wslio.run(params.distro, params.command, user=params.user, cwd=params.cwd, timeout=params.timeout)
        return _ok(**res)
    except wslio.WslError as exc:
        return _err(str(exc))
    except subprocess.TimeoutExpired:
        return _err(f"WSL command timed out after {params.timeout}s")


@mcp.tool(
    name="wsl_list_temp",
    annotations={
        "title": "List Throwaway WSL Distros",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wsl_list_temp() -> str:
    """List the throwaway distros this server session provisioned.

    Returns:
        str: JSON {"ok": true, "count": N, "distros": [{name, install_dir, source, created_at}, ...]}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    t = wslio.list_temp()
    return _ok(count=len(t), distros=t)


class WslDestroyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Distro name to terminate and unregister", min_length=1)
    remove_files: bool = Field(default=True, description="Also delete the distro's backing files")


@mcp.tool(
    name="wsl_destroy",
    annotations={
        "title": "Destroy WSL Distro",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wsl_destroy(params: WslDestroyInput) -> str:
    """Terminate and unregister a WSL distro, deleting its files (irreversible).

    Args:
        params (WslDestroyInput): distro name and whether to delete files.

    Returns:
        str: JSON {"ok": true, "name": "...", "destroyed": true}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    try:
        return _ok(**wslio.destroy(params.name, remove_files=params.remove_files))
    except wslio.WslError as exc:
        return _err(str(exc))


@mcp.tool(
    name="wsl_destroy_all_temp",
    annotations={
        "title": "Destroy All Throwaway WSL Distros",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wsl_destroy_all_temp() -> str:
    """Tear down every throwaway distro provisioned in this session.

    Returns:
        str: JSON {"ok": true, "destroyed": [...], "count": N}.
    """
    if (e := _require(wslio, "wslio")):
        return e
    return _ok(**wslio.destroy_all())


# =========================================================================== #
# ADMIN / ELEVATION + BOOT STARTUP
# =========================================================================== #
@mcp.tool(
    name="is_admin",
    annotations={
        "title": "Check Admin Privileges",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def is_admin() -> str:
    """Report whether this server process is running elevated (as Administrator).

    Returns:
        str: JSON {"ok": true, "is_admin": bool, "platform": "Windows"}.
    """
    return _ok(is_admin=_is_admin(), platform=platform.system())


class RunAsAdminInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    command: str = Field(..., description="Command line to execute with elevation (via cmd.exe)", min_length=1)
    timeout: float = Field(default=120.0, description="Max seconds to wait", ge=1, le=3600)
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Required after explicit user consent because Windows may show a UAC secure-desktop prompt.",
    )


@mcp.tool(
    name="run_command_as_admin",
    annotations={
        "title": "Run Command As Admin",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def run_command_as_admin(params: RunAsAdminInput) -> str:
    """Run a shell command with Administrator privileges.

    If the server is not already elevated this triggers a Windows UAC prompt that
    the user must approve. Output is captured and returned. This runs commands
    with full administrative rights - use with care.

    Args:
        params (RunAsAdminInput): the command line and a timeout.

    Returns:
        str: JSON {"ok": bool, "returncode": int, "output": "...", "elevated_prompt": bool}.
    """
    if os.name != "nt":
        return _err("run_command_as_admin requires Windows.")
    if not _is_admin():
        if (e := _focus_guard(params.confirm_focus_disruption, "UAC elevation prompt")):
            return e
    escaped = params.command.replace("'", "''")
    body = f"& $env:ComSpec /c '{escaped}'\nexit $LASTEXITCODE"
    needed_prompt = not _is_admin()
    result = _run_powershell(body, require_admin=True, timeout=params.timeout)
    return json.dumps(
        {
            "ok": result["ok"],
            "returncode": result["returncode"],
            "output": result["output"],
            "elevated_prompt": needed_prompt,
        },
        indent=2,
        default=str,
    )


class InstallStartupInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    run_as_admin: bool = Field(
        default=False,
        description="Opt in to highest privileges; false avoids a UAC focus interruption and is the safe default.",
    )
    http: bool = Field(
        default=True,
        description="Start the server in HTTP mode at boot (recommended; a stdio server has no client to talk to at boot)",
    )
    host: str = Field(default=DEFAULT_HTTP_HOST, description="Host for HTTP mode")
    port: int = Field(default=DEFAULT_HTTP_PORT, description="Port for HTTP mode", ge=1, le=65535)
    confirm_focus_disruption: bool = Field(
        default=False,
        description="Required only when run_as_admin=true and Windows must display a UAC prompt.",
    )


@mcp.tool(
    name="install_startup",
    annotations={
        "title": "Install Boot Startup",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def install_startup(params: InstallStartupInput) -> str:
    """Install a scheduled task so this server starts automatically at user logon.

    By default the task runs without elevation and launches the server in HTTP
    mode through pythonw.exe, so logon produces no terminal or focus change.

    Args:
        params (InstallStartupInput): run_as_admin, http, host and port options.

    Returns:
        str: JSON {"ok": bool, "output": "...", "task_name": "...", "run_as_admin": bool}.
    """
    if os.name != "nt":
        return _err("install_startup requires Windows.")
    if params.run_as_admin and not _is_admin():
        if (e := _focus_guard(params.confirm_focus_disruption, "UAC elevation prompt")):
            return e
    result = _install_startup(params.http, params.host, params.port, params.run_as_admin)
    return json.dumps(
        {
            "ok": result["ok"],
            "task_name": TASK_NAME,
            "run_as_admin": params.run_as_admin,
            "mode": "http" if params.http else "stdio",
            "endpoint": f"http://{params.host}:{params.port}/mcp" if params.http else None,
            "output": result["output"],
        },
        indent=2,
        default=str,
    )


@mcp.tool(
    name="uninstall_startup",
    annotations={
        "title": "Uninstall Boot Startup",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def uninstall_startup() -> str:
    """Remove user startup without showing UAC; elevated tasks may require an elevated server.

    Returns:
        str: JSON {"ok": bool, "output": "...", "task_name": "..."}.
    """
    if os.name != "nt":
        return _err("uninstall_startup requires Windows.")
    result = _uninstall_startup()
    return json.dumps(
        {"ok": result["ok"], "task_name": TASK_NAME, "output": result["output"]},
        indent=2,
        default=str,
    )


@mcp.tool(
    name="startup_status",
    annotations={
        "title": "Boot Startup Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def startup_status() -> str:
    """Report whether the boot-startup scheduled task is installed and its state.

    Returns:
        str: JSON {"ok": bool, "installed": bool, "details": "...", "task_name": "..."}.
    """
    if os.name != "nt":
        return _err("startup_status requires Windows.")
    result = _startup_status()
    out = result["output"]
    installed = out.startswith("INSTALLED") or out.startswith("STARTUP_SCRIPT|Installed=true")
    method = "scheduled-task" if out.startswith("INSTALLED") else "startup-folder-pythonw"
    return _ok(installed=installed, method=method if installed else None, details=out, task_name=TASK_NAME)


# =========================================================================== #
# CHEAP VERSION — no-MCP command-line fallback
# =========================================================================== #
# When MCP connections keep failing, every tool can be invoked directly from the
# command line. This "Cheap Version" runs the exact same tool function in-process
# and prints its JSON result — no MCP client, transport, or server needed.
#
#   lowlevel-computer-use-cheap <tool> [--key value ...] [--json '{...}']
#   lowlevel-computer-use-mcp cheap <tool> [--key value ...]
#
# Examples:
#   lowlevel-computer-use-cheap get_screen_size
#   lowlevel-computer-use-cheap screenshot --monitor 1
#   lowlevel-computer-use-cheap mouse_click --x 960 --y 540 --clicks 2
#   lowlevel-computer-use-cheap press_keys --keys '["ctrl","s"]'
#   lowlevel-computer-use-cheap run_command --command "ipconfig /all"
#   lowlevel-computer-use-cheap --list

def _cheap_tool_names() -> list[str]:
    names = []
    for name, obj in globals().items():
        if name.startswith("_") or name in ("main", "cheap_entry"):
            continue
        if inspect.iscoroutinefunction(obj):
            names.append(name)
    return sorted(names)


def _cheap_usage() -> str:
    lines = [
        "Cheap Version — run any tool directly, without MCP.",
        "",
        "Usage:",
        "  lowlevel-computer-use-cheap <tool> [--key value ...] [--json '{...}']",
        "  lowlevel-computer-use-mcp cheap <tool> [--key value ...]",
        "",
        "Values are parsed as JSON when possible (so --keys '[\"ctrl\",\"c\"]' and",
        "--x 100 work); otherwise treated as a string. A bare --flag means true.",
        "",
        "Tools:",
    ]
    for t in _cheap_tool_names():
        lines.append("  " + t)
    return "\n".join(lines)


def _cheap_parse_args(rest: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--json":
            data.update(json.loads(rest[i + 1]))
            i += 2
            continue
        if tok.startswith("--"):
            key = tok[2:]
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                raw = rest[i + 1]
                try:
                    val: Any = json.loads(raw)
                except (ValueError, json.JSONDecodeError):
                    val = raw
                data[key] = val
                i += 2
            else:
                data[key] = True
                i += 1
        else:
            i += 1
    return data


def _cheap_main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "--list", "list", "help"):
        print(_cheap_usage())
        return 0
    name = argv[0]
    func = globals().get(name)
    if not inspect.iscoroutinefunction(func):
        print(json.dumps({"ok": False, "error": f"Unknown tool '{name}'. Run with --list."}, indent=2))
        return 1
    try:
        data = _cheap_parse_args(argv[1:])
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"Could not parse arguments: {exc}"}, indent=2))
        return 1
    try:
        sig = inspect.signature(func)
        if "params" in sig.parameters:
            model_cls = get_type_hints(func).get("params")
            result = asyncio.run(func(model_cls(**data)))
        else:
            result = asyncio.run(func())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1
    print(result)
    return 0


def cheap_entry() -> None:
    """Console-script entry point for the Cheap Version CLI."""
    sys.exit(_cheap_main(sys.argv[1:]))


# =========================================================================== #
# Entry point
# =========================================================================== #
def _serve(http: bool, host: str, port: int) -> None:
    if http:
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


def _ensure_standard_streams() -> None:
    """Give pythonw HTTP startup valid null streams without allocating a console."""
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> None:
    """CLI entry point.

    Default: run the MCP server over stdio (for Claude Code / Codex).
    Subcommands manage the boot-startup scheduled task. Flags switch transport
    and elevation.
    """
    _ensure_standard_streams()

    # Cheap Version fallback: `... cheap <tool> [args]` runs a tool without MCP.
    if len(sys.argv) > 1 and sys.argv[1] == "cheap":
        sys.exit(_cheap_main(sys.argv[2:]))

    parser = argparse.ArgumentParser(
        prog="lowlevel-computer-use-mcp",
        description="Low-level computer-use MCP server. Subcommand `cheap` runs a tool "
        "directly from the command line without MCP (fallback when connections fail).",
    )
    parser.add_argument("--http", action="store_true", help="Serve over streamable HTTP instead of stdio")
    parser.add_argument("--host", default=DEFAULT_HTTP_HOST, help="Host for --http mode")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT, help="Port for --http mode")
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Relaunch the server elevated (UAC) if not already running as Administrator",
    )

    sub = parser.add_subparsers(dest="cmd")
    p_install = sub.add_parser("install-startup", help="Register a logon scheduled task to auto-start the server")
    p_install.add_argument(
        "--admin-task",
        action="store_true",
        help="Opt in to an elevated scheduled task (shows UAC); default uses a console-free user Startup launcher",
    )
    p_install.add_argument("--no-admin", action="store_true", help=argparse.SUPPRESS)
    p_install.add_argument("--stdio", action="store_true", help="Start in stdio mode instead of HTTP")
    p_install.add_argument("--host", default=DEFAULT_HTTP_HOST)
    p_install.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    sub.add_parser("uninstall-startup", help="Remove the auto-start scheduled task")
    sub.add_parser("startup-status", help="Show the auto-start task status")

    args = parser.parse_args()

    if args.cmd == "install-startup":
        res = _install_startup(
            http=not args.stdio,
            host=args.host,
            port=args.port,
            run_as_admin=args.admin_task and not args.no_admin,
        )
        print(res["output"])
        sys.exit(0 if res["ok"] else 1)
    if args.cmd == "uninstall-startup":
        res = _uninstall_startup()
        print(res["output"])
        sys.exit(0 if res["ok"] else 1)
    if args.cmd == "startup-status":
        res = _startup_status()
        print(res["output"])
        sys.exit(0 if res["ok"] else 1)

    # Serve mode
    if args.admin and os.name == "nt" and not _is_admin():
        # Relaunch through the GUI-subsystem interpreter so UAC never creates a
        # terminal window. Stdio elevation still belongs to the parent client.
        forwarded = [a for a in sys.argv[1:] if a != "--admin"]
        params = subprocess.list2cmdline(["-m", "lowlevel_computer_use_mcp.server", *forwarded])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", pythonw_executable(), params, None, 0
        )
        sys.exit(0)

    _serve(http=args.http, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
