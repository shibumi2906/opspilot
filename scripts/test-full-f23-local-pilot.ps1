param(
 [ValidateSet('Prepare','Start','Probe','Fixture','AdminMfa','AdminMfaResume','Stop')][string]$Mode='Prepare',
 [ValidatePattern('^opspilot-full-test-f23-[a-z0-9]+$')][string]$Project='opspilot-full-test-f23-pilot1',
 [ValidateRange(65,96)][int]$Subnet=70
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$py='.venv/Scripts/python.exe'
$private=".tools/$Project"
$env:COMPOSE_PARALLEL_LIMIT='1'
$c=@('compose','-p',$Project,'-f',"$private/compose.json")
function Run([string[]]$Arguments){
 & docker @c @Arguments *>> "$private/rehearsal.log"
 if($LASTEXITCODE){throw "F23 pilot $Mode failed; see ignored rehearsal.log"}
}
if($Mode -eq 'Prepare'){
 $mvp=(Get-Content .tools/opspilot-full-workspace.json -Raw | ConvertFrom-Json).mvp_path
 & ./scripts/check-full-isolation.ps1 -MvpPath $mvp -MvpDocumentationHead (git -C $mvp rev-parse bec833b) -ReportPath .tools/f23-pilot-mvp-before.json
 if($LASTEXITCODE){throw 'MVP isolation failed'}
 & $py scripts/prepare-full-f23-local-pilot.py --project $Project --subnet $Subnet
 if($LASTEXITCODE){throw 'Pilot preparation failed; existing state preserved'}
 Run @('up','-d','--wait','--wait-timeout','120','--no-build','postgres','redis','oidc')
 $env:F23_PILOT_PRIVATE=$private
 $env:F23_PILOT_PROJECT=$Project
 & $py -c "import os,runpy,json;from pathlib import Path;p=Path(os.environ['F23_PILOT_PRIVATE']).resolve();project=os.environ['F23_PILOT_PROJECT'];manifest=json.loads((p/'release-manifest.json').read_bytes());d=runpy.run_path('scripts/setup-full-f17-manager.py');f=d['bootstrap'];f.__globals__.update(PRIVATE=p/'manager',RECOVERY=p/'manager-recovery',PROJECT=project+'-manager',PORT=18270,IMAGE=manifest['images']['manager'],APPLICATION_NETWORKS=(),EXTERNAL_NETWORK=project+'_default',MANAGEMENT_SUBNET=manifest['management_network']);f()"
 if($LASTEXITCODE){throw 'Pilot manager setup failed; private state preserved'}
 Run @('run','--rm','--no-deps','admin')
 Run @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.seed')
 Run @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.bootstrap_identity')
 Run @('run','--rm','--no-deps','telemetry-init')
}
if($Mode -in @('Prepare','Start')){
 Run @('up','-d','--wait','--wait-timeout','120','--no-build','postgres','redis','oidc','collector','mcp','api','worker','web')
}
if($Mode -in @('Probe','Fixture')){
 $report="$private/reports/$Mode-"+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')
 New-Item -ItemType Directory $report | Out-Null
 $mount=(Resolve-Path $report).Path+':/reports'
 if($Mode -eq 'Probe'){Run @('run','--rm','--no-deps','-v',$mount,'probe')}
 $arguments=@('run','--rm','--no-deps','-v',$mount)
 if($Mode -eq 'Fixture'){$arguments+=@('-e','F23_LEAVE_PENDING=1')}
 Run ($arguments+@('browser'))
}
if($Mode -in @('AdminMfa','AdminMfaResume')){
 if($Mode -eq 'AdminMfa'){New-Item -ItemType Directory "$private/admin-mfa" | Out-Null}
 $arguments=@('run','--rm','--no-deps','-v',((Resolve-Path "$private/admin-mfa").Path+':/admin-state'),'browser','node','/work/scripts/security_pilot_admin_mfa.mjs')
 if($Mode -eq 'AdminMfaResume'){$arguments+=@('--resume-incomplete')}
 Run $arguments
}
if($Mode -eq 'Stop'){
 Run @('stop')
 if(Test-Path "$private/manager/compose.json"){
  & docker compose -p "$Project-manager" -f "$private/manager/compose.json" stop
  if($LASTEXITCODE){throw 'Pilot manager stop failed'}
 }
}
