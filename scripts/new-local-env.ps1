param([string]$OutputPath = '.env')
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputPath) { throw 'Refusing to replace an existing environment file.' }
$template = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../.env.example')
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    foreach ($name in @('MCP_SERVICE_TOKEN', 'POSTGRES_PASSWORD', 'WORKFLOW_DB_PASSWORD', 'DOMAIN_DB_PASSWORD', 'CHECKPOINT_DB_PASSWORD')) {
        $bytes = New-Object byte[] 32
        $generator.GetBytes($bytes)
        $value = -join ($bytes | ForEach-Object { '{0:x2}' -f $_ })
        $template = $template -replace "(?m)^$name=?$", "$name=$value"
    }
    [System.IO.File]::WriteAllText($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath), $template)
} finally { $generator.Dispose() }
Write-Output 'Created an environment file with independent random local secrets.'
