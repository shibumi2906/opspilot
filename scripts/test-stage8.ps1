param([string]$Project = 'opspilot-test', [string]$EnvFile = '.env', [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$composeArgs = @('compose', '--env-file', $EnvFile, '-p', $Project, '-f', 'compose.yaml', '-f', 'compose.test.yaml')
function Invoke-Checks {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Release check failed (exit $LASTEXITCODE)" }
}
try {
    if (-not $SkipBuild) { Invoke-Checks -Arguments @('build', 'api', 'mcp', 'tests', 'web', 'e2e') }
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'postgres')
    Invoke-Checks -Arguments @('run', '--rm', 'admin')
    Invoke-Checks -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.seed')
    Invoke-Checks -Arguments @('up', '-d', '--wait', 'mcp', 'api', 'web')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'ruff', 'check', '--no-cache', 'src', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'ruff', 'format', '--check', '--no-cache', 'src', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'tests', 'mypy', '--cache-dir', '/tmp/opspilot-mypy', 'src')
    Invoke-Checks -Arguments @('run', '--rm', 'tests')
    Invoke-Checks -Arguments @('run', '--rm', 'e2e')
    Invoke-Checks -Arguments @('stop', 'api')
    Invoke-Checks -Arguments @('run', '--rm', '--no-deps', '-e', 'TEST_RECOVERY_API=1', 'tests', 'python', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'tests/integration/test_api_restart.py')
    $revision = (& git rev-parse HEAD).Trim()
    $evalArgs = @('run', '--rm', '--no-deps', 'evals', 'python', '-m', 'opspilot.evals.runner', '--mode', 'scripted', '--commit', $revision)
    if (& git status --porcelain) { $evalArgs += '--dirty' }
    Invoke-Checks -Arguments $evalArgs
} finally {
    & docker @composeArgs stop
}
