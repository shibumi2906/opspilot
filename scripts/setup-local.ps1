param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Create .env from .env.example and fill database passwords and MCP token first.'
}

function Invoke-LocalCompose {
    param([string[]]$Arguments)
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Local setup failed (exit $LASTEXITCODE)" }
}

if (-not $SkipBuild) {
    Invoke-LocalCompose -Arguments @('build', 'api', 'mcp')
}
Invoke-LocalCompose -Arguments @('up', '-d', '--wait', 'postgres')
Invoke-LocalCompose -Arguments @('run', '--rm', 'admin')
Invoke-LocalCompose -Arguments @('run', '--rm', 'admin', 'python', '-m', 'opspilot.cli.seed')
Invoke-LocalCompose -Arguments @('run', '--rm', '--no-deps', 'api', 'python', '-m', 'opspilot.cli.init_checkpoints')
Invoke-LocalCompose -Arguments @('up', '-d', '--wait', 'mcp', 'api')
Write-Output 'Local opspilot database and services ready: http://127.0.0.1:8000/health (default port).'
