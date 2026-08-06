"""Process-launch helpers that keep automation off the user's visible desktop.

Every child process started by the server is non-interactive by default.  On
Windows this means no inherited console, no new console window, and a hidden
startup state.  The helper is deliberately small so all platform backends and
the installer use the same policy instead of each reimplementing it slightly
differently.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return subprocess kwargs for a child that must not show a terminal.

    ``CREATE_NO_WINDOW`` applies to console children and ``STARTF_USESHOWWINDOW``
    covers GUI-capable launchers that honour the startup information.  Neither
    flag changes the caller's foreground window or cursor.
    """
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def run_hidden(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a child process without creating a terminal window on Windows."""
    kwargs.setdefault("capture_output", True)
    kwargs.update(hidden_subprocess_kwargs())
    return subprocess.run(*args, **kwargs)


def popen_hidden(*args: Any, **kwargs: Any) -> subprocess.Popen:
    """Start a child process without creating a terminal window on Windows."""
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    kwargs.update(hidden_subprocess_kwargs())
    return subprocess.Popen(*args, **kwargs)
