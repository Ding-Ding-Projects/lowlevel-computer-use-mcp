"""Optional C++ Win32 bridge for desktop lifetime and quiet process launch."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any

ABI_VERSION = 1
ERROR_BUFFER_LENGTH = 2048
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
WAIT_FAILED = 0xFFFFFFFF


class NativeWin32Error(RuntimeError):
    pass


class NativeWin32Bridge:
    def __init__(self, library: ctypes.CDLL, path: Path) -> None:
        self.library = library
        self.path = path
        library.ll_native_abi_version.argtypes = []
        library.ll_native_abi_version.restype = wintypes.DWORD
        if library.ll_native_abi_version() != ABI_VERSION:
            raise NativeWin32Error(
                f"Native Win32 ABI mismatch: expected {ABI_VERSION}, loaded {library.ll_native_abi_version()} from {path}."
            )

        library.ll_desktop_create.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        library.ll_desktop_create.restype = ctypes.c_int
        library.ll_desktop_launch.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        library.ll_desktop_launch.restype = ctypes.c_int
        library.ll_desktop_close.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_int),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        library.ll_desktop_close.restype = ctypes.c_int

    @staticmethod
    def _error_buffer() -> ctypes.Array[Any]:
        return ctypes.create_unicode_buffer(ERROR_BUFFER_LENGTH)

    @staticmethod
    def _raise_on_error(code: int, message: str, operation: str) -> None:
        if code:
            detail = message or f"Win32 error {code}"
            raise NativeWin32Error(f"{operation}: {detail}")

    def create_desktop(self, name: str) -> dict[str, Any]:
        handle = ctypes.c_uint64()
        already_exists = ctypes.c_int()
        error = self._error_buffer()
        code = self.library.ll_desktop_create(
            name, ctypes.byref(handle), ctypes.byref(already_exists), error, len(error)
        )
        self._raise_on_error(code, error.value, "Native desktop create")
        return {
            "name": name,
            "handle": handle.value,
            "full": f"WinSta0\\{name}",
            "already_exists": bool(already_exists.value),
            "backend": "native-cpp",
            "native_abi": ABI_VERSION,
        }

    def launch_on_desktop(self, name: str, command_line: str, input_idle_timeout_ms: int = 10_000) -> dict[str, Any]:
        process_id = wintypes.DWORD()
        thread_id = wintypes.DWORD()
        wait_result = wintypes.DWORD(WAIT_FAILED)
        error = self._error_buffer()
        code = self.library.ll_desktop_launch(
            name,
            command_line,
            input_idle_timeout_ms,
            ctypes.byref(process_id),
            ctypes.byref(thread_id),
            ctypes.byref(wait_result),
            error,
            len(error),
        )
        self._raise_on_error(code, error.value, "Native desktop launch")
        idle_state = {
            WAIT_OBJECT_0: "ready",
            WAIT_TIMEOUT: "timeout",
            WAIT_FAILED: "not-applicable",
        }.get(wait_result.value, f"wait-result-{wait_result.value}")
        return {
            "desktop": name,
            "pid": process_id.value,
            "thread_id": thread_id.value,
            "command": command_line,
            "terminal_window": False,
            "focus_stealing": False,
            "input_idle": idle_state,
            "input_idle_timeout_ms": input_idle_timeout_ms,
            "backend": "native-cpp",
            "native_abi": ABI_VERSION,
        }

    def close_desktop(self, name: str) -> dict[str, Any]:
        closed = ctypes.c_int()
        error = self._error_buffer()
        code = self.library.ll_desktop_close(name, ctypes.byref(closed), error, len(error))
        self._raise_on_error(code, error.value, "Native desktop close")
        return {"name": name, "closed": bool(closed.value), "backend": "native-cpp"}


def candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("LOWLEVEL_WIN32_NATIVE_DLL")
    if configured:
        candidates.append(Path(configured))
    package = Path(__file__).resolve().parent
    candidates.extend(
        [
            package / "native" / "lowlevel_win32_native.dll",
            package / "lowlevel_win32_native.dll",
        ]
    )
    return candidates


def load_native_bridge() -> tuple[NativeWin32Bridge | None, str | None]:
    if os.name != "nt":
        return None, "The native Win32 bridge is available only on Windows."
    failures: list[str] = []
    for path in candidate_paths():
        if not path.is_file():
            continue
        try:
            return NativeWin32Bridge(ctypes.CDLL(str(path)), path), None
        except (OSError, NativeWin32Error) as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        return None, "; ".join(failures)
    return None, "lowlevel_win32_native.dll was not found in the configured or packaged locations."
