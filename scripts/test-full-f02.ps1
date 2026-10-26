param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$compose = @('compose', '-p', 'opspilot-full-f02-migrations', '-f', 'compose.full.yaml', '-f', 'compose.full.test.yaml', '-f', 'compose.full.migrations.yaml')
function Invoke-MigrationCheck {
    param([string[]]$Arguments)
    & docker @compose @Arguments
    if ($LASTEXITCODE) { throw "F02 migration check failed: $LASTEXITCODE" }
}
try {
    if (-not $SkipBuild) { Invoke-MigrationCheck -Arguments @('build','postgres','api','mcp','tests','web','e2e') }
    Invoke-MigrationCheck -Arguments @('run','--rm','--no-deps','tests','ruff','check','--no-cache','src','tests','migrations')
    Invoke-MigrationCheck -Arguments @('run','--rm','--no-deps','tests','ruff','format','--check','--no-cache','src','tests','migrations')
    Invoke-MigrationCheck -Arguments @('up','-d','--wait','postgres')
    Invoke-MigrationCheck -Arguments @('run','--rm','--no-deps','tests')
} finally { & docker @compose stop }
& (Join-Path $PSScriptRoot 'test-full-f01.ps1') -SkipBuild
