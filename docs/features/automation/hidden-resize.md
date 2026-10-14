# Exact hidden-desktop resize

`resize_hidden_window` is separate from unchanged ordinary `resize_window`.
The caller must freshly prove launch ancestry, native process incarnation and HWND ownership.

```json
{"desktop_name":"Owned-Capture","handle":12345,"pid":6789,"creation_filetime":"134360000000000000","executable_path":"C:\\Example\\App.exe","expected_outer":[0,0,1200,800],"width":760,"height":560}
```

Pass this JSON through the cheap CLI's existing `--json <JSON>` option. The worker opens only the exact existing
named desktop in the current window station. Default, Winlogon and Disconnect are rejected.
It attaches its own thread, enumerates only that desktop and matches exact HWND/native PID.
A retained query/synchronize process handle validates exact decimal FILETIME and executable
path before and after dispatch. Missing desktop, stale geometry and changed identity fail closed.
Before dispatch and throughout observation, OpenInputDesktop and GetUserObjectInformationW
read the current input desktop name. A matching name or unavailable probe rejects the operation.
This checks observed state; it cannot atomically prevent an external desktop switch after a check.

Per-monitor-v2 DPI awareness plus SetWindowPos NOMOVE, NOZORDER, NOACTIVATE, NOOWNERZORDER and
ASYNCWINDOWPOS preserve requested position, activation and ordering. No show/hide, foreground,
input or desktop-switch API is invoked. Post-operation outer dimensions must match within three
seconds. Outer/client rectangles and native DPI are separate physical-pixel facts. An application
minimum size or unprocessed request is unsuccessful. An asynchronous request is not rolled back
on timeout. The six-second worker timeout does not prove that no request was applied.
The worker restores its original thread desktop/DPI context and closes owned handles.
Each restoration is attempted independently. A failed DPI restore cannot skip desktop restore
or desktop close, and any restoration failure prevents a successful result.

`build.bat` bootstraps hash-pinned uv 0.12.20, locked dependencies and Python 3.13.15 into this
checkout only, emits a wheel and compiles bytecode. The ctypes worker requires no additional C++
binary. The existing optional native producer remains scripts/build-native.ps1.
`build-installer.bat` packages the existing manual client through its real Squirrel.Windows
target. It is separate from the Python client-registration GUI. See the [installer producer](../releases/README.md).

`python tests/test_hidden_resize.py` exercises request, identity, exact desktop ownership,
stale geometry, deadline and positive dispatch with a fake adapter, including active-desktop rejection with zero dispatch, native input-name API boundary checks,
and continuation after each individual restoration fault. Eleven controls pass; deliberate
active-desktop omission and premature cleanup termination each fail before exact restoration.
These are source controls, not kernel/application acceptance. Independent review and source/output binding precede any
actual resize. No installed cutover is part of this recovery.

Primary contracts: [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos),
[SetThreadDesktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddesktop),
[OpenDesktopW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-opendesktopw).

## Observed native boundary

At source 5aa63767d491e7de104ae9d2ab4eb206560b0a80, the isolated CLI resized
one exact owned hidden target from physical outer 1822x1139 to 1222x911, retaining
its origin. The result independently matched physical client 1200x900, native
DPI144 and renderer 800x600 at DPR1.5. The input desktop remained different from
the target. Owner-held capture/layout and normal-close absence receipts remain
private. The operation source is unchanged in the verified 1fe2 producer.
The geometry receipt SHA-256 is
37881989d601cb69bb60c109bc3732afd3903f27dd561573477655b8e16e28c8.
This proves that bounded native resize, not physical 100-percent scaling, native
input, restart, installed helper cutover or a complete feature matrix.
