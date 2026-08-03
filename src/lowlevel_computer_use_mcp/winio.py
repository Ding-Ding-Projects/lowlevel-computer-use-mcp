"""Win32 background input + per-window capture + hidden-desktop helpers.

This module makes it possible to drive a target window *without* bringing it to
the foreground:

  * Mouse input  - PostMessage WM_*BUTTON* to the deepest child control at a point
  * Keyboard     - PostMessage WM_CHAR / WM_KEYDOWN / WM_KEYUP, or WM_SETTEXT
  * Capture      - PrintWindow (PW_RENDERFULLCONTENT) renders a window into a DC
                   even when it is occluded, unfocused, or on another desktop
  * Headless GUI - CreateDesktop + CreateProcess(lpDesktop=...) runs a real GUI
                   app on an off-screen desktop that never touches the visible one

Everything is implemented with ctypes against user32/gdi32/kernel32 so behaviour
is predictable on 64-bit Python. All functions raise WinIOError with an
actionable message on failure.

Caveats (inherent to message-based injection, documented for honesty):
  * Apps that read raw input / DirectInput / check physical key state
    (GetAsyncKeyState) may ignore posted messages. Modifier combos (Ctrl+C) are
    unreliable via messages; prefer WM_SETTEXT / app-specific messages, or use
    foreground input for those apps.
  * PrintWindow works for most GDI and Chromium/DWM windows with
    PW_RENDERFULLCONTENT, but a few GPU-exclusive surfaces render black.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Any, Callable, Optional

# --------------------------------------------------------------------------- #
# ctypes setup
# --------------------------------------------------------------------------- #
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WPARAM = ctypes.c_size_t  # unsigned, pointer-sized
LPARAM = ctypes.c_ssize_t  # signed, pointer-sized
LRESULT = ctypes.c_ssize_t
HWND = wintypes.HWND
HDESK = wintypes.HANDLE

# Window messages
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0201, 0x0202, 0x0203
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK = 0x0204, 0x0205, 0x0206
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK = 0x0207, 0x0208, 0x0209
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_CHAR = 0x0102
WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH = 0x000C, 0x000D, 0x000E

MK_LBUTTON, MK_RBUTTON, MK_MBUTTON = 0x0001, 0x0002, 0x0010

# ChildWindowFromPointEx flags
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPTRANSPARENT = 0x0004

# PrintWindow flags
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002

# Desktop / process
GENERIC_ALL = 0x10000000
DESKTOP_CREATEWINDOW = 0x0002
STARTF_USESHOWWINDOW = 0x00000001
# A headless GUI process must not inherit or create a console.  CREATE_NO_WINDOW
# is ignored for GUI-subsystem apps, but suppresses a console for command-line
# programs launched on the hidden desktop too.
CREATE_NO_WINDOW = 0x08000000
SW_SHOWNORMAL = 1


class WinIOError(RuntimeError):
    pass


def _check(value: Any, what: str) -> Any:
    if not value:
        err = ctypes.get_last_error()
        raise WinIOError(f"{what} failed (GetLastError={err}: {ctypes.FormatError(err).strip()})")
    return value


# argtypes / restypes
user32.PostMessageW.argtypes = [HWND, wintypes.UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.SendMessageW.argtypes = [HWND, wintypes.UINT, WPARAM, LPARAM]
user32.SendMessageW.restype = LRESULT
user32.SendMessageTimeoutW.argtypes = [
    HWND, wintypes.UINT, WPARAM, LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)
]
user32.SendMessageTimeoutW.restype = LRESULT
user32.PrintWindow.argtypes = [HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowDC.argtypes = [HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [HWND, wintypes.HDC]
user32.ClientToScreen.argtypes = [HWND, ctypes.POINTER(wintypes.POINT)]
user32.ScreenToClient.argtypes = [HWND, ctypes.POINTER(wintypes.POINT)]
user32.MapWindowPoints.argtypes = [HWND, HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT]
user32.ChildWindowFromPointEx.argtypes = [HWND, wintypes.POINT, wintypes.UINT]
user32.ChildWindowFromPointEx.restype = HWND
user32.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindow.argtypes = [HWND]
user32.IsWindowVisible.argtypes = [HWND]
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetDpiForWindow.argtypes = [HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int


# --------------------------------------------------------------------------- #
# Window discovery
# --------------------------------------------------------------------------- #
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, LPARAM)


def _get_window_text(hwnd: int) -> str:
    length = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(hwnd, WM_GETTEXT, length + 1, ctypes.addressof(buf))
    return buf.value


def _get_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_top_window(title: Optional[str], handle: Optional[int]) -> int:
    """Resolve a top-level window handle by exact handle or title substring."""
    if handle is not None:
        if not user32.IsWindow(handle):
            # Not on this thread's desktop — accept it if ANY desktop owns it
            # (headless-desktop windows); raises WinIOError otherwise.
            return run_on_window_desktop(int(handle), lambda: int(handle))
        return int(handle)
    if not title:
        raise WinIOError("Provide a window title or handle.")
    title_l = title.lower()
    matches: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _lparam):
        text = _get_window_text(hwnd)
        if text and title_l in text.lower():
            matches.append(int(hwnd))
        return True

    user32.EnumWindows(cb, 0)
    if not matches:
        raise WinIOError(f"No top-level window whose title contains '{title}'.")
    return matches[0]


def list_child_windows(hwnd: int) -> list[dict[str, Any]]:
    """Enumerate child controls of a window with class, text and client rect.

    Works for windows on headless desktops too (cross-desktop dispatch).
    """
    return run_on_window_desktop(int(hwnd), lambda: _list_child_windows_impl(hwnd))


def _list_child_windows_impl(hwnd: int) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    top_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(top_rect))

    @WNDENUMPROC
    def cb(child, _lparam):
        r = wintypes.RECT()
        user32.GetWindowRect(child, ctypes.byref(r))
        children.append(
            {
                "handle": int(child),
                "class": _get_class_name(child),
                "text": _get_window_text(child),
                # rect relative to the top-level window's top-left
                "left": r.left - top_rect.left,
                "top": r.top - top_rect.top,
                "width": r.right - r.left,
                "height": r.bottom - r.top,
                "visible": bool(user32.IsWindowVisible(child)),
            }
        )
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return children


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", HWND),
        ("hwndFocus", HWND),
        ("hwndCapture", HWND),
        ("hwndMenuOwner", HWND),
        ("hwndMoveSize", HWND),
        ("hwndCaret", HWND),
        ("rcCaret", wintypes.RECT),
    ]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL


def focused_control(hwnd: int) -> int:
    """Return the focused control within the window's UI thread, or hwnd itself."""
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    gui = GUITHREADINFO()
    gui.cbSize = ctypes.sizeof(GUITHREADINFO)
    if user32.GetGUIThreadInfo(tid, ctypes.byref(gui)) and gui.hwndFocus:
        return int(gui.hwndFocus)
    return int(hwnd)


