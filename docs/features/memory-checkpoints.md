# Memory checkpoints and local revisions

## Behaviour

The Electron Memory page saves a named snapshot of the app-owned settings,
saved LAN connections, subagent lanes, and tab layout. Each checkpoint carries
its creation time, action, and local revision when Git is available. Restore is
an append-only action: the current state is checkpointed first, then the chosen
state is applied and a second revision records the restore.

The checkpoint search is plain-text-first and has its own bounded regex builder.
The page exports a Markdown index of checkpoints and shows whether each revision
is Git-backed or snapshot-only.

## Configuration

Open the **Memory** tab, enter a meaningful label, and choose **Save
checkpoint**. The app stores the record under Electron's user-data directory.
The isolated version repository is `local-versions/` below that directory and
never lives inside a project the user is automating.

## Failure modes

- An empty label is rejected without writing a record.
- A missing checkpoint produces an error notification and changes no state.
- If local Git cannot initialize or commit, the checkpoint remains usable as a
  snapshot-only record and its metadata contains the reason.
- Restoring does not silently discard the current state: the app creates a
  before-restore checkpoint first.

## Security

Checkpoint data stays local. The app does not upload it, add it to the LAN API,
or place it in the user's project folder. Connection records are treated as
user-managed data; do not put secrets into a saved URL or label.

## Verification

`electron/contract-check.cjs` checks the Memory IPC surface and UI controls.
The Electron off-screen capture includes the Memory page. The Python suite and
Electron syntax/contract checks run before packaging. Manual runtime proof
should create a checkpoint, inspect the isolated local Git revision, restore it,
and confirm that the restore appears as a new entry. The console-free backend
probe `npm run start --prefix electron -- --memory-self-test` produced two
distinct local revisions in a fresh profile during this task.

## Suggested articles

- [Electron manual client](electron-manual-client.md) — the surrounding app
- [Tab groups and bulk close](tab-management.md) — the state most often restored
- [Trusted LAN API](trusted-lan-api.md) — connection security and scope
