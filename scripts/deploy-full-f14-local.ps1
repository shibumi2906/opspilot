param([Parameter(Mandatory=$true)][string]$MvpPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f14/mvp-before-rollout.json
if($LASTEXITCODE){throw 'MVP isolation prerequisite failed'}
$c=@('compose','--env-file','.env','-p','opspilot-full','-f','compose.full.yaml')
function Check { param([string[]]$A) & docker @c @A; if($LASTEXITCODE){throw "Full rollout failed ($LASTEXITCODE)"} }
Check -A @('up','-d','--wait','postgres')
Check -A @('stop','-t','150','worker','worker2')
Check -A @('stop','api','mcp')
$query="SELECT json_build_object('schema',(SELECT version_num FROM workflow.alembic_version),'tickets',(SELECT count(*) FROM domain.tickets),'comments',(SELECT count(*) FROM domain.ticket_comments),'notifications',(SELECT count(*) FROM domain.notifications),'receipts',(SELECT count(*) FROM workflow.actions WHERE execution_status='succeeded'),'tickets_sha256',(SELECT encode(sha256(convert_to(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY id),''),'UTF8')),'hex') FROM domain.tickets t),'comments_sha256',(SELECT encode(sha256(convert_to(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY id),''),'UTF8')),'hex') FROM domain.ticket_comments t),'notifications_sha256',(SELECT encode(sha256(convert_to(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY id),''),'UTF8')),'hex') FROM domain.notifications t),'actions_sha256',(SELECT encode(sha256(convert_to(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY id),''),'UTF8')),'hex') FROM workflow.actions t))"
$before=(& docker @c exec -T postgres psql -U ops_migration -d opspilot_full -Atc $query | ConvertFrom-Json)
if($LASTEXITCODE -or $before.schema -ne '0014_freshness'){throw 'Expected preserved F13 dev database'}
$before | ConvertTo-Json -Depth 5 | Set-Content .tools/f14-rollout-before.json
if(Test-Path -LiteralPath '.tools/f14-oidc-before.tgz'){throw 'Preserve the existing pre-upgrade IdP backup'}
Check -A @('stop','oidc')
& docker run --rm --network none --user 0 --entrypoint tar -v "opspilot-full_oidcdata:/source:ro" -v "${PWD}/.tools:/backup" opspilot-full/app:f01 -czf /backup/f14-oidc-before.tgz -C /source .
if($LASTEXITCODE){throw 'Quiesced IdP backup failed'}
Check -A @('run','--rm','admin')
Check -A @('up','-d','--wait','oidc','collector','jaeger','mcp','api','web')
& .venv/Scripts/python.exe scripts/apply-full-f14-identity.py
if($LASTEXITCODE){throw 'Reviewed IdP policy update failed'}
$after=(& docker @c exec -T postgres psql -U ops_migration -d opspilot_full -Atc $query | ConvertFrom-Json)
if($LASTEXITCODE -or $after.schema -ne '0015_workspace' -or $before.tickets -ne $after.tickets -or $before.receipts -ne $after.receipts){throw 'Full F14 rollout preservation failed'}
foreach($key in @('tickets','comments','notifications','receipts','tickets_sha256','comments_sha256','notifications_sha256','actions_sha256')){if($before.$key -ne $after.$key){throw "Preserved Full data mismatch: $key"}}
@{before=$before;after=$after;preserved=$true} | ConvertTo-Json -Depth 5 | Set-Content docs/full/evidence/f14/rollout-preservation.json
Check -A @('up','-d','--wait','postgres','oidc','collector','jaeger','mcp','api','worker','worker2','web')
& node scripts/smoke-full-f14.mjs
if($LASTEXITCODE){throw 'Live F14 workspace smoke failed'}
$ui=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8091).StatusCode
$api=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/health).StatusCode
$workers=@(& docker @c ps --services --status running | Where-Object {$_ -in @('worker','worker2')})
if($ui -ne 200 -or $api -ne 200 -or $workers.Count -ne 2){throw 'Full HTTP/worker readiness failed'}
@{ui=$ui;api=$api;workers=$workers;schema='0015_workspace'} | ConvertTo-Json -Depth 4 | Set-Content docs/full/evidence/f14/restored-full.json
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f14/mvp-isolation.json
if($LASTEXITCODE){throw 'MVP preservation failed'}
