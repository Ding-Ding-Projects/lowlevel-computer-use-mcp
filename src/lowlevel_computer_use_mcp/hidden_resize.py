"""Exact-desktop, identity-bound resize. No global window discovery or activation."""
import ctypes
from ctypes import wintypes as W
import os
import re
import threading
import time


class ResizeRejected(RuntimeError):
    pass


def validate_request(r):
    if set(r) != {"desktop_name", "handle", "pid", "creation_filetime", "executable_path", "expected_outer", "width", "height"}:
        raise ResizeRejected("REQUEST_FIELDS")
    name = r["desktop_name"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name) or name.lower() in {"default", "winlogon", "disconnect"}:
        raise ResizeRejected("HIDDEN_DESKTOP_REQUIRED")
    for key in ("handle", "pid", "width", "height"):
        if type(r[key]) is not int or r[key] <= 0:
            raise ResizeRejected("INVALID_INTEGER")
    if r["pid"] > 0xFFFFFFFF or max(r["width"], r["height"]) > 16384:
        raise ResizeRejected("OUT_OF_RANGE")
    if not isinstance(r["creation_filetime"], str) or not re.fullmatch(r"[1-9][0-9]{0,18}", r["creation_filetime"]) or int(r["creation_filetime"]) > 0x7FFFFFFFFFFFFFFF:
        raise ResizeRejected("EXACT_CREATION_TIME_REQUIRED")
    p = r["executable_path"]
    if not isinstance(p, str) or not re.match(r"^[A-Za-z]:\\", p) or len(p) > 32760 or any(ord(c) < 32 for c in p):
        raise ResizeRejected("ABSOLUTE_EXECUTABLE_REQUIRED")
    rect = r["expected_outer"]
    if not isinstance(rect, list) or len(rect) != 4 or any(type(x) is not int for x in rect) or rect[2] <= rect[0] or rect[3] <= rect[1]:
        raise ResizeRejected("EXPECTED_GEOMETRY_REQUIRED")


def resize_bound(r, api, canceled=lambda: False):
    """Execute on a worker already attached to the explicit desktop."""
    validate_request(r)
    with api.process(r["pid"]) as process:
        def verify():
            if canceled():
                raise ResizeRejected("DEADLINE")
            if api.input_desktop_name().casefold() == r["desktop_name"].casefold():
                raise ResizeRejected("TARGET_IS_CURRENT_INPUT_DESKTOP")
            if not api.live(process) or api.identity(process) != (r["creation_filetime"], r["executable_path"].casefold()):
                raise ResizeRejected("PROCESS_IDENTITY_MISMATCH")
            if not api.owns_window(r["handle"], r["pid"]):
                raise ResizeRejected("WINDOW_OUTSIDE_EXACT_DESKTOP")
        verify()
        before = api.geometry(r["handle"])
        if before["outer"] != r["expected_outer"]:
            raise ResizeRejected("STALE_GEOMETRY")
        verify()
        # Posting avoids an unbounded cross-thread synchronous window procedure.
        api.resize(r["handle"], r["width"], r["height"])
        deadline = time.monotonic() + 3
        while True:
            verify()
            after = api.geometry(r["handle"])
            rect = after["outer"]
            if rect[:2] != before["outer"][:2]:
                raise ResizeRejected("UNEXPECTED_POSITION_CHANGE")
            if rect[2] - rect[0] == r["width"] and rect[3] - rect[1] == r["height"]:
                return {"ok": True, "desktop": r["desktop_name"], "handle": r["handle"], "pid": r["pid"],
                        "creation_filetime": r["creation_filetime"], "before": before, "after": after,
                        "geometry_units": "physical-pixels", "activation_requested": False,
                        "caller_ancestry_proof_required": True}
            if time.monotonic() >= deadline:
                raise ResizeRejected("POST_GEOMETRY_NOT_OBSERVED")
            time.sleep(.025)