def _deepest_child_at(top: int, x: int, y: int) -> tuple[int, int, int]:
    """Descend from `top` to the deepest child containing client point (x, y).

    Returns (target_hwnd, child_x, child_y) where child_x/y are client coords of
    the returned window.
    """
    cur, cx, cy = top, x, y
    for _ in range(32):  # guard against cycles
        pt = wintypes.POINT(cx, cy)
        child = user32.ChildWindowFromPointEx(cur, pt, CWP_SKIPINVISIBLE | CWP_SKIPTRANSPARENT)
        if not child or int(child) == int(cur):
            break
        p = wintypes.POINT(cx, cy)
        user32.MapWindowPoints(cur, child, ctypes.byref(p), 1)
        cur, cx, cy = int(child), p.x, p.y
    return cur, cx, cy


# --------------------------------------------------------------------------- #
# Cross-desktop dispatch
#
# USER hwnd operations (IsWindow, GetWindowRect, PostMessage, PrintWindow, ...)
# only resolve windows on the *calling thread's* desktop. Windows launched on a
# headless desktop (create_desktop / launch_on_desktop) are therefore invisible
# to a caller attached to the default desktop, even though the hwnd itself is
# session-valid. run_on_window_desktop() fixes that transparently: if the hwnd
# does not resolve on the current desktop, it retries the operation on a fresh
# worker thread attached (SetThreadDesktop) to each desktop of this window
# station until one owns the hwnd. Fresh threads are required because
# SetThreadDesktop fails on threads that already own windows/hooks.
# --------------------------------------------------------------------------- #
user32.GetProcessWindowStation.restype = wintypes.HANDLE
DESKTOPENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.LPWSTR, LPARAM)
user32.EnumDesktopsW.argtypes = [wintypes.HANDLE, DESKTOPENUMPROC, LPARAM]
user32.SetThreadDesktop.argtypes = [HDESK]
user32.SetThreadDesktop.restype = wintypes.BOOL

