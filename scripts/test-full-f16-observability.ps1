param([ValidatePattern('^opspilot-full-test-[a-z0-9-]+$')][string]$Project='opspilot-full-test-f16-r1')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f13-checks.yaml','-f','compose.full.f16-checks.yaml')
$report=Join-Path $PWD 'docs/full/evidence/f16/observability'
$backup=Join-Path $PWD ('.tools/f16-journal-drill-'+[DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))
New-Item -ItemType Directory -Force $report,$backup | Out-Null
function Check([string[]]$A){& docker @c @A; if($LASTEXITCODE){throw "F16 observability check failed: $($A[0])"}}
function Probe([string]$Mode){
 Check @('run','--rm','--no-deps','-v',('{0}:/work:ro' -f $PWD),'-v',('{0}:/reports' -f $report),'tests','python','/work/scripts/probe-full-f16-observability.py','--mode',$Mode)
}
function Journal([string]$Mode){
 Check @('run','--rm','--no-deps','--user','10001:10001','-v',('{0}:/backup' -f $backup),'-v',('{0}:/work:ro' -f $PWD),'--entrypoint','python','collector','/work/scripts/f16-journal-drill.py',$Mode)
}
$tampered=$false
$restored=$false
Probe 'native'
Check @('stop','collector')
Start-Sleep -Seconds 3
try {
 Probe 'outage'
 Journal 'original'
 Check @('up','-d','--wait','collector')
 Probe 'recovered'
 Journal 'tamper'
 $tampered=$true
 Start-Sleep -Seconds 3
 Probe 'tampered'
 Check @('stop','collector')
 Journal 'corrupt'
 Journal 'restore'
 $restored=$true
} finally {
 if($tampered -and -not $restored){Check @('stop','collector');if(-not (Test-Path (Join-Path $backup 'corrupt'))){Journal 'corrupt'};Journal 'restore'}
 Check @('up','-d','--wait','collector')
}
Probe 'recovered'
Check @('exec','-T','collector','python','-c',"from pathlib import Path;assert b'F16_SENTINEL_PRIVATE_PASSWORD_COOKIE_SQL_PROMPT_749e5a' not in Path('/var/lib/opspilot-observability/journal.db').read_bytes()")
# A real upstream failure exercises nginx error logging with a hostile query.
Check @('stop','api')
try{
 Check @('run','--rm','--no-deps','tests','python','-c',"import httpx;r=httpx.get('http://web/api/v2/diagnostics?secret=F16_SENTINEL_PRIVATE_PASSWORD_COOKIE_SQL_PROMPT_749e5a');assert r.status_code==502")
} finally {Check @('up','-d','--wait','api')}
$proxy=(& docker @c logs --no-log-prefix web | Out-String)
if($LASTEXITCODE -or $proxy.Contains('F16_SENTINEL_PRIVATE_PASSWORD_COOKIE_SQL_PROMPT_749e5a') -or -not $proxy.Contains('UPSTREAM_UNAVAILABLE') -or -not $proxy.Contains('proxy.access')){throw 'Nginx diagnostic/redaction check'}
foreach($service in @('api','mcp','collector')){
 $logs=(& docker @c logs --no-log-prefix $service | Out-String)
 if($LASTEXITCODE -or $logs.Contains('F16_SENTINEL_PRIVATE_PASSWORD_COOKIE_SQL_PROMPT_749e5a')){throw 'Sentinel in persisted Docker diagnostics'}
}
@{passed=$true;native_probe='collector-native.json';outage='collector-outage.json';tamper='collector-tampered.json';paired_restore=$true;forensics_preserved_privately=$true;nginx_error_category='UPSTREAM_UNAVAILABLE';nginx_access_retained=$true;sentinel_absent_in_journal_and_docker_logs=$true} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $report 'fault-drills.json')
