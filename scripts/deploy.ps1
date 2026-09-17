[CmdletBinding()]
param(
    [string]$SshAlias = 'raku-cn',
    [string]$Domain = 'xq.rakubank.com',
    [int]$Port = 8040,
    [string]$KeyDatabase = '.secrets/api-keys.sqlite3'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $ProjectRoot
try {
    $status = (& git status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Git status.' }
    if ($status) { throw 'Commit the project before production deployment.' }

    $revision = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve Git revision.' }
    & python scripts/verify_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Model verification failed.' }

    $stage = Join-Path $ProjectRoot "tmp/deploy-$revision"
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $archive = Join-Path $stage "rakuxq-$revision.tar.gz"
    & git archive --format=tar.gz --output=$archive HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Git archive failed.' }

    $poseUpload = Join-Path $stage 'rakuxq-pose.onnx'
    $layoutUpload = Join-Path $stage 'rakuxq-layout.onnx'
    $serverScriptUpload = Join-Path $stage 'deploy-rakuxq-server.sh'
    Copy-Item -LiteralPath models/pose.onnx -Destination $poseUpload -Force
    Copy-Item -LiteralPath models/layout.onnx -Destination $layoutUpload -Force
    Copy-Item -LiteralPath scripts/deploy-server.sh -Destination $serverScriptUpload -Force
    $uploads = @($archive, $poseUpload, $layoutUpload, $serverScriptUpload)
    if (Test-Path -LiteralPath $KeyDatabase) {
        $keyDatabaseUpload = Join-Path $stage 'rakuxq-api-keys.sqlite3'
        Copy-Item -LiteralPath $KeyDatabase -Destination $keyDatabaseUpload -Force
        $uploads += $keyDatabaseUpload
    }
    & scp @uploads "${SshAlias}:/tmp/"
    if ($LASTEXITCODE -ne 0) { throw 'Uploading deployment inputs failed.' }

    & ssh $SshAlias "bash /tmp/deploy-rakuxq-server.sh '$revision' '$Domain' '$Port'"
    if ($LASTEXITCODE -ne 0) { throw 'Remote deployment failed.' }
}
finally {
    Pop-Location
}
