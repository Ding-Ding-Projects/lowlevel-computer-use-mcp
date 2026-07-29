"""Cross-platform process-launch helpers.

Windows console programs allocate a visible console unless callers explicitly
opt out.  Every child process launched by this project goes through these
helpers so startup and tool execution cannot flash a terminal over the user's
active application.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CREATE_NO_WINDOW = 0x08000000


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return subprocess options that suppress Windows console/window creation."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": startupinfo, "creationflags": CREATE_NO_WINDOW}


def pythonw_executable() -> str:
    """Return the GUI-subsystem Python beside the active interpreter on Windows."""
    if os.name != "nt":
        return sys.executable
    candidate = Path(sys.executable).with_name("pythonw.exe")
    if not candidate.exists():
        raise FileNotFoundError(
            f"Console-free startup requires pythonw.exe beside {sys.executable}; "
            "refusing to fall back to a console executable."
        )
    return str(candidate)


def hidden_server_command() -> tuple[str, list[str]]:
    """Command/arguments for a console-free server process."""
    return pythonw_executable(), ["-m", "lowlevel_computer_use_mcp.server"]
