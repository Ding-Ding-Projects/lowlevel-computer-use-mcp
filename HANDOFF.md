# Handoff

The pulled `main` checkout now contains multi-agent headless desktop APIs,
quiet child-process launch helpers, automatic AutoHotkey installation in the GUI
installer, a trusted-LAN Streamable HTTP API with command/file transfer routes,
and an Electron Material 3 manual client under `electron/`. The client can
explicitly host the retired compatibility API, save named remote computers, and
route later tool calls to one of those saved connections; ordinary local calls
use the Cheap Version.

The current Electron pass also adds a
native inline Quick launch app browser with a visible Browse button, a complete tool catalog, independent
tab-search regex state, a full-history changelog, persistent tab groups with
reviewable bulk-close actions, a public catalog-backed release code name, and
quiet runtime repair for the Electron binary cache. This pass adds a persisted
Memory page with Git-backed local revisions and append-only restores, a Tool runner file-transfer card with bounded send/receive and user-controlled saves, and a per-target appearance editor with typography controls and presets. The next verification pass
should run the Windows-only headless desktop tests and a second-computer LAN
check. Static Python compilation and model tests do not prove those runtime
boundaries.

## Current task: make Cheap Version primary and retire legacy HTTP startup

Implemented in the working tree:

- The Cheap Version is the primary local tool route and exposes only registered
  MCP tool functions; transport endpoints such as `/health` are not callable
  through its CLI catalog.
- The installer removes the retired `lowlevel-computer-use-http` entries from
  Claude, Codex, and OpenCode configuration before registering quiet `pythonw`
  compatibility stdio entries.
- The old persistent HTTP/logon launcher is retired by default. `install-startup`
  refuses unless `--legacy-http` is explicitly supplied; the GUI offers cleanup,
  not a new logon service.
- The Electron Tool runner uses the Cheap Version for local calls. Its LAN API
  controls are labelled as explicit compatibility transport and no longer offer
  logon installation.
- The hidden GUI entry point uses the same Cheap Version implementation, and the
  installer now imports the shared hidden-command helper correctly.
- Feature, API, README, roadmap, and handoff documentation describe the new
  default and the explicit compatibility boundary.

Verification so far:

- Python unit suite: 43 tests ran, with 42 passed and one expected non-Windows
  branch skipped; the new Cheap Version catalog and retired-startup tests are
  included.
- `compileall`, `git diff --check`, `uv lock --check`, and `uv build` passed.
- Electron contract verification and the packaged Squirrel.Windows installer
  check passed.
- Live user-profile migration is verified: the `lowlevel-computer-use-http` entry
  was removed from Claude, Codex, and OpenCode; `LowLevelComputerUseMCP` was
  removed from Task Scheduler; and no Startup-folder launcher remains.
- The installed `venv-primary` environment runs the Cheap Version catalog without
  `health` or `api_execute`, returns a real `get_screen_size` result, and has the
  MCP dependency bounded to the compatible `<2.0.0` API range.
- A real `pythonw.exe -m lowlevel_computer_use_mcp.server --help` launch exited
  successfully with zero matching top-level windows from the Cheap Version
  window enumeration. No non-Cheap Python process remains with `--http`.
- `npm run check` passed. The package produced the Windows Squirrel installer
  under `electron/dist/squirrel-windows/`.
- The first Ubuntu release test exposed a missing `tkinter` runtime dependency;
  `.github/workflows/ci-release.yml` now installs `python3-tk` before the locked
  test environment is synchronized, so the installer migration tests exercise
  the same GUI import path on both operating systems.

## Remote handoff

- This file ships in the integration commit. Issue #1 and Discussion #2 are the
  rolling sources
  for its exact pushed hash, Actions run, release, Pages, and wiki evidence.
- GitHub Pages is enabled for Actions after the first deployment attempt found
  no configured Pages site; the corrected deployment run is being monitored.
- Remote CI/release state is recorded as running, failed, or verified in the
  issue and Discussion rather than predicted here.
- The final audit found no stash entries. The main checkout retains its unrelated
  `software/docker.exe` modification; it is outside this task and was not staged.