# Desktop handles opened for cross-desktop dispatch. Kept for the process
# lifetime on purpose: a desktop handle must outlive any thread attached to it,
# and the handles are tiny (the CLI is one-shot; the server benefits from reuse).
_XDESK_CACHE: dict[str, int] = {}


def _enum_desktop_names() -> list[str]:
    """Names of all desktops in this process's window station."""
    names: list[str] = []

    @DESKTOPENUMPROC
    def cb(name, _lparam):
        if name:
            names.append(str(name))
        return True

    user32.EnumDesktopsW(user32.GetProcessWindowStation(), cb, 0)
    return names


def run_on_window_desktop(hwnd: int, fn: Callable[[], Any]) -> Any:
    """Run fn() attached to whichever desktop owns `hwnd`.

    Fast path: the hwnd resolves on the current thread's desktop -> call fn()
    inline. Slow path: try each desktop in the window station on a dedicated
    worker thread; the first desktop where IsWindow(hwnd) succeeds runs fn()
    there (its result / exception is propagated). Raises WinIOError when the
    hwnd resolves on no desktop at all.
    """
    if user32.IsWindow(hwnd):
        return fn()

    for name in _enum_desktop_names():
        outcome: dict[str, Any] = {}

        def worker(desk_name=name):
            hd = _XDESK_CACHE.get(desk_name)
            if not hd:
                hd = user32.OpenDesktopW(desk_name, 0, False, GENERIC_ALL)
                if not hd:
                    return
                _XDESK_CACHE[desk_name] = int(hd)
            if not user32.SetThreadDesktop(hd):
                return
            if not user32.IsWindow(hwnd):
                return
            outcome["found"] = True
            try:
                outcome["result"] = fn()
            except BaseException as exc:  # propagate to the caller thread
                outcome["error"] = exc

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=60)
        if outcome.get("found"):
            if "error" in outcome:
                raise outcome["error"]
            return outcome.get("result")

    raise WinIOError(
        f"No window with handle {hwnd} on any desktop of this window station."
    )


# --------------------------------------------------------------------------- #
# Background mouse / keyboard
# --------------------------------------------------------------------------- #
def _lparam_xy(x: int, y: int) -> int:
    return (y << 16) | (x & 0xFFFF)


_BTN = {
    "left": (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK, MK_LBUTTON),
    "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK, MK_RBUTTON),
    "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK, MK_MBUTTON),
}


def send_click(top: int, x: int, y: int, button: str = "left", double: bool = False) -> dict[str, Any]:
    """Post a mouse click to the deepest control at client point (x, y) of `top`.

    x, y are in client coordinates of the top-level window. The window does not
    need to be focused or visible — headless-desktop windows work too.
    """
    return run_on_window_desktop(int(top), lambda: _send_click_impl(top, x, y, button, double))


def _send_click_impl(top: int, x: int, y: int, button: str, double: bool) -> dict[str, Any]:
    down, up, dbl, mk = _BTN[button]
    target, cx, cy = _deepest_child_at(top, x, y)
    lp = _lparam_xy(cx, cy)
    user32.PostMessageW(target, WM_MOUSEMOVE, 0, lp)
    user32.PostMessageW(target, down, mk, lp)
    user32.PostMessageW(target, up, 0, lp)
    if double:
        user32.PostMessageW(target, dbl, mk, lp)
        user32.PostMessageW(target, up, 0, lp)
    return {"target_hwnd": target, "client_x": cx, "client_y": cy, "button": button, "double": double}


def send_text(hwnd: int, text: str) -> dict[str, Any]:
    """Post each character as WM_CHAR to a window (typically a focused control)."""
    def _impl() -> dict[str, Any]:
        for ch in text:
            user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
        return {"target_hwnd": int(hwnd), "chars": len(text)}

    return run_on_window_desktop(int(hwnd), _impl)