class Native:
    def __init__(self):
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        def bind(dll, name, args, result):
            f = getattr(dll, name); f.argtypes = args; f.restype = result; return f
        H = W.HANDLE
        self.open_desktop = bind(self.u, "OpenDesktopW", [W.LPCWSTR, W.DWORD, W.BOOL, W.DWORD], H)
        self.set_desktop = bind(self.u, "SetThreadDesktop", [H], W.BOOL)
        self.close_desktop = bind(self.u, "CloseDesktop", [H], W.BOOL)
        self.open_input = bind(self.u, "OpenInputDesktop", [W.DWORD, W.BOOL, W.DWORD], H)
        self.object_info = bind(self.u, "GetUserObjectInformationW", [H, ctypes.c_int, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD)], W.BOOL)
        self.thread_desktop = bind(self.u, "GetThreadDesktop", [W.DWORD], H)
        self.thread_id = bind(self.k, "GetCurrentThreadId", [], W.DWORD)
        self.callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.enum = bind(self.u, "EnumDesktopWindows", [H, self.callback_type, W.LPARAM], W.BOOL)
        self.owner = bind(self.u, "GetWindowThreadProcessId", [W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD)
        self.window_rect = bind(self.u, "GetWindowRect", [W.HWND, ctypes.POINTER(W.RECT)], W.BOOL)
        self.client_rect = bind(self.u, "GetClientRect", [W.HWND, ctypes.POINTER(W.RECT)], W.BOOL)
        self.dpi = bind(self.u, "GetDpiForWindow", [W.HWND], W.UINT)
        self.set_pos = bind(self.u, "SetWindowPos", [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT], W.BOOL)
        self.set_dpi = bind(self.u, "SetThreadDpiAwarenessContext", [H], H)
        self.open_process = bind(self.k, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], H)
        self.close_handle = bind(self.k, "CloseHandle", [H], W.BOOL)
        self.wait = bind(self.k, "WaitForSingleObject", [H, W.DWORD], W.DWORD)
        self.times = bind(self.k, "GetProcessTimes", [H] + [ctypes.POINTER(W.FILETIME)] * 4, W.BOOL)
        self.image = bind(self.k, "QueryFullProcessImageNameW", [H, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)], W.BOOL)
        self.desktop = None

    @staticmethod
    def check(ok):
        if not ok:
            raise ResizeRejected("NATIVE_CALL_" + str(ctypes.get_last_error()))

    def process(self, pid):
        from contextlib import contextmanager
        @contextmanager
        def held():
            h = self.open_process(0x101000, False, pid); self.check(h)
            try:
                yield h
            finally:
                self.check(self.close_handle(h))
        return held()

    def live(self, handle):
        return self.wait(handle, 0) == 258

    def input_desktop_name(self):
        handle = self.open_input(0, False, 1); self.check(handle)
        try:
            text = ctypes.create_unicode_buffer(32768); needed = W.DWORD()
            self.check(self.object_info(handle, 2, text, ctypes.sizeof(text), ctypes.byref(needed)))
            if not text.value: raise ResizeRejected("INPUT_DESKTOP_NAME_UNAVAILABLE")
            return text.value
        finally:
            self.check(self.close_desktop(handle))

    def identity(self, handle):
        ts = [W.FILETIME() for _ in range(4)]
        self.check(self.times(handle, *(ctypes.byref(t) for t in ts)))
        size = W.DWORD(32768); path = ctypes.create_unicode_buffer(size.value)
        self.check(self.image(handle, 0, path, ctypes.byref(size)))
        return str((ts[0].dwHighDateTime << 32) | ts[0].dwLowDateTime), path.value.casefold()

    def owns_window(self, hwnd, pid):
        found = False
        @self.callback_type
        def visit(candidate, _):
            nonlocal found
            if candidate == hwnd:
                actual = W.DWORD()
                tid = self.owner(candidate, ctypes.byref(actual))
                found = bool(tid) and actual.value == pid
            return True
        self.check(self.enum(self.desktop, visit, 0))
        return found

    def geometry(self, hwnd):
        outer = W.RECT(); client = W.RECT()
        self.check(self.window_rect(hwnd, ctypes.byref(outer)))
        self.check(self.client_rect(hwnd, ctypes.byref(client)))
        dpi = self.dpi(hwnd); self.check(dpi)
        return {"outer": [outer.left, outer.top, outer.right, outer.bottom],
                "client": [client.left, client.top, client.right, client.bottom], "dpi": dpi}

    def resize(self, hwnd, width, height):
        # NOMOVE | NOZORDER | NOACTIVATE | NOOWNERZORDER | ASYNCWINDOWPOS.
        self.check(self.set_pos(hwnd, None, 0, 0, width, height, 0x4216))


def cleanup_worker(api, old_dpi, original_desktop, desktop):
    """Attempt every owned restoration independently, retaining every failure."""
    errors = []
    actions = []
    if api and old_dpi: actions.append(("dpi-restore", lambda: api.check(api.set_dpi(old_dpi))))
    if api and desktop:
        actions.append(("desktop-restore", lambda: api.check(api.set_desktop(original_desktop))))
        actions.append(("desktop-close", lambda: api.check(api.close_desktop(desktop))))
    for stage, action in actions:
        try: action()
        except Exception as exc: errors.append({"stage": stage, "type": type(exc).__name__})
    return errors


def resize_hidden_window(request):
    validate_request(request)
    if os.name != "nt":
        raise ResizeRejected("WINDOWS_REQUIRED")
    result = {}; canceled = threading.Event()
    def worker():
        api = None; desktop = None; old_dpi = None; original_desktop = None
        try:
            api = Native()
            original_desktop = api.thread_desktop(api.thread_id()); api.check(original_desktop)
            desktop = api.open_desktop(request["desktop_name"], 0, False, 0x0081)
            api.check(desktop); api.desktop = desktop
            api.check(api.set_desktop(desktop))
            old_dpi = api.set_dpi(ctypes.c_void_p(-4)); api.check(old_dpi)
            result["value"] = resize_bound(request, api, canceled.is_set)
        except Exception as exc:
            result["error"] = exc
        finally:
            errors = cleanup_worker(api, old_dpi, original_desktop, desktop)
            result["cleanup"] = errors
            if errors:
                result["error"] = ResizeRejected("WORKER_CLEANUP_INCOMPLETE:" + ",".join(e["stage"] for e in errors))
    t = threading.Thread(target=worker, daemon=True); t.start(); t.join(6)
    if t.is_alive():
        canceled.set()
        raise ResizeRejected("WORKER_DEADLINE_NO_SUCCESS")
    if "error" in result: raise result["error"]
    return result["value"]
