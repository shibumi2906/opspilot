param([switch]$SkipBuild, [string]$Project = 'opspilot-full-test-f07')
$EnvFile = '.env'
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$composeArgs = @('compose', '--env-file', $EnvFile, '-p', $Project, '-f', 'compose.full.yaml', '-f', 'compose.full.test.yaml')
function Invoke-Checks {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Release check failed (exit $LASTEXITCODE)" }
}
New-Item -ItemType Directory -Force docs/full/evidence/f07/process, docs/full/evidence/f07/evals | Out-Null
$keysPath=Join-Path (Get-Location) '.tools/service-keys'
New-Item -ItemType Directory -Force $keysPath | Out-Null
if ([Environment]::OSVersion.Platform -eq 'Unix') { & chmod 0777 $keysPath }
try {
    if (-not $SkipBuild) { Invoke-Checks -Arguments @('build', 'oidc', 'postgres', 'collector', 'jaeger', 'api', 'mcp', 'tests', 'web', 'e2e') }
    Invoke-Checks -Arguments @('run','--rm','--no-deps','service-keys')
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'postgres', 'oidc')
    Invoke-Checks -Arguments @('run', '--rm', 'admin')
    Invoke-Checks -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.seed')
    Invoke-Checks -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.bootstrap_identity')
    Invoke-Checks -Arguments @('stop','worker','worker2')
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'collector', 'jaeger', 'mcp', 'api', 'web')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'ruff', 'check', '--no-cache', 'src', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'ruff', 'format', '--check', '--no-cache', 'src', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'mypy', '--cache-dir', '/tmp/opspilot-mypy', 'src')
    Invoke-Checks -Arguments @('run', '--rm', 'tests')
    Invoke-Checks -Arguments @('up', '-d', 'worker', 'worker2')
    Invoke-Checks -Arguments @('run', '--rm', 'e2e')
    Invoke-Checks -Arguments @('stop', 'worker', 'worker2')
    Invoke-Checks -Arguments @('stop', 'api')
    Invoke-Checks -Arguments @('run', '--rm', '--no-deps', '-e', 'TEST_QUEUE_PROCESSES=1', '-e', 'WORKER_LEASE_SECONDS=3', '-e', 'WORKER_HEARTBEAT_SECONDS=1', 'tests', 'python', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'tests/integration/test_durable_jobs.py')
    Invoke-Checks -Arguments @('run','--rm','--no-deps','-e','TEST_F06_PROCESSES=1','-e','WORKER_LEASE_SECONDS=3','-e','WORKER_HEARTBEAT_SECONDS=1','-e','F06_REPORT_DIR=/reports/process','-v', "${PWD}/docs/full/evidence/f07:/reports",'tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/integration/test_execution_fences.py')
    $revision = (& git rev-parse HEAD).Trim()
    $evalArgs = @('run', '--rm', '--no-deps', 'evals', 'python', '-m', 'opspilot.evals.runner', '--mode', 'scripted', '--commit', $revision)
    if (& git status --porcelain) { $evalArgs += '--dirty' }
    Invoke-Checks -Arguments $evalArgs
} finally {
    & docker @composeArgs stop
}