def set_control_text(hwnd: int, text: str) -> dict[str, Any]:
    """Set a control's text directly via WM_SETTEXT (reliable for edit controls)."""
    def _impl() -> dict[str, Any]:
        buf = ctypes.create_unicode_buffer(text)
        res = user32.SendMessageTimeoutW(
            hwnd, WM_SETTEXT, 0, ctypes.addressof(buf), 0, 2000, ctypes.byref(ctypes.c_size_t())
        )
        return {"target_hwnd": int(hwnd), "ok": bool(res), "text_len": len(text)}

    return run_on_window_desktop(int(hwnd), _impl)


_VK = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "win": 0x5B,
    "capslock": 0x14, "printscreen": 0x2C,
}
for _i in range(1, 25):  # F1..F24
    _VK[f"f{_i}"] = 0x70 + (_i - 1)


def _vk_for(name: str) -> int:
    name = name.lower()
    if name in _VK:
        return _VK[name]
    if len(name) == 1:
        res = user32.VkKeyScanW(name)
        if res != -1:
            return res & 0xFF
    raise WinIOError(f"Unknown key name: '{name}'")


def _key_lparams(vk: int) -> tuple[int, int]:
    scan = user32.MapVirtualKeyW(vk, 0)
    down = 1 | (scan << 16)
    up = down | (0x3 << 30)  # transition + previous-state bits
    return down, up


def send_keys(hwnd: int, keys: list[str]) -> dict[str, Any]:
    """Post a key / key-combo via WM_KEYDOWN/UP.

    A single key is pressed and released. Multiple keys are pressed in order then
    released in reverse (modifier-style), but note message-based modifier combos
    are unreliable for apps that check physical key state - prefer set_control_text
    for text entry.
    """
    def _impl() -> dict[str, Any]:
        vks = [_vk_for(k) for k in keys]
        for vk in vks:
            down, _ = _key_lparams(vk)
            user32.PostMessageW(hwnd, WM_KEYDOWN, vk, down)
        for vk in reversed(vks):
            _, up = _key_lparams(vk)
            user32.PostMessageW(hwnd, WM_KEYUP, vk, up)
        return {"target_hwnd": int(hwnd), "keys": keys}

    return run_on_window_desktop(int(hwnd), _impl)


# --------------------------------------------------------------------------- #
# Per-window capture via PrintWindow
# --------------------------------------------------------------------------- #
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def capture_window(hwnd: int, client_only: bool = False):
    """Capture a window via PrintWindow into a PIL Image, even if unfocused/occluded.

    Returns (PIL.Image, rendered_ok: bool). Requires Pillow. Windows living on a
    headless desktop are captured via cross-desktop dispatch.
    """
    return run_on_window_desktop(int(hwnd), lambda: _capture_window_impl(hwnd, client_only))


def _capture_window_impl(hwnd: int, client_only: bool = False):
    from PIL import Image  # local import keeps the dependency optional

    if not user32.IsWindow(hwnd):
        raise WinIOError(f"No window with handle {hwnd}.")

    rect = wintypes.RECT()
    if client_only:
        user32.GetClientRect(hwnd, ctypes.byref(rect))
    else:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise WinIOError(f"Window has non-positive size ({w}x{h}); it may be minimized.")

    hdc_win = _check(user32.GetWindowDC(hwnd), "GetWindowDC")
    hdc_mem = _check(gdi32.CreateCompatibleDC(hdc_win), "CreateCompatibleDC")
    hbmp = _check(gdi32.CreateCompatibleBitmap(hdc_win, w, h), "CreateCompatibleBitmap")
    try:
        gdi32.SelectObject(hdc_mem, hbmp)
        flags = PW_RENDERFULLCONTENT | (PW_CLIENTONLY if client_only else 0)
        rendered = bool(user32.PrintWindow(hwnd, hdc_mem, flags))

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        _check(
            gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0),
            "GetDIBits",
        )
        img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
        return img, rendered
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_win)


# --------------------------------------------------------------------------- #
# Headless GUI: off-screen desktop
# --------------------------------------------------------------------------- #
user32.CreateDesktopW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
]
user32.CreateDesktopW.restype = HDESK
user32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenDesktopW.restype = HDESK
user32.CloseDesktop.argtypes = [HDESK]
user32.EnumDesktopWindows.argtypes = [HDESK, WNDENUMPROC, LPARAM]


class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
    wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
    ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION),
]
kernel32.CreateProcessW.restype = wintypes.BOOL

# name -> HDESK handle for desktops we created
_DESKTOPS: dict[str, int] = {}


