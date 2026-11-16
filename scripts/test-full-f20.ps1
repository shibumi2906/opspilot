param(
 [ValidateSet('Prepare','Units','Boundaries','Backend','Scripted','Live','Stop')][string]$Mode='Units',
 [ValidatePattern('^opspilot-full-test-f20-[a-z0-9]+$')][string]$Project='opspilot-full-test-f20-r1',
 [ValidateRange(64,98)][int]$Subnet=64,
 [string[]]$TestTargets=@('tests/unit','tests/integration')
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$py='.venv/Scripts/python.exe'
$env:COMPOSE_PARALLEL_LIMIT='1'
$env:F22_SUBNET_PREFIX="10.245.$Subnet"
$private=".tools/f20/$Project"
$env:F22_MANAGER_DIR="./$private/manager"
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f22-checks.yaml','-f','compose.full.f20-checks.yaml')
function Run([string[]]$A){
 & docker @c @A *>> "$private/rehearsal.log"
 if($LASTEXITCODE){throw "F20 $Mode failed. See ignored rehearsal.log."}
}
if($Mode -eq 'Prepare'){
 New-Item -ItemType Directory $private | Out-Null
 $mvp=(Get-Content .tools/opspilot-full-workspace.json -Raw | ConvertFrom-Json).mvp_path
 & ./scripts/check-full-isolation.ps1 -MvpPath $mvp -MvpDocumentationHead (git -C $mvp rev-parse bec833b) -ReportPath "$private/mvp-before.json"
 if($LASTEXITCODE){throw 'MVP isolation failed'}
 & $py scripts/setup-full-f15-cache.py --test
 if($LASTEXITCODE){throw 'Cache setup failed'}
 & $py scripts/setup-full-f16-observability.py --test
 if($LASTEXITCODE){throw 'Telemetry setup failed'}
 & $py -c "import json,subprocess,ipaddress,os;ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split();ns=json.loads(subprocess.check_output(['docker','network','inspect',*ids],text=True));target=ipaddress.ip_network(os.environ['F22_SUBNET_PREFIX']+'.0/24');assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
 if($LASTEXITCODE){throw 'Network overlaps an existing project'}
 Run @('up','-d','--wait','--no-build','postgres','redis')
 $env:F20_PRIVATE=$private
 $env:F20_PROJECT=$Project
 & $py -c "import os,runpy;from pathlib import Path;p=Path(os.environ['F20_PRIVATE']).resolve();d=runpy.run_path('scripts/setup-full-f17-manager.py');f=d['bootstrap'];f.__globals__.update(PRIVATE=p/'manager',RECOVERY=p/'recovery',PROJECT=os.environ['F20_PROJECT']+'-manager',PORT=18240,IMAGE='opspilot-full/manager:f23',APPLICATION_NETWORKS=(),EXTERNAL_NETWORK=os.environ['F20_PROJECT']+'_default');f()"
 if($LASTEXITCODE){throw 'Manager setup failed'}
 Run @('run','--rm','--no-deps','admin')
 Run @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.seed')
 Run @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.bootstrap_identity')
 Run @('run','--rm','--no-deps','telemetry-init')
 Run @('up','-d','--wait','--no-build','collector','mcp')
}
if($Mode -eq 'Units'){
 Run @('run','--rm','--no-deps','tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/unit','tests/test_f20_jira_payload.py',('--junitxml=/reports/runtime-units-'+$stamp+'.xml'))
}
if($Mode -eq 'Boundaries'){
 Run @('run','--rm','--no-deps','tests','python','-m','pytest','-p','no:cacheprovider','-q','tests/integration/test_f20_jira_runtime.py',('--junitxml=/reports/runtime-boundaries-'+$stamp+'.xml'))
}
if($Mode -eq 'Backend'){
 # Fail before pytest when API dependencies are absent or schema readiness fails.
 Run @('up','-d','--wait','--wait-timeout','90','--no-build','postgres','redis','collector','mcp','api')
 Run @('run','--rm','--no-deps','tests','python','-c','import httpx; r=httpx.get("http://api:8000/health/ready",timeout=15); r.raise_for_status()')
 $report='backend-regression-'+$stamp+'.xml'
 New-Item -ItemType Directory "docs/full/evidence/f20/backend-$stamp" | Out-Null
 Run (@('run','--rm','--no-deps','-e',('F21_REPORT_DIR=/reports/backend-'+$stamp),'-e','MAX_ACTOR_ACTIVE_RUNS=1000','-e','MAX_TENANT_ACTIVE_RUNS=5000','-e','MAX_GLOBAL_ACTIVE_RUNS=10000','tests','python','-m','pytest','-p','no:cacheprovider','-q','--maxfail=3','--tb=short','-o','faulthandler_timeout=60')+$TestTargets+@('--junitxml=/reports/'+$report))
}
if($Mode -eq 'Scripted'){
 Run @('run','--rm','--no-deps','-e',('F22_REPORT_DIR=/reports/scripted-'+$stamp),'-e',('F22_COMMIT='+(git rev-parse HEAD)),'tests','python','-m','tests.f22_lab')
}
if($Mode -eq 'Live'){
 if(-not $env:F20_LIVE_ATTEMPT){throw 'Set a unique F20_LIVE_ATTEMPT. An existing report cannot be reused.'}
 Run @('run','--rm','--no-deps','-e',('F20_LIVE_ATTEMPT='+$env:F20_LIVE_ATTEMPT),'tests','python','-m','tests.f20_jira_live')
}
if($Mode -eq 'Stop'){
 Run @('stop')
 & docker compose -p "$Project-manager" -f "$private/manager/compose.json" stop
 if($LASTEXITCODE){throw 'Manager stop failed'}
}
