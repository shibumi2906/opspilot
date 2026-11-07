param([switch]$SkipBuild, [string]$MvpPath = '', [ValidatePattern('^opspilot-full-test-f19-[a-z0-9-]+$')][string]$Project = 'opspilot-full-test-f19-regression', [string]$ComposeOverride = 'compose.full.f13-checks.yaml')
$EnvFile = '.env'
$ErrorActionPreference = 'Stop'
$env:COMPOSE_PARALLEL_LIMIT='1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$composeArgs = @('compose', '--env-file', $EnvFile, '-p', $Project, '-f', 'compose.full.yaml', '-f', 'compose.full.test.yaml')
if ($ComposeOverride) { $composeArgs += @('-f', $ComposeOverride) }
$composeArgs += @('-f', 'compose.full.f16-checks.yaml')
$composeArgs += @('-f', 'compose.full.f17-checks.yaml', '-f', 'compose.full.f19-regression.yaml')
function Invoke-Checks {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Release check failed (exit $LASTEXITCODE)" }
}
New-Item -ItemType Directory -Force docs/full/evidence/f19/regression/process, docs/full/evidence/f19/regression/evals | Out-Null
$keysPath=Join-Path (Get-Location) '.tools/service-keys'
New-Item -ItemType Directory -Force $keysPath | Out-Null
if ([Environment]::OSVersion.Platform -eq 'Unix') { & chmod 0777 $keysPath }
if (-not $MvpPath) {
    $locatorPath = Join-Path (Get-Location) '.tools/opspilot-full-workspace.json'
    if (Test-Path -LiteralPath $locatorPath) {
        $MvpPath = (Get-Content -Raw -LiteralPath $locatorPath | ConvertFrom-Json).mvp_path
    }
}
if (-not $MvpPath) { throw 'Explicit MVP path or workspace locator required; never infer from independent Git storage' }
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f19/regression/mvp-before-gates.json
if($LASTEXITCODE){throw 'MVP prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f17-manager.py
if($LASTEXITCODE){throw 'Reviewed real secrets manager prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f15-cache.py --test
if($LASTEXITCODE){throw 'Private test cache preparation'}
& .venv/Scripts/python.exe scripts/setup-full-f16-observability.py --test
if($LASTEXITCODE){throw 'Protected test telemetry preparation'}
try {
    if (-not $SkipBuild) {
        Invoke-Checks -Arguments @('build','api','tests')

    }
    $existing=[string](& docker ps -aq --filter "name=^/${Project}-postgres-1`$")
    if(-not [string]::IsNullOrWhiteSpace($existing)){
        $previous=(& docker inspect $existing.Trim() --format '{{.Image}}').Trim()
        $current=(& docker image inspect opspilot-full/postgres:f01 --format '{{.Id}}').Trim()
        if($LASTEXITCODE -or $previous -ne $current){
            throw 'Database runtime changed; use a fresh F19 test project, never reuse old libc volume'
        }
    }else{
        $oldVolume=[string](& docker volume ls -q --filter "name=^${Project}_pgdata`$")
        if(-not [string]::IsNullOrWhiteSpace($oldVolume)){throw 'Unproven existing test volume; select a fresh F19 project'}
    }
    $otherServices=@(& docker ps --filter 'network=opspilot-full-test-f17-manager_default' --format '{{.Label "com.docker.compose.project"}} {{.Label "com.docker.compose.service"}}' | Where-Object {
        $pair=$_ -split ' '; $pair.Count -eq 2 -and $pair[0] -ne $Project -and $pair[1] -in @('postgres','redis','oidc','api','mcp','worker','worker2','web')
    })
    if($otherServices.Count){throw 'Another test profile owns shared service DNS aliases; stop only that test profile before continuing'}
    Invoke-Checks -Arguments @('run','--rm','--no-deps','service-keys')
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'postgres', 'redis', 'oidc')
    Invoke-Checks -Arguments @('run', '--rm', 'admin')
    Invoke-Checks -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.seed')
    Invoke-Checks -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.bootstrap_identity')
    Invoke-Checks -Arguments @('stop','worker','worker2')
    Invoke-Checks -Arguments @('run','--rm','--no-deps','telemetry-init')
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'collector', 'mcp', 'api', 'web')
    Invoke-Checks -Arguments @('restart','web')
    Invoke-Checks -Arguments @('run','--rm','tests','ruff','check','--no-cache','src','tests')
    Invoke-Checks -Arguments @('run','--rm','tests','ruff','format','--check','--no-cache','src','tests')
    Invoke-Checks -Arguments @('run','--rm','tests','mypy','--cache-dir','/tmp/f19-mypy','src')
    Invoke-Checks -Arguments @('run','--rm','tests')
} finally {
    & docker @composeArgs stop
}
