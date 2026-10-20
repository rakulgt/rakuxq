[CmdletBinding()]
param([string]$BaseUrl = 'https://xq.rakubank.com')

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
if ($BaseUrl -notin @('https://xq.rakubank.com', 'https://xq-fast.rakubank.com', 'http://127.0.0.1:8052')) {
    throw 'Unexpected legal smoke-test target.'
}
$session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$status = Invoke-RestMethod "$BaseUrl/api/legal/status" -WebSession $session -TimeoutSec 15
if ($status.accepted -or !$status.acceptance_available -or $status.training_collection_enabled) {
    throw 'Unexpected initial legal status.'
}
foreach ($name in @('terms', 'privacy')) {
    $page = Invoke-WebRequest "$BaseUrl/$name" -WebSession $session -TimeoutSec 15
    if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'RakuXQ' -or $page.Content -match '\{\{(TITLE|BODY)\}\}') {
        throw "Invalid rendered $name page."
    }
    $text = Invoke-WebRequest "$BaseUrl/legal/$($status.version)/$name.txt" -WebSession $session -TimeoutSec 15
    $bytes = [Text.Encoding]::UTF8.GetBytes([string]$text.Content)
    $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    if ($actual -ne $status."${name}_sha256") { throw "Wrong $name hash." }
}
$payload = @{version=$status.version; terms_sha256=$status.terms_sha256; privacy_sha256=$status.privacy_sha256; accepted=$true; training_license=$true} | ConvertTo-Json -Compress
$blocked = Invoke-WebRequest "$BaseUrl/api/legal/acceptances" -Method Post -ContentType 'application/json' -Body $payload -Headers @{Origin='https://unrelated.invalid'} -SkipHttpErrorCheck -TimeoutSec 15
if ($blocked.StatusCode -ne 403) { throw 'Cross-origin acceptance was not blocked.' }
$accepted = Invoke-RestMethod "$BaseUrl/api/legal/acceptances" -Method Post -ContentType 'application/json' -Body $payload -Headers @{Origin=$BaseUrl} -WebSession $session -TimeoutSec 15
if (!$accepted.accepted) { throw 'Explicit acceptance failed.' }
$saved = Invoke-RestMethod "$BaseUrl/api/legal/status" -WebSession $session -TimeoutSec 15
if (!$saved.accepted) { throw 'Receipt was not persisted.' }
$anonymous = Invoke-WebRequest "$BaseUrl/v1/recognitions" -Method Post -SkipHttpErrorCheck -TimeoutSec 15
if ($BaseUrl.StartsWith('https://') -and $anonymous.StatusCode -ne 401) { throw 'Existing API authentication changed.' }
[pscustomobject]@{target=$BaseUrl; version=$saved.version; documents_and_hashes='passed'; explicit_receipt='passed'; cross_origin='blocked'; training_collection=$saved.training_collection_enabled; api_auth=$anonymous.StatusCode}
