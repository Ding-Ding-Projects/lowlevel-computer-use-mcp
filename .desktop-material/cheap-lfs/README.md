<!-- desktop-material-managed-cheap-lfs-clone-helper:v1 -->
# Restore Cheap LFS files

Desktop Material generated this helper from the Cheap LFS pointers committed in
this repository. It downloads the selected GitHub Release assets with GitHub
CLI, verifies every decoded part and the complete file by exact byte size and
SHA-256, then replaces the matching pointer. Existing files that do not match
the managed pointer or the already-restored payload are left untouched.

Requirements: Node.js and GitHub CLI. For a private repository, authenticate
GitHub CLI with an account that can read the repository and its Releases.

## Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\.desktop-material\cheap-lfs\hydrate.ps1"
```

## Linux

```sh
sh ./.desktop-material/cheap-lfs/hydrate.sh
```

With no arguments the helper restores every supported pointer in
`hydrate-inventory.json`. The separate `inventory.json` is Desktop
Material's bounded clone-selection hint. To restore only chosen files, append
one or more
`--path "repository/relative/file"` arguments. Use `--list` to print the
available paths.

Raw, multipart, and raw-DEFLATE GitHub Release pointers are supported. The
helper stops with an actionable message for encrypted Release or OCI registry
pointers; restore those through Desktop Material so its password and immutable
registry validation remain in the trusted app flow.
