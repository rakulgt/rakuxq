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

    & scp $archive "${SshAlias}:/tmp/rakuxq-$revision.tar.gz"
    & scp models/pose.onnx "${SshAlias}:/tmp/rakuxq-pose.onnx"
    & scp models/layout.onnx "${SshAlias}:/tmp/rakuxq-layout.onnx"
    & scp scripts/deploy-server.sh "${SshAlias}:/tmp/deploy-rakuxq-server.sh"
    if (Test-Path -LiteralPath $KeyDatabase) {
        & scp $KeyDatabase "${SshAlias}:/tmp/rakuxq-api-keys.sqlite3"
    }
    if ($LASTEXITCODE -ne 0) { throw 'Uploading deployment inputs failed.' }

    & ssh $SshAlias "bash /tmp/deploy-rakuxq-server.sh '$revision' '$Domain' '$Port'"
    if ($LASTEXITCODE -ne 0) { throw 'Remote deployment failed.' }
}
finally {
    Pop-Location
}
