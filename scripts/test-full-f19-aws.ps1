param([ValidateSet('Start','Smoke','Browser','Stop')][string]$Action='Start')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:COMPOSE_PARALLEL_LIMIT='1'
$env:PYTHONUTF8='1'
$env:F19_SUBNET_PREFIX='10.245.26'
$env:F19_CLOCK=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$project='opspilot-full-test-f19-aws-r1'
New-Item -ItemType Directory -Force docs/full/evidence/f19-aws | Out-Null
$c=@('compose','--env-file','.env','-p',$project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f13-checks.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f19-checks.yaml','-f','compose.full.f19-aws.yaml')
function Invoke-AwsLab([string[]]$Arguments){
    & docker @c @Arguments
    if($LASTEXITCODE){throw "F19 AWS lab gate failed: $($Arguments[0])"}
}
Invoke-AwsLab -Arguments @('config','--quiet')
if($Action -eq 'Stop'){Invoke-AwsLab -Arguments @('stop'); return}
if($Action -eq 'Smoke'){
    Invoke-AwsLab -Arguments @('run','--rm','--no-deps','tests','python','-m','pytest','-q','-p','no:cacheprovider','--tb=short','tests/integration/test_prometheus_staging.py')
    return
}
if($Action -eq 'Browser'){
    Invoke-AwsLab -Arguments @('up','-d','--wait','--no-build','api','mcp','worker','worker2')
    Invoke-AwsLab -Arguments @('restart','web')
    # Health endpoints alone do not exercise the external connector after a cold restart.
    Invoke-AwsLab -Arguments @('run','--rm','--no-deps','tests','python','-m','pytest','-q','-p','no:cacheprovider','--tb=short','tests/integration/test_prometheus_staging.py')
    Invoke-AwsLab -Arguments @('run','--rm','--no-deps','-e','PLAYWRIGHT_JSON_OUTPUT_FILE=/reports/browser.json','e2e','node','node_modules/@playwright/test/cli.js','test','prometheus-staging.spec.ts','--reporter=list,json')
    return
}
& ./scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath .tools/f19-aws-mvp-lab-before.json
if($LASTEXITCODE){throw 'MVP isolation prerequisite failed'}
& .venv/Scripts/python.exe -c "import json,subprocess,ipaddress;ns=json.loads(subprocess.check_output(['docker','network','inspect',*subprocess.check_output(['docker','network','ls','-q'],text=True).split()],text=True));target=ipaddress.ip_network('10.245.26.0/24');assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!='opspilot-full-test-f19-aws-r1_default' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
if($LASTEXITCODE){throw 'AWS lab network overlap'}
if([string](& docker volume ls -q --filter "name=^${project}_pgdata`$")){
    throw 'Fresh AWS lab DB required; inspect retained lab before retrying Start'
}
Invoke-AwsLab -Arguments @('up','-d','--wait','--no-build','postgres','redis','oidc')
& docker network connect --alias manager ($project+'_default') opspilot-full-test-f17-manager-r2-manager-1
if($LASTEXITCODE){throw 'Manager network binding failed'}
Invoke-AwsLab -Arguments @('run','--rm','admin')
Invoke-AwsLab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.seed')
Invoke-AwsLab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.bootstrap_identity')
Invoke-AwsLab -Arguments @('run','--rm','--no-deps','telemetry-init')
Invoke-AwsLab -Arguments @('up','-d','--wait','--no-build','collector','mcp','api','web')