def create_desktop(name: str) -> dict[str, Any]:
    """Create or reopen an off-screen desktop in the current window station."""
    existing = _DESKTOPS.get(name)
    if existing:
        return {
            "name": name,
            "handle": existing,
            "full": f"WinSta0\\{name}",
            "already_exists": True,
        }

    # Make repeated calls idempotent even after a server restart or a prior
    # caller opened the named desktop in this window station.
    reopened = user32.OpenDesktopW(name, 0, False, GENERIC_ALL)
    if reopened:
        _DESKTOPS[name] = int(reopened)
        return {
            "name": name,
            "handle": int(reopened),
            "full": f"WinSta0\\{name}",
            "already_exists": True,
        }

    hdesk = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    _check(hdesk, f"CreateDesktopW('{name}')")
    _DESKTOPS[name] = int(hdesk)
    return {
        "name": name,
        "handle": int(hdesk),
        "full": f"WinSta0\\{name}",
        "already_exists": False,
    }


def create_desktops(names: list[str]) -> list[dict[str, Any]]:
    """Create or reopen several independent headless desktops."""
    if not names:
        raise WinIOError("Provide at least one desktop name.")
    if len(set(names)) != len(names):
        raise WinIOError("Desktop names must be unique within one request.")
    return [create_desktop(name) for name in names]


def list_desktops() -> list[dict[str, Any]]:
    """List the headless desktops currently owned by this server process."""
    return [
        {
            "name": name,
            "handle": handle,
            "full": f"WinSta0\\{name}",
            "window_count": len(list_desktop_windows(name)),
        }
        for name, handle in list(_DESKTOPS.items())
    ]


def launch_on_desktop(name: str, command_line: str) -> dict[str, Any]:
    """Launch a process whose GUI appears on the off-screen desktop `name`."""
    if name not in _DESKTOPS:
        create_desktop(name)
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.lpDesktop = f"WinSta0\\{name}"
    si.dwFlags = STARTF_USESHOWWINDOW
    si.wShowWindow = SW_SHOWNORMAL
    pi = PROCESS_INFORMATION()
    cmd_buf = ctypes.create_unicode_buffer(command_line)
    ok = kernel32.CreateProcessW(
        None, cmd_buf, None, None, False, CREATE_NO_WINDOW, None, None,
        ctypes.byref(si), ctypes.byref(pi),
    )
    _check(ok, f"CreateProcessW('{command_line}')")
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(pi.hProcess)
    return {
        "desktop": name,
        "pid": int(pi.dwProcessId),
        "command": command_line,
        "terminal_window": False,
        "focus_stealing": False,
    }


def list_desktop_windows(name: str) -> list[dict[str, Any]]:
    """Enumerate top-level windows that live on the off-screen desktop `name`."""
    hdesk = _DESKTOPS.get(name)
    if hdesk is None:
        hdesk = user32.OpenDesktopW(name, 0, False, GENERIC_ALL)
        _check(hdesk, f"OpenDesktopW('{name}')")
        _DESKTOPS[name] = int(hdesk)
    out: list[dict[str, Any]] = []

    @WNDENUMPROC
    def cb(hwnd, _lparam):
        # Resolve identity while the HWND is valid in this desktop's enumeration
        # callback. A caller attached to another desktop may not be able to query it.
        process_id = wintypes.DWORD()
        thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        dpi = user32.GetDpiForWindow(hwnd)
        text = _get_window_text(hwnd)
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        out.append(
            {
                "handle": int(hwnd),
                "process_id": int(process_id.value),
                "thread_id": int(thread_id),
                "dpi": int(dpi),
                "title": text,
                "class": _get_class_name(hwnd),
                "width": r.right - r.left,
                "height": r.bottom - r.top,
            }
        )
        return True

    user32.EnumDesktopWindows(hdesk, cb, 0)
    return out


def close_desktop(name: str) -> dict[str, Any]:
    """Close our handle to the off-screen desktop (it is freed once no process uses it)."""
    hdesk = _DESKTOPS.pop(name, None)
    if hdesk is None:
        return {"name": name, "closed": False, "note": "not tracked"}
    user32.CloseDesktop(hdesk)
    cached = _XDESK_CACHE.pop(name, None)
    if cached:
        user32.CloseDesktop(cached)
    return {"name": name, "closed": True}


