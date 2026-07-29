"""AutoHotkey add-in.

Lets the MCP server run AutoHotkey (AHK) scripts. AHK is a powerful complement to
the built-in Win32 tools: its ControlSend / ControlClick reliably drive *background*
windows, and arbitrary AHK gives agents a full automation escape hatch.

AHK is detected automatically (PATH + common install locations + the
LOWLEVEL_CU_AHK environment variable). AutoHotkey v2 syntax is generated for the
convenience helpers; raw run_script accepts whatever the installed interpreter
supports.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .processes import hidden_subprocess_kwargs


class AhkError(RuntimeError):
    pass


_CANDIDATE_EXES = [
    "AutoHotkey64.exe",
    "AutoHotkey32.exe",
    "AutoHotkeyU64.exe",
    "AutoHotkeyU32.exe",
    "AutoHotkey.exe",
    "AutoHotkeyV2.exe",
]


def _common_install_paths() -> list[Path]:
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "AutoHotkey",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "AutoHotkey",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AutoHotkey",
    ]
    out: list[Path] = []
    for root in roots:
        for sub in ("v2", "", "v1"):
            base = root / sub if sub else root
            for exe in _CANDIDATE_EXES:
                out.append(base / exe)
    return out


def find_ahk() -> Optional[str]:
    """Return the path to an AutoHotkey interpreter, or None if not found."""
    env = os.environ.get("LOWLEVEL_CU_AHK")
    if env and Path(env).exists():
        return env
    for exe in _CANDIDATE_EXES:
        found = shutil.which(exe)
        if found:
            return found
    for path in _common_install_paths():
        if path.exists():
            return str(path)
    return None


def ahk_version(exe: str) -> str:
    """Best-effort major version guess ('v2' or 'v1') from the interpreter path."""
    low = exe.lower()
    if "v2" in low or "autohotkey64" in low or "autohotkey32" in low:
        return "v2"
    if "v1" in low:
        return "v1"
    return "v2"  # modern default


def status() -> dict[str, Any]:
    exe = find_ahk()
    if not exe:
        return {
            "installed": False,
            "hint": "Install AutoHotkey (https://www.autohotkey.com) or set LOWLEVEL_CU_AHK "
            "to the AutoHotkey*.exe path. On Windows: `winget install AutoHotkey.AutoHotkey`.",
        }
    return {"installed": True, "path": exe, "version": ahk_version(exe)}


def run_script(code: str, args: Optional[list[str]] = None, timeout: float = 60.0,
               exe_path: Optional[str] = None) -> dict[str, Any]:
    """Write `code` to a temp .ahk file and run it, capturing stdout/stderr.

    The script must terminate (call ExitApp, or be non-persistent) or it will run
    until the timeout. Use FileAppend with target "*" to emit to stdout.
    """
    exe = exe_path or find_ahk()
    if not exe:
        raise AhkError(
            "AutoHotkey not found. Install it or set LOWLEVEL_CU_AHK to the interpreter path."
        )
    fd, path = tempfile.mkstemp(suffix=".ahk", prefix="llcu-")
    os.close(fd)
    try:
        # UTF-8 with BOM so AutoHotkey reads unicode correctly.
        Path(path).write_text(code, encoding="utf-8-sig")
        cmd = [exe, "/ErrorStdOut", path, *(args or [])]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exe": exe,
        }
    except subprocess.TimeoutExpired:
        raise AhkError(
            f"AHK script exceeded {timeout}s. Ensure it calls ExitApp / is non-persistent."
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _esc_v2(s: str) -> str:
    """Escape a string for an AutoHotkey v2 double-quoted literal."""
    return s.replace("`", "``").replace('"', '`"').replace("\n", "`n").replace("\t", "`t")


def control_send(text: str, window: str, control: str = "", as_keys: bool = False,
                 timeout: float = 30.0, exe_path: Optional[str] = None) -> dict[str, Any]:
    """Send text (or keystrokes) to a background window/control via AHK ControlSend.

    `window` and `control` are AHK target strings, e.g. "ahk_id 0x1234" (a HWND),
    "ahk_exe notepad.exe", or a window title. This works without focusing the window
    and is often more reliable than raw WM_CHAR for complex controls.

    If as_keys is True the text is interpreted as AHK key syntax (e.g. "^a{Del}").
    """
    exe = exe_path or find_ahk()
    if not exe:
        raise AhkError("AutoHotkey not found.")
    cmd = "ControlSend" if as_keys else "ControlSendText"
    code = (
        f'{cmd} "{_esc_v2(text)}", "{_esc_v2(control)}", "{_esc_v2(window)}"\n'
        "ExitApp 0\n"
    )
    return run_script(code, timeout=timeout, exe_path=exe)


def control_click(window: str, control: str = "", button: str = "Left", x: Optional[int] = None,
                  y: Optional[int] = None, timeout: float = 30.0,
                  exe_path: Optional[str] = None) -> dict[str, Any]:
    """Click a control in a background window via AHK ControlClick (no focus needed)."""
    exe = exe_path or find_ahk()
    if not exe:
        raise AhkError("AutoHotkey not found.")
    pos = f'"x{x} y{y}"' if x is not None and y is not None else '""'
    code = (
        f'ControlClick {pos}, "{_esc_v2(window)}", , "{button}", 1, '
        f'(("{_esc_v2(control)}" = "") ? "" : "")\n'
    )
    # Simpler, robust form: use the Control parameter explicitly.
    code = (
        f'try ControlClick "{_esc_v2(control)}", "{_esc_v2(window)}", , "{button}"\n'
        f'catch as e\n'
        f'    FileAppend "ERROR: " e.Message, "*"\n'
        "ExitApp 0\n"
    )
    return run_script(code, timeout=timeout, exe_path=exe)
