param([ValidatePattern('^opspilot-full-test-f23-[a-z0-9]+$')][string]$Project='opspilot-full-test-f23-r1',[ValidateRange(35,98)][int]$Subnet=37,[string]$ManagerImage="opspilot-full/manager:f17",[switch]$RecoverySmoke)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$py='.venv/Scripts/python.exe'
$private=".tools/f23/$Project"
$report="docs/full/evidence/f23/$Project"
$log="$private/rehearsal.log"
function Run($Exe,[string[]]$Arguments) {
    & $Exe @Arguments *>> $log
    if($LASTEXITCODE -ne 0){throw "F23 command failed at $step (exit $LASTEXITCODE). See ignored rehearsal log."}
}
function Image($Tag) {
    $id=(& docker image inspect $Tag --format '{{.Id}}')
    if($LASTEXITCODE -ne 0 -or $id -notmatch '^sha256:[a-f0-9]{64}$'){throw "Missing local image: $Tag"}
    return $id
}
$mvp=(Get-Content .tools/opspilot-full-workspace.json -Raw | ConvertFrom-Json).mvp_path
$mvpHead=(git -C $mvp rev-parse HEAD).Trim()
New-Item -ItemType Directory -Force $report | Out-Null
New-Item -ItemType Directory $private | Out-Null
& ./scripts/check-full-isolation.ps1 -MvpPath $mvp -MvpDocumentationHead $mvpHead -ReportPath "$report/mvp-before.json"
$env:COMPOSE_PARALLEL_LIMIT='1'
$env:F22_SUBNET_PREFIX="10.245.$Subnet"
$env:F22_MANAGER_DIR="./$private/manager"
$env:F23_POSTGRES_IMAGE=Image 'opspilot-full/postgres:f01'
$env:F23_APP_IMAGE=Image 'opspilot-full/app:f19'
$env:F23_REDIS_IMAGE=Image 'opspilot-full/redis:f15'
$env:F23_TEST_IMAGE=Image 'opspilot-full/tests:f19'
$env:F23_MANAGER_IMAGE=Image $ManagerImage
$env:F23_PROJECT=$Project
$env:F23_PRIVATE=$private
$env:F23_EVIDENCE_DIR=$report
$step='network preflight'
$env:F23_SMOKE_SUBNET=if($RecoverySmoke){"10.245.$($Subnet+1).0/24"}else{""}
Run $py @('-c',"import json,subprocess,ipaddress,os; ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split(); ns=json.loads(subprocess.check_output(['docker','network','inspect',*ids],text=True)); targets=[ipaddress.ip_network(c) for c in (os.environ['F22_SUBNET_PREFIX']+'.0/24',os.environ['F23_SMOKE_SUBNET']) if c]; assert not any(target.overlaps(ipaddress.ip_network(c['Subnet'])) for target in targets for n in ns for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c and ':' not in c['Subnet'])")
$envFile="$private/lab.env"
$keys=@('POSTGRES_PASSWORD','WORKFLOW_DB_PASSWORD','DOMAIN_DB_PASSWORD','CHECKPOINT_DB_PASSWORD','IDENTITY_DB_PASSWORD','MCP_SERVICE_TOKEN','SESSION_SIGNING_KEY','OIDC_BOOTSTRAP_PASSWORD','OIDC_DEMO_PASSWORD')
$keys | ForEach-Object { "$_=$([Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant())" } | Set-Content -Encoding ascii $envFile
$c=@('compose','--env-file',$envFile,'-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml','-f','compose.full.f16-checks.yaml','-f','compose.full.f17-checks.yaml','-f','compose.full.f22-checks.yaml','-f','compose.full.f23-checks.yaml')
$r=@('compose','--env-file',$envFile,'-p',"$Project-restore",'-f','compose.full.f23-restore.yaml')
try {
    $step='prepare test cache and telemetry'
    Run $py @('scripts/setup-full-f15-cache.py','--test')
    Run $py @('scripts/setup-full-f16-observability.py','--test')
    $step='start private baseline database and cache'
    Run docker ($c+@('up','-d','--wait','--no-build','postgres','redis'))
    $step='provision isolated manager'
    Run $py @('-c',"import os,runpy; from pathlib import Path; p=Path(os.environ['F23_PRIVATE']); project=os.environ['F23_PROJECT']; d=runpy.run_path('scripts/setup-full-f17-manager.py'); f=d['bootstrap']; f.__globals__.update(PRIVATE=p.resolve()/'manager',RECOVERY=p.resolve()/'manager-recovery',PROJECT=project+'-manager',IMAGE=os.environ['F23_MANAGER_IMAGE'],PORT=18237,APPLICATION_NETWORKS=(),EXTERNAL_NETWORK=project+'_default'); f()")
    $step='migrate and seed baseline'
    Run docker ($c+@('run','--rm','--no-deps','admin','alembic','upgrade','0020_prometheus'))
    Run docker ($c+@('run','--rm','--no-deps','admin','python','-m','opspilot.cli.seed'))
    Run docker ($c+@('run','--rm','--no-deps','admin','python','-m','opspilot.cli.bootstrap_identity'))
    Run docker ($c+@('run','--rm','--no-deps','telemetry-init'))
    $step='create scripted pending interrupt and committed operation'
    Run docker ($c+@('up','-d','--wait','--no-build','collector','mcp'))
    Run docker ($c+@('run','--rm','--no-deps','-e',('F23_PROJECT='+$Project),'tests','python','-m','tests.f23_fixture'))
    $step='drain local writers and create encrypted backup'
    Run docker ($c+@('stop','mcp','collector','redis'))
    Run $py @('scripts/rehearse-full-f23-recovery.py','backup',$Project)

    $step='apply candidate migration'
    Run docker ($c+@('run','--rm','--no-deps','admin','alembic','upgrade','0021_worker_admission'))
    $step='restore previous schema into empty offline instance'
    Run docker ($r+@('up','-d','--wait','--no-build','postgres'))
    Run $py @('scripts/rehearse-full-f23-recovery.py','restore',$Project)
    if($RecoverySmoke){
        $step='restore a writable synthetic copy with egress denied'
        $timer=[Diagnostics.Stopwatch]::StartNew()
        Run docker @('network','disconnect',"${Project}_default","$Project-manager-manager-1")
        # The manager was provisioned through loopback. Reattach it only to the private lab.
        $internal="${Project}_smoke"
        Run docker @('network','create','--internal','--subnet',$env:F23_SMOKE_SUBNET,$internal)
        Run docker @('network','connect','--alias','manager',$internal,"$Project-manager-manager-1")
        Run docker @('network','disconnect',"${Project}_default","$Project-postgres-1")
        Run docker @('network','connect','--alias','postgres',$internal,"$Project-postgres-1")
        $smokeOverride="$private/smoke-network.yaml"
        @"
networks:
  default:
    external: true
    name: $internal
    ipam: !reset null
"@ | Set-Content -Encoding utf8 $smokeOverride
        Run $py @('scripts/rehearse-full-f23-recovery.py','smoke-copy',$Project)
        $smoke=$c+@('-f',$smokeOverride)
        Run docker ($smoke+@('up','-d','--wait','--no-build','--no-deps','--force-recreate','redis','collector','mcp'))
        $step='resume a restored workflow and check committed replay'
        Run docker ($smoke+@('run','--rm','--no-deps','-e',('F23_PROJECT='+$Project),'-e','F23_RECOVERY_SMOKE=1','tests','python','-m','tests.f23_fixture'))
        @{project=$Project;passed=$true;private_network=$internal;local_restore_to_worker_smoke_seconds=[math]::Round($timer.Elapsed.TotalSeconds,2);committed_extra_tickets=0;pending_new_tickets=1} | ConvertTo-Json | Set-Content "$report/recovery-worker.json"
    }
} finally {
    $step='stop isolated services'
    try {
        Run docker ($r+@('stop'))
        if($smoke){ Run docker ($smoke+@('stop')) }
        Run docker ($c+@('stop'))
        if(Test-Path "$private/manager/compose.json"){
            Run docker @('compose','-p',"$Project-manager",'-f',"$private/manager/compose.json",'stop')
        }
    } finally {
        & ./scripts/check-full-isolation.ps1 -MvpPath $mvp -MvpDocumentationHead $mvpHead -ReportPath "$report/mvp-after.json"
    }
}