# --------------------------------------------------------------------------- #
# Temporary visibility: show a hidden window / switch to a headless desktop
# (e.g. so a human can complete an interactive login), then hide again.
# --------------------------------------------------------------------------- #
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9
DESKTOP_SWITCHDESKTOP = 0x0100

# Safety banner shown whenever a headless desktop becomes interactive.
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_SETFONT = 0x0030
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
SS_CENTER = 0x00000001
SS_CENTERIMAGE = 0x00000200
BS_DEFPUSHBUTTON = 0x00000001
DEFAULT_GUI_FONT = 17
COLOR_INFOBK = 24
EMERGENCY_EXIT_CONTROL_ID = 0xE911

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, wintypes.UINT, WPARAM, LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenInputDesktop.restype = HDESK
user32.SwitchDesktop.argtypes = [HDESK]
user32.SwitchDesktop.restype = wintypes.BOOL
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = HWND
user32.DefWindowProcW.argtypes = [HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.DestroyWindow.argtypes = [HWND]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = wintypes.HGDIOBJ
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# Remembers the input desktop we left so hide_desktop can switch back.
_saved_input_desktop: Optional[int] = None
_desktop_switch_lock = threading.RLock()


class _HeadlessSafetyBanner:
    """Non-dismissible top banner hosted directly on a headless Win32 desktop."""

    def __init__(self, desktop_name: str, instruction: str) -> None:
        self.desktop_name = desktop_name
        self.instruction = instruction
        self.ready = threading.Event()
        self.allow_close = threading.Event()
        self.error: Optional[BaseException] = None
        self.hwnd: Optional[int] = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"headless-safety-banner-{desktop_name}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()
        if not self.ready.wait(timeout=5):
            raise WinIOError("Timed out while creating the headless desktop safety banner.")
        if self.error is not None:
            raise WinIOError(f"Could not create the headless desktop safety banner: {self.error}")

    def close(self) -> None:
        self.allow_close.set()
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        hdesk = None
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"LowLevelCUSafetyBanner_{id(self):x}"

        @WNDPROC
        def window_proc(hwnd: HWND, message: int, wparam: int, lparam: int) -> int:
            if message == WM_COMMAND and (int(wparam) & 0xFFFF) == EMERGENCY_EXIT_CONTROL_ID:
                try:
                    _restore_input_desktop()
                except BaseException:
                    # Stay visible and usable if Windows refuses the switch; removing
                    # the only escape control would leave the user stranded.
                    return 0
                self.allow_close.set()
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_CLOSE:
                # Deliberately ignore Alt+F4 and close requests. Only normal cleanup or
                # the emergency-exit button sets allow_close first.
                if self.allow_close.is_set():
                    user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return int(user32.DefWindowProcW(hwnd, message, wparam, lparam))

        try:
            hdesk = user32.OpenDesktopW(self.desktop_name, 0, False, GENERIC_ALL)
            _check(hdesk, f"OpenDesktopW('{self.desktop_name}') for safety banner")
            _check(user32.SetThreadDesktop(hdesk), "SetThreadDesktop(safety banner)")

            window_class = WNDCLASSW()
            window_class.lpfnWndProc = window_proc
            window_class.hInstance = hinstance
            window_class.hbrBackground = wintypes.HBRUSH(COLOR_INFOBK + 1)
            window_class.lpszClassName = class_name
            _check(user32.RegisterClassW(ctypes.byref(window_class)), "RegisterClassW(safety banner)")

            width = max(640, user32.GetSystemMetrics(0))
            height = 72
            hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
                class_name,
                "Agent desktop instructions",
                WS_POPUP | WS_VISIBLE,
                0,
                0,
                width,
                height,
                None,
                None,
                hinstance,
                None,
            )
            _check(hwnd, "CreateWindowExW(safety banner)")
            self.hwnd = int(hwnd)

            message = (
                "AGENT TEMPORARY DESKTOP — "
                + self.instruction
                + "  Tell the agent when finished."
            )
            label_width = max(300, width - 220)
            label = user32.CreateWindowExW(
                0,
                "STATIC",
                message,
                WS_CHILD | WS_VISIBLE | SS_CENTER | SS_CENTERIMAGE,
                8,
                8,
                label_width,
                56,
                hwnd,
                None,
                hinstance,
                None,
            )
            _check(label, "CreateWindowExW(safety banner label)")
            button = user32.CreateWindowExW(
                0,
                "BUTTON",
                "EMERGENCY EXIT",
                WS_CHILD | WS_VISIBLE | BS_DEFPUSHBUTTON,
                width - 200,
                16,
                184,
                40,
                hwnd,
                wintypes.HMENU(EMERGENCY_EXIT_CONTROL_ID),
                hinstance,
                None,
            )
            _check(button, "CreateWindowExW(emergency exit button)")
            font = gdi32.GetStockObject(DEFAULT_GUI_FONT)
            user32.SendMessageW(label, WM_SETFONT, font, 1)
            user32.SendMessageW(button, WM_SETFONT, font, 1)
            self.ready.set()

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except BaseException as exc:
            self.error = exc
            self.ready.set()
        finally:
            self.hwnd = None
            user32.UnregisterClassW(class_name, hinstance)
            if hdesk:
                user32.CloseDesktop(hdesk)


