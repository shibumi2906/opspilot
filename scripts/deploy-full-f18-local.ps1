param([string]$MvpPath='C:/Users/user/Desktop/code/AI Incident & Operations Agent')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8='1'
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f18/mvp-before-rollout.json
if($LASTEXITCODE){throw 'MVP rollout prerequisite'}
$volume=(& docker inspect opspilot-full-postgres-1 --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}').Trim()
if($LASTEXITCODE -or $volume -notmatch '^opspilot-full-f17-logical-[a-f0-9]{12}$'){throw 'Verified F17 logical Full volume required; original volume is preserved'}
$sourceImage=(& docker inspect opspilot-full-postgres-1 --format '{{.Image}}').Trim()
$currentImage=(& docker image inspect opspilot-full/postgres:f01 --format '{{.Id}}').Trim()
if($LASTEXITCODE -or $sourceImage -ne $currentImage){throw 'F18 does not change PostgreSQL runtime; exact existing image required before stopping services'}
$schema=(& docker exec opspilot-full-postgres-1 psql -XAt -U ops_migration -d opspilot_full -c 'SELECT version_num FROM workflow.alembic_version').Trim()
if($LASTEXITCODE -or $schema -ne '0018_lifecycle'){throw 'One-time F18 upgrade requires schema0018; refuse before stopping services'}
& .venv/Scripts/python.exe -c "import json,subprocess,ipaddress; ns=json.loads(subprocess.check_output(['docker','network','inspect',*subprocess.check_output(['docker','network','ls','-q'],text=True).split()],text=True)); target=ipaddress.ip_network('10.245.22.0/24'); assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!='opspilot-full_adapters' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
if($LASTEXITCODE){throw 'Private simulator subnet overlap'}
& .venv/Scripts/python.exe scripts/setup-full-f18.py --local
if($LASTEXITCODE){throw 'Independent Full connector manager prerequisite'}
$c=@('compose','--env-file','.env','-p','opspilot-full','-f','compose.full.yaml','-f','compose.full.f17-local.yaml','-f','compose.full.f18-local.yaml')
function Check([string[]]$A){& docker @c @A; if($LASTEXITCODE){throw 'Full F18 rollout gate failed'}}
Check -A @('stop','-t','150','worker','worker2')
Check -A @('stop','api','mcp')
$before=(& docker @c run --rm --no-deps -v "${PWD}/scripts/fingerprint-full-f18.py:/fingerprint.py:ro" admin python /fingerprint.py | ConvertFrom-Json)
if($LASTEXITCODE -or $before.schema -ne '0018_lifecycle'){throw 'Quiesced Full fingerprint unavailable'}
$before | ConvertTo-Json -Depth 8 | Set-Content .tools/f18-rollout-before.json
Check -A @('stop','postgres')
& .venv/Scripts/python.exe scripts/backup-full-f18-local.py --before-file .tools/f18-rollout-before.json
if($LASTEXITCODE){throw 'Encrypted backup and offline fresh restore prerequisite; services remain quiesced'}
Check -A @('up','-d','--wait','postgres')
Check -A @('run','--rm','--no-deps','admin')
Check -A @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.ingress_role')
$after=(& docker @c run --rm --no-deps -v "${PWD}/scripts/fingerprint-full-f18.py:/fingerprint.py:ro" admin python /fingerprint.py | ConvertFrom-Json)
if($LASTEXITCODE -or $after.schema -ne '0019_adapters'){throw 'F18 migrated schema required'}
foreach($field in $before.PSObject.Properties.Name){
 if($field -eq 'schema'){continue}
 if($before.$field.count -ne $after.$field.count -or $before.$field.sha256 -ne $after.$field.sha256){throw "Legacy Full data mismatch: $field"}
}
$adapters=(& docker @c exec -T postgres psql -XAt -U ops_migration -d opspilot_full -c 'SELECT count(*) FROM integrations.connector_configs').Trim()
if($LASTEXITCODE -or $adapters -ne '0'){throw 'Default registry must remain empty; do not seed or enable customer adapters'}
@{before=$before;after=$after;preserved=$true;all_legacy_schemas=@('domain','workflow','identity','checkpoints');timing='Quiesced before/after migration, all legacy columns hashed; before workers/smoke';default_registry_empty=$true} | ConvertTo-Json -Depth 8 | Set-Content docs/full/evidence/f18/rollout-preservation.json
Check -A @('up','-d','--wait','redis','oidc','collector','mcp','api','worker','worker2','ingress-worker','web')
Check -A @('restart','web')
& .venv/Scripts/python.exe scripts/check-full-f18-worker.py
if($LASTEXITCODE){throw 'Deployed observation worker isolation'}
& node scripts/smoke-full-f18.mjs
if($LASTEXITCODE){throw 'Local scripted/OIDC/refresh smoke'}
$ui=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8091).StatusCode
$api=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/health).StatusCode
$worker=(& docker inspect opspilot-full-ingress-worker-1 --format '{{.State.Running}}').Trim()
if($ui -ne 200 -or $api -ne 200 -or $worker -ne 'true'){throw 'Full readiness/observation worker restoration'}
@{ui=$ui;api=$api;schema='0019_adapters';observation_worker=$worker;default_registry_empty=$true;simulator_profile='optional; disabled by default';original_full_volume_preserved=$true} | ConvertTo-Json -Depth 4 | Set-Content docs/full/evidence/f18/restored-full.json
& ./scripts/check-full-isolation.ps1 -MvpPath $MvpPath -ReportPath docs/full/evidence/f18/mvp-isolation.json
if($LASTEXITCODE){throw 'Final MVP isolation'}
