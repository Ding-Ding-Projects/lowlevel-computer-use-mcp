# desktop-material-managed-cheap-lfs-clone-helper:v1
$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -LiteralPath $PSCommandPath -Parent
& node (Join-Path $scriptDirectory 'hydrate.mjs') @args
exit $LASTEXITCODE
