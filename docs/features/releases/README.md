# Windows installer production

The root `build-installer.bat` packages the existing manual client using its locked
`electron-builder --win squirrel --publish never` command. It bootstraps Python
through `build.bat -BootstrapOnly`, then reuses compatible Node 22.12 or later in
major 22 with npm. Otherwise it verifies and extracts portable Node 22.16.0 from
the official distribution into the ignored local bootstrap directory. Global
runtimes, installed helpers and signing stores remain untouched.

The generated configuration starts from an exact deep copy of the existing package build configuration, retaining app identity, product naming, file selection, Squirrel icon URL and x64 target. Only output, unsigned settings and optional catalog mapping are overridden.

Each run has a unique ignored `dist/installer/<id>` output directory. Its JSON
receipt retains the source hash, tracked before/after hashes, index trees, actual
child exit codes, tool/configuration hashes and generated assets. An optional
`-ReleaseCodename <json>` is copied into that run's packaging configuration,
never written over the tracked catalog document. Child environments omit signing
credentials and disable automatic signing discovery. The actual Squirrel producer
must succeed and emit a setup executable, RELEASES and a full package. Setup.exe
is copied only when the producer's executable has a different path.

The release workflow runs on branch pushes and manual dispatch, excludes branch
deletion and publisher-created tags, and invokes the exact root entrypoints.
It runs no tests or lint. Local verification remains separate. Safe logs, receipts,
wheel and Squirrel outputs are retained defensively after failure for seven days;
retention failures cannot mask a producer failure. Generated catalog notes remain
in runner scratch storage. GitHub exits are checked before consuming outputs.

The bundled catalog entry and image come from Ding-Ding-Projects/dim-sum-photos,
catalog-v1 asset hk-dish-0001-classic-har-gow.png. The image was decoded and visually
inspected before inclusion. SHA-256:
`c6ff2d32938f1e4c4ea685442f69227b8cd387f302ab8f8a62e8dd96c62b5ac0`.
This is release decoration, not application evidence. Exhausting this bounded
catalog produces the existing truthful Unassigned build result rather than an
invented unused dish. Every release still attaches the bundled reviewed photo.

Successful packaging does not prove package consistency, unsigned executable
status, installation, updater behavior or running application acceptance. Inspect
RELEASES hashes and sizes, full-package decompression and actual unsigned assets
before accepting the producer. Release readback verifies normal classification,
source tag and asset names separately. Release notes disclose unsigned assets and
unknown-publisher/SmartScreen warnings, local verification limits and measured
workflow timing. The correction is source-only until two reviews and real root
producers finish.
