param([Parameter(Mandatory=$true)][string]$MvpPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8='1'
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f16/mvp-before-rollout.json
if($LASTEXITCODE){throw 'MVP rollout prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f15-cache.py
if($LASTEXITCODE){throw 'Private dev cache preparation'}
& .venv/Scripts/python.exe scripts/setup-full-f16-observability.py
if($LASTEXITCODE){throw 'Private dev observability preparation'}
$c=@('compose','--env-file','.env','-p','opspilot-full','-f','compose.full.yaml')
function Check {param([string[]]$A) & docker @c @A; if($LASTEXITCODE){throw 'Full F16 rollout failed'}}
Check -A @('up','-d','--wait','postgres')
Check -A @('stop','-t','150','worker','worker2')
Check -A @('stop','api','mcp')
$before=(& docker @c run --rm --no-deps -v "${PWD}:/work:ro" admin python /work/scripts/fingerprint-full-f16.py | ConvertFrom-Json)
if($LASTEXITCODE -or $before.schema -ne '0016_governance'){throw 'Expected preserved F15 database'}
$before | ConvertTo-Json -Depth 6 | Set-Content .tools/f16-rollout-before.json
Check -A @('run','--rm','admin')
$after=(& docker @c run --rm --no-deps -v "${PWD}:/work:ro" admin python /work/scripts/fingerprint-full-f16.py | ConvertFrom-Json)
if($LASTEXITCODE -or $after.schema -ne '0017_observability'){throw 'Expected F16 schema'}
foreach($field in $before.PSObject.Properties.Name){
 if($field -eq 'schema'){continue}
 if($before.$field.count -ne $after.$field.count -or $before.$field.sha256 -ne $after.$field.sha256){throw "Preserved Full data mismatch: $field"}
}
@{before=$before;after=$after;preserved=$true;timing='Immediately after migration, before worker schedulers/live smoke'} | ConvertTo-Json -Depth 8 | Set-Content docs/full/evidence/f16/rollout-preservation.json
Check -A @('run','--rm','--no-deps','telemetry-init')
Check -A @('up','-d','--wait','redis','oidc','collector','mcp','api','worker','worker2','web')
& node scripts/smoke-full-f16.mjs
if($LASTEXITCODE){throw 'F16 live resource smoke'}
$ui=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8091).StatusCode
$api=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/health).StatusCode
$workers=@(& docker @c ps --services --status running | Where-Object {$_ -in @('worker','worker2')})
if($ui -ne 200 -or $api -ne 200 -or $workers.Count -ne 2){throw 'Full readiness/worker restoration'}
@{ui=$ui;api=$api;workers=$workers;schema='0017_observability';redis='private authenticated ephemeral cache'} | ConvertTo-Json -Depth 4 | Set-Content docs/full/evidence/f16/restored-full.json
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f16/mvp-isolation.json
if($LASTEXITCODE){throw 'Final MVP preservation'}
