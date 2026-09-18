[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\tmp\pikafish-2026-09-06")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$release = "Pikafish-2026-09-06"
$archiveName = "Pikafish.2026-09-06.7z"
$archiveSha256 = "41952bbfe2520faceb5902c69e6ab4845cc999841d2b49a95cc1be7867a25e5b"
$downloadUrl = "https://github.com/official-pikafish/Pikafish/releases/download/$release/$archiveName"
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$archivePath = Join-Path $destinationPath $archiveName
$partialPath = "$archivePath.part"
$markerPath = Join-Path $destinationPath ".extracted-$archiveSha256"

New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null

if (-not (Test-Path -LiteralPath $archivePath)) {
    & curl.exe --fail --location --retry 3 --output $partialPath $downloadUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Pikafish download failed with exit code $LASTEXITCODE"
    }
    Move-Item -LiteralPath $partialPath -Destination $archivePath
}

$actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
if ($actualSha256 -ne $archiveSha256) {
    throw "Pikafish archive SHA-256 mismatch: expected $archiveSha256, got $actualSha256"
}

if (-not (Test-Path -LiteralPath $markerPath)) {
    & tar -xf $archivePath -C $destinationPath
    if ($LASTEXITCODE -ne 0) {
        throw "Pikafish extraction failed with exit code $LASTEXITCODE"
    }
    New-Item -ItemType File -Force -Path $markerPath | Out-Null
}

$engine = Get-ChildItem -LiteralPath $destinationPath -Recurse -File |
    Where-Object { $_.Name -eq "Pikafish-Windows-x86-64-universal.exe" } |
    Select-Object -First 1
$network = Get-ChildItem -LiteralPath $destinationPath -Recurse -File |
    Where-Object { $_.Name -eq "pikafish.nnue" } |
    Select-Object -First 1

if ($null -eq $engine -or $null -eq $network) {
    throw "The verified archive did not contain the expected Windows engine and NNUE network."
}

$networkSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $network.FullName).Hash.ToLowerInvariant()

Write-Output "Verified local Pikafish assets (not added to Git):"
Write-Output "  release: $release"
Write-Output "  engine:  $($engine.FullName)"
Write-Output "  network: $($network.FullName)"
Write-Output "  network SHA-256: $networkSha256"
Write-Output ""
Write-Output "Configure the current PowerShell session with:"
Write-Output ('  $env:RAKUXQ_ENGINE_PATH = "{0}"' -f $engine.FullName)
Write-Output ('  $env:RAKUXQ_ENGINE_NETWORK = "{0}"' -f $network.FullName)
Write-Output ('  $env:RAKUXQ_ENGINE_VERSION = "{0}"' -f $release)
