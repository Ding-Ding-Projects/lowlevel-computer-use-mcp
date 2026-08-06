#!/usr/bin/env sh
# desktop-material-managed-cheap-lfs-clone-helper:v1
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec node "$script_dir/hydrate.mjs" "$@"
