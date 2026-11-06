param([switch]$SkipBuild, [switch]$FocusedOnly, [switch]$AfterBackend, [switch]$AcceptanceOnly, [string]$MvpPath = '', [ValidatePattern('^opspilot-full-test-[a-z0-9-]+$')][string]$Project = 'opspilot-full-test-f18-regression', [string]$ComposeOverride = 'compose.full.f13-checks.yaml')
$EnvFile = '.env'
$ErrorActionPreference = 'Stop'
$env:COMPOSE_PARALLEL_LIMIT='1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$composeArgs = @('compose', '--env-file', $EnvFile, '-p', $Project, '-f', 'compose.full.yaml', '-f', 'compose.full.test.yaml')
if ($ComposeOverride) { $composeArgs += @('-f', $ComposeOverride) }
$composeArgs += @('-f', 'compose.full.f16-checks.yaml')
$composeArgs += @('-f', 'compose.full.f17-checks.yaml')
function Invoke-Checks {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Release check failed (exit $LASTEXITCODE)" }
}
New-Item -ItemType Directory -Force docs/full/evidence/f18/regression/process, docs/full/evidence/f18/regression/evals | Out-Null
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
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f18/regression/mvp-before-gates.json
if($LASTEXITCODE){throw 'MVP prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f17-manager.py
if($LASTEXITCODE){throw 'Reviewed real secrets manager prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f15-cache.py --test
if($LASTEXITCODE){throw 'Private test cache preparation'}
& .venv/Scripts/python.exe scripts/setup-full-f16-observability.py --test
if($LASTEXITCODE){throw 'Protected test telemetry preparation'}
try {
    if (-not $SkipBuild) {
        Invoke-Checks -Arguments @('build','api','tests','postgres','oidc','redis')
        Invoke-Checks -Arguments @('build','web','e2e')
    }
    $existing=[string](& docker ps -aq --filter "name=^/${Project}-postgres-1`$")
    if($AcceptanceOnly -and -not [string]::IsNullOrWhiteSpace($existing)){throw 'Fresh browser/process project required; existing fixture data is preserved'}
    if(-not [string]::IsNullOrWhiteSpace($existing)){
        $previous=(& docker inspect $existing.Trim() --format '{{.Image}}').Trim()
        $current=(& docker image inspect opspilot-full/postgres:f01 --format '{{.Id}}').Trim()
        if($LASTEXITCODE -or $previous -ne $current){
            throw 'Database runtime changed; use a fresh F18 test project, never reuse old libc volume'
        }
    }else{
        $oldVolume=[string](& docker volume ls -q --filter "name=^${Project}_pgdata`$")
        if(-not [string]::IsNullOrWhiteSpace($oldVolume)){throw 'Unproven existing test volume; select a fresh F18 project'}
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
    if ($FocusedOnly) {
        Invoke-Checks -Arguments @('run','--rm','tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/integration/test_lifecycle.py','tests/integration/test_lifecycle_serialization.py')
        return
    }
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'ruff', 'check', '--no-cache', 'src', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'ruff', 'format', '--check', '--no-cache', 'src', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'mypy', '--cache-dir', '/tmp/opspilot-mypy', 'src')
    if(-not $AcceptanceOnly){
    if(-not $AfterBackend){Invoke-Checks -Arguments @('run', '--rm', 'tests')}
    Invoke-Checks -Arguments @('run','--rm','--no-deps','-v',"${PWD}:/work:ro",'admin','python','/work/scripts/check-f09-security-state.py')
    Invoke-Checks -Arguments @('run','--rm','--no-deps','-v',"${PWD}:/work:ro",'admin','python','/work/scripts/check-full-f17-security-state.py')
    Invoke-Checks -Arguments @('run','--rm','--no-deps','-e','TEST_F15_PROCESS=1','tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/integration/test_governance.py','-k','crash_after_dispatch_reservation')
    & ./scripts/test-full-f18-redis-restart.ps1 -Project $Project
    if($LASTEXITCODE){throw 'Redis outage/restart gate'}
    # Negative fencing/backend fixtures intentionally retain stale claims. Browser/process
    # acceptance uses a separate seeded database; no jobs or leases are deleted/repaired.
    Invoke-Checks -Arguments @('stop')
    $acceptanceProject=$Project+'-browser-'+[guid]::NewGuid().ToString('N').Substring(0,8)
    & $PSCommandPath -SkipBuild -AcceptanceOnly -Project $acceptanceProject
    if($LASTEXITCODE){throw 'Fresh browser/process/supply-chain acceptance failed'}
    return
    }
    # Native TLS/collector/MFA and manager drills use their separate scoped runners.
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'oidc', 'web')
    Invoke-Checks -Arguments @('up', '-d', 'worker', 'worker2')
    Invoke-Checks -Arguments @('exec','-T','api','python','-c',"from pathlib import Path; assert Path('/run/service-private/current.pem').is_file(); assert not Path('/run/service-private/grant-current.pem').exists()")
    Invoke-Checks -Arguments @('exec','-T','worker','python','-c',"from pathlib import Path; assert Path('/run/service-private/current.pem').is_file(); assert not Path('/run/service-private/grant-current.pem').exists(); assert Path('/run/manager-client/token').is_file()")
    Invoke-Checks -Arguments @('exec','-T','mcp','python','-c',"from pathlib import Path; assert Path('/run/service-public/grants.json').is_file(); assert not Path('/run/service-private/grant-current.pem').exists()")
    Invoke-Checks -Arguments @('run','--rm','--no-deps','-v',"${PWD}:/work:ro",'admin','python','/work/scripts/wait-full-test-queue.py')
    Invoke-Checks -Arguments @('run', '--rm', 'e2e')
    Invoke-Checks -Arguments @('stop', 'worker', 'worker2')
    Invoke-Checks -Arguments @('stop', 'api')
    Invoke-Checks -Arguments @('run', '--rm', '--no-deps', '-e', 'TEST_QUEUE_PROCESSES=1', '-e', 'WORKER_LEASE_SECONDS=3', '-e', 'WORKER_HEARTBEAT_SECONDS=1', 'tests', 'python', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'tests/integration/test_durable_jobs.py')
    Invoke-Checks -Arguments @('run','--rm','--no-deps','-e','TEST_F06_PROCESSES=1','-e','WORKER_LEASE_SECONDS=3','-e','WORKER_HEARTBEAT_SECONDS=1','-e','F06_REPORT_DIR=/reports/process','-v', "${PWD}/docs/full/evidence/f18/regression:/reports",'tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/integration/test_execution_fences.py')
    & ./scripts/scan-full-f15-security.ps1 -ReportDir docs/full/evidence/f18/regression/security
    if($LASTEXITCODE){throw 'F15 IdP supply-chain gate failed'}
    $revision = (& git rev-parse HEAD).Trim()
    $evalArgs = @('run', '--rm', '--no-deps', '-v', "${PWD}/docs/full/evidence/f18/regression/evals:/reports-f16", '-e','OPENAI_API_KEY=','-e','LLM_MODE=scripted','evals', 'python', '-m', 'opspilot.evals.runner', '--output', '/reports-f16', '--mode', 'scripted', '--commit', $revision)
    if (& git status --porcelain) { $evalArgs += '--dirty' }
    Invoke-Checks -Arguments $evalArgs
} finally {
    & docker @composeArgs stop
}
