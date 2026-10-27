param([switch]$SkipBuild, [string]$ReportDir='docs/security/hardening/evidence')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$project='opspilot-full-security'
$compose=@('compose','-p',$project,'-f','.tools/security-local/compose.json')
function Invoke-Lab([string[]]$Arguments) {
    & docker @compose @Arguments
    if($LASTEXITCODE){throw "Security lab check failed: $($Arguments[0])"}
}
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$overlay=Join-Path (Get-Location) '.tools/security-report-overlay.json'
@{services=@{probe=@{volumes=@("${reports}:/reports")};browser=@{volumes=@("${reports}:/reports")}}} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $overlay
$compose += @('-f',$overlay)
if(-not $SkipBuild){
    & docker compose --env-file .env -p opspilot-full-security-build -f compose.full.yaml -f compose.full.test.yaml build api tests web e2e oidc postgres
    if($LASTEXITCODE){throw 'Security images build failed'}
}
if(-not (Test-Path -LiteralPath '.tools/security-local/compose.json')){
    & docker run --rm -u root -v "${PWD}:/work" -w /work --entrypoint python opspilot-full/tests:f01 infra/security/generate_local.py
    if($LASTEXITCODE){throw 'Lab generation failed'}
}
Invoke-Lab -Arguments @('up','-d','--wait','postgres','oidc')
Invoke-Lab -Arguments @('run','--rm','admin')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.seed')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.bootstrap_identity')
Invoke-Lab -Arguments @('up','-d','--wait','api','mcp','worker','web')
Invoke-Lab -Arguments @('run','--rm','probe')
Invoke-Lab -Arguments @('run','--rm','browser')
Write-Host 'Local TLS/MFA lab verified; production ASVS L2 acceptance remains separate.'
