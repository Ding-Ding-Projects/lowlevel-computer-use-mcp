[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release',
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $repositoryRoot '.native-build-vs2026'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repositoryRoot 'src\lowlevel_computer_use_mcp\native'
}

$cmake = Get-Command cmake.exe -ErrorAction Stop
$developerCommand = Get-ChildItem 'C:\Program Files\Microsoft Visual Studio' -Recurse -Filter VsDevCmd.bat -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $developerCommand) {
    throw 'A Visual Studio C++ developer command prompt was not found.'
}
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$configure = '"{0}" -no_logo -arch=x64 && "{1}" -S "{2}" -B "{3}" -G Ninja -DCMAKE_BUILD_TYPE={4}' -f @(
    $developerCommand.FullName, $cmake.Source, (Join-Path $repositoryRoot 'native'), $buildRoot, $Configuration
)
& cmd.exe /d /s /c $configure
if ($LASTEXITCODE -ne 0) { throw "CMake configure failed with exit code $LASTEXITCODE." }
$build = '"{0}" -no_logo -arch=x64 && "{1}" --build "{2}" --parallel' -f @(
    $developerCommand.FullName, $cmake.Source, $buildRoot
)
& cmd.exe /d /s /c $build
if ($LASTEXITCODE -ne 0) { throw "CMake build failed with exit code $LASTEXITCODE." }

$built = Join-Path $buildRoot "bin\lowlevel_win32_native.dll"
if (-not (Test-Path -LiteralPath $built)) {
    throw "Native build reported success but did not produce $built."
}
Copy-Item -LiteralPath $built -Destination (Join-Path $OutputDirectory 'lowlevel_win32_native.dll') -Force
$supervisor = Join-Path $buildRoot "bin\lowlevel_mcp_supervisor.exe"
if (-not (Test-Path -LiteralPath $supervisor)) {
    throw "Native build reported success but did not produce $supervisor."
}
Copy-Item -LiteralPath $supervisor -Destination (Join-Path $OutputDirectory 'lowlevel_mcp_supervisor.exe') -Force
Get-FileHash -Algorithm SHA256 -LiteralPath @(
    (Join-Path $OutputDirectory 'lowlevel_win32_native.dll'),
    (Join-Path $OutputDirectory 'lowlevel_mcp_supervisor.exe')
)
