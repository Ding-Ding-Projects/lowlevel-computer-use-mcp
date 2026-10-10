[CmdletBinding(PositionalBinding=$false)]
param([string]$ReleaseCodename, [switch]$Silent, [Parameter(ValueFromRemainingArguments=$true)][string[]]$RemainingArguments)
foreach($argument in $RemainingArguments){
 if($argument -notin @("/s","--silent")){throw "Unsupported argument: $argument"}
 $Silent=$true
}
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if(-not [Environment]::Is64BitOperatingSystem){throw 'Windows x64 is required'}
& (Join-Path $root 'build.bat') -BootstrapOnly
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
# Use a compatible existing Node 22 installation; otherwise use verified portable Node.
$node=Get-Command node.exe -ErrorAction SilentlyContinue
$usable=$false
if($node){$version=& $node.Source --version; $usable=$LASTEXITCODE -eq 0 -and $version -match '^v22\.' -and [version]$version.Substring(1) -ge [version]'22.12.0'}
if(-not $usable){
 $cache=Join-Path $root '.bootstrap'
 New-Item -ItemType Directory -Force -Path $cache | Out-Null
 $archive=Join-Path $cache 'node-v22.16.0-win-x64.zip'
 if(-not(Test-Path -LiteralPath $archive)){Invoke-WebRequest -UseBasicParsing 'https://nodejs.org/dist/v22.16.0/node-v22.16.0-win-x64.zip' -OutFile $archive}
 $sha=[Security.Cryptography.SHA256]::Create()
 try{$actual=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($archive))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
 if($actual -cne '21c2d9735c80b8f86dab19305aa6a9f6f59bbc808f68de3eef09d5832e3bfbbd'){throw 'Pinned Node archive hash mismatch'}
 $stage=Join-Path $cache ('node-'+[Guid]::NewGuid().ToString('N'))
 Add-Type -AssemblyName System.IO.Compression.FileSystem
 [IO.Compression.ZipFile]::ExtractToDirectory($archive,$stage)
 $nodeDir=Join-Path $stage 'node-v22.16.0-win-x64'
}else{$nodeDir=Split-Path -Parent $node.Source}
$env:PATH=$nodeDir+';'+$env:PATH
$npm=Join-Path $nodeDir 'npm.cmd'
if(-not(Test-Path -LiteralPath $npm)){throw 'Node installation lacks npm.cmd'}
$argsList=@((Join-Path $root 'scripts/package-installer.py'),'--node',(Join-Path $nodeDir 'node.exe'),'--npm-cli',(Join-Path $nodeDir 'node_modules/npm/bin/npm-cli.js'))
if($ReleaseCodename){$argsList+=@('--codename',$ReleaseCodename)}
& (Join-Path $root '.venv/Scripts/python.exe') @argsList
exit $LASTEXITCODE
