# Handoff

## Current hidden resize recovery

The canonical source was cloned and verified before isolated recovery. The
current implementation is preserved at `1fe2a321c22114dd921be9f27b51c0e97b4ace36`.
Later documentation changes do not rebind these producer results to a new source.

Exact `build.bat /s` and `build-installer.bat /s` both exited 0. Each retained
122 unchanged tracked inputs plus source/tree/index/ref/status. Their complete
output inventories contain 16,064 and 18,606 rows. Independent byte audit covered
18,728 unique paths with zero differences. The wheel passed CRC and exact worker/
server source-byte comparison. No fresh-environment bootstrap claim is made.

The genuine Squirrel full package passed all 89 entries and RELEASES SHA1/size
verification. Setup/main/stub/updater are unsigned; two vendor graphics DLLs retain
valid catalog signatures. Eight packaged runtime/catalog source files match.
The independent bounded package/privacy review accepted the inspected entries and
app.asar pattern scan, with zero matches. This is bounded package evidence, not
installation, updater, packaged runtime or publication acceptance.

A source-bound native resize at `5aa63767d491e7de104ae9d2ab4eb206560b0a80`
produced a 1222 by 911 physical outer rectangle, 1200 by 900 physical client,
DPI 144 and 800 by 600 renderer at DPR 1.5. The operation source is unchanged in
1fe2. The owner retained 25 validated captures/layouts and normal-close absence
proof. No physical 100-percent display-scale, native input or restart claim follows.
Consumer identities, captures and raw machine-specific receipts remain private.

The source operation has eleven focused controls and deliberate omission witnesses.
Installer boundaries have seven focused controls and deliberate silent-binding,
self-copy, signing-environment and inherited-config omission witnesses.

### Preserved failed attempts

- `d6c5697`: root build failed because Get-FileHash was unavailable; module-independent
  .NET hashing/archive extraction repaired bootstrap.
- The first root installer returned 2 with an incorrect nonapplicability claim;
  the existing manual client already had a supported Squirrel target.
- `a18cd48`: build passed; installer exited 1 after interpreting /s as a codename
  path. Explicit non-positional binding repaired argument handling.
- `13dcbd9`: build passed; real Squirrel packaging exited 1 because generated config
  lost the inherited icon and product settings. Deep-copying the real package
  build configuration repaired that boundary.
- A BOM-unaware inspection attempt failed on valid RELEASES text. The original
  inspector result is retained; BOM-aware byte inspection passed without changing
  package bytes.

All original failed receipts and final setup/package/feed bytes remain in private
owner-managed evidence storage. Only public-safe summaries are tracked here.
See [producer documentation](docs/features/releases/README.md) and the
[versioned verification summary](docs/features/releases/verification-1fe2.json).

### Remaining owner actions

Integration and release remain coordinator-owned. Installation/update lifecycle,
optional scratch catalog packaging, packaged runtime and fresh-machine bootstrap
remain unverified. The installed/shared helper inventory retained fifteen unchanged
rows. No installation, cutover, integration, release or publication occurred in
this isolated recovery lane.

## Historical inherited baseline

The records below predate this isolated recovery. Their older workflow and runtime
claims are retained as history and are superseded by the current scope above.

## Native Windows runtime and resilient transport

The Windows package now contains a C++ DLL that owns named desktop handles for
the lifetime of the server process and performs quiet process creation with
optional GUI-readiness waiting. A separate GUI-subsystem C++ supervisor proxies
stdio byte-for-byte and performs bounded child restart without creating a console
window. Installer registration prefers that supervisor when packaged and keeps
the existing `pythonw.exe` route as the explicit fallback. The independent
`lowlevel-computer-use-cheap` entry point remains available whether or not MCP is
running.

Focused evidence on Windows: the native build succeeded with MSVC 19.51; six
native bridge tests passed with one expected non-Windows branch skipped; eight
headless multi-agent tests passed; and the live native round trip created,
reopened, launched on, and closed a named desktop without a terminal window.
The new `native_backend_status` tool reports the loaded DLL, active backend, ABI,
or exact fallback reason.

## Repository ownership links

The canonical repository, homepage, Pages metadata, release-download links, and
Electron documentation/changelog URLs now use
`Ding-Ding-Projects/lowlevel-computer-use-mcp`. The Pages site is
`https://ding-ding-projects.github.io/lowlevel-computer-use-mcp/`. The Windows
installer links use the verified `automation-31156143884-1` release asset.

The Electron `appId` remains unchanged because it is installed application
identity rather than a repository link.

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

## Verified hidden-resize recovery and releases, 2026-10-10

The bounded recovery is integrated and independently verified on main at
fb78adc8065a41fd490e9abe29a264f3e77d85d3. Its isolated task branch remains in use
by an active dependent capture and is retained. Both exact local root producers
passed at 1fe2a321c22114dd921be9f27b51c0e97b4ace36, with 122 stable inputs and
18,728 independently verified unique output paths. These historical results are
not rebound to the later documentation revision.

Both workflow publications are verified normal releases, with direct tags at
fb78adc and all six expected assets checked by API hash, size and actual delivery:

- https://github.com/Ding-Ding-Projects/lowlevel-computer-use-mcp/releases/tag/automation-38054417261-1
- https://github.com/Ding-Ding-Projects/lowlevel-computer-use-mcp/releases/tag/automation-38054635110-1

Distinct package bytes passed CRC/decompression and RELEASES consistency. Exact
matching wheel, photo and packaged payload bytes were reused by hash. The actual
cloud publication exercised the optional generated catalog path. Product
executables are unsigned; vendor catalog signatures remain separate. Installation,
update lifecycle, fresh-machine bootstrap and packaged runtime remain unverified.

Issue 6 is completed after exact handoff readback. Discussion 7 preserves progress;
Announcements Discussion 8 records the verified releases. PinDiscussionInput is
unavailable in the exposed schema, so pinning is not claimed. The exact About
homepage and live home/article HTTP 200 were verified. Wiki discovery was
unavailable. Preserve every original producer, package and private announcement;
no installed/shared helper cutover or deletion occurred.