_safety_banner: Optional[_HeadlessSafetyBanner] = None


def _restore_input_desktop() -> None:
    """Return to the saved input desktop without manipulating the banner."""
    global _saved_input_desktop
    with _desktop_switch_lock:
        target = _saved_input_desktop
        opened_default = False
        if target is None:
            target = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
            _check(target, "OpenDesktopW('Default')")
            opened_default = True
        _check(user32.SwitchDesktop(target), "SwitchDesktop(restore)")
        if _saved_input_desktop is not None:
            user32.CloseDesktop(_saved_input_desktop)
            _saved_input_desktop = None
        elif opened_default:
            user32.CloseDesktop(target)


def show_window(hwnd: int) -> dict[str, Any]:
    """Make a hidden/minimized window visible and bring it to the foreground.

    Use this when an automated app on the *normal* desktop needs human interaction
    (e.g. a login prompt). Pair with hide_window to put it away again afterwards.
    """
    if not user32.IsWindow(hwnd):
        raise WinIOError(f"No window with handle {hwnd}.")
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.SetForegroundWindow(hwnd)
    return {"hwnd": int(hwnd), "visible": True}


def hide_window(hwnd: int, minimize: bool = False) -> dict[str, Any]:
    """Hide a window again (SW_HIDE removes it from the taskbar; minimize just tucks it away)."""
    if not user32.IsWindow(hwnd):
        raise WinIOError(f"No window with handle {hwnd}.")
    user32.ShowWindow(hwnd, SW_MINIMIZE if minimize else SW_HIDE)
    return {"hwnd": int(hwnd), "visible": False, "minimized": minimize}


def show_desktop(
    name: str,
    instruction: str = "Complete the requested manual step.",
) -> dict[str, Any]:
    """Switch the live input desktop to a headless desktop so a human can use it.

    The whole off-screen desktop becomes the interactive one (its app windows are
    now on screen). Remember to call hide_desktop to return to the normal desktop -
    typically after the user finishes an interactive login.
    """
    global _saved_input_desktop, _safety_banner
    with _desktop_switch_lock:
        hdesk = _DESKTOPS.get(name)
        if hdesk is None:
            hdesk = user32.OpenDesktopW(name, 0, False, GENERIC_ALL)
            _check(hdesk, f"OpenDesktopW('{name}')")
            _DESKTOPS[name] = int(hdesk)
        if _safety_banner is not None:
            _safety_banner.close()
        banner = _HeadlessSafetyBanner(name, instruction)
        banner.start()
        _safety_banner = banner
        current = user32.OpenInputDesktop(0, False, GENERIC_ALL)
        _saved_input_desktop = int(current) if current else None
        try:
            _check(user32.SwitchDesktop(hdesk), f"SwitchDesktop('{name}')")
        except BaseException:
            banner.close()
            _safety_banner = None
            if _saved_input_desktop is not None:
                user32.CloseDesktop(_saved_input_desktop)
                _saved_input_desktop = None
            raise
    return {
        "name": name,
        "visible": True,
        "safety_banner": True,
        "note": (
            "This desktop is now interactive with a non-dismissible instruction banner. "
            "Call hide_headless_desktop to switch back; the user can also use EMERGENCY EXIT."
        ),
    }


def hide_desktop(name: Optional[str] = None) -> dict[str, Any]:
    """Switch the input desktop back to the one we came from (or 'Default')."""
    global _safety_banner
    _restore_input_desktop()
    banner = _safety_banner
    _safety_banner = None
    if banner is not None:
        banner.close()
    return {"restored": True}
