param(
 [ValidateSet('Prepare','Smoke','Load','Faults','ResumeFaults','Fencing','Units','Stop')][string]$Mode='Prepare',
 [ValidatePattern('^opspilot-full-test-f21-[a-z0-9-]+$')][string]$Project='opspilot-full-test-f21-r4',
 [ValidateRange(27,99)][int]$Subnet=30
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:COMPOSE_PARALLEL_LIMIT='1'
$env:PYTHONUTF8='1'
$env:F21_SUBNET_PREFIX='10.245.'+$Subnet
$env:F21_MANAGER_DIR='./.tools/f21/'+$Project+'/manager'
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f13-checks.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f21-checks.yaml')
function Invoke-F21([string[]]$A){ & docker @c @A; if($LASTEXITCODE){throw "F21 $Mode command failed (exit $LASTEXITCODE)"} }
New-Item -ItemType Directory -Force docs/full/evidence/f21,docs/full/evidence/f21/smoke,docs/full/evidence/f21/process | Out-Null
switch($Mode){
 'Prepare' {
  & ./scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath docs/full/evidence/f21/mvp-before.json
  if($LASTEXITCODE){throw 'MVP prerequisite failed'}
  & .venv/Scripts/python.exe scripts/setup-full-f15-cache.py --test
  if($LASTEXITCODE){throw 'Test cache prerequisite failed'}
  & .venv/Scripts/python.exe scripts/setup-full-f16-observability.py --test
  if($LASTEXITCODE){throw 'Test telemetry prerequisite failed'}
  $env:F21_PROJECT=$Project
  & .venv/Scripts/python.exe -c "import json,subprocess,ipaddress,os; ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split();ns=json.loads(subprocess.check_output(['docker','network','inspect',*ids],text=True));target=ipaddress.ip_network(os.environ['F21_SUBNET_PREFIX']+'.0/24');assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!=os.environ['F21_PROJECT']+'_default' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
  if($LASTEXITCODE){throw 'F21 subnet overlaps another project'}
  $existing=[string](& docker ps -aq --filter "name=^/${Project}-postgres-1`$")
  if($existing){
   $previous=(& docker inspect $existing.Trim() --format '{{.Image}}').Trim()
   $current=(& docker image inspect opspilot-full/postgres:f01 --format '{{.Id}}').Trim()
   if($LASTEXITCODE -or $previous -ne $current){throw 'PG runtime changed; fresh test project required'}
  }elseif([string](& docker volume ls -q --filter "name=^${Project}_pgdata`$")){
   throw 'Unproven test volume; fresh project required'
  }
  Invoke-F21 -A @('up','-d','--wait','--no-build','postgres','redis')
  & .venv/Scripts/python.exe scripts/setup-full-f21-manager.py --project $Project
  if($LASTEXITCODE){throw 'Independent F21 manager prerequisite failed'}
  Invoke-F21 -A @('run','--rm','--no-deps','admin')
  Invoke-F21 -A @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.seed')
  Invoke-F21 -A @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.bootstrap_identity')
  Invoke-F21 -A @('run','--rm','--no-deps','telemetry-init')
  Invoke-F21 -A @('up','-d','--wait','--no-build','collector','mcp','api')
 }
 'Smoke' {
  & docker @c run --rm --no-deps -e F21_REPORT_DIR=/reports/smoke tests python -m tests.f21_lab --smoke
  if($LASTEXITCODE -ne 2){throw "Smoke must complete without claiming 30-min acceptance (exit $LASTEXITCODE)"}; $global:LASTEXITCODE=0
 }
 'Load' {
  Invoke-F21 -A @('run','--rm','--no-deps','--name',($Project+'-soak'),'tests','python','-m','tests.f21_lab','--soak-seconds','1800')
 }
 'Faults' {
  Invoke-F21 -A @('run','--rm','--no-deps','-e','MAX_ACTOR_ACTIVE_RUNS=1000','-e','MAX_TENANT_ACTIVE_RUNS=5000','-e','MAX_GLOBAL_ACTIVE_RUNS=10000','-e','TEST_QUEUE_PROCESSES=1','-e','TEST_F15_PROCESS=1','-e','WORKER_LEASE_SECONDS=3','-e','WORKER_HEARTBEAT_SECONDS=1','tests','python','-u','-m','pytest','-p','no:cacheprovider','-vv','-o','faulthandler_timeout=120','tests/integration/test_f21_resilience.py','tests/integration/test_durable_jobs.py','tests/integration/test_freshness.py','tests/integration/test_action_grants.py','tests/integration/test_authorization.py','tests/integration/test_human_commands.py','tests/integration/test_governance.py','tests/integration/test_recovery.py','tests/integration/test_checkpoint_compatibility.py','tests/integration/test_lifecycle_serialization.py','tests/integration/test_security_baseline.py','tests/integration/test_sse.py','tests/integration/test_observability.py','--junitxml=/reports/faults.xml')
  # Run Fencing in a separate freshly prepared project; preserve broad-suite fixtures.
 }
 'ResumeFaults' {
  Invoke-F21 -A @('run','--rm','--no-deps','-e','PYTHONUNBUFFERED=1','-e','MAX_ACTOR_ACTIVE_RUNS=1000','-e','MAX_TENANT_ACTIVE_RUNS=5000','-e','MAX_GLOBAL_ACTIVE_RUNS=10000','-e','TEST_QUEUE_PROCESSES=1','-e','TEST_F15_PROCESS=1','-e','WORKER_LEASE_SECONDS=3','-e','WORKER_HEARTBEAT_SECONDS=1','tests','python','scripts/resume-full-f21-faults.py')
 }
 'Fencing' {
  Invoke-F21 -A @('run','--rm','--no-deps','-e','MAX_ACTOR_ACTIVE_RUNS=1000','-e','MAX_TENANT_ACTIVE_RUNS=5000','-e','MAX_GLOBAL_ACTIVE_RUNS=10000','-e','TEST_F06_PROCESSES=1','-e','WORKER_LEASE_SECONDS=3','-e','WORKER_HEARTBEAT_SECONDS=1','-e','F06_REPORT_DIR=/reports/process','tests','python','-m','pytest','-p','no:cacheprovider','-vv','tests/integration/test_execution_fences.py','--junitxml=/reports/fencing.xml')
 }
 'Units' {
  Invoke-F21 -A @('run','--rm','--no-deps','tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/unit','tests/test_f20_jira_payload.py','--junitxml=/reports/units.xml')
 }
 'Stop' { Invoke-F21 -A @('stop') }
}
