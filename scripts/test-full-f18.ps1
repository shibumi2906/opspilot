param([switch]$SkipBuild,[switch]$StartOnly,[string]$Project='opspilot-full-test-f18-r4',[ValidateRange(18,99)][int]$Subnet=21)
$ErrorActionPreference='Stop'
if($Project -notmatch '^opspilot-full-test-f18-[a-z0-9-]+$'){throw 'Explicit isolated F18 project required'}
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8='1'
$env:F18_SUBNET_PREFIX='10.245.'+$Subnet
New-Item -ItemType Directory -Force docs/full/evidence/f18 | Out-Null
& ./scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath docs/full/evidence/f18/mvp-before.json
if($LASTEXITCODE){throw 'MVP prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f18.py
if($LASTEXITCODE){throw 'F18 real manager and PKI setup'}
$env:F18_TEST_INGRESS_PASSWORD=(Get-Content -Raw .tools/f18-private/fixture.json | ConvertFrom-Json).db_password
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f13-checks.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f18-checks.yaml')
function Invoke-F18([string[]]$A){ & docker @c @A; if($LASTEXITCODE){throw "F18 $($A[0]) gate failed"} }
if(-not $SkipBuild){Invoke-F18 -A @('build','api','tests','web')}
& .venv/Scripts/python.exe scripts/setup-full-f15-cache.py --test
if($LASTEXITCODE){throw 'Cache setup'}
& .venv/Scripts/python.exe scripts/setup-full-f16-observability.py --test
if($LASTEXITCODE){throw 'Telemetry setup'}
# The explicit subnet is reserved for this serial simulator lab; reject overlap before creation.
$env:F18_PROJECT=$Project
& .venv/Scripts/python.exe -c "import os,json,subprocess,ipaddress;ns=json.loads(subprocess.check_output(['docker','network','inspect',*subprocess.check_output(['docker','network','ls','-q'],text=True).split()],text=True));target=ipaddress.ip_network(os.environ['F18_SUBNET_PREFIX']+'.0/24');assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!=os.environ['F18_PROJECT']+'_default' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
if($LASTEXITCODE){throw 'F18 subnet overlaps another project'}
Invoke-F18 -A @('up','-d','--wait','postgres','redis','oidc')
$connected=(& docker inspect opspilot-full-test-f17-manager-r2-manager-1 --format '{{json .NetworkSettings.Networks}}' | ConvertFrom-Json)
if(-not $connected.PSObject.Properties[$Project+'_default']){
    & docker network connect --alias manager ($Project+'_default') opspilot-full-test-f17-manager-r2-manager-1
    if($LASTEXITCODE){throw 'Manager private network binding'}
}
Invoke-F18 -A @('run','--rm','admin')
Invoke-F18 -A @('run','--rm','admin','python','-m','opspilot.cli.ingress_role')
Invoke-F18 -A @('run','--rm','admin','python','-m','opspilot.cli.seed')
Invoke-F18 -A @('run','--rm','admin','python','-m','opspilot.cli.bootstrap_identity')
Invoke-F18 -A @('run','--rm','--no-deps','telemetry-init')
Invoke-F18 -A @('up','-d','--wait','collector','adapter-simulator','mcp','api','web')
if($StartOnly){return}
try {
    Invoke-F18 -A @('run','--rm','tests','ruff','check','--no-cache','src','tests')
    Invoke-F18 -A @('run','--rm','tests','mypy','--cache-dir','/tmp/f18-mypy','src')
    Invoke-F18 -A @('run','--rm','tests','python','-m','pytest','-q','-p','no:cacheprovider','tests/integration/test_adapter_platform.py')
}finally{& docker @c stop | Out-Null}
