# Headless desktops and multi-agent isolation

## Behavior

Windows headless desktops are real Win32 desktops created with `CreateDesktopW`.
`create_headless_desktops` creates several in one request; explicit `names` are
best for durable project identity, while `prefix` plus `count` is convenient for
parallel agents. Existing names are reopened idempotently. `list_headless_desktops`
reports the server-owned desktops and current window counts.

Use a name such as `project-a-agent-2-1` for each project/agent workspace. Launch
GUI apps with `launch_on_headless_desktop`, then use HWND-targeted input and
`PrintWindow` capture. The server never calls `SwitchDesktop` for background work.

## Failure modes

- Duplicate names in one batch are rejected before a desktop is created.
- A desktop with a still-running process is not destroyed merely by closing the
  server's handle; close those processes first.
- `show_headless_desktop` is the explicit human-login exception and displays the
  non-dismissible safety banner with Emergency Exit.

## Security

Desktop names are coordination labels, not access control. All agents under the
same Windows user can potentially access the same window station. Use distinct
names and do not put secrets in names or commands.

## Verification

The model tests cover generated project/agent names, duplicate rejection, and
targeted hotkey inputs. Win32 enumeration and capture tests remain Windows-host
runtime checks because this CI environment may not provide a GUI desktop.
