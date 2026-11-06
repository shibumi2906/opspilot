param([switch]$SkipBuild, [string]$ReportDir='docs/full/evidence/f18/tls')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force $ReportDir | Out-Null
& ./scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath (Join-Path $ReportDir 'mvp-before.json')
if($LASTEXITCODE){throw 'MVP native TLS prerequisite'}
& .venv/Scripts/python.exe scripts/setup-full-f18.py
if($LASTEXITCODE){throw 'Native TLS manager readiness and fresh scoped tokens'}
& .venv/Scripts/python.exe -c "import json,subprocess,ipaddress; ns=json.loads(subprocess.check_output(['docker','network','inspect',*subprocess.check_output(['docker','network','ls','-q'],text=True).split()],text=True)); target=ipaddress.ip_network('10.245.23.0/24'); assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for n in ns if n['Name']!='opspilot-full-test-f18-tls_default' for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])"
if($LASTEXITCODE){throw 'Native TLS subnet overlap'}
$project='opspilot-full-test-f18-tls'
$compose=@('compose','-p',$project,'-f','.tools/security-f18-final/compose.json')
function Invoke-Lab([string[]]$Arguments) {
    & docker @compose @Arguments
    if($LASTEXITCODE){throw "Security lab check failed: $($Arguments[0])"}
}
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$overlay=Join-Path (Get-Location) '.tools/security-f18-final-report-overlay.json'
@{services=@{probe=@{volumes=@("${reports}:/reports","${PWD}/.tools/security-f18-final/observability/probe:/run/observability-probe:ro","${PWD}/.tools/security-f18-final/observability/worker:/run/observability-worker:ro")};browser=@{volumes=@("${reports}:/reports");ipc='private';shm_size='256m';mem_limit='1g';memswap_limit='1g';environment=@{NODE_OPTIONS='--max-old-space-size=256'}}}} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $overlay
$compose += @('-f',$overlay)
$managerOverlay=Join-Path $PWD '.tools/f18-tls-manager-overlay.json'
$managedServices=@{}
foreach($serviceName in @('worker','mcp')){
    $tokenName=if($serviceName -eq 'worker'){'worker'}else{'mcp'}
    $managedServices[$serviceName]=@{
        networks=@('default')
        environment=@{SECRET_MANAGER_URL='https://manager:8200';SECRET_MANAGER_CA_FILE='/run/manager-client/ca.crt';SECRET_MANAGER_TOKEN_FILE='/run/manager-client/token'}
        volumes=@("${PWD}/.tools/f17-manager/ca.crt:/run/manager-client/ca.crt:ro","${PWD}/.tools/f17-manager/${tokenName}.token:/run/manager-client/token:ro")
    }
    if($serviceName -eq 'worker'){
        $managedServices[$serviceName].volumes += "${PWD}/.tools/security-f18-final/runtime-service-private:/run/service-private:ro"
    }
}
@{services=$managedServices;networks=@{default=@{external=$false;name='opspilot-full-test-f18-tls_default';ipam=@{config=@(@{subnet='10.245.23.0/24'})}}}} | ConvertTo-Json -Depth 8 | Set-Content $managerOverlay
$compose += @('-f',$managerOverlay)
if(-not $SkipBuild){
    & docker compose --env-file .env -p opspilot-full-security-build -f compose.full.yaml -f compose.full.test.yaml build api tests web e2e oidc postgres redis
    if($LASTEXITCODE){throw 'Security images build failed'}
}
if(-not (Test-Path -LiteralPath '.tools/security-f18-final/compose.json')){
    $generator = Get-Content -Raw -LiteralPath 'infra/security/generate_local.py'
    $generator = $generator.Replace('ROOT = Path(__file__).resolve().parents[2]', 'ROOT = Path.cwd()')
    $generator = $generator.Replace('.tools/security-local', '.tools/security-f18-final')
    $generator = $generator.Replace('"name": "opspilot-full-security"', '"name": "opspilot-full-test-f18-tls"')
    Set-Content -LiteralPath '.tools/f18-generate-lab-final.py' -Value $generator -Encoding utf8NoBOM
    & docker run --rm -u root -v "${PWD}:/work" -w /work --entrypoint python opspilot-full/tests:f01 .tools/f18-generate-lab-final.py
    if($LASTEXITCODE){throw 'Lab generation failed'}
}
$runtimeKeys=Join-Path $PWD '.tools/security-f18-final/runtime-service-private'
New-Item -ItemType Directory -Force $runtimeKeys | Out-Null
Copy-Item -LiteralPath '.tools/security-f18-final/service-private/current.pem' -Destination $runtimeKeys
& docker run --rm --network none -u root -v "${PWD}/.tools/security-f18-final:/lab" --entrypoint python opspilot-full/tests:f01 -c "from pathlib import Path;from opspilot.observability.provision import prepare;Path('/lab').chmod(0o755);prepare(Path('/lab/observability'))"
if($LASTEXITCODE){throw 'Lab mount permissions failed'}
& .venv/Scripts/python.exe scripts/setup-full-f18-native.py
if($LASTEXITCODE){throw 'Native ingress private overlay preparation'}
$compose += @('-f','.tools/security-f18-final/compose-ingress.json')
try {
Invoke-Lab -Arguments @('up','-d','--wait','postgres','redis','oidc')
$connected=(& docker inspect opspilot-full-test-f17-manager-r2-manager-1 --format '{{json .NetworkSettings.Networks}}' | ConvertFrom-Json)
if(-not $connected.PSObject.Properties['opspilot-full-test-f18-tls_default']){
 & docker network connect --alias manager opspilot-full-test-f18-tls_default opspilot-full-test-f17-manager-r2-manager-1
 if($LASTEXITCODE){throw 'TLS manager network binding'}
}
Invoke-Lab -Arguments @('run','--rm','admin')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.ingress_role')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.seed')
Invoke-Lab -Arguments @('run','--rm','admin','python','-m','opspilot.cli.bootstrap_identity')
Invoke-Lab -Arguments @('run','--rm','--no-deps','telemetry-init')
Invoke-Lab -Arguments @('up','-d','--wait','collector','api','mcp','worker','web')
Invoke-Lab -Arguments @('restart','web')
Invoke-Lab -Arguments @('run','--rm','probe')
Invoke-Lab -Arguments @('run','--rm','probe','python','/work/scripts/probe-full-f18-ingress-edge.py')
Invoke-Lab -Arguments @('run','--rm','probe','python','/work/scripts/probe-full-f16-observability.py')
Invoke-Lab -Arguments @('run','--rm','probe','python','/work/scripts/probe-full-f15-redis.py')
Invoke-Lab -Arguments @('run','--rm','browser')
Invoke-Lab -Arguments @('run','--rm','-v',"${PWD}:/work:ro",'admin','python','/work/scripts/prepare-full-f18-native.py')
Invoke-Lab -Arguments @('run','--rm','probe','python','/work/scripts/probe-full-f18-native.py')
Write-Host 'Local TLS/MFA lab verified; production ASVS L2 acceptance remains separate.'



} finally { & docker @compose stop | Out-Null }
