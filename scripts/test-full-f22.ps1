param(
 [ValidateSet('Prepare','Scripted','Regression','Units','Security','Stop')][string]$Mode='Scripted',
 [ValidatePattern('^opspilot-full-test-f22-[a-z0-9-]+$')][string]$Project='opspilot-full-test-f22-r1',
 [ValidateRange(34,99)][int]$Subnet=34,
 [string]$ReportDir='docs/full/evidence/f22'
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:COMPOSE_PARALLEL_LIMIT='1'
$env:PYTHONUTF8='1'
$env:F22_SUBNET_PREFIX='10.245.'+$Subnet
$env:F22_MANAGER_DIR='./.tools/f22/'+$Project+'/manager'
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f13-checks.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f22-checks.yaml')
function Invoke-F22([string[]]$A){ & docker @c @A; if($LASTEXITCODE){throw "F22 $Mode failed (exit $LASTEXITCODE)"} }
New-Item -ItemType Directory -Force $ReportDir | Out-Null
switch($Mode){
 'Prepare' {
  & ./scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath (Join-Path $ReportDir 'mvp-before.json')
  if($LASTEXITCODE){throw 'MVP prerequisite failed'}
  $env:F22_PROJECT=$Project
  & .venv/Scripts/python.exe -c "import json,subprocess,ipaddress,os; ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split();ns=json.loads(subprocess.check_output(['docker','network','inspect',*ids],text=True));target=ipaddress.ip_network(os.environ['F22_SUBNET_PREFIX']+'.0/24');assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!=os.environ['F22_PROJECT']+'_default' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
  if($LASTEXITCODE){throw 'F22 subnet overlap'}
  if([string](& docker volume ls -q --filter "name=^${Project}_pgdata`$")){throw 'Use a fresh F22 project for Prepare; retained volumes are evidence'}
  & .venv/Scripts/python.exe scripts/setup-full-f15-cache.py --test
  if($LASTEXITCODE){throw 'Test cache prerequisite failed'}
  & .venv/Scripts/python.exe scripts/setup-full-f16-observability.py --test
  if($LASTEXITCODE){throw 'Test telemetry prerequisite failed'}
  Invoke-F22 -A @('up','-d','--wait','--no-build','postgres','redis')
  & .venv/Scripts/python.exe scripts/setup-full-f22-manager.py --project $Project
  if($LASTEXITCODE){throw 'F22 manager prerequisite failed'}
  Invoke-F22 -A @('run','--rm','--no-deps','admin')
  Invoke-F22 -A @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.seed')
  Invoke-F22 -A @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.bootstrap_identity')
  Invoke-F22 -A @('run','--rm','--no-deps','telemetry-init')
  Invoke-F22 -A @('up','-d','--wait','--no-build','collector','mcp')
 }
 'Scripted' {
  $commit=(& git rev-parse HEAD).Trim()
  Invoke-F22 -A @('run','--rm','--no-deps','-e',('F22_COMMIT='+$commit),'tests','python','-m','tests.f22_lab')
 }
 'Regression' {
  $commit=(& git rev-parse HEAD).Trim()
  Invoke-F22 -A @('run','--rm','--no-deps','tests','python','-m','opspilot.evals.runner','--mode','scripted','--commit',$commit,'--dirty','--output','/reports/mvp-regression')
 }
 'Units' { Invoke-F22 -A @('run','--rm','--no-deps','tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/unit/test_full_eval.py','tests/unit/test_eval_safety.py','tests/unit/test_eval_token_guard.py','--junitxml=/reports/unit.xml') }
 'Security' { & ./scripts/scan-full-f22-security.ps1 -ReportDir (Join-Path $ReportDir 'security'); if($LASTEXITCODE){throw 'Security gate NOT_MET'} }
 'Stop' {
  Invoke-F22 -A @('stop')
  & docker compose -p ($Project+'-manager') -f ($env:F22_MANAGER_DIR+'/compose.json') stop
  if($LASTEXITCODE){throw 'F22 manager stop failed'}
 }
}
