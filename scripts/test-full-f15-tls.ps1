param([switch]$SkipBuild, [string]$ReportDir='docs/full/evidence/f15/tls')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$project='opspilot-full-security-f15-final'
$compose=@('compose','-p',$project,'-f','.tools/security-f15-final/compose.json')
function Invoke-Lab([string[]]$Arguments) {
    & docker @compose @Arguments
    if($LASTEXITCODE){throw "Security lab check failed: $($Arguments[0])"}
}
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$overlay=Join-Path (Get-Location) '.tools/security-f15-final-report-overlay.json'
@{services=@{probe=@{volumes=@("${reports}:/reports")};browser=@{volumes=@("${reports}:/reports");ipc='private';shm_size='256m';mem_limit='1g';memswap_limit='1g';environment=@{NODE_OPTIONS='--max-old-space-size=256'}}}} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $overlay
$compose += @('-f',$overlay)
if(-not $SkipBuild){
    & docker compose --env-file .env -p opspilot-full-security-build -f compose.full.yaml -f compose.full.test.yaml build api tests web e2e oidc postgres redis
    if($LASTEXITCODE){throw 'Security images build failed'}
}
if(-not (Test-Path -LiteralPath '.tools/security-f15-final/compose.json')){
    $generator = Get-Content -Raw -LiteralPath 'infra/security/generate_local.py'
    $generator = $generator.Replace('ROOT = Path(__file__).resolve().parents[2]', 'ROOT = Path.cwd()')
    $generator = $generator.Replace('.tools/security-local', '.tools/security-f15-final')
    $generator = $generator.Replace('"name": "opspilot-full-security"', '"name": "opspilot-full-security-f15-final"')
    Set-Content -LiteralPath '.tools/f15-generate-lab-final.py' -Value $generator -Encoding utf8NoBOM
    & docker run --rm -u root -v "${PWD}:/work" -w /work --entrypoint python opspilot-full/tests:f01 .tools/f15-generate-lab-final.py
    if($LASTEXITCODE){throw 'Lab generation failed'}
}
& docker run --rm --network none -u root -v "${PWD}/.tools/security-f15-final:/lab" --entrypoint python opspilot-full/tests:f01 -c "from pathlib import Path;Path('/lab').chmod(0o755)"
if($LASTEXITCODE){throw 'Lab mount permissions failed'}
Invoke-Lab -Arguments @('up','-d','--wait','postgres','redis','oidc')
Invoke-Lab -Arguments @('run','--rm','admin')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.seed')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.bootstrap_identity')
Invoke-Lab -Arguments @('up','-d','--wait','api','mcp','worker','web')
Invoke-Lab -Arguments @('run','--rm','probe')
Invoke-Lab -Arguments @('run','--rm','probe','python','/work/scripts/probe-full-f15-redis.py')
Invoke-Lab -Arguments @('run','--rm','browser')
Write-Host 'Local TLS/MFA lab verified; production ASVS L2 acceptance remains separate.'
