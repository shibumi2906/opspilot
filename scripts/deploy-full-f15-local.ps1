param([Parameter(Mandatory=$true)][string]$MvpPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8='1'
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f15/mvp-before-rollout.json
if($LASTEXITCODE){throw 'MVP rollout prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f15-cache.py
if($LASTEXITCODE){throw 'Private dev cache preparation'}
$c=@('compose','--env-file','.env','-p','opspilot-full','-f','compose.full.yaml')
function Check {param([string[]]$A) & docker @c @A; if($LASTEXITCODE){throw 'Full F15 rollout failed'}}
Check -A @('up','-d','--wait','postgres')
Check -A @('stop','-t','150','worker','worker2')
Check -A @('stop','api','mcp')
$before=(& docker @c run --rm --no-deps -v "${PWD}:/work:ro" admin python /work/scripts/fingerprint-full-f15.py | ConvertFrom-Json)
if($LASTEXITCODE -or $before.schema -ne '0015_workspace'){throw 'Expected preserved F14 database'}
$before | ConvertTo-Json -Depth 6 | Set-Content .tools/f15-rollout-before.json
Check -A @('run','--rm','admin')
$after=(& docker @c run --rm --no-deps -v "${PWD}:/work:ro" admin python /work/scripts/fingerprint-full-f15.py | ConvertFrom-Json)
if($LASTEXITCODE -or $after.schema -ne '0016_governance'){throw 'Expected F15 schema'}
foreach($field in $before.PSObject.Properties.Name){
 if($field -eq 'schema'){continue}
 if($before.$field.count -ne $after.$field.count -or $before.$field.sha256 -ne $after.$field.sha256){throw "Preserved Full data mismatch: $field"}
}
@{before=$before;after=$after;preserved=$true;timing='Immediately after migration, before worker schedulers/live smoke'} | ConvertTo-Json -Depth 8 | Set-Content docs/full/evidence/f15/rollout-preservation.json
Check -A @('up','-d','--wait','redis','oidc','collector','jaeger','mcp','api','worker','worker2','web')
& node scripts/smoke-full-f15.mjs
if($LASTEXITCODE){throw 'F15 live resource smoke'}
$ui=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8091).StatusCode
$api=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/health).StatusCode
$workers=@(& docker @c ps --services --status running | Where-Object {$_ -in @('worker','worker2')})
if($ui -ne 200 -or $api -ne 200 -or $workers.Count -ne 2){throw 'Full readiness/worker restoration'}
@{ui=$ui;api=$api;workers=$workers;schema='0016_governance';redis='private authenticated ephemeral cache'} | ConvertTo-Json -Depth 4 | Set-Content docs/full/evidence/f15/restored-full.json
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f15/mvp-isolation.json
if($LASTEXITCODE){throw 'Final MVP preservation'}
