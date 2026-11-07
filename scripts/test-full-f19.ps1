param([switch]$SkipBuild,[switch]$StartOnly,[string]$Project='opspilot-full-test-f19-local-final',[ValidateRange(24,99)][int]$Subnet=25)
$ErrorActionPreference='Stop'
if($Project -notmatch '^opspilot-full-test-f19-[a-z0-9-]+$'){throw 'Isolated F19 project required'}
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:COMPOSE_PARALLEL_LIMIT='1'
$env:PYTHONUTF8='1'
$env:F19_SUBNET_PREFIX='10.245.'+$Subnet
$env:F19_CLOCK=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
New-Item -ItemType Directory -Force docs/full/evidence/f19 | Out-Null
& ./scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath docs/full/evidence/f19/mvp-before.json
if($LASTEXITCODE){throw 'MVP prerequisite'}
& .tools/bin/uv.exe --cache-dir .tools/f19-uv-cache run --frozen --with bcrypt==5.0.0 python scripts/setup-full-f19.py
if($LASTEXITCODE){throw 'F19 local manager and PKI setup'}
& .venv/Scripts/python.exe scripts/setup-full-f15-cache.py --test
if($LASTEXITCODE){throw 'Cache setup'}
& .venv/Scripts/python.exe scripts/setup-full-f16-observability.py --test
if($LASTEXITCODE){throw 'Telemetry setup'}
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f13-checks.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f19-checks.yaml')
function Invoke-F19([string[]]$A){ & docker @c @A; if($LASTEXITCODE){throw "F19 $($A[0]) gate failed"} }
$env:F19_PROJECT=$Project
& .venv/Scripts/python.exe -c "import os,json,subprocess,ipaddress;ns=json.loads(subprocess.check_output(['docker','network','inspect',*subprocess.check_output(['docker','network','ls','-q'],text=True).split()],text=True));target=ipaddress.ip_network(os.environ['F19_SUBNET_PREFIX']+'.0/24');assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!=os.environ['F19_PROJECT']+'_default' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
if($LASTEXITCODE){throw 'F19 subnet overlaps another project'}
$existing=[string](& docker ps -aq --filter "name=^/${Project}-postgres-1`$")
if($existing){
    $previous=(& docker inspect $existing.Trim() --format '{{.Image}}').Trim()
    $current=(& docker image inspect opspilot-full/postgres:f01 --format '{{.Id}}').Trim()
    if($LASTEXITCODE -or $previous -ne $current){throw 'PG runtime differs; use a fresh test project'}
}elseif([string](& docker volume ls -q --filter "name=^${Project}_pgdata`$")){
    throw 'Unproven existing PG volume; select a fresh F19 test project'
}
if(-not $SkipBuild){Invoke-F19 -A @('build','api','tests','prometheus')}
Invoke-F19 -A @('up','-d','--wait','postgres','redis','oidc')
$connected=(& docker inspect opspilot-full-test-f17-manager-r2-manager-1 --format '{{json .NetworkSettings.Networks}}' | ConvertFrom-Json)
if(-not $connected.PSObject.Properties[$Project+'_default']){
    & docker network connect --alias manager ($Project+'_default') opspilot-full-test-f17-manager-r2-manager-1
    if($LASTEXITCODE){throw 'Manager private network binding'}
}
Invoke-F19 -A @('run','--rm','admin')
Invoke-F19 -A @('run','--rm','admin','python','-m','opspilot.cli.seed')
Invoke-F19 -A @('run','--rm','admin','python','-m','opspilot.cli.bootstrap_identity')
Invoke-F19 -A @('run','--rm','--no-deps','telemetry-init')
Invoke-F19 -A @('up','-d','--wait','collector','prometheus','metric-fixture','mcp','api','web')
if($StartOnly){return}
try {
    Invoke-F19 -A @('run','--rm','tests','ruff','check','--no-cache','src','tests')
    Invoke-F19 -A @('run','--rm','tests','mypy','--cache-dir','/tmp/f19-mypy','src')
    Invoke-F19 -A @('run','--rm','tests','python','-m','pytest','-q','-p','no:cacheprovider','tests/unit','tests/integration/test_prometheus.py')
    $env:F19_CLOCK=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    Invoke-F19 -A @('up','-d','--wait','api','mcp','worker','worker2')
    Invoke-F19 -A @('restart','web')
    Invoke-F19 -A @('run','--rm','--no-deps','-v',"${PWD}/docs/full/evidence/f19:/reports",'-e','PLAYWRIGHT_JSON_OUTPUT_FILE=/reports/browser.json','e2e','node','node_modules/@playwright/test/cli.js','test','prometheus.spec.ts','--reporter=list,json')
}finally{& docker @c stop | Out-Null}
