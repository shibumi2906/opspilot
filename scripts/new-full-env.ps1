param([string]$OutputPath = '.env')
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputPath) { throw 'Refusing to replace an existing environment file.' }
$template = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../.env.full.example')
foreach ($match in [regex]::Matches($template, '(?m)^(?:API|WEB|JAEGER|OIDC)_PORT=(\d+)')) {
    $port = [int]$match.Groups[1].Value
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() }
    catch { throw "Full port $port unavailable; select a free port in the Full template." }
    finally { $listener.Stop() }
}
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    foreach ($name in @('MCP_SERVICE_TOKEN', 'POSTGRES_PASSWORD', 'WORKFLOW_DB_PASSWORD', 'DOMAIN_DB_PASSWORD', 'CHECKPOINT_DB_PASSWORD')) {
        $bytes = New-Object byte[] 32
        $generator.GetBytes($bytes)
        $value = -join ($bytes | ForEach-Object { '{0:x2}' -f $_ })
        $template = $template -replace "(?m)^$name=
?$", "$name=$value"
    }
    [System.IO.File]::WriteAllText($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath), $template)
} finally { $generator.Dispose() }
Write-Output 'Created an environment file with independent random local secrets.'
