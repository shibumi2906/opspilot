param([Parameter(Mandatory=$true)][string]$MvpPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8='1'
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f17/mvp-before-rollout.json
if($LASTEXITCODE){throw 'MVP rollout prerequisite'}
$sourceVolume=(& docker inspect opspilot-full-postgres-1 --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}').Trim()
if($LASTEXITCODE -or $sourceVolume -ne 'opspilot-full_pgdata'){
    throw 'One-time F16 upgrade requires original Full volume; refuse before stopping services'
}
$sourceImage=(& docker inspect opspilot-full-postgres-1 --format '{{.Image}}').Trim()
$originalImage=(& docker image inspect opspilot-full/postgres:f16-before-f17 --format '{{.Id}}').Trim()
if($LASTEXITCODE -or $sourceImage -ne $originalImage){throw 'Preserved original PostgreSQL image required'}
& .venv/Scripts/python.exe scripts/setup-full-f17-manager.py --local
if($LASTEXITCODE){throw 'Independent Full manager preparation'}
$compose=@('compose','--env-file','.env','-p','opspilot-full','-f','compose.full.yaml','-f','compose.full.f17-local.yaml')
function Check {param([string[]]$A) & docker @compose @A; if($LASTEXITCODE){throw 'Full F17 rollout failed'}}
Check -A @('stop','-t','150','worker','worker2')
Check -A @('stop','api','mcp')
& docker start opspilot-full-postgres-1
if($LASTEXITCODE){throw 'Preserved F16 PostgreSQL container required before upgrade'}
for($attempt=0;$attempt -lt 40;$attempt++){
    & docker exec opspilot-full-postgres-1 pg_isready -U ops_migration -d opspilot_full | Out-Null
    if(-not $LASTEXITCODE){break}
    Start-Sleep -Milliseconds 500
}
if($LASTEXITCODE){throw 'Preserved F16 database not ready'}
$before=(& docker @compose run --rm --no-deps -v "${PWD}/scripts/fingerprint-full-f17.py:/fingerprint.py:ro" admin python /fingerprint.py | ConvertFrom-Json)
if($LASTEXITCODE -or $before.schema -ne '0017_observability'){throw 'Expected preserved F16 database; do not repeat a committed migration'}
$before | ConvertTo-Json -Depth 8 | Set-Content .tools/f17-rollout-before.json
Check -A @('stop','postgres')
& .venv/Scripts/python.exe scripts/backup-full-f17-local.py --before-file .tools/f17-rollout-before.json
if($LASTEXITCODE){throw 'Encrypted backup/fresh isolated restore prerequisite'}
# Recover the original runtime for a logical dump; never mount old bytes into musl.
& docker start opspilot-full-postgres-1
if($LASTEXITCODE){throw 'Original Full PostgreSQL restart'}
& .venv/Scripts/python.exe scripts/migrate-full-f17-postgres.py --before-file .tools/f17-rollout-before.json
if($LASTEXITCODE){throw 'Verified logical restore prerequisite; original volume preserved'}
Check -A @('stop','postgres')
$volume=(Get-Content -Raw .tools/f17-postgres-volume.json | ConvertFrom-Json).volume
if($volume -notmatch '^opspilot-full-f17-logical-[a-f0-9]{12}$'){throw 'Unexpected Full volume'}
@{volumes=@{pgdata=@{external=$true;name=$volume}}} | ConvertTo-Json -Depth 5 | Set-Content .tools/f17-postgres-volume-overlay.json
$compose += @('-f','.tools/f17-postgres-volume-overlay.json')
Check -A @('up','-d','--wait','postgres')
Check -A @('run','--rm','admin')
$after=(& docker @compose run --rm --no-deps -v "${PWD}/scripts/fingerprint-full-f17.py:/fingerprint.py:ro" admin python /fingerprint.py | ConvertFrom-Json)
if($LASTEXITCODE -or $after.schema -ne '0018_lifecycle'){throw 'Expected F17 schema'}
foreach($field in $before.PSObject.Properties.Name){
    if($field -eq 'schema'){continue}
    if($before.$field.count -ne $after.$field.count -or $before.$field.sha256 -ne $after.$field.sha256){throw "Preserved Full data mismatch: $field"}
}
@{before=$before;after=$after;preserved=$true;timing='After migration, before workers and smoke; all legacy columns included'} | ConvertTo-Json -Depth 8 | Set-Content docs/full/evidence/f17/rollout-preservation.json
$envText=[IO.File]::ReadAllText((Join-Path $PWD '.env'))
if($envText -match '(?m)^FULL_F17_PG_VOLUME='){
    $envText=[regex]::Replace($envText,'(?m)^FULL_F17_PG_VOLUME=.*$',"FULL_F17_PG_VOLUME=$volume")
}else{$envText += "`nFULL_F17_PG_VOLUME=$volume`n"}
[IO.File]::WriteAllText((Join-Path $PWD '.env'),$envText)
Check -A @('up','-d','--wait','redis','oidc','collector','mcp','api','worker','worker2','web')
Check -A @('restart','web')
& node scripts/smoke-full-f17.mjs
if($LASTEXITCODE){throw 'F17 local real OIDC/scripted smoke'}
$managerImage=(& docker inspect opspilot-full-manager-1 --format '{{.Image}}').Trim()
$ui=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8091).StatusCode
$api=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/health).StatusCode
$workers=@(& docker @compose ps --services --status running | Where-Object {$_ -in @('worker','worker2')})
if($ui -ne 200 -or $api -ne 200 -or $workers.Count -ne 2){throw 'Full readiness/worker restoration'}
@{ui=$ui;api=$api;workers=$workers;schema='0018_lifecycle';manager_image=$managerImage;manager_profile='independent Full TLS/ACL; preserved grant identities'} | ConvertTo-Json -Depth 4 | Set-Content docs/full/evidence/f17/restored-full.json
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f17/mvp-isolation.json
if($LASTEXITCODE){throw 'Final MVP preservation'}
