param([string]$OutputDirectory = 'docs/assets')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$recordName = 'opspilot-demo-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$scriptPath = Join-Path (Get-Location) 'web/demo.mjs'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Demo command failed ($LASTEXITCODE)" } }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
try {
    docker run -d --name $recordName --network opspilot_default --mount "type=bind,source=$scriptPath,target=/app/web/demo.mjs,readonly" -e DEMO_BASE_URL=http://web opspilot:e2e node demo.mjs
    Check-Exit
    docker exec $recordName node -e "const fs=require('fs');const t=setInterval(()=>{if(fs.existsSync('/tmp/opspilot-demo/restart-ready')){clearInterval(t);process.exit(0)}},500);setTimeout(()=>process.exit(1),90000)"
    Check-Exit
    docker kill --signal KILL opspilot-api-1
    Check-Exit
    docker start opspilot-api-1
    Check-Exit
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $health = docker inspect --format '{{.State.Health.Status}}' opspilot-api-1
        if ($health -eq 'healthy') { break }
        Start-Sleep -Milliseconds 500
    }
    if ($health -ne 'healthy') { throw 'OpsPilot API did not become healthy.' }
    docker exec $recordName node -e "require('fs').writeFileSync('/tmp/opspilot-demo/restart-done','healthy')"
    Check-Exit
    $exitCode = docker wait $recordName
    if ($exitCode -ne '0') { docker logs $recordName; throw 'Recording failed.' }
    docker cp "${recordName}:/tmp/opspilot-demo/opspilot-demo.webm" "$OutputDirectory/opspilot-demo.webm"
    Check-Exit
    foreach ($name in @('workspace','evidence','pending','verified','rejected')) {
        docker cp "${recordName}:/tmp/opspilot-demo/$name.png" "$OutputDirectory/$name.png"
        Check-Exit
    }
} finally {
    docker rm -f $recordName
}
