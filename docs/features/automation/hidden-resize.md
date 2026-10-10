# Exact hidden-desktop resize

`resize_hidden_window` is separate from unchanged ordinary `resize_window`.
The caller must freshly prove launch ancestry, native process incarnation and HWND ownership.

```json
{"desktop_name":"Owned-Capture","handle":12345,"pid":6789,"creation_filetime":"134360000000000000","executable_path":"C:\\Example\\App.exe","expected_outer":[0,0,1200,800],"width":760,"height":560}
```

Pass this JSON to the cheap CLI on standard input. The worker opens only the exact existing
named desktop in the current window station. Default, Winlogon and Disconnect are rejected.
It attaches its own thread, enumerates only that desktop and matches exact HWND/native PID.
A retained query/synchronize process handle validates exact decimal FILETIME and executable
path before and after dispatch. Missing desktop, stale geometry and changed identity fail closed.

Per-monitor-v2 DPI awareness plus SetWindowPos NOMOVE, NOZORDER, NOACTIVATE, NOOWNERZORDER and
ASYNCWINDOWPOS preserve requested position, activation and ordering. No show/hide, foreground,
input or desktop-switch API is invoked. Post-operation outer dimensions must match within three
seconds. Outer/client rectangles and native DPI are separate physical-pixel facts. An application
minimum size or unprocessed request is unsuccessful. An asynchronous request is not rolled back
on timeout. The six-second worker timeout does not prove that no request was applied.
The worker restores its original thread desktop/DPI context and closes owned handles.

`build.bat` bootstraps hash-pinned uv 0.9.5, locked dependencies and Python 3.13.15 into this
checkout only, emits a wheel and compiles bytecode. The ctypes worker requires no additional C++
binary. The existing optional native producer remains scripts/build-native.ps1.
`build-installer.bat` exits 2 because no genuine supported Squirrel installer target exists;
the client-registration GUI is not such an installer.

`python tests/test_hidden_resize.py` exercises request, identity, exact desktop ownership,
stale geometry, deadline and positive dispatch with a fake adapter. These are source controls,
not kernel/application acceptance. Independent review and source/output binding precede any
actual resize. No installed cutover is part of this recovery.

Primary contracts: [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos),
[SetThreadDesktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddesktop),
[OpenDesktopW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-opendesktopw).
