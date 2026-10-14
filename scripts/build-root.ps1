[CmdletBinding(PositionalBinding=$false)]
param([switch]$BootstrapOnly, [switch]$Silent, [string]$EnvironmentPath, [Parameter(ValueFromRemainingArguments=$true)][string[]]$RemainingArguments)
foreach($argument in $RemainingArguments){
 if($argument -notin @("/s","--silent")){throw "Unsupported argument: $argument"}
 $Silent=$true
}
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if(-not [Environment]::Is64BitOperatingSystem){throw 'Windows x64 is required'}
$cache=Join-Path $root '.bootstrap'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$archive=Join-Path $cache 'uv-0.12.20.zip'
$expected='1502e03f4da3280cbb493d356d59bdd401bf23197cd71df64e1c6feac156090c'
if(-not(Test-Path -LiteralPath $archive)){
 Invoke-WebRequest -UseBasicParsing 'https://files.pythonhosted.org/packages/1f/72/c98ecbe0c4dbaf9118776053688a43dfca5708d86223cf3aa5d38066df21/uv-0.12.20-py3-none-win_amd64.whl' -OutFile $archive
}
$sha=[Security.Cryptography.SHA256]::Create()
try{$actual=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($archive))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
if($actual -cne $expected){throw 'Pinned uv archive hash mismatch'}
$unpacked=Join-Path $cache ('uv-0.12.20-'+[Guid]::NewGuid().ToString('N'))
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive,$unpacked)
$uv=Get-ChildItem -LiteralPath $unpacked -Recurse -Filter uv.exe | Select-Object -First 1 -ExpandProperty FullName
if(-not $uv){throw 'Pinned uv executable is absent'}
$previousEnvironment=$env:UV_PROJECT_ENVIRONMENT
try {
 if($EnvironmentPath){
  $environment=[IO.Path]::GetFullPath($EnvironmentPath)
 }else{
  $environment=Join-Path $root '.venv'
 }
 $env:UV_PROJECT_ENVIRONMENT=$environment
 & $uv sync --frozen --python 3.13.15
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
 if($BootstrapOnly){exit 0}
 & $uv build --wheel
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
 & (Join-Path $environment 'Scripts/python.exe') -m compileall -q src/lowlevel_computer_use_mcp
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
}finally{
 $env:UV_PROJECT_ENVIRONMENT=$previousEnvironment
}
Write-Output 'Build complete: isolated locked Python environment, wheel and bytecode. Existing optional C++ binaries are not required by the ctypes hidden-resize worker.'
exit 0
