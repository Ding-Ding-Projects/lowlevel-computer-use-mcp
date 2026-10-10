param([switch]$BootstrapOnly)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if(-not [Environment]::Is64BitOperatingSystem){throw 'Windows x64 is required'}
$cache=Join-Path $root '.bootstrap'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$archive=Join-Path $cache 'uv-0.9.5.zip'
$expected='48a12390421f91af8a8993cf15c38297c0bb121936046286e287975b2fbf1789'
if(-not(Test-Path -LiteralPath $archive)){
 Invoke-WebRequest -UseBasicParsing 'https://files.pythonhosted.org/packages/af/14/0f07d0b2e561548b4e3006208480a5fce8cdaae5247d85efbfb56e8e596b/uv-0.9.5-py3-none-win_amd64.whl' -OutFile $archive
}
$sha=[Security.Cryptography.SHA256]::Create()
try{$actual=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($archive))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
if($actual -cne $expected){throw 'Pinned uv archive hash mismatch'}
$unpacked=Join-Path $cache ('uv-0.9.5-'+[Guid]::NewGuid().ToString('N'))
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive,$unpacked)
$uv=Get-ChildItem -LiteralPath $unpacked -Recurse -Filter uv.exe | Select-Object -First 1 -ExpandProperty FullName
if(-not $uv){throw 'Pinned uv executable is absent'}
& $uv sync --frozen --python 3.13.15
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
if($BootstrapOnly){exit 0}
& $uv build --wheel
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& (Join-Path $root '.venv/Scripts/python.exe') -m compileall -q src/lowlevel_computer_use_mcp
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
Write-Output 'Build complete: isolated locked Python environment, wheel and bytecode. Existing optional C++ binaries are not required by the ctypes hidden-resize worker.'
exit 0
