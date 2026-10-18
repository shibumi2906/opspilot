$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$composeArgs = @('compose', '-p', 'opspilot-test', '-f', 'compose.yaml', '-f', 'compose.test.yaml')

function Invoke-TestCompose {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Test Compose failed (exit $LASTEXITCODE)" }
}

Invoke-TestCompose -Arguments @('build', 'api', 'mcp', 'tests', 'web', 'e2e')
try {
    Invoke-TestCompose -Arguments @('up', '-d', '--wait', 'postgres')
    Invoke-TestCompose -Arguments @('run', '--rm', 'admin')
    Invoke-TestCompose -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.seed')
    Invoke-TestCompose -Arguments @('up', '-d', '--wait', 'mcp', 'api', 'web')
    Invoke-TestCompose -Arguments @('run', '--rm', 'tests')
    Invoke-TestCompose -Arguments @('run', '--rm', 'e2e')
    Invoke-TestCompose -Arguments @('stop', 'api')
    Invoke-TestCompose -Arguments @('run', '--rm', '--no-deps', '-e', 'TEST_RECOVERY_API=1', 'tests', 'python', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'tests/integration/test_api_restart.py')
} finally {
    # Keep the isolated test volume for diagnosis; never remove demo data.
    & docker @composeArgs stop
}
